<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-use-before-define, no-underscore-dangle */
import { computed, h, onMounted, reactive, ref } from 'vue';
import {
  NButton,
  NCard,
  NDataTable,
  NDatePicker,
  NDescriptions,
  NDescriptionsItem,
  NEmpty,
  NIcon,
  NLog,
  NSelect,
  NSpace,
  NSplit,
  NTag,
  useMessage
} from 'naive-ui';
import { format } from 'date-fns';
import { useI18n } from 'vue-i18n';
import {
  BugOutline,
  CloseCircleOutline,
  DocumentTextOutline,
  InformationCircleOutline,
  ReloadOutline,
  SearchOutline,
  TerminalOutline,
  WarningOutline
} from '@vicons/ionicons5';
import hljs from 'highlight.js/lib/core';
import javascript from 'highlight.js/lib/languages/javascript';
import { getAppLogs, getFunctionLogs } from '@/service/api/logs';
import { GetFunctionData } from '@/service/api/function';
import { useApplicationStore } from '@/store/modules/application';
import { useAppStore } from '@/store/modules/app';
hljs.registerLanguage('javascript', javascript);

const { t } = useI18n();
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
  dateRange: null as [number, number] | null
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

const levelOptions = computed(() => [
  { label: t('page.log.debug'), value: 'DEBUG' },
  { label: t('page.log.info'), value: 'INFO' },
  { label: t('page.log.warning'), value: 'WARNING' },
  { label: t('page.log.error'), value: 'ERROR' },
  { label: t('page.log.critical'), value: 'CRITICAL' }
]);

const logTypeOptions = computed(() => [
  { label: t('page.log.system'), value: 'system' },
  { label: t('page.log.function'), value: 'function' }
]);

// --- 数据获取 ---
const fetchFunctions = async () => {
  if (!applicationStore.appId) return;
  try {
    const { data, error } = await GetFunctionData(applicationStore.appId, 1, 1000); // 获取所有函数
    if (error) {
      message.error(t('page.log.loadFunctionListFailed'));
      return;
    }
    if (data?.data) {
      functions.value = data.data.map(f => ({
        label: f.function_name,
        value: f.function_id
      }));
    }
  } catch (e: any) {
    message.error(`${t('page.log.requestFunctionListError', { message: e.message })}`);
  }
};

const handleSearch = async () => {
  if (!applicationStore.appId) {
    message.warning(t('page.log.selectAppFirst'));
    return;
  }
  loading.value = true;
  selectedLog.value = null;
  try {
    const extra: Api.Log.LogQueryExtra = {
      level: filters.level || undefined,
      logtype: filters.logtype || undefined,
      dateStart: filters.dateRange ? format(filters.dateRange[0], "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'") : undefined,
      dateEnd: filters.dateRange ? format(filters.dateRange[1], "yyyy-MM-dd'T'HH:mm:ss.SSS'Z'") : undefined
    };

    const apiCall = filters.funcId
      ? getFunctionLogs(applicationStore.appId, filters.funcId, pagination.page, pagination.pageSize, extra)
      : getAppLogs(applicationStore.appId, pagination.page, pagination.pageSize, extra);

    const { data, error } = await apiCall;
    if (error) {
      message.error(`${t('page.log.loadLogFailed', { message: error.message })}`);
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
    message.error(`${t('page.log.requestLogError', { message: e.message })}`);
  } finally {
    loading.value = false;
  }
};

const levelConfig: Record<string, { type: 'info' | 'warning' | 'error' | 'default'; icon: any }> = {
  info: { type: 'info', icon: InformationCircleOutline },
  warning: { type: 'warning', icon: WarningOutline },
  error: { type: 'error', icon: CloseCircleOutline },
  critical: { type: 'error', icon: CloseCircleOutline },
  debug: { type: 'default', icon: BugOutline }
};

const createColumns = () => [
  {
    title: t('page.log.time'),
    key: 'timestamp',
    width: 200,
    render(row: Api.Log.LogEntry) {
      return format(new Date(row.timestamp), 'yyyy-MM-dd HH:mm:ss');
    }
  },
  {
    key: 'level',
    title: t('page.log.level'),
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
    title: t('page.log.logContent'),
    key: 'message',
    ellipsis: { tooltip: true }
  },
  {
    title: t('page.log.source'),
    key: 'logtype',
    width: 150,
    render(row: Api.Log.LogEntry) {
      return row.logtype === 'function' ? `${t('page.log.function')}:${row.extra.function_name}` : t('page.log.system');
    }
  }
];

const columns = computed(() => createColumns());

const rowProps = (row: Api.Log.LogEntry) => {
  return {
    style: 'cursor: pointer;',
    onClick: () => {
      selectedLog.value = row;
    },
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
  <div class="logs-page">
    <header class="logs-toolbar">
      <div class="toolbar-title">
        <NIcon :component="TerminalOutline" :size="18" />
              <span>{{ t('route.log') }}</span>
      </div>
      <div class="toolbar-filters">
        <NSpace align="center">
          <NSelect
            v-model:value="filters.funcId"
            :options="functions"
            :placeholder="t('page.log.allFunctions')"
            clearable
            class="filter-select function"
            size="small"
          />
          <NSelect
            v-model:value="filters.level"
            :options="levelOptions"
            :placeholder="t('page.log.allLevels')"
            clearable
            class="filter-select level"
            size="small"
          />
          <NSelect
            v-model:value="filters.logtype"
            :options="logTypeOptions"
            :placeholder="t('page.log.allTypes')"
            clearable
            class="filter-select level"
            size="small"
          />
          <NDatePicker v-model:value="filters.dateRange" type="datetimerange" clearable size="small" class="date-range" />
          <NButton type="default" size="small" @click="appStore.reloadPage(500)">
            <template #icon>
              <NIcon :component="ReloadOutline" />
            </template>
          </NButton>
          <NButton type="primary" size="small" @click="handleSearch">
            <template #icon>
              <NIcon :component="SearchOutline" />
            </template>
            {{ t('page.log.query') }}
          </NButton>
        </NSpace>
      </div>
    </header>

    <NSplit class="logs-split" :default-size="0.74" :min="0.45" :max="0.86">
      <template #1>
      <NCard
        class="apple-panel"
        :bordered="false"
        :content-style="{ padding: '0px', height: '100%', 'overflow-y': 'auto' }"
      >
        <NDataTable
          :columns="columns"
          :data="logs"
          :pagination="pagination"
          :loading="loading"
          :bordered="false"
          :single-line="false"
          :row-props="rowProps"
          :row-key="(row: Api.Log.LogEntry) => row._id"
          remote
        />
      </NCard>
      </template>
      <template #2>
      <NCard
        class="apple-panel detail-panel"
        :bordered="false"
        :content-style="{ padding: '10px', height: '100%', 'overflow-y': 'auto' }"
      >
        <template #header>
          <div class="panel-title">
            <NIcon :component="DocumentTextOutline" :size="16" />
            <span>{{ t('page.log.logDetail') }}</span>
          </div>
        </template>
        <div v-if="selectedLog" class="h-full flex flex-col gap-4">
          <NDescriptions label-placement="left" :column="1" bordered size="small">
            <NDescriptionsItem :label="t('page.log.time')">
              {{ format(new Date(selectedLog.timestamp), 'yyyy-MM-dd HH:mm:ss.SSS') }}
            </NDescriptionsItem>
            <NDescriptionsItem :label="t('page.log.level')">
              <NTag :type="levelConfig[selectedLog.level.toLowerCase()]?.type || 'default'" size="small">
                {{ selectedLog.level }}
              </NTag>
            </NDescriptionsItem>
            <NDescriptionsItem :label="t('page.log.type')">
              {{ selectedLog.logtype === 'function' ? t('page.log.function') : t('page.log.system') }}
            </NDescriptionsItem>
            <NDescriptionsItem v-if="selectedLog.extra.function_name" :label="t('page.log.functionName')">
              {{ selectedLog.extra.function_name }}
            </NDescriptionsItem>
          </NDescriptions>
          <div class="min-h-0 flex-grow">
            <NScrollbar class="h-full">
              <NLog :hljs="hljs" :log="selectedLog.message" :rows="30" language="json" trim class="h-full" />
            </NScrollbar>
          </div>
        </div>
        <NEmpty v-else :description="t('page.log.selectLogToView')" class="h-full flex-center" />
      </NCard>
      </template>
    </NSplit>
  </div>
</template>

<style scoped>
.logs-page {
  --logs-gap: 6px;

  height: 100%;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
  background: #f5f5f7;
  overflow: hidden;
  padding: 8px;
}

.logs-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
  min-width: 0;
  padding: 10px 12px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
}

.toolbar-title,
.panel-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1d1d1f;
  white-space: nowrap;
}

.toolbar-filters {
  min-width: 0;
}

.filter-select.function {
  width: 180px;
}

.filter-select.level {
  width: 132px;
}

.date-range {
  width: 320px;
}

.logs-split {
  flex: 1;
  min-height: 0;
}

.logs-split :deep(.n-split-pane) {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.logs-split :deep(.n-split-pane-1) {
  padding-right: var(--logs-gap);
}

.logs-split :deep(.n-split-pane-2) {
  padding-left: var(--logs-gap);
}

.apple-panel {
  height: 100%;
  border-radius: 12px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: #ffffff;
}

.flex-center {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}

.selected-row {
  background-color: rgba(0, 122, 255, 0.08);
}

.n-data-table {
  height: 100%;
}

:deep(.n-card-header) {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: #f9f9fb;
}

:deep(.n-data-table) {
  --n-td-color-hover: #f5f5f7;
  --n-merged-border-color: rgba(0, 0, 0, 0.06);
}
</style>
