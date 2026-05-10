<script setup lang="ts">
import { computed, defineAsyncComponent, h, onMounted, ref } from 'vue';
import { NIcon, NMenu, NSplit } from 'naive-ui';
import {
  CloudUploadOutline,
  CodeSlashOutline,
  HardwareChipOutline,
  KeyOutline,
  NotificationsOutline,
  PersonCircleOutline,
  ShareSocialOutline,
  WarningOutline
} from '@vicons/ionicons5';
import { useAppStore } from '@/store/modules/app';
import { $t } from '@/locales';

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
  <div class="setting-page">
    <NSplit direction="horizontal" :default-size="0.18" :min="0.12" :max="0.34" class="setting-split">
      <template #1>
        <aside class="setting-sidebar">
          <div class="sidebar-title">
            <NIcon :component="HardwareChipOutline" :size="16" />
            <span>{{ $t('route.setting') }}</span>
          </div>
          <NMenu
            :value="activeKey"
            :options="menuOptions"
            :collapsed-width="64"
            :collapsed-icon-size="22"
            @update:value="key => (activeKey = key)"
          />
        </aside>
      </template>
      <template #2>
        <main class="setting-content">
          <component :is="currentComponent" />
        </main>
      </template>
    </NSplit>
  </div>
</template>

<style scoped>
.setting-page {
  --setting-gap: 6px;

  height: 100%;
  min-height: 0;
  width: 100%;
  overflow: hidden;
  background: #f5f5f7;
  padding: 8px;
}

.setting-split {
  height: 100%;
  min-height: 0;
}

.setting-split :deep(.n-split-pane) {
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.setting-split :deep(.n-split-pane-1) {
  padding-right: var(--setting-gap);
}

.setting-split :deep(.n-split-pane-2) {
  padding-left: var(--setting-gap);
}

.setting-sidebar {
  height: 100%;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  font-size: 13px;
  font-weight: 600;
  color: #1d1d1f;
}

.setting-content {
  height: 100%;
  overflow-y: auto;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  background: rgba(255, 255, 255, 0.78);
  padding: 20px;
}

:deep(.n-menu) {
  padding: 8px;
}

:deep(.n-menu-item-content) {
  border-radius: 8px;
}

.setting-content :deep(.n-card) {
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  overflow: hidden;
  box-shadow: none;
}

.setting-content :deep(.n-card-header) {
  padding: 14px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: #f9f9fb;
}

.setting-content :deep(.n-data-table) {
  --n-td-color-hover: #f5f5f7;
  --n-merged-border-color: rgba(0, 0, 0, 0.06);
}
</style>
