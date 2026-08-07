<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-use-before-define */
import { computed, h, onMounted, onUnmounted, reactive, ref, watch } from 'vue';
import {
  NButton,
  NDataTable,
  NDropdown,
  NForm,
  NFormItem,
  NIcon,
  NInput,
  NModal,
  NSpace,
  NTag,
  useDialog,
  useMessage
} from 'naive-ui';
import type { DataTableColumn as TableColumn } from 'naive-ui';
import {
  AddCircleOutline,
  AddOutline as AddIcon,
  CreateOutline,
  EllipsisHorizontal,
  RocketOutline,
  StopCircleOutline
} from '@vicons/ionicons5';
import { useHookTable } from '@sa/hooks';
import { createApp, deleteApp, getApps, restartApp, startApp, stopApp } from '@/service/api/app';
import { useAuthStore } from '@/store/modules/auth';
import { useAppStore } from '@/store/modules/app';
import { useThemeStore } from '@/store/modules/theme';
import { useRouterPush } from '@/hooks/common/router';
import { localStg } from '@/utils/storage';
import HomeLayout from '@/layouts/home-layout/index.vue';
import { $t } from '@/locales';

const { routerPush } = useRouterPush();
const authStore = useAuthStore();
const message = useMessage();
const dialog = useDialog();
const appStore = useAppStore();
const themeStore = useThemeStore();

const showCreateModal = ref(false);
const createAppForm = reactive({
  appName: '',
  description: ''
});

const formRef = ref<any>(null);

const rules = {
  appName: {
    required: true,
    message: $t('page.home.appNamePlaceholder'),
    trigger: 'blur'
  }
};

// Fallback to 'wicos' if userName is not available from store
const userName = authStore.userInfo?.username || 'wicos';

const cardData = [
  { title: $t('page.home.miniProgram') },
  { title: $t('page.home.androidOrIos') },
  { title: $t('page.home.blogOrWebsite') },
  { title: $t('page.home.enterpriseInfo') },
  { title: $t('page.home.handyCloud') },
  { title: $t('page.home.explore') }
];

const apiParams = reactive({
  page: 1,
  length: 10
});

const routerToApps = (data: any) => {
  localStg.set('appId', data.app_id);
  routerPush({ name: 'apps' });
};

const tableColumns = (): TableColumn<any>[] => [
  {
    key: 'index',
    title: $t('common.index'),
    align: 'center',
    width: 50,
    render: (_, index) => {
      return (apiParams.page - 1) * apiParams.length + index + 1;
    }
  },
  {
    key: 'app_id',
    title: $t('page.home.appId'),
    align: 'center',
    width: 160
  },
  {
    key: 'app_name',
    title: $t('page.home.appName'),
    align: 'center',
    minWidth: 60
  },
  {
    key: 'description',
    title: $t('page.home.appDesc'),
    align: 'left',
    minWidth: 220
  },
  {
    key: 'status',
    title: $t('page.home.appStatus'),
    align: 'center',
    width: 120,
    render(row) {
      const status = row.status as Api.Settings.ApplicationStatus;
      const tagTypes: Record<Api.Settings.ApplicationStatus, NaiveUI.ThemeColor> = {
        starting: 'warning',
        running: 'success',
        stopping: 'warning',
        stopped: 'error',
        error: 'error'
      };
      return h(
        NTag,
        {
          type: tagTypes[status] || 'default',
          round: true
        },
        { default: () => status }
      );
    }
  },
  {
    key: 'operate',
    title: $t('common.operate'),
    align: 'center',
    width: 220,
    render: (row: any) => {
      const isRunning = row.status === 'running' || row.status === 'starting';
      const isStarting = row.status === 'starting';
      const isStopping = row.status === 'stopping';
      const isDeleting = row.status === 'deleting';

      const dropdownOptions = [
        {
          label: $t('page.home.restart'),
          key: 'restart',
          disabled: row.status !== 'running'
        },
        {
          label: $t('common.delete'),
          key: 'delete',
          disabled: isDeleting
        }
      ];

      const handleDropdownSelect = (key: string) => {
        if (key === 'restart') {
          handleRestartApp(row.app_id);
        } else if (key === 'delete') {
          handleDeleteApp(row.app_id);
        }
      };

      const editButton = h(
        NButton,
        {
          size: 'small',
          type: 'primary',
          disabled: row.status !== 'running',
          onClick: () => routerToApps(row)
        },
        { default: () => [h(NIcon, { component: CreateOutline }), $t('common.edit')] }
      );

      const toggleStatusButton = h(
        NButton,
        {
          size: 'small',
          type: isRunning ? 'warning' : 'success',
          disabled: isDeleting || isStarting || isStopping,
          onClick: () => (isRunning ? handleStopApp(row.app_id) : handleStartApp(row.app_id))
        },
        {
          default: () =>
            isRunning
              ? [h(NIcon, { component: StopCircleOutline }), $t('page.home.pause')]
              : [h(NIcon, { component: RocketOutline }), $t('page.home.start')]
        }
      );

      const moreButton = h(
        NDropdown,
        {
          options: dropdownOptions,
          onSelect: handleDropdownSelect
        },
        {
          default: () =>
            h(
              NButton,
              {
                size: 'small',
                circle: true
              },
              { default: () => h(NIcon, { component: EllipsisHorizontal }) }
            )
        }
      );

      return h(NSpace, { justify: 'center' }, () => [editButton, toggleStatusButton, moreButton]);
    }
  }
];

const getColumnChecks = (columns: TableColumn<any>[]) => {
  const checks: NaiveUI.TableColumnCheck[] = [];
  columns.forEach(column => {
    if ('key' in column && 'title' in column) {
      checks.push({
        key: column.key as string,
        title: column.title as string,
        checked: true
      });
    }
  });
  return checks;
};

const getColumns = (columns: TableColumn<any>[], checks: NaiveUI.TableColumnCheck[]) =>
  columns.filter((column: TableColumn<any>) =>
    checks.find(check => 'key' in column && column.key === check.key && check.checked)
  );

const transformer = (response: any) => ({
  data: response.data.data,
  pageNum: response.data.pageNum,
  pageSize: response.data.pageSize,
  total: response.data.total
});

const isSilentLoading = ref(false);
const displayLoading = computed(() => loading.value && !isSilentLoading.value);

const {
  loading,
  empty,
  data,
  getData: fetchData,
  columns
} = useHookTable({
  apiFn: getApps,
  apiParams,
  transformer,
  columns: tableColumns,
  getColumnChecks,
  getColumns,
  immediate: true
});

const getData = async (silent = false) => {
  isSilentLoading.value = silent;
  await fetchData();
  isSilentLoading.value = false;
};

let pollingInterval: NodeJS.Timeout | null = null;

const managePolling = () => {
  const shouldPoll = data.value.some((app: any) => ['starting', 'stopping', 'deleting'].includes(app.status));

  if (shouldPoll && !pollingInterval) {
    pollingInterval = setInterval(() => {
      getData(true);
    }, 3000);
  } else if (!shouldPoll && pollingInterval) {
    clearInterval(pollingInterval);
    pollingInterval = null;
  }
};

watch(data, managePolling, { deep: true });

onUnmounted(() => {
  if (pollingInterval) {
    clearInterval(pollingInterval);
  }
});

onMounted(() => {
  appStore.updateDemoMode();
});

const createNewApp = () => {
  showCreateModal.value = true;
};

const handleCreateApp = async () => {
  formRef.value?.validate(async (errors: any) => {
    if (!errors) {
      try {
        const { error } = await createApp(createAppForm.appName, createAppForm.description);
        if (!error) {
          message.success($t('page.home.appCreationRequestSent'));
          showCreateModal.value = false;
          createAppForm.appName = '';
          createAppForm.description = '';
          getData(); // Refresh the table immediately
        } else {
          message.error($t('page.home.failedToCreateApp'));
        }
      } catch {
        message.error($t('page.home.errorCreatingApp'));
      }
    } else {
      message.error($t('page.home.fillInCompletely'));
    }
  });
};

const handleDeleteApp = (appId: string) => {
  dialog.warning({
    title: $t('common.warning'),
    content: $t('page.home.deleteConfirm'),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      try {
        const { error } = await deleteApp(appId);
        if (!error) {
          message.success($t('page.home.appDeleted'));
          getData();
        } else {
          message.error($t('page.home.failedToDeleteApp'));
        }
      } catch {
        message.error($t('page.home.errorDeletingApp'));
      }
    }
  });
};

const handleStartApp = async (appId: string) => {
  try {
    const { error } = await startApp(appId);
    if (!error) {
      message.success($t('page.home.appStarting'));
      getData();
    } else {
      message.error($t('page.home.failedToStartApp'));
    }
  } catch {
    message.error($t('page.home.errorStartingApp'));
  }
};

const handleStopApp = async (appId: string) => {
  try {
    const { error } = await stopApp(appId);
    if (!error) {
      message.success($t('page.home.appStopping'));
      getData();
    } else {
      message.error($t('page.home.failedToStopApp'));
    }
  } catch {
    message.error($t('page.home.errorStoppingApp'));
  }
};

const handleRestartApp = async (appId: string) => {
  try {
    const { error } = await restartApp(appId);
    if (!error) {
      message.success($t('page.home.appRestarting'));
      getData();
    } else {
      message.error($t('page.home.failedToRestartApp'));
    }
  } catch {
    message.error($t('page.home.errorRestartingApp'));
  }
};
</script>

<template>
  <HomeLayout>
    <!-- Has apps: show table -->
    <div v-if="!empty" class="home-content">
      <div class="home-table-section">
        <div class="home-table-header">
          <h2 class="home-section-title">{{ $t('page.home.applications') }}</h2>
          <NButton class="apple-btn" @click="createNewApp">
            <template #icon>
              <NIcon :component="AddCircleOutline" />
            </template>
            {{ $t('page.home.createApp') }}
          </NButton>
        </div>
        <div class="home-table-wrapper">
          <NDataTable :columns="columns" :data="data" size="small" :scroll-x="962" :loading="displayLoading" />
        </div>
      </div>
    </div>

    <!-- Empty state: show welcome -->
    <div v-else class="home-empty">
      <div class="home-empty-inner">
        <h1 class="home-welcome-title">{{ $t('page.home.welcome', { userName }) }}</h1>
        <p class="home-welcome-desc">{{ $t('page.home.welcomeDescription') }}</p>

        <div class="home-cards-grid">
          <div v-for="(item, index) in cardData" :key="index" class="home-card-item">
            <div class="home-card-accent" />
            <span class="home-card-text">{{ item.title }}</span>
          </div>
        </div>

        <p class="home-hint">{{ $t('page.home.createYourApp') }}</p>

        <NButton class="apple-btn apple-btn-lg" @click="createNewApp">
          <template #icon>
            <NIcon :component="AddIcon" />
          </template>
          {{ $t('page.home.newApplication') }}
        </NButton>
      </div>
    </div>

    <!-- Create modal -->
    <NModal
      v-model:show="showCreateModal"
      preset="card"
      :title="$t('page.home.newApplication')"
      :mask-closable="false"
      :auto-focus="false"
      style="width: 480px"
    >
      <NForm
        ref="formRef"
        :model="createAppForm"
        :rules="rules"
        label-placement="left"
        label-width="auto"
        @keyup.enter="handleCreateApp"
      >
        <NFormItem :label="$t('page.home.appName')" path="appName">
          <NInput v-model:value="createAppForm.appName" :placeholder="$t('page.home.appNamePlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('page.home.appDesc')" path="description">
          <NInput
            v-model:value="createAppForm.description"
            type="textarea"
            :placeholder="$t('page.home.appDescPlaceholder')"
          />
        </NFormItem>
      </NForm>
      <template #footer>
        <div class="flex justify-end gap-12px">
          <NButton @click="showCreateModal = false">{{ $t('common.cancel') }}</NButton>
          <NButton class="apple-btn" @click="handleCreateApp">{{ $t('page.home.create') }}</NButton>
        </div>
      </template>
    </NModal>
  </HomeLayout>
</template>

<style scoped>
/* Layout */
.home-content {
  padding: 24px 32px;
  height: 100%;
  overflow: auto;
}

.home-table-section {
  background: var(--n-color);
  border-radius: 12px;
  border: 1px solid v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)'");
  box-shadow: v-bind("themeStore.darkMode ? '0 1px 3px rgba(0,0,0,0.2)' : '0 1px 3px rgba(0,0,0,0.04)'");
  overflow: hidden;
}

.home-table-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 20px;
  border-bottom: 1px solid v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)'");
}

.home-section-title {
  font-size: 15px;
  font-weight: 600;
  color: v-bind("themeStore.darkMode ? '#e5e5e5' : '#1d1d1f'");
}

.home-table-wrapper {
  padding: 4px 0;
}

/* Table Apple style */
.home-table-wrapper :deep(.n-data-table) {
  border-radius: 0 0 12px 12px;
  overflow: hidden;
}

.home-table-wrapper :deep(.n-data-table-th) {
  background: v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.03)' : 'rgba(0,0,0,0.01)'");
  border-bottom: 1px solid v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)'");
  font-weight: 500;
  font-size: 13px;
  color: v-bind("themeStore.darkMode ? '#98989d' : '#86868b'");
  padding: 12px 16px;
}

.home-table-wrapper :deep(.n-data-table-td) {
  padding: 10px 16px;
  font-size: 14px;
  color: v-bind("themeStore.darkMode ? '#e5e5e5' : '#1d1d1f'");
  border-bottom: 1px solid v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.03)'");
}

.home-table-wrapper :deep(.n-data-table-tr:hover .n-data-table-td) {
  background: v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.04)' : 'rgba(0,0,0,0.02)'");
}

.home-table-wrapper :deep(.n-data-table .n-data-table-th__title) {
  font-weight: 500;
}

/* Empty state */
.home-empty {
  height: 100%;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 40px 24px;
}

.home-empty-inner {
  display: flex;
  flex-direction: column;
  align-items: center;
  max-width: 720px;
}

.home-welcome-title {
  font-size: 28px;
  font-weight: 700;
  letter-spacing: -0.02em;
  color: v-bind("themeStore.darkMode ? '#f5f5f7' : '#1d1d1f'");
  text-align: center;
}

.home-welcome-desc {
  margin-top: 8px;
  font-size: 15px;
  color: v-bind("themeStore.darkMode ? '#98989d' : '#86868b'");
  text-align: center;
  line-height: 1.5;
}

/* Cards grid */
.home-cards-grid {
  display: grid;
  grid-template-columns: repeat(3, 1fr);
  gap: 16px;
  margin-top: 32px;
  width: 100%;
  max-width: 640px;
}

.home-card-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 16px;
  border-radius: 12px;
  background: v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.05)' : 'rgba(0,0,0,0.02)'");
  border: 1px solid v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.06)' : 'rgba(0,0,0,0.04)'");
  transition: all 0.2s ease;
  cursor: default;
}

.home-card-item:hover {
  background: v-bind("themeStore.darkMode ? 'rgba(255,255,255,0.08)' : 'rgba(0,0,0,0.04)'");
}

.home-card-accent {
  width: 4px;
  height: 24px;
  border-radius: 2px;
  background-color: #007aff;
  flex-shrink: 0;
}

.home-card-text {
  font-size: 14px;
  color: v-bind("themeStore.darkMode ? '#e5e5e5' : '#1d1d1f'");
  line-height: 1.4;
}

.home-hint {
  margin-top: 24px;
  font-size: 13px;
  color: v-bind("themeStore.darkMode ? '#6e6e73' : '#aeaeb2'");
}

/* Buttons */
.apple-btn {
  height: 36px;
  border-radius: 8px;
  font-size: 14px;
  font-weight: 500;
  background-color: #007aff;
  border: none;
  color: #fff;
  transition:
    background-color 0.15s ease,
    transform 0.15s ease;
}

.apple-btn:hover {
  background-color: #0071e3;
}

.apple-btn:active {
  background-color: #006edb;
  transform: scale(0.98);
}

.apple-btn-lg {
  height: 42px;
  padding: 0 24px;
  font-size: 15px;
  margin-top: 16px;
}

/* Responsive */
@media (max-width: 768px) {
  .home-content {
    padding: 16px;
  }

  .home-cards-grid {
    grid-template-columns: repeat(2, 1fr);
  }

  .home-welcome-title {
    font-size: 22px;
  }
}
</style>
