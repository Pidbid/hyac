<script setup lang="ts">
import { ref, computed, h, onMounted, onBeforeUnmount, nextTick } from 'vue';
import JsonEditor from '@/components/custom/JsonEditor.vue';
import {
  NCard,
  NButton,
  NIcon,
  NSpace,
  NDataTable,
  NBreadcrumb,
  NBreadcrumbItem,
  useDialog,
  useMessage,
  NInput,
  NDescriptions,
  NDescriptionsItem,
  NTag,
  NEmpty
} from 'naive-ui';
import {
  FolderOutline,
  DocumentTextOutline,
  TrashOutline,
  CloudUploadOutline,
  CloudDownloadOutline,
  FolderOpenOutline,
  ImageOutline,
  VideocamOutline,
  CodeSlashOutline,
  ChevronForwardOutline
} from '@vicons/ionicons5';
import { listObjects, getDownloadUrl, uploadFile, deleteFile, deleteFolder, createFolder } from "@/service/api";
import { useApplicationStore } from '@/store/modules/application';

const message = useMessage();
const dialog = useDialog();
const applicationStore = useApplicationStore();

// --- 状态管理 ---

// 面包屑导航路径，模仿文件路径
const breadcrumbPath = ref<{ key: string; name: string; isFolder: boolean }[]>([]);

// 文件和文件夹列表
const files = ref<any[]>([]);

// 选中的文件或文件夹
const selectedFile = ref<any>(null);
const previewUrl = ref<string | null>(null);
const previewContent = ref<any>(null);
const previewType = ref<'image' | 'video' | 'json' | 'other' | null>(null);


// 表格高度计算
const tableContainerRef = ref<HTMLElement | null>(null);

// --- 数据获取与初始化 ---

const formatBytes = (bytes: number, decimals = 2) => {
  if (!bytes || bytes === 0) return '0 Bytes';
  const k = 1024;
  const dm = decimals < 0 ? 0 : decimals;
  const sizes = ['Bytes', 'KB', 'MB', 'GB', 'TB', 'PB', 'EB', 'ZB', 'YB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(dm))} ${sizes[i]}`;
}

const pathArrayToString = () => {
  if (breadcrumbPath.value.length >= 1) {
    return breadcrumbPath.value.map(p => p.name).join('/') + "/";
  } else {
    return '';
  }
}

const handleDataInit = async () => {
  const currentPath = pathArrayToString();
  console.info('currentPath', currentPath, breadcrumbPath.value)
  try {
    const { data, error } = await listObjects(applicationStore.appId, currentPath);
    if (error) {
      message.error(`加载文件列表失败: ${error.message}`);
      files.value = [];
      return;
    }
    if (data) {
      files.value = data
        .filter((obj: Api.Storage.MinioObject) => obj.name !== currentPath)
        .map((obj: Api.Storage.MinioObject) => {
          const relativeName = obj.name.startsWith(currentPath) ? obj.name.substring(currentPath.length) : obj.name;
          return {
            name: obj.is_dir ? relativeName.replace(/\/$/, '') : relativeName,
            type: obj.is_dir ? 'folder' : 'file',
            size: obj.is_dir ? '-' : formatBytes(obj.size),
            modified: new Date(obj.last_modified).toLocaleString()
          };
        });
    } else {
      files.value = [];
    }
  } catch (e: any) {
    message.error(`请求异常: ${e.message}`);
    files.value = []; // 出错时清空列表
  }
};

const getFileTypeForPreview = (fileName: string) => {
  const extension = fileName.split('.').pop()?.toLowerCase();
  if (!extension) return 'other';

  if (['png', 'jpg', 'jpeg', 'gif', 'svg', 'webp'].includes(extension)) {
    return 'image';
  }
  if (['mp4', 'mov', 'avi', 'wmv', 'webm'].includes(extension)) {
    return 'video';
  }
  if (extension === 'json') {
    return 'json';
  }
  return 'other';
};

const updatePreview = async (file: any) => {
  previewUrl.value = null;
  previewContent.value = null;
  previewType.value = getFileTypeForPreview(file.name);

  if (previewType.value === 'other') {
    return;
  }

  try {
    const currentPath = pathArrayToString();
    const objectName = `${currentPath}${file.name}`;
    const { data, error } = await getDownloadUrl(applicationStore.appId, objectName);
    if (error) {
      message.error(`生成预览链接失败: ${error.message}`);
      previewType.value = 'other';
      return;
    }
    if (data?.url) {
      previewUrl.value = data.url;
      if (previewType.value === 'json') {
        const response = await fetch(data.url);
        if (response.ok) {
          previewContent.value = await response.json();
        } else {
          message.error('加载JSON内容失败');
          previewType.value = 'other';
        }
      }
    }
  } catch (e: any) {
    message.error(`预览失败: ${e.message}`);
    previewType.value = 'other';
  }
};


// --- 事件处理 ---

const handleUploadFile = () => {
  const input = document.createElement('input');
  input.type = 'file';
  input.onchange = async e => {
    const file = (e.target as HTMLInputElement).files?.[0];
    if (!file) return;

    const currentPath = pathArrayToString();
    const objectName = `${currentPath}${file.name}`;

    try {
      message.loading('正在上传文件...', { duration: 0 });
      const { error } = await uploadFile(applicationStore.appId, objectName, file);
      message.destroyAll();
      if (error) {
        message.error(`上传失败: ${error.message}`);
        return;
      }
      message.success(`文件 "${file.name}" 上传成功`);
      await handleDataInit(); // 刷新列表
    } catch (err: any) {
      message.destroyAll();
      message.error(`上传异常: ${err.message}`);
    }
  };
  input.click();
};

const handleCreateFolder = () => {
  let folderName = '';
  dialog.info({
    title: '新建文件夹',
    content: () =>
      h(NInput, {
        placeholder: '请输入文件夹名称',
        onUpdateValue: (v: string) => {
          folderName = v;
        }
      }),
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      if (!folderName || folderName.includes('/')) {
        message.error('文件夹名称不能为空且不能包含斜杠');
        return;
      }

      const currentPath = pathArrayToString();
      const fullFolderName = `${currentPath}${folderName}`;

      try {
        message.loading('正在创建文件夹...', { duration: 0 });
        const { error } = await createFolder(applicationStore.appId, fullFolderName);
        message.destroyAll();

        if (error) {
          message.error(`创建失败: ${error.message}`);
          return;
        }

        message.success(`文件夹 "${folderName}" 创建成功`);
        await handleDataInit(); // 刷新列表
      } catch (err: any) {
        message.destroyAll();
        message.error(`创建异常: ${err.message}`);
      }
    }
  });
};

const handleRowClick = async (row: any, rowIndex: number) => {
  if (row.type === 'folder') {
    breadcrumbPath.value.push({ key: row.name, name: row.name, isFolder: true });
    await handleDataInit(); // 重新获取数据
    selectedFile.value = null; // 进入文件夹后清空文件选中状态
    previewUrl.value = null;
    previewContent.value = null;
    previewType.value = null;
    message.info(`进入文件夹: ${row.name}`);
  } else {
    selectedFile.value = row;
    await updatePreview(row);
  }
};

const handleBreadcrumbClick = (path: any, index: number) => {
  breadcrumbPath.value = breadcrumbPath.value.slice(0, index + 1);
  handleDataInit(); // 重新获取数据
  selectedFile.value = null;
  previewUrl.value = null;
  previewContent.value = null;
  previewType.value = null;
  message.info(`返回到: ${path.name}`);
};

const handleDeleteFile = (row: any) => {
  const typeText = row.type === 'folder' ? '文件夹' : '文件';
  dialog.warning({
    title: '确认删除',
    content: `删除后不可恢复，确定要删除${typeText} "${row.name}" 吗？`,
    positiveText: '删除',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        message.loading('正在删除...', { duration: 0 });
        const currentPath = pathArrayToString();
        const objectName = `${currentPath}${row.name}`;
        const apiCall =
          row.type === 'folder'
            ? deleteFolder(applicationStore.appId, objectName)
            : deleteFile(applicationStore.appId, objectName);

        const { error } = await apiCall;
        message.destroyAll();

        if (error) {
          message.error(`删除失败: ${error.message}`);
          return;
        }

        message.success(`${typeText} "${row.name}" 已删除`);
        await handleDataInit(); // 重新加载数据

        if (selectedFile.value?.name === row.name) {
          selectedFile.value = null;
          previewUrl.value = null;
          previewContent.value = null;
          previewType.value = null;
        }
      } catch (err: any) {
        message.destroyAll();
        message.error(`删除异常: ${err.message}`);
      }
    }
  });
};

const handleDownloadFile = async (row: any) => {
  try {
    message.info(`正在生成下载链接: ${row.name}`);
    const currentPath = pathArrayToString();
    const objectName = `${currentPath}${row.name}`;
    const { data, error } = await getDownloadUrl(applicationStore.appId, objectName);
    if (error) {
      message.error(`生成下载链接失败: ${error.message}`);
      return;
    }
    if (data?.url) {
      window.open(data.url, '_blank');
      message.success(`开始下载: ${row.name}`);
    }
  } catch (e: any) {
    message.error(`下载失败: ${e.message}`);
  }
};


// --- 表格定义 ---

const getFileIcon = (fileName: string) => {
  const extension = fileName.split('.').pop()?.toLowerCase();
  if (!extension) return DocumentTextOutline;

  switch (extension) {
    case 'png':
    case 'jpg':
    case 'jpeg':
    case 'gif':
    case 'svg':
    case 'webp':
      return ImageOutline;
    case 'mp4':
    case 'mov':
    case 'avi':
    case 'wmv':
    case 'webm':
      return VideocamOutline;
    case 'py':
    case 'js':
    case 'ts':
    case 'html':
    case 'css':
    case 'json':
      return CodeSlashOutline;
    default:
      return DocumentTextOutline;
  }
};

const createColumns = () => [
  {
    key: 'icon',
    title: '',
    width: 50,
    render(row: any) {
      const icon = row.type === 'folder' ? FolderOutline : getFileIcon(row.name);
      const color = row.type === 'folder' ? '#ffca28' : '#607d8b';
      return h(NIcon, { size: 24, component: icon, color });
    }
  },
  {
    title: '名称',
    key: 'name',
    render(row: any) {
      return h(
        'span',
        {
          style: {
            color: row.type === 'folder' ? 'var(--n-item-text-color-hover)' : 'inherit'
          }
        },
        row.name
      );
    }
  },
  {
    title: '大小',
    key: 'size',
    width: 120,
  },
  {
    title: '修改日期',
    key: 'modified',
    width: 200,
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    render(row: any) {
      const downloadButton = h(
        NButton,
        {
          quaternary: true,
          circle: true,
          size: 'small',
          title: '下载',
          onClick: (e) => { e.stopPropagation(); handleDownloadFile(row); }
        },
        { default: () => h(NIcon, null, { default: () => h(CloudDownloadOutline) }) }
      );

      const deleteButton = h(
        NButton,
        {
          quaternary: true,
          circle: true,
          size: 'small',
          type: 'error',
          title: '删除',
          onClick: (e) => { e.stopPropagation(); handleDeleteFile(row); }
        },
        { default: () => h(NIcon, null, { default: () => h(TrashOutline) }) }
      );

      return h(
        NSpace,
        { justify: 'center' },
        () => row.type === 'file' ? [downloadButton, deleteButton] : [deleteButton]
      );
    }
  }
];

const columns = createColumns();
const pagination = { pageSize: 20 };

const rowProps = (row: any) => {
  return {
    style: 'cursor: pointer;',
    onClick: () => handleRowClick(row, 0), // rowIndex is not critical here
    class: selectedFile.value?.name === row.name ? 'selected-row' : ''
  };
};

const handleBakToRootPath = async() =>{
  breadcrumbPath.value = [];
  await handleDataInit();
}

// --- 生命周期钩子 ---
onMounted(async () => {
  await handleDataInit();
});

onBeforeUnmount(() => {
});
</script>

<template>
  <div class="h-full flex flex-col p-4 bg-gray-100 dark:bg-gray-800">
    <!-- 头部操作栏 -->
    <header class="flex items-center justify-between mb-4">
      <NBreadcrumb class="path-breadcrumb">
        <NBreadcrumbItem @click="handleBakToRootPath">
          <NIcon :component="FolderOutline" class="mr-1" />
          <span>根目录</span>
        </NBreadcrumbItem>
        <NBreadcrumbItem v-for="(path, index) in breadcrumbPath" :key="path.key"
          @click="handleBreadcrumbClick(path, index)">
          <NIcon :component="FolderOutline" class="mr-1" />
          {{ path.name }}
        </NBreadcrumbItem>
      </NBreadcrumb>
      <NSpace>
        <NButton size="small" @click="handleCreateFolder">
          <template #icon>
            <NIcon :component="FolderOpenOutline" />
          </template>
          新建文件夹
        </NButton>
        <NButton size="small" type="primary" @click="handleUploadFile">
          <template #icon>
            <NIcon :component="CloudUploadOutline" />
          </template>
          上传文件
        </NButton>
      </NSpace>
    </header>

    <!-- 主内容区: 左侧列表 + 右侧详情 -->
    <div class="flex-1 flex gap-4 min-h-0">
      <!-- 左侧: 文件列表 -->
      <NCard ref="tableContainerRef" class="flex-1 rounded-lg shadow-md" :bordered="false"
        :content-style="{ padding: '0px', height: '100%', 'overflow-y': 'auto' }">
        <NDataTable :columns="columns" :data="files" :pagination="pagination" :bordered="false" :single-line="false"
          :row-props="rowProps" :row-key="(row: any) => row.name" />
      </NCard>
      <!-- 右侧: 详情区域 -->
      <NCard title="详情" class="w-80 rounded-lg shadow-md" :bordered="false"
        :content-style="{ padding: '10px', height: '100%', 'overflow-y': 'auto' }">
        <div v-if="selectedFile" class="h-full flex flex-col gap-4">
          <!-- Preview Area -->
          <div class="preview-area flex-shrink-0">
            <!-- Image Preview -->
            <div v-if="previewType === 'image' && previewUrl" class="flex-center">
              <img :src="previewUrl" alt="Image Preview" class="max-w-full max-h-48 object-contain">
            </div>
            <!-- Video Preview -->
            <div v-else-if="previewType === 'video' && previewUrl" class="flex-center">
              <video :src="previewUrl" controls class="max-w-full max-h-48"></video>
            </div>
            <!-- JSON Preview -->
            <div v-else-if="previewType === 'json' && previewContent !== null">
              <JsonEditor v-model="previewContent" :height="200" />
            </div>
          </div>

          <!-- Details Area -->
          <div class="details-area flex-grow">
            <NSpace vertical :size="16">
              <div class="text-center">
                <NIcon v-if="!previewType || previewType === 'other'" :component="getFileIcon(selectedFile.name)"
                  size="48" :color="selectedFile.type === 'folder' ? '#ffca28' : '#607d8b'" />
                <div class="font-bold mt-2 break-all">{{ selectedFile.name }}</div>
              </div>
              <NDescriptions label-placement="left" :column="1" bordered size="small">
                <NDescriptionsItem label="类型">
                  <NTag size="small" :type="selectedFile.type === 'folder' ? 'info' : 'success'">
                    {{ selectedFile.type === 'folder' ? '文件夹' : '文件' }}
                  </NTag>
                </NDescriptionsItem>
                <NDescriptionsItem label="大小">{{ selectedFile.size }}</NDescriptionsItem>
                <NDescriptionsItem label="修改日期">{{ selectedFile.modified }}</NDescriptionsItem>
              </NDescriptions>
              <NButton type="primary" block @click="handleDownloadFile(selectedFile)"
                v-if="selectedFile.type === 'file'">
                <template #icon>
                  <NIcon :component="CloudDownloadOutline" />
                </template>
                下载
              </NButton>
            </NSpace>
          </div>
        </div>
        <NEmpty v-else description="选择一个文件或文件夹查看详情" class="h-full flex-center">
          <template #icon>
            <NIcon :component="ChevronForwardOutline" />
          </template>
        </NEmpty>
      </NCard>
    </div>
  </div>
</template>

<style scoped>
.path-breadcrumb {
  background-color: var(--n-card-color);
  padding: 8px 12px;
  border-radius: 6px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.05);
  cursor: pointer;
}

.dark .path-breadcrumb {
  background-color: var(--n-color-embedded);
}

.n-data-table {
  height: 100%;
}

.flex-center {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.selected-row {
  background-color: var(--n-action-color);
}
</style>
