<script setup lang="ts">
import { ref, onMounted } from 'vue';
import {
  NCard,
  NForm,
  NFormItem,
  NSwitch,
  NButton,
  NDynamicInput,
  NSpace,
  useMessage,
  NAlert
} from 'naive-ui';
import { $t } from '@/locales';
import { useApplicationStore } from '@/store/modules/application';
import { corsData, corsUpdate } from '@/service/api/settings';

defineOptions({
  name: 'CorsSettings'
});

const applicationStore = useApplicationStore();
const message = useMessage();
const isLoading = ref(false);

const corsConfig = ref<Api.Settings.CorsConfig>({
  allow_origins: [],
  allow_credentials: true,
  allow_methods: [],
  allow_headers: []
});

async function fetchData() {
  isLoading.value = true;
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { data, error } = await corsData({ appId });
    if (!error) {
      corsConfig.value = data;
    } else {
      message.error($t('common.fetchFailed'));
    }
  }
  isLoading.value = false;
}

async function handleSave() {
  isLoading.value = true;
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { error } = await corsUpdate({ appId, config: corsConfig.value });
    if (!error) {
      message.success($t('common.saveSuccess'));
    } else {
      message.error($t('common.saveFailed'));
    }
  }
  isLoading.value = false;
}

onMounted(fetchData);
</script>

<template>
  <NCard :title="$t('page.setting.cors')" :bordered="false">
    <NSpace vertical :size="24">
      <NAlert type="info" :title="$t('page.setting.corsTipTitle')">
        {{ $t('page.setting.corsTipContent') }} <br>
        {{ $t('page.setting.corsTipDynamicInput') }}
      </NAlert>
      <NForm :model="corsConfig" label-placement="left" label-width="auto" :disabled="isLoading">
        <NFormItem :label="$t('page.setting.allowOrigins')">
          <NDynamicInput v-model:value="corsConfig.allow_origins" :placeholder="$t('page.setting.originPlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('page.setting.allowMethods')">
          <NDynamicInput v-model:value="corsConfig.allow_methods" :placeholder="$t('page.setting.methodPlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('page.setting.allowHeaders')">
          <NDynamicInput v-model:value="corsConfig.allow_headers" :placeholder="$t('page.setting.headerPlaceholder')" />
        </NFormItem>
        <NFormItem :label="$t('page.setting.allowCredentials')">
          <NSwitch v-model:value="corsConfig.allow_credentials" />
        </NFormItem>
        <NButton type="primary" @click="handleSave" :loading="isLoading">
          {{ $t('common.save') }}
        </NButton>
      </NForm>
    </NSpace>
  </NCard>
</template>
