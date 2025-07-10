<script setup lang="ts">
import { ref, h, onMounted, reactive, computed, watch } from 'vue';
import {
  NCard,
  NButton,
  NIcon,
  NSpace,
  NDataTable,
  NSelect,
  NDatePicker,
  NTag,
  NEmpty,
  NSwitch,
  NDescriptions,
  NDescriptionsItem,
  useMessage,
  NLog,
  NCode
} from 'naive-ui';
import { SearchOutline, SyncOutline, InformationCircleOutline, WarningOutline, CloseCircleOutline, BugOutline, ReloadOutline } from '@vicons/ionicons5';
import { getAppLogs, getFunctionLogs } from "@/service/api/logs";
import { GetFunctionData } from "@/service/api/function";
import { useApplicationStore } from '@/store/modules/application';
import { useAppStore } from '@/store/modules/app';
import { format } from 'date-fns';
import hljs from 'highlight.js/lib/core'
import javascript from 'highlight.js/lib/languages/javascript'
hljs.registerLanguage('javascript', javascript)

const message = useMessage();
const applicationStore = useApplicationStore();
const appStore = useAppStore();

// --- 状态管理 ---
const loading = ref(false);
const logs = ref<Api.Log.LogEntry[]>([]);
const functions = ref<{ label: string; value: string }[]>([]);
const selectedLog = ref<Api.Log.LogEntry | null>(null);

const filters = reactive({
  funcId: null,
  level: null,
  logtype: null,
  dateRange: null as [number, number] | null,
});

const pagination = reactive({
  page: 1,
  pageSize: 20,
  itemCount: 0,
  onChange: (page: number) => {
    pagination.page = page;
    handleSearch();
  },
  onUpdatePageSize: (pageSize: number) => {
    pagination.pageSize = pageSize;
    pagination.page = 1;
    handleSearch();
  }
});

const levelOptions = [
  { label: 'Info', value: 'info' },
  { label: 'Warning', value: 'warning' },
  { label: 'Error', value: 'error' },
  { label: 'Debug', value: 'debug' },
];

const logTypeOptions = [
  { label: '系统', value: 'system' },
  { label: '函数', value: 'function' },
];

// --- 数据获取 ---
const fetchFunctions = async () => {
  if (!applicationStore.appId) return;
  try {
    const { data, error } = await GetFunctionData(applicationStore.appId, 1, 1000); // 获取所有函数
    if (error) {
      message.error('加载函数列表失败');
      return;
    }
    if (data?.data) {
      functions.value = data.data.map(f => ({
        label: f.function_name,
        value: f.function_id
      }));
    }
  } catch (e: any) {
    message.error(`请求函数列表异常: ${e.message}`);
  }
};

const handleSearch = async () => {
  if (!applicationStore.appId) {
    message.warning('请先选择一个应用');
    return;
  }
  loading.value = true;
  selectedLog.value = null;
  try {
    const extra: Api.Log.LogQueryExtra = {
      level: filters.level || undefined,
      logtype: filters.logtype || undefined,
      dateStart: filters.dateRange ? format(filters.dateRange[0], "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'") : undefined,
      dateEnd: filters.dateRange ? format(filters.dateRange[1], "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'") : undefined,
    };

    const apiCall = filters.funcId
      ? getFunctionLogs(applicationStore.appId, filters.funcId, pagination.page, pagination.pageSize, extra)
      : getAppLogs(applicationStore.appId, pagination.page, pagination.pageSize, extra);

    const { data, error } = await apiCall;
    if (error) {
      message.error(`加载日志失败: ${error.message}`);
      logs.value = [];
      pagination.itemCount = 0;
      return;
    }
    if (data) {
      logs.value = data.data;
      pagination.itemCount = data.total;
    } else {
      logs.value = [];
      pagination.itemCount = 0;
    }
  } catch (e: any) {
    message.error(`请求日志异常: ${e.message}`);
  } finally {
    loading.value = false;
  }
};

const levelConfig: Record<string, { type: 'info' | 'warning' | 'error' | 'default', icon: any }> = {
  info: { type: 'info', icon: InformationCircleOutline },
  warning: { type: 'warning', icon: WarningOutline },
  error: { type: 'error', icon: CloseCircleOutline },
  debug: { type: 'default', icon: BugOutline },
};

const createColumns = () => [
  {
    title: '时间',
    key: 'timestamp',
    width: 200,
    render(row: Api.Log.LogEntry) {
      return format(new Date(row.timestamp), 'yyyy-MM-dd HH:mm:ss');
    }
  },
  {
    key: 'level',
    title: '级别',
    width: 100,
    render(row: Api.Log.LogEntry) {
      const config = levelConfig[row.level.toLowerCase()] || { type: 'default', icon: BugOutline };
      return h(
        NTag,
        { type: config.type, size: 'small' },
        {
          default: () => row.level,
          icon: () => h(NIcon, { component: config.icon })
        }
      );
    }
  },
  {
    title: '日志',
    key: 'message',
    ellipsis: { tooltip: true }
  },
  {
    title: '来源',
    key: 'logtype',
    width: 150,
    render(row: Api.Log.LogEntry) {
      return row.logtype === 'function' ? `函数:${row.extra.function_name}` : '系统';
    }
  }
];

const columns = createColumns();

const rowProps = (row: Api.Log.LogEntry) => {
  return {
    style: 'cursor: pointer;',
    onClick: () => { selectedLog.value = row; },
    class: selectedLog.value?._id === row._id ? 'selected-row' : ''
  };
};

// --- 生命周期 ---
onMounted(async () => {
  await fetchFunctions();
  await handleSearch();
});

</script>

<template>
    <div class="h-full flex flex-col p-4 bg-gray-100 dark:bg-gray-800">
      <!-- 头部筛选与操作栏 -->
      <header class="flex items-center justify-between mb-4">
        <NSpace align="center">
          <NSelect v-model:value="filters.funcId" :options="functions" placeholder="所有函数" clearable class="w-48"
            size="small" />
          <NSelect v-model:value="filters.level" :options="levelOptions" placeholder="所有级别" clearable class="w-36"
            size="small" />
          <NSelect v-model:value="filters.logtype" :options="logTypeOptions" placeholder="所有类型" clearable class="w-36"
            size="small" />
          <NDatePicker v-model:value="filters.dateRange" type="datetimerange" clearable size="small" class="w-96" />
          <NButton type="default" size="small" @click="appStore.reloadPage(500)">
            <template #icon>
              <NIcon :component="ReloadOutline" />
            </template>
          </NButton>
          <NButton type="primary" size="small" @click="handleSearch">
            <template #icon>
              <NIcon :component="SearchOutline" />
            </template>
            查询
          </NButton>
        </NSpace>
      </header>

      <!-- 主内容区: 左侧列表 + 右侧详情 -->
      <div class="flex-1 flex gap-4 min-h-0">
        <!-- 左侧: 日志列表 -->
        <NCard class="flex-1 rounded-lg shadow-md" :bordered="false"
          :content-style="{ padding: '0px', height: '100%', 'overflow-y': 'auto' }">
          <NDataTable :columns="columns" :data="logs" :pagination="pagination" :loading="loading" :bordered="false"
            :single-line="false" :row-props="rowProps" :row-key="(row: Api.Log.LogEntry) => row._id" remote />
        </NCard>
        <!-- 右侧: 详情区域 -->
        <NCard title="日志详情" class="w-96 rounded-lg shadow-md" :bordered="false"
          :content-style="{ padding: '10px', height: '100%', 'overflow-y': 'auto' }">
          <div v-if="selectedLog" class="h-full flex flex-col gap-4">
            <NDescriptions label-placement="left" :column="1" bordered size="small">
              <NDescriptionsItem label="时间">{{ format(new Date(selectedLog.timestamp), 'yyyy-MM-dd HH:mm:ss.SSS') }}
              </NDescriptionsItem>
              <NDescriptionsItem label="级别">
                <NTag :type="levelConfig[selectedLog.level.toLowerCase()]?.type || 'default'" size="small">{{
                  selectedLog.level }}</NTag>
              </NDescriptionsItem>
              <NDescriptionsItem label="类型">{{ selectedLog.logtype === 'function' ? '函数' : '系统' }}</NDescriptionsItem>
              <NDescriptionsItem v-if="selectedLog.extra.function_name" label="函数名">{{ selectedLog.extra.function_name
                }}
              </NDescriptionsItem>
            </NDescriptions>
            <div class="flex-grow min-h-0">
              <NScrollbar class="h-full">
                <NLog :hljs="hljs" :log="selectedLog.message" :rows="30" language="json" trim class="h-full" />
              </NScrollbar>
            </div>
          </div>
          <NEmpty v-else description="选择一条日志查看详情" class="h-full flex-center" />
        </NCard>
      </div>
    </div>
</template>

<style scoped>
.flex-center {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.selected-row {
  background-color: var(--n-action-color);
}

.n-data-table {
  height: 100%;
}
</style>
