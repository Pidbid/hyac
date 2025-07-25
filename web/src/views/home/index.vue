<script setup lang="ts">
import { reactive, h, ref, watch, onUnmounted, computed, onMounted } from 'vue';
import {
  NButton,
  NPopconfirm,
  NCard,
  NDataTable,
  NEmpty,
  NIcon,
  NGi,
  NGrid,
  NH1,
  NP,
  NModal,
  NForm,
  NFormItem,
  NInput,
  useMessage,
  NSpace,
  NTag,
  NDropdown,
  useDialog
} from 'naive-ui';
import { AddCircleOutline, AddOutline as AddIcon, CreateOutline, TrashBinOutline, StopCircleOutline, RocketOutline, EllipsisHorizontal } from '@vicons/ionicons5';
import { useHookTable } from '@sa/hooks';
import { getApps, createApp, deleteApp, startApp, stopApp, restartApp } from '@/service/api/app';
import { applicationStatus } from '@/service/api/settings';
import { useRouterPush } from '@/hooks/common/router';
import HomeLayout from '@/layouts/home-layout/index.vue';
import { $t } from '@/locales';
import { localStg } from '@/utils/storage';
import { useAuthStore } from '@/store/modules/auth';
import { useAppStore } from '@/store/modules/app';
import type { DataTableColumn as TableColumn } from 'naive-ui';

const { routerPush } = useRouterPush();
const authStore = useAuthStore();
const message = useMessage();
const dialog = useDialog();
const appStore = useAppStore();

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
    width: 64,
    render: (_, index) => {
      return (apiParams.page - 1) * apiParams.length + index + 1;
    }
  },
  {
    key: 'app_id',
    title: $t('page.home.appId'),
    align: 'center',
    minWidth: 60
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
    minWidth: 220,
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
        { default: () => (isRunning ? [h(NIcon, { component: StopCircleOutline }), $t('page.home.pause')] : [h(NIcon, { component: RocketOutline }), $t('page.home.start')]) }
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

const { loading, empty, data, getData: fetchData, columns } = useHookTable({
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
        const { data: responseData, error } = await createApp(createAppForm.appName, createAppForm.description);
        if (!error) {
          message.success($t('page.home.appCreationRequestSent'));
          showCreateModal.value = false;
          createAppForm.appName = '';
          createAppForm.description = '';
          getData(); // Refresh the table immediately
        } else {
          message.error($t('page.home.failedToCreateApp'));
        }
      } catch (e) {
        message.error($t('page.home.errorCreatingApp'));
      }
    } else {
      console.log(errors)
      message.error($t('page.home.fillInCompletely'))
    }
  })
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
      } catch (e) {
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
  } catch (e) {
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
  } catch (e) {
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
  } catch (e) {
    message.error($t('page.home.errorRestartingApp'));
  }
};
</script>

<template>
  <HomeLayout>
    <NGrid cols="24" class="mt-15">
      <NGridItem offset="4" span="16">
        <div v-if="!empty" class="min-h-500px flex-col-stretch gap-16px overflow-hidden lt-sm:overflow-auto">
          <NCard :bordered="false" size="small" class="sm:flex-1-hidden card-wrapper">
            <template #header>
              <NButton type="primary" size="large" @click="createNewApp">
                <template #icon>
                  <NIcon :component="AddCircleOutline"></NIcon>
                </template>
                {{ $t('page.home.createApp') }}
              </NButton>
            </template>
            <NDataTable
              :columns="columns"
              :data="data"
              size="small"
              :scroll-x="962"
              class="sm:h-full"
              :loading="displayLoading"
            />
          </NCard>
        </div>
        <div v-else class="h-full w-full flex-col-center">
          <div class="m-auto flex-col-center">
            <NH1 class="text-3xl! font-bold!">
              {{ $t('page.home.welcome', { userName }) }}
            </NH1>
            <NP class="text-16px text-gray-500 mt-4 text-center">
              {{ $t('page.home.welcomeDescription') }}
            </NP>

            <NGrid :x-gap="24" :y-gap="24" :cols="3" class="mt-8 w-[900px]">
              <NGi v-for="(item, index) in cardData" :key="index">
                <NCard hoverable class="h-full! rounded-lg!">
                  <div class="flex items-center">
                    <div class="h-30px w-4px bg-primary mr-12px"></div>
                    <span class="text-16px">{{ item.title }}</span>
                  </div>
                </NCard>
              </NGi>
            </NGrid>

            <NP class="text-14px text-gray-400 mt-8">
              {{ $t('page.home.createYourApp') }}
            </NP>

            <NButton type="primary" size="large" class="mt-4" @click="createNewApp">
              <template #icon>
                <NIcon :component="AddIcon" />
              </template>
              {{ $t('page.home.newApplication') }}
            </NButton>
          </div>
        </div>
      </NGridItem>
    </NGrid>

    <NModal v-model:show="showCreateModal" preset="card" :title="$t('page.home.newApplication')" style="width: 600px">
      <NForm ref="formRef" :model="createAppForm" :rules="rules" label-placement="left" label-width="auto" @keyup.enter="handleCreateApp">
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
        <div class="flex justify-end gap-x-4">
          <NButton @click="showCreateModal = false">{{ $t('common.cancel') }}</NButton>
          <NButton type="primary" @click="handleCreateApp">{{ $t('page.home.create') }}</NButton>
        </div>
      </template>
    </NModal>
  </HomeLayout>
</template>

<style scoped></style>
