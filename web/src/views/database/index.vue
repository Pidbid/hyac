<script setup lang="ts">
import { computed, h, nextTick, onMounted, ref, watch } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NEmpty,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NList,
  NListItem,
  NPagination,
  NSpace,
  NThing,
  useDialog,
  useMessage,
  NSplit,
  NButtonGroup,
  NScrollbar,
  NFlex
} from 'naive-ui';
import {
  AddOutline,
  BanOutline,
  CreateOutline,
  DocumentTextOutline,
  PencilOutline,
  RefreshOutline,
  TrashOutline
} from '@vicons/ionicons5';
import { Console } from 'console';
import { GetCollectionData, CreateCollection, GetDocumentData, CreateDocument, DeleteCollection, ClearCollection, DeleteDocument, UpdateDocument } from "@/service/api"
import { useApplicationStore } from '@/store/modules/application';
import JsonEditor from '@/components/custom/jsonEditor.vue';

const message = useMessage();
const dialog = useDialog();

const applicationStore = useApplicationStore()

// 模拟集合（表）数据
const collections = ref<string[]>([])
const selectedCollection = ref(collections.value[0] || '');

const documents = ref<object[]>([
]);

// 分页相关
const pageSize = ref(15);
const page = ref(1);
const totalDocuments = ref(0);
const paginatedDocuments = computed(() => {
  const start = (page.value - 1) * pageSize.value;
  const end = start + pageSize.value;
  console.info(documents.value.slice(start, end))
  return documents.value.slice(start, end);
});

// 选中的文档用于编辑
const editingDocument = ref<any>(null);
const editingDocumentJson = ref<string>("{}");

// 监听选中集合变化，重置文档和页码
watch(selectedCollection, () => {
  page.value = 1; // 切换集合时重置页码
  editingDocument.value = null; // 清空编辑中的文档
  editingDocumentJson.value = '';
});


// 操作函数
const handleCreateCollection = () => {
  let collectionName = '';
  dialog.info({
    title: '创建集合',
    content: () => h(NInput, {
      placeholder: '请输入集合名称',
      onUpdateValue: (v: string) => {
        collectionName = v;
      }
    }),
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      if (collectionName) {
        const { data, error } = await CreateCollection(applicationStore.appId, collectionName)
        if (!error) {
          await getApplicationCollections()
          selectedCollection.value = collectionName;
          message.success("集合创建成功")
        }
      }
    }
  });
};

const handleCreateDocument = () => {
  const documentContent = ref<string>("{}");
  dialog.info({
    title: '插入文档',
    content: () =>
      h(JsonEditor, {
        modelValue: documentContent.value,
        'onUpdate:modelValue': (v: any) => {
          documentContent.value = v;
        }
      }),
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      try {
        const { data, error } = await CreateDocument(
          applicationStore.appId,
          selectedCollection.value,
          JSON.parse(documentContent.value)
        );
        if (!error) {
          nextTick(async () => {
            await getCollectionDocuments(selectedCollection.value, 1, 15)
          })
          page.value = 1;
          message.success("创建成功")
        }
      } catch {
        message.error('JSON格式错误，请检查');
      }
    }
  });
};

const handleEditDocument = (doc: any) => {
  editingDocument.value = { ...doc }; // 复制一份进行编辑
  // editingDocumentJson.value = JSON.parse(JSON.stringify(doc));
  editingDocumentJson.value = JSON.stringify(doc, null, 4);
};

const handleDeleteDocument = (doc: any) => {
  dialog.warning({
    title: '确认删除',
    content: `确定要删除文档 ID: ${doc._id} 吗？`,
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      const { data, error } = await DeleteDocument(applicationStore.appId, selectedCollection.value, doc._id)
      if (!error) {
        await getCollectionDocuments(selectedCollection.value, 1, 15)
        message.success("删除成功")
      }
    },
    onNegativeClick: () => {
      message.info('已取消删除');
    }
  });
};

const handleDeleteCollection = (colName: string) => {
  dialog.error({
    title: '确认删除',
    content: `确定要删除集合: ${colName} 吗？删除后不可恢复，请谨慎操作！`,
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      const { data, error } = await DeleteCollection(applicationStore.appId, colName)
      if (!error) {
        await getApplicationCollections()
        selectedCollection.value = collections.value[0];
        message.success("删除成功")
      }
    }
  });
};

const handleClearCollection = (colName: string) => {
  dialog.warning({
    title: '确认清空',
    content: `确定要清空集合: ${colName} 吗？清空后不可恢复，请谨慎操作！`,
    positiveText: '确定',
    negativeText: '取消',
    onPositiveClick: async () => {
      const { data, error } = await ClearCollection(applicationStore.appId, colName)
      if (!error) {
        await getCollectionDocuments(selectedCollection.value, 1, 15)
        message.success("清空成功")
      }
    },
    onNegativeClick: () => {
      message.info('已取消删除');
    }
  });
};

const handleSaveDocument = async () => {
  try {
    // The v-model from JsonEditor should always be an object
    const { data, error } = await UpdateDocument(applicationStore.appId, selectedCollection.value, editingDocument.value._id, JSON.parse(editingDocumentJson.value))
    if (!error) {
      await getCollectionDocuments(selectedCollection.value, 1, 15)
      editingDocument.value = null; // 保存后清空编辑状态
      editingDocumentJson.value = "";
      message.success("保存成功")
    }
  } catch (e) {
    message.error('保存失败，请检查数据格式');
  }
};

const handleCancelEdit = () => {
  editingDocument.value = null;
  editingDocumentJson.value = '';
  message.info('取消编辑');
};

const handleRefreshDocuments = async () => {
  await getCollectionDocuments(selectedCollection.value, 1, 15)
  message.success("刷新成功")
};


// JSON格式化显示
const formatJson = (data: any) => {
  try {
    return JSON.stringify(data, null, 2);
  } catch {
    return String(data);
  }
};

// 表格列定义
const documentColumns = [
  {
    title: 'ID',
    key: 'id',
    width: 100,
    render: (row: any, index: number) => h('span', {}, (page.value - 1) * pageSize.value + index + 1)
  },
  {
    title: '内容',
    key: 'content',
    minWidth: 200,
    render: (row: any) => h(
      NInput,
      {
        type: 'textarea',
        value: formatJson(row),
        rows: 5,
        readonly: true,
        autosize: {
          minRows: 3,
          maxRows: 10
        },
        style: {
          '--n-border-radius': '0px',
          '--n-border': 'none',
          '--n-border-hover': 'none',
          '--n-border-focus': 'none',
          '--n-box-shadow-focus': 'none',
          '--n-color': 'transparent',
          '--n-text-color': 'var(--n-text-color)',
          '--n-caret-color': 'var(--n-caret-color)'
        }
      }
    )
  },
  {
    title: '操作',
    key: 'actions',
    width: 120,
    render: (row: any) => h(
      NSpace,
      { justify: 'center' },
      () => [
        h(
          NButton,
          {
            quaternary: true,
            circle: true,
            size: 'small',
            onClick: () => handleEditDocument(row)
          },
          { default: () => h(NIcon, null, { default: () => h(CreateOutline) }) }
        ),
        h(
          NButton,
          {
            quaternary: true,
            circle: true,
            size: 'small',
            type: 'error',
            onClick: () => handleDeleteDocument(row)
          },
          { default: () => h(NIcon, null, { default: () => h(TrashOutline) }) }
        )
      ]
    )
  }
];

const handleCollectionClick = async (collection: string) => {
  selectedCollection.value = collection;
  await getCollectionDocuments(selectedCollection.value, 1, 15)
}

const getCollectionDocuments = async (docName: string, page: number, length: number) => {
  const { data, error } = await GetDocumentData(applicationStore.appId, docName, page, length)
  if (!error) {
    documents.value = data.data
    totalDocuments.value = data.total; // 更新总文档数
  }
}

const getApplicationCollections = async () => {
  const { data, error } = await GetCollectionData(applicationStore.appId)
  if (!error) {
    collections.value = data.data
  }
}

const paginationUpPage = (newPage: number) => {
  page.value = newPage;
  getCollectionDocuments(selectedCollection.value, newPage, pageSize.value);
};

const paginationUpSize = (newSize: number) => {
  page.value = 1;
  pageSize.value = newSize;
  getCollectionDocuments(selectedCollection.value, page.value, newSize);
};

onMounted(async () => {
  await getApplicationCollections();
  if (collections.value.length > 0) {
    selectedCollection.value = collections.value[0]
    await getCollectionDocuments(collections.value[0], 1, 15)
  }
});
</script>

<template>
  <div class="h-full flex w-full">
    <NSplit :size="0.1" :min="0.1" :max="0.3">
      <template #1>
        <NCard title="集合" :bordered="false" size="small" class="h-full flex flex-col card-wrapper"
          :content-style="{ padding: '0px', flex: 1, overflow: 'hidden' }">
          <template #header-extra>
            <NButton type="primary" size="small" @click="handleCreateCollection">
              <template #icon>
                <NIcon :component="AddOutline" />
              </template>
            </NButton>
          </template>
          <NScrollbar class="h-full">
            <NList hoverable clickable>
              <NListItem v-for="collection in collections" :key="collection"
                :class="{ 'selected-collection-item': selectedCollection === collection }"
                @click="handleCollectionClick(collection)">
                <NThing :title="collection">
                  <template #header-extra>
                    <NButtonGroup>
                      <NButton quaternary circle size="small" type="warning"
                        @click.stop="handleClearCollection(collection)">
                        <template #icon>
                          <NIcon :component="BanOutline" />
                        </template>
                      </NButton>
                      <NButton quaternary circle size="small" type="error"
                        @click.stop="handleDeleteCollection(collection)">
                        <template #icon>
                          <NIcon :component="TrashOutline" />
                        </template>
                      </NButton>
                    </NButtonGroup>
                  </template>
                </NThing>
              </NListItem>
            </NList>
          </NScrollbar>
        </NCard>
      </template>
      <template #2>
        <NSplit :size="0.85" :min="0.4" :max="0.9">
          <template #1>
            <NCard :title="selectedCollection || '文档'" :bordered="false" size="small"
              class="h-full flex flex-col card-wrapper"
              :content-style="{ padding: '0px', flex: 1, display: 'flex', flexDirection: 'column' }">
              <template #header-extra>
                <NSpace>
                  <NButton quaternary circle size="small" @click="handleRefreshDocuments">
                    <template #icon>
                      <NIcon :component="RefreshOutline" />
                    </template>
                  </NButton>
                  <NButton size="small" type="primary" @click="handleCreateDocument">
                    <template #icon>
                      <NIcon :component="AddOutline" />
                    </template>
                    插入文档
                  </NButton>
                </NSpace>
              </template>
              <div class="flex-grow-1" style="overflow: hidden;">
                <NDataTable :columns="documentColumns" :data="documents" :bordered="false" flex-height
                  :single-line="false" :row-key="(row: any) => row._id" style="height:100%;" />
              </div>
              <div class="flex justify-center p-4 border-t border-gray-200">
                <NPagination v-model:page="page" v-model:page-size="pageSize" :item-count="totalDocuments"
                  :page-sizes="[10, 15, 20, 50]" show-size-picker :on-update:page="paginationUpPage"
                  :on-update:page-size="paginationUpSize" />
              </div>
            </NCard>
          </template>
          <template #2>
            <NCard title="文档操作" :bordered="false" size="small" class="h-full flex flex-col card-wrapper">
              <div class="flex-1 min-h-0 p-4">
                <div v-if="editingDocument">
                  <NThing title="编辑内容"></NThing>
                  <jsonEditor v-model="editingDocumentJson" :height="400">
                  </jsonEditor>
                  <div class="flex flex-row gap-2 flex-row-reverse">
                    <NButton type="primary" @click="handleSaveDocument">保存</NButton>
                    <NButton type="error" @click="handleCancelEdit">取消</NButton>
                  </div>
                </div>
                <NEmpty v-else description="选择一个文档进行编辑或创建新文档" class="h-full flex items-center justify-center">
                  <template #icon>
                    <NIcon :component="DocumentTextOutline" />
                  </template>
                </NEmpty>
              </div>
            </NCard>
          </template>
        </NSplit>
      </template>
    </NSplit>
  </div>
</template>

<style scoped>
.card-wrapper {
  border-radius: 8px;
  overflow: hidden;
  display: flex;
  flex-direction: column;
  height: 100%;
}

.selected-collection-item {
  background-color: #e8f0ff;
  /* A light blue for selection */
}

.n-data-table .n-data-table-td {
  vertical-align: top;
}
</style>
