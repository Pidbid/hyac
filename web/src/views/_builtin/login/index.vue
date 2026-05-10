<script setup lang="ts">
import { useAppStore } from '@/store/modules/app';
import { useThemeStore } from '@/store/modules/theme';
import { $t } from '@/locales';
import PwdLogin from './modules/pwd-login.vue';

const appStore = useAppStore();
const themeStore = useThemeStore();
</script>

<template>
  <div
    class="login-page size-full overflow-hidden"
    :class="themeStore.darkMode ? 'login-page-dark' : 'login-page-light'"
  >
    <div class="login-bg-orb login-bg-orb-1" />
    <div class="login-bg-orb login-bg-orb-2" />
    <div class="login-bg-orb login-bg-orb-3" />

    <div class="relative z-10 size-full flex-col-center">
      <div class="login-card w-380px lt-sm:w-320px">
        <!-- Logo -->
        <div class="mb-28px flex-col-center gap-12px">
          <SystemLogo class="text-56px" />
          <h1 class="text-22px font-600 tracking-tight" :class="themeStore.darkMode ? 'text-white' : 'text-gray-900'">
            {{ $t('system.title') }}
          </h1>
        </div>

        <!-- Form -->
        <PwdLogin />

        <!-- Footer -->
        <div class="mt-24px flex items-center justify-center gap-16px">
          <ThemeSchemaSwitch
            :theme-schema="themeStore.themeScheme"
            :show-tooltip="false"
            class="text-16px"
            @switch="themeStore.toggleThemeScheme"
          />
          <LangSwitch
            v-if="themeStore.header.multilingual.visible"
            :lang="appStore.locale"
            :lang-options="appStore.localeOptions"
            :show-tooltip="false"
            @change-lang="appStore.changeLocale"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.login-page {
  position: relative;
}

.login-page-light {
  background: linear-gradient(180deg, #e8f0fe 0%, #f5f7fa 40%, #ffffff 100%);
}

.login-page-dark {
  background: linear-gradient(180deg, #0a1628 0%, #111827 50%, #1a1a2e 100%);
}

.login-bg-orb {
  position: absolute;
  border-radius: 50%;
  filter: blur(100px);
  pointer-events: none;
}

.login-bg-orb-1 {
  width: 600px;
  height: 600px;
  top: -200px;
  right: -100px;
  opacity: 0.3;
  background: v-bind(themeStore.darkMode ? '#1e3a5f': '#a3c4f3');
}

.login-bg-orb-2 {
  width: 500px;
  height: 500px;
  bottom: -150px;
  left: -100px;
  opacity: 0.25;
  background: v-bind(themeStore.darkMode ? '#2d1b69': '#c4b5fd');
}

.login-bg-orb-3 {
  width: 350px;
  height: 350px;
  top: 50%;
  left: 50%;
  transform: translate(-50%, -50%);
  opacity: 0.15;
  background: v-bind(themeStore.darkMode ? '#0d4f4f': '#99f6e4');
}

.login-card {
  padding: 40px 32px 32px;
  border-radius: 16px;
  background: v-bind(themeStore.darkMode ? 'rgba(30, 32, 38, 0.85)': 'rgba(255, 255, 255, 0.72)');
  backdrop-filter: blur(40px) saturate(180%);
  -webkit-backdrop-filter: blur(40px) saturate(180%);
  border: 1px solid v-bind(themeStore.darkMode ? 'rgba(255,255,255,0.08)': 'rgba(255,255,255,0.6)');
  box-shadow: v-bind(
    themeStore.darkMode ? '0 8px 32px rgba(0,0,0,0.3)': '0 2px 16px rgba(0,0,0,0.06), 0 0 0 1px rgba(0,0,0,0.02)'
  );
  transition:
    box-shadow 0.3s ease,
    transform 0.3s ease;
}

.login-card:hover {
  box-shadow: v-bind(
    themeStore.darkMode ? '0 12px 40px rgba(0,0,0,0.4)': '0 4px 24px rgba(0,0,0,0.1), 0 0 0 1px rgba(0,0,0,0.02)'
  );
  transform: translateY(-1px);
}
</style>
