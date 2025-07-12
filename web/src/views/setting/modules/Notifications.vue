<script setup lang="ts">
import { ref, onMounted } from 'vue';
import {
  NCard,
  NForm,
  NFormItem,
  NSwitch,
  NButton,
  NInput,
  NInputNumber,
  NSelect,
  NSpace,
  useMessage,
  NAlert,
  NTabs,
  NTabPane
} from 'naive-ui';
import { $t } from '@/locales';
import { useApplicationStore } from '@/store/modules/application';
import { notificationData, notificationUpdate } from '@/service/api/settings';

defineOptions({
  name: 'NotificationsSettings'
});

const applicationStore = useApplicationStore();
const message = useMessage();
const isLoading = ref(false);

const settings = ref<Api.Settings.NotificationConfig>({
  email: { enabled: false, smtpServer: '', port: 465, username: '', password: '', fromAddress: '' },
  webhook: { enabled: false, url: '', method: 'POST', template: '' },
  wechat: { enabled: false, notificationId: '' }
});

async function fetchData() {
  isLoading.value = true;
  const appId = applicationStore.appInfo.appId;
  if (appId) {
    const { data, error } = await notificationData({ appId });
    if (!error) {
      settings.value = data;
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
    const { error } = await notificationUpdate({ appId, config: settings.value });
    if (!error) {
      message.success($t('common.saveSuccess'));
    } else {
      message.error($t('common.saveFailed'));
    }
  }
  isLoading.value = false;
}

function handleTest(type: 'email' | 'webhook' | 'wechat') {
  // TODO: Implement test logic
  message.info(`Test for ${type} is not implemented yet.`);
}

onMounted(fetchData);
</script>

<template>
  <NCard :title="$t('page.setting.notifications')" :bordered="false">
    <NSpace vertical :size="24">
      <NAlert type="info" :title="$t('page.setting.notificationTipTitle')">
        {{ $t('page.setting.notificationTipContent') }}
      </NAlert>

      <NTabs type="line" animated>
        <!-- Email -->
        <NTabPane name="email" :tab="$t('page.setting.emailNotifications')">
          <NForm :model="settings.email" label-placement="left" label-width="auto" :disabled="isLoading">
            <NFormItem :label="$t('common.switch')">
              <NSwitch v-model:value="settings.email.enabled" />
            </NFormItem>
            <NFormItem :label="`SMTP ${$t('page.setting.server')}`">
              <NInput v-model:value="settings.email.smtpServer" />
            </NFormItem>
            <NFormItem :label="$t('page.setting.port')">
              <NInputNumber v-model:value="settings.email.port" />
            </NFormItem>
            <NFormItem :label="$t('page.setting.username')">
              <NInput v-model:value="settings.email.username" />
            </NFormItem>
            <NFormItem :label="$t('page.setting.password')">
              <NInput v-model:value="settings.email.password" type="password" show-password-on="click" />
            </NFormItem>
            <NFormItem :label="$t('page.setting.senderEmail')">
              <NInput v-model:value="settings.email.fromAddress" />
            </NFormItem>
            <NButton type="info" ghost @click="handleTest('email')">{{ $t('page.setting.sendTest') }}</NButton>
          </NForm>
        </NTabPane>

        <!-- Webhook -->
        <NTabPane name="webhook" :tab="$t('page.setting.webhookNotifications')">
          <NForm :model="settings.webhook" label-placement="left" label-width="auto" :disabled="isLoading">
            <NFormItem :label="$t('common.switch')">
              <NSwitch v-model:value="settings.webhook.enabled" />
            </NFormItem>
            <NFormItem :label="$t('page.setting.url')">
              <NInput v-model:value="settings.webhook.url" />
            </NFormItem>
            <NFormItem :label="$t('page.setting.requestMethod')">
              <NSelect v-model:value="settings.webhook.method" :options="[{label: 'POST', value: 'POST'}, {label: 'GET', value: 'GET'}]" />
            </NFormItem>
            <NFormItem :label="$t('page.setting.requestBodyTemplate')">
              <NInput v-model:value="settings.webhook.template" type="textarea" :rows="5" />
            </NFormItem>
            <NButton type="info" ghost @click="handleTest('webhook')">{{ $t('page.setting.sendTest') }}</NButton>
          </NForm>
        </NTabPane>

        <!-- WeChat -->
        <NTabPane name="wechat" :tab="$t('page.setting.wechatNotifications')">
           <NForm :model="settings.wechat" label-placement="left" label-width="auto" :disabled="isLoading">
            <NFormItem :label="$t('common.switch')">
              <NSwitch v-model:value="settings.wechat.enabled" />
            </NFormItem>
            <NFormItem :label="$t('page.setting.notificationId')">
              <NInput v-model:value="settings.wechat.notificationId" />
            </NFormItem>
            <NButton type="info" ghost @click="handleTest('wechat')">{{ $t('page.setting.sendTest') }}</NButton>
          </NForm>
        </NTabPane>
      </NTabs>

      <NButton type="primary" @click="handleSave" :loading="isLoading" class="mt-4">
        {{ $t('common.save') }}
      </NButton>
    </NSpace>
  </NCard>
</template>
