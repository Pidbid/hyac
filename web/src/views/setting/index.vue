<script setup lang="ts">
import { ref, computed, h, defineAsyncComponent, onMounted } from 'vue';
import { NLayout, NLayoutSider, NLayoutContent, NMenu, NCard, NSplit, NIcon } from 'naive-ui';
import {
  CodeSlashOutline,
  ServerOutline,
  ShareSocialOutline,
  NotificationsOutline,
  WarningOutline,
  KeyOutline,
  HardwareChipOutline,
  CloudUploadOutline,
  PersonCircleOutline
} from '@vicons/ionicons5';
import { $t } from '@/locales';
import { useAppStore } from '@/store/modules/app';

 defineOptions({
  name: 'SettingIndex'
});

const appStore = useAppStore();
const activeKey = ref('dependencies');

const menuOptions = computed(() => [
  {
    label: $t('page.setting.group.application'),
    key: 'application-settings',
    type: 'group',
    children: [
      {
        label: $t('page.setting.dependencies'),
        key: 'dependencies',
        icon: () => h(NIcon, { component: CodeSlashOutline })
      },
      {
        label: $t('page.setting.environmentVariables'),
        key: 'environment',
        icon: () => h(NIcon, { component: KeyOutline })
      },
      {
        label: $t('page.setting.cors'),
        key: 'cors',
        icon: () => h(NIcon, { component: ShareSocialOutline })
      },
      {
        label: $t('page.setting.dangerZone'),
        key: 'danger-zone',
        icon: () => h(NIcon, { component: WarningOutline })
      }
    ]
  },
  {
    label: $t('page.setting.group.system'),
    key: 'system-settings',
    type: 'group',
    children: [
      {
        label: $t('page.setting.userProfile.title'),
        key: 'user-profile',
        icon: () => h(NIcon, { component: PersonCircleOutline })
      },
      {
        label: $t('page.setting.ai.title'),
        key: 'ai-settings',
        icon: () => h(NIcon, { component: HardwareChipOutline })
      },
      {
        label: $t('page.setting.notifications'),
        key: 'notifications',
        icon: () => h(NIcon, { component: NotificationsOutline })
      },
      {
        label: $t('page.setting.systemUpdate.title'),
        key: 'system-update',
        icon: () => h(NIcon, { component: CloudUploadOutline })
      }
    ]
  }
]);

const componentMap = {
  dependencies: defineAsyncComponent(() => import('./modules/Dependencies.vue')),
  environment: defineAsyncComponent(() => import('./modules/Environment.vue')),
  'ai-settings': defineAsyncComponent(() => import('./modules/AiSettings.vue')),
  cors: defineAsyncComponent(() => import('./modules/Cors.vue')),
  notifications: defineAsyncComponent(() => import('./modules/Notifications.vue')),
  'danger-zone': defineAsyncComponent(() => import('./modules/DangerZone.vue')),
  'system-update': defineAsyncComponent(() => import('./modules/SystemUpdate.vue')),
  'user-profile': defineAsyncComponent(() => import('./modules/UserProfile.vue'))
};

const currentComponent = computed(() => {
  return componentMap[activeKey.value as keyof typeof componentMap];
});

onMounted(() => {
  appStore.updateDemoMode();
});
</script>

<template>
  <NCard :bordered="false" class="h-full" content-style="padding: 0; height: 100%;">
    <NSplit direction="horizontal" :default-size="0.1" class="h-full">
      <template #1>
        <div class="h-full">
          <NMenu
            :value="activeKey"
            :options="menuOptions"
            :collapsed-width="64"
            :collapsed-icon-size="22"
            @update:value="key => (activeKey = key)"
          />
        </div>
      </template>
      <template #2>
        <div class="p-4 sm:p-6 md:p-8 h-full overflow-y-auto">
          <component :is="currentComponent" />
        </div>
      </template>
    </NSplit>
  </NCard>
</template>

<style scoped>
:deep(.n-split__pane-1) {
  background-color: var(--n-color);
}
</style>
