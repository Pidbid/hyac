<script setup lang="ts">
import { h, ref } from 'vue';
import { NCard, NButton, NSpace, useDialog, useMessage, NText, NInput } from 'naive-ui';
import { $t } from '@/locales';
import { useApplicationStore } from '@/store/modules/application';
import { restartApp, stopApp, deleteApp } from '@/service/api/app';
import { useRouter } from 'vue-router';

defineOptions({
  name: 'DangerZone'
});

const applicationStore = useApplicationStore();
const message = useMessage();
const dialog = useDialog();
const router = useRouter();

const handleRestart = () => {
  dialog.warning({
    title: $t('page.setting.confirmRestart'),
    content: $t('page.setting.restartAppConfirm'),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const { error } = await restartApp(applicationStore.appInfo.appId);
      if (!error) {
        message.success($t('page.setting.restartInitiated'));
        router.push({ name: 'home' });
      } else {
        message.error($t('page.setting.restartFailed'));
      }
    }
  });
};

const handleStop = () => {
  dialog.warning({
    title: $t('page.setting.confirmStop'),
    content: $t('page.setting.stopAppConfirm'),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      const { error } = await stopApp(applicationStore.appInfo.appId);
      if (!error) {
        message.success($t('page.setting.stopInitiated'));
        router.push({ name: 'home' });
      } else {
        message.error($t('page.setting.stopFailed'));
      }
    }
  });
};

const handleDelete = () => {
  const inputValue = ref('');
  dialog.error({
    title: $t('page.setting.confirmDeleteApp'),
    content: () =>
      h('div', [
        h('p', $t('page.setting.deleteAppConfirm1')),
        h('p', $t('page.setting.deleteAppConfirm2')),
        h('p', [
          $t('page.setting.deleteAppConfirm3'),
          h(NText, { type: 'error', strong: true }, ` ${applicationStore.appInfo.appId} `),
          $t('page.setting.deleteAppConfirm4')
        ]),
        h(NInput, {
          value: inputValue.value,
          onInput: (e: any) => (inputValue.value = e.target.value),
          placeholder: $t('page.setting.deleteAppInputPlaceholder')
        })
      ]),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      if (inputValue.value !== applicationStore.appInfo.appId) {
        message.error($t('page.setting.incorrectAppId'));
        return;
      }
      const { error } = await deleteApp(applicationStore.appInfo.appId);
      if (!error) {
        message.success($t('page.setting.deleteInitiated'));
        router.push({ name: 'home' });
      } else {
        message.error($t('page.setting.deleteFailed'));
      }
    }
  });
};
</script>

<template>
  <NCard :title="$t('page.setting.dangerZone')" :bordered="false">
    <NSpace vertical>
      <!-- Restart Application -->
      <NCard size="small">
        <NSpace align="center" justify="space-between">
          <div>
            <NText strong>{{ $t('page.setting.restartApp') }}</NText>
            <p class="text-sm text-gray-500">{{ $t('page.setting.restartAppDesc') }}</p>
          </div>
          <NButton type="warning" ghost @click="handleRestart">{{ $t('page.setting.restartApp') }}</NButton>
        </NSpace>
      </NCard>

      <!-- Stop Application -->
      <NCard size="small">
        <NSpace align="center" justify="space-between">
          <div>
            <NText strong>{{ $t('page.setting.stopApp') }}</NText>
            <p class="text-sm text-gray-500">{{ $t('page.setting.stopAppDesc') }}</p>
          </div>
          <NButton type="error" ghost @click="handleStop">{{ $t('page.setting.stopApp') }}</NButton>
        </NSpace>
      </NCard>

      <!-- Delete Application -->
      <NCard size="small">
        <NSpace align="center" justify="space-between">
          <div>
            <NText strong>{{ $t('page.setting.deleteApp') }}</NText>
            <p class="text-sm text-gray-500">{{ $t('page.setting.deleteAppDesc') }}</p>
          </div>
          <NButton type="error" @click="handleDelete">{{ $t('page.setting.deleteApp') }}</NButton>
        </NSpace>
      </NCard>
    </NSpace>
  </NCard>
</template>
