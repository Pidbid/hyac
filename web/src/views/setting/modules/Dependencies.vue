<script setup lang="ts">
import { ref, onMounted, h } from 'vue';
import {
  NCard,
  NDataTable,
  NButton,
  NSpace,
  NModal,
  NInput,
  useMessage,
  NSelect,
  NTabs,
  NTabPane,
  NAlert,
  NIcon,
  useDialog,
  NInputGroup
} from 'naive-ui';
import { AddOutline, CubeOutline, TrashOutline, SearchOutline, BrushOutline, LinkOutline } from '@vicons/ionicons5';
import { $t } from '@/locales';
import { useApplicationStore } from '@/store/modules/application';
import { dependenciesData, packageAdd, packageRemove, dependenceSearch, packageInfo } from '@/service/api/settings';
import { restartApp } from '@/service/api/app';

defineOptions({
  name: 'DependenciesSettings'
});

const applicationStore = useApplicationStore();
const message = useMessage();
const dialog = useDialog();

const userDependencies = ref<Api.Settings.Dependency[]>([]);
const systemDependencies = ref<Api.Settings.Dependency[]>([]);
const isLoading = ref(true);
const showAddModal = ref(false);
const newPackageName = ref('');
const newPackageVersion = ref('');
const searchResults = ref<any[]>([]);
const searchLoading = ref(false);
const versionOptions = ref<any[]>([]);
const versionLoading = ref(false);

const searchColumns = [
  {
    title: $t('page.setting.dependencyName'),
    key: 'label'
  },
  {
    title: $t('common.action._self'),
    key: 'actions',
    width: 100,
    render(row: any) {
      return h(
        NButton,
        {
          type: 'primary',
          size: 'small',
          onClick: () => handleSelectPackage(row.value)
        },
        { default: () => $t('common.action.select') }
      );
    }
  }
];

const userColumns = [
  {
    title: $t('page.setting.dependencyName'),
    key: 'name',
    render(row: any) {
      return h('div', { class: 'flex items-center' }, [
        h(NIcon, { component: CubeOutline, size: 20, class: 'mr-2 text-gray-500' }),
        h('span', row.name),
        h(
          'a',
          {
            href: `https://pypi.org/project/${row.name}`,
            target: '_blank',
            class: 'ml-2 text-gray-400 hover:text-primary flex items-center'
          },
          h(NIcon, { component: LinkOutline, size: 22 })
        )
      ]);
    }
  },
  {
    title: $t('page.function.version'),
    key: 'version'
  },
  {
    title: $t('common.action._self'),
    key: 'actions',
    width: 150,
    render(row: any) {
      return h(NSpace, {}, () => [
        h(
          NButton,
          {
            strong: true,
            tertiary: true,
            circle: true,
            type: 'primary',
            onClick: () => handleEdit(row)
          },
          { default: () => h(NIcon, { component: BrushOutline }) }
        ),
        h(
          NButton,
          {
            strong: true,
            tertiary: true,
            circle: true,
            type: 'error',
            onClick: () => handleDelete(row)
          },
          { default: () => h(NIcon, { component: TrashOutline }) }
        )
      ]);
    }
  }
];

const systemColumns = [
  {
    title: $t('page.setting.dependencyName'),
    key: 'name',
    render(row: any) {
      return h('div', { class: 'flex items-center' }, [
        h(NIcon, { component: CubeOutline, class: 'mr-2 text-gray-500' }),
        h('span', row.name)
      ]);
    }
  },
  {
    title: $t('page.function.version'),
    key: 'version'
  }
];

async function fetchData() {
  isLoading.value = true;
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { data, error } = await dependenciesData(appId);
    if (!error) {
      userDependencies.value = data.common;
      systemDependencies.value = data.system;
    } else {
      message.error($t('common.fetchFailed'));
    }
  }
  isLoading.value = false;
}

let searchTimeout: number | null = null;

async function handleSearch(query: string) {
  if (!query) {
    searchResults.value = [];
    return;
  }
  searchLoading.value = true;
  const appId = applicationStore.appInfo.appId;
  const { data } = await dependenceSearch(appId, query);
  if (data) {
    searchResults.value = data.map((item: Api.Settings.PackageInfo) => ({ label: item.name, value: item.name }));
  }
  searchLoading.value = false;
}

function onSearchInput(value: string) {
  newPackageName.value = value;
  if (searchTimeout) {
    clearTimeout(searchTimeout);
  }
  searchTimeout = window.setTimeout(() => {
    handleSearch(value);
  }, 500); // 500ms debounce
}

async function handleSelectPackage(packageName: string) {
  newPackageName.value = packageName;
  versionLoading.value = true;
  const appId = applicationStore.appInfo.appId;
  const { data, error } = await packageInfo(appId, packageName);
  if (!error && data?.versions) {
    versionOptions.value = data.versions.map((v: string) => ({ label: v, value: v }));
    newPackageVersion.value = data.versions[0] || '';
  } else {
    message.error($t('page.function.getPackageInfoFailed'));
  }
  versionLoading.value = false;
  searchResults.value = [];
}

async function handleAddPackage() {
  const appId = applicationStore.appInfo.appId;
  if (appId && newPackageName.value) {
    const { error } = await packageAdd(appId, newPackageName.value, newPackageVersion.value || 'latest');
    if (!error) {
      message.success($t('common.addSuccess'));
      showAddModal.value = false;
      newPackageName.value = '';
      newPackageVersion.value = '';
      fetchData();
      promptRestart();
    } else {
      message.error($t('common.addFailed'));
    }
  }
}

function handleEdit(row: Api.Settings.Dependency) {
  const editPackageName = ref(row.name);
  const editPackageVersion = ref(row.version);
  const editVersionOptions = ref<any[]>([]);
  const editVersionLoading = ref(true);

  const fetchVersions = async () => {
    const appId = applicationStore.appInfo.appId;
    const { data, error } = await packageInfo(appId, editPackageName.value);
    if (!error && data?.versions) {
      editVersionOptions.value = data.versions.map((v: string) => ({ label: v, value: v }));
    } else {
      message.error($t('page.function.getPackageInfoFailed'));
    }
    editVersionLoading.value = false;
  };

  fetchVersions();

  dialog.info({
    title: `${$t('common.action.edit')} - ${row.name}`,
    content: () =>
      h(NSpace, { vertical: true, class: 'pt-4' }, () => [
        h(NSelect, {
          value: editPackageVersion.value,
          options: editVersionOptions.value,
          loading: editVersionLoading.value,
          onUpdateValue: value => {
            editPackageVersion.value = value;
          }
        })
      ]),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const appId = applicationStore.appInfo.appId;
      if (appId && editPackageName.value) {
        const { error } = await packageAdd(appId, editPackageName.value, editPackageVersion.value);
        if (!error) {
          message.success($t('common.editSuccess'));
          fetchData();
          promptRestart();
        } else {
          message.error($t('common.editFailed'));
        }
      }
    }
  });
}

function handleDelete(row: Api.Settings.Dependency) {
  dialog.warning({
    title: $t('page.setting.confirmDelete'),
    content: $t('page.setting.deleteDependencyConfirm', { name: row.name }),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const appId = applicationStore.appInfo.appId;
      if (appId) {
        const { error } = await packageRemove(appId, row.name);
        if (!error) {
          message.success($t('common.deleteSuccess'));
          fetchData();
          promptRestart();
        } else {
          message.error($t('common.deleteFailed'));
        }
      }
    }
  });
}

function promptRestart() {
  dialog.warning({
    title: $t('page.setting.restartRequired'),
    content: $t('page.setting.dependencyChangeRestartPrompt'),
    positiveText: $t('page.setting.restartNow'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const d = dialog.info({
        title: $t('page.setting.restarting'),
        content: $t('page.setting.restartingTip'),
        closable: false
      });
      const appId = applicationStore.appInfo.appId;
      const { error } = await restartApp(appId);
      d.destroy();
      if (!error) {
        message.success($t('page.setting.restartInitiated'));
      } else {
        message.error($t('page.setting.restartFailed'));
      }
    }
  });
}

onMounted(fetchData);
</script>

<template>
  <NCard :title="$t('page.setting.dependencies')" :bordered="false">
    <NSpace vertical :size="24">
      <NAlert type="info" :title="$t('page.setting.dependenciesTipTitle')">
        {{ $t('page.setting.dependenciesTipContent') }}
      </NAlert>

      <NTabs type="line" animated>
        <NTabPane name="user" :tab="$t('page.setting.userDependencies')">
          <NDataTable :columns="userColumns" :data="userDependencies" :loading="isLoading" :bordered="false" />
          <NButton type="primary" dashed block class="mt-4" @click="showAddModal = true">
            <template #icon>
              <NIcon :component="AddOutline" />
            </template>
            {{ $t('page.setting.addDependency') }}
          </NButton>
        </NTabPane>
        <NTabPane name="system" :tab="$t('page.setting.systemDependencies')">
          <NDataTable :columns="systemColumns" :data="systemDependencies" :loading="isLoading" :bordered="false" />
        </NTabPane>
      </NTabs>
    </NSpace>

    <NModal
      v-model:show="showAddModal"
      preset="card"
      :title="$t('page.setting.addDependency')"
      style="width: 600px"
      @after-leave="() => { newPackageName = ''; newPackageVersion = ''; searchResults = []; versionOptions = []; }"
    >
      <NSpace vertical>
        <NInput
          :value="newPackageName"
          :placeholder="$t('page.setting.dependencyNamePlaceholder')"
          clearable
          :loading="searchLoading"
          @update:value="onSearchInput"
        >
          <template #suffix>
            <NIcon :component="SearchOutline" />
          </template>
        </NInput>
        <NDataTable
          v-if="searchResults.length > 0"
          :columns="searchColumns"
          :data="searchResults"
          :max-height="200"
          :bordered="false"
        />
        <NSelect
          v-model:value="newPackageVersion"
          :options="versionOptions"
          :placeholder="$t('page.setting.dependencyVersionPlaceholder')"
          :loading="versionLoading"
          clearable
        />
        <NButton type="primary" block @click="handleAddPackage">{{ $t('common.confirm') }}</NButton>
      </NSpace>
    </NModal>
  </NCard>
</template>
