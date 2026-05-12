<script setup lang="ts">
/* eslint-disable @typescript-eslint/no-use-before-define, no-underscore-dangle */
import { onMounted, ref } from 'vue';
import { NButton, NIcon, NSelect, NSpace, useMessage } from 'naive-ui';
import { useI18n } from 'vue-i18n';
import { ReloadOutline, TerminalOutline } from '@vicons/ionicons5';
import { GetFunctionData } from '@/service/api/function';
import { useApplicationStore } from '@/store/modules/application';
import { useAppStore } from '@/store/modules/app';
import RuntimeLogPanel from './modules/RuntimeLogPanel.vue';
import './index.css';

const { t } = useI18n();
const message = useMessage();
const applicationStore = useApplicationStore();
const appStore = useAppStore();

const functions = ref<{ label: string; value: string }[]>([]);
const selectedFuncId = ref<string | null>(null);

// --- 数据获取 ---
const fetchFunctions = async () => {
  if (!applicationStore.appId) return;
  try {
    const { data, error } = await GetFunctionData(applicationStore.appId, 1, 1000); // 获取所有函数
    if (error) {
      message.error(t('page.log.loadFunctionListFailed'));
      return;
    }
    if (data?.data) {
      functions.value = data.data.map(f => ({
        label: f.function_name,
        value: f.function_id
      }));
    }
  } catch (e: any) {
    message.error(`${t('page.log.requestFunctionListError', { message: e.message })}`);
  }
};

// --- 生命周期 ---
onMounted(async () => {
  await fetchFunctions();
});
</script>

<template>
  <div class="logs-page">
    <header class="logs-toolbar">
      <div class="toolbar-title">
        <NIcon :component="TerminalOutline" :size="18" />
        <span>{{ t('route.log') }}</span>
      </div>
      <div class="toolbar-filters">
        <NSpace align="center">
          <NSelect
            v-model:value="selectedFuncId"
            :options="functions"
            :placeholder="t('page.log.allFunctions')"
            clearable
            class="filter-select function"
            size="small"
          />
          <NButton type="default" size="small" @click="appStore.reloadPage(500)">
            <template #icon>
              <NIcon :component="ReloadOutline" />
            </template>
          </NButton>
        </NSpace>
      </div>
    </header>
    <RuntimeLogPanel :app-id="applicationStore.appId" :func-id="selectedFuncId" :tail="200" :title="t('route.log')" />
  </div>
</template>
