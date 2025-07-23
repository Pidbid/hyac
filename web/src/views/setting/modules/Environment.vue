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
  NTabs,
  NTabPane,
  NAlert,
  NIcon,
  useDialog,
  NForm,
  NFormItem
} from 'naive-ui';
import { AddOutline, KeyOutline, TrashOutline, EyeOutline, EyeOffOutline } from '@vicons/ionicons5';
import { $t } from '@/locales';
import { useApplicationStore } from '@/store/modules/application';
import { getEnvsData, addEnv, removeEnv } from '@/service/api/settings';

defineOptions({
  name: 'EnvironmentSettings'
});

const applicationStore = useApplicationStore();
const message = useMessage();
const dialog = useDialog();

const userEnv = ref<Api.Settings.EnvInfo[]>([]);
const systemEnv = ref<Api.Settings.EnvInfo[]>([]);
const isLoading = ref(true);
const showAddModal = ref(false);
const isEditMode = ref(false);
const newEnv = ref({ key: '', value: '' });
const revealedKeys = ref<Set<string>>(new Set());

const toggleVisibility = (key: string) => {
  if (revealedKeys.value.has(key)) {
    revealedKeys.value.delete(key);
  } else {
    revealedKeys.value.add(key);
  }
};

const userColumns = [
  {
    title: $t('page.setting.key'),
    key: 'key',
    render(row: any) {
      return h('div', { class: 'flex items-center' }, [
        h(NIcon, { component: KeyOutline, class: 'mr-2 text-gray-500' }),
        h('span', row.key)
      ]);
    }
  },
  {
    title: $t('page.setting.value'),
    key: 'value',
    render(row: any) {
      const isRevealed = revealedKeys.value.has(row.key);
      return h(NSpace, { align: 'center' }, {
        default: () => [
          h('span', isRevealed ? row.value : '••••••••'),
          h(NButton, {
            quaternary: true,
            circle: true,
            size: 'small',
            onClick: () => toggleVisibility(row.key)
          }, { icon: () => h(NIcon, { component: isRevealed ? EyeOffOutline : EyeOutline }) })
        ]
      });
    }
  },
  {
    title: $t('common.action._self'),
    key: 'actions',
    width: 150,
    render(row: any) {
      return h(NSpace, {}, {
        default: () => [
          h(NButton, { strong: true, tertiary: true, size: 'small', onClick: () => handleEdit(row) }, { default: () => $t('common.edit') }),
          h(NButton, { strong: true, tertiary: true, size: 'small', type: 'error', onClick: () => handleDelete(row) }, { default: () => $t('common.delete') })
        ]
      });
    }
  }
];

const systemColumns = [
  {
    title: $t('page.setting.key'),
    key: 'key'
  },
  {
    title: $t('page.setting.value'),
    key: 'value',
    render(row: any) {
      const isRevealed = revealedKeys.value.has(row.key);
      return h(NSpace, { align: 'center' }, {
        default: () => [
          h('span', isRevealed ? row.value : '••••••••'),
          h(NButton, {
            quaternary: true,
            circle: true,
            size: 'small',
            onClick: () => toggleVisibility(row.key)
          }, { icon: () => h(NIcon, { component: isRevealed ? EyeOffOutline : EyeOutline }) })
        ]
      });
    }
  }
];

async function fetchData() {
  isLoading.value = true;
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { data, error } = await getEnvsData(appId);
    if (!error) {
      userEnv.value = data.user;
      systemEnv.value = data.system;
      // Default sensitive keys to be hidden
      const sensitiveKeywords = ['password', 'secret', 'key', 'token'];
      const allEnvs = [...data.user, ...data.system];
      allEnvs.forEach((env: Api.Settings.EnvInfo) => {
        const isSensitive = sensitiveKeywords.some(keyword => env.key.toLowerCase().includes(keyword));
        if (!isSensitive) {
          revealedKeys.value.add(env.key);
        }
      });
    } else {
      message.error($t('common.fetchFailed'));
    }
  }
  isLoading.value = false;
}

function handleAdd() {
  isEditMode.value = false;
  newEnv.value = { key: '', value: '' };
  showAddModal.value = true;
}

function handleEdit(row: Api.Settings.EnvInfo) {
  isEditMode.value = true;
  newEnv.value = { ...row };
  showAddModal.value = true;
}

async function handleSave() {
  const appId = applicationStore.appInfo.appId;
  if (appId && newEnv.value.key) {
    const { error } = await addEnv(appId, newEnv.value.key, newEnv.value.value);
    if (!error) {
      message.success($t('common.saveSuccess'));
      showAddModal.value = false;
      fetchData();
    } else {
      message.error($t('common.saveFailed'));
    }
  }
}

function handleDelete(row: Api.Settings.EnvInfo) {
  dialog.warning({
    title: $t('page.setting.confirmDelete'),
    content: $t('page.setting.deleteEnvConfirm', { key: row.key }),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const appId = applicationStore.appInfo.appId;
      if (appId) {
        const { error } = await removeEnv(appId, row.key);
        if (!error) {
          message.success($t('common.deleteSuccess'));
          fetchData();
        } else {
          message.error($t('common.deleteFailed'));
        }
      }
    }
  });
}


onMounted(fetchData);
</script>

<template>
  <NCard :title="$t('page.setting.environmentVariables')" :bordered="false">
    <NSpace vertical :size="24">
      <NAlert type="info" :title="$t('page.setting.envTipTitle')">
        {{ $t('page.setting.envTipContent') }}
      </NAlert>

      <NTabs type="line" animated>
        <NTabPane name="user" :tab="$t('page.setting.userEnv')">
          <NDataTable :columns="userColumns" :data="userEnv" :loading="isLoading" :bordered="false" />
          <NButton type="primary" dashed block class="mt-4" @click="handleAdd">
            <template #icon>
              <NIcon :component="AddOutline" />
            </template>
            {{ $t('page.setting.addEnv') }}
          </NButton>
        </NTabPane>
        <NTabPane name="system" :tab="$t('page.setting.systemEnv')">
          <NDataTable :columns="systemColumns" :data="systemEnv" :loading="isLoading" :bordered="false" />
        </NTabPane>
      </NTabs>
    </NSpace>

    <NModal
      v-model:show="showAddModal"
      preset="card"
      :title="isEditMode ? $t('page.setting.editEnv') : $t('page.setting.addEnv')"
      style="width: 600px"
    >
      <NForm>
        <NFormItem :label="$t('page.setting.key')">
          <NInput v-model:value="newEnv.key" :disabled="isEditMode" :placeholder="$t('page.setting.keyPlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('page.setting.value')">
          <NInput v-model:value="newEnv.value" :placeholder="$t('page.setting.valuePlaceholder')" />
        </NFormItem>
        <NButton type="primary" block @click="handleSave">{{ $t('common.save') }}</NButton>
      </NForm>
    </NModal>
  </NCard>
</template>
