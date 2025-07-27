<template>
  <n-card :title="$t('page.setting.systemUpdate.title')" :bordered="false">
    <n-alert type="warning" :title="$t('page.setting.systemUpdate.updateDevInProgress')" class="mb-4" />
    <n-tabs type="line" animated>
      <n-tab-pane name="auto-update" :tab="$t('page.setting.systemUpdate.autoUpdateTab')">
        <n-space vertical>
          <!-- Check for Updates Section -->
          <n-input v-model:value="proxyUrl" :placeholder="$t('page.setting.systemUpdate.proxyPlaceholder')" />
          <n-button type="primary" @click="checkUpdates" :loading="loading">
            {{ $t('page.setting.systemUpdate.checkForUpdates') }}
          </n-button>

          <div v-if="loading" class="flex items-center mt-4">
            <n-spin size="small" />
            <span style="margin-left: 8px;">{{ $t('page.setting.systemUpdate.checkingForUpdates') }}</span>
          </div>

          <div v-if="updateInfo" class="mt-4">
            <n-alert v-if="updateInfo.update_available" :title="$t('page.setting.systemUpdate.newVersionAvailable')" type="success">
              <p>{{ $t('page.setting.systemUpdate.latestVersion') }}: {{ updateInfo.latest_version_info.version }}</p>
              <p>{{ $t('page.setting.systemUpdate.publishedAt') }}: {{ new Date(updateInfo.latest_version_info.published_at).toLocaleString() }}</p>
              <n-collapse class="mt-4">
                <n-collapse-item :title="$t('page.setting.systemUpdate.changelog')" name="1">
                  <div v-html="changelogHtml" class="prose dark:prose-invert"></div>
                </n-collapse-item>
              </n-collapse>
              <n-button @click="handleUpdate" type="primary" :loading="updateInProgress" class="mt-4">
                {{ $t('page.setting.systemUpdate.updateNow') }}
              </n-button>
            </n-alert>
            <n-alert v-else :title="$t('page.setting.systemUpdate.upToDate')" type="info">
              {{ $t('page.setting.systemUpdate.upToDateMessage') }}
            </n-alert>
            <div class="mt-4 text-sm text-gray-500">
              <p>{{ $t('page.setting.systemUpdate.currentServerVersion') }}: {{ updateInfo.current_versions.server_version }}</p>
              <p>{{ $t('page.setting.systemUpdate.currentAppVersion') }}: {{ updateInfo.current_versions.app_version || 'N/A' }}</p>
              <p>{{ $t('page.setting.systemUpdate.currentLspVersion') }}: {{ updateInfo.current_versions.lsp_version || 'N/A' }}</p>
              <p>{{ $t('page.setting.systemUpdate.currentWebVersion') }}: {{ updateInfo.current_versions.web_version || 'N/A' }}</p>
            </div>
          </div>
        </n-space>
      </n-tab-pane>
      <n-tab-pane name="manual-update" :tab="$t('page.setting.systemUpdate.manualUpdateTab')">
        <n-space vertical>
          <!-- Manual Update Section -->
          <n-alert type="warning" :title="$t('page.setting.systemUpdate.manualUpdateInfo')" />

          <n-form>
            <n-form-item :label="$t('page.setting.systemUpdate.serverTag')">
              <n-input v-model:value="manualUpdateTags.server" :placeholder="$t('page.setting.systemUpdate.serverTagPlaceholder')" />
            </n-form-item>
            <n-form-item :label="$t('page.setting.systemUpdate.appTag')">
              <n-input v-model:value="manualUpdateTags.app" :placeholder="$t('page.setting.systemUpdate.appTagPlaceholder')" />
            </n-form-item>
            <n-form-item :label="$t('page.setting.systemUpdate.lspTag')">
              <n-input v-model:value="manualUpdateTags.lsp" :placeholder="$t('page.setting.systemUpdate.lspTagPlaceholder')" />
            </n-form-item>
            <n-form-item :label="$t('page.setting.systemUpdate.webTag')">
              <n-input v-model:value="manualUpdateTags.web" :placeholder="$t('page.setting.systemUpdate.webTagPlaceholder')" />
            </n-form-item>
          </n-form>
          <n-button type="error" @click="handleManualUpdate" :loading="updateInProgress">
            {{ $t('page.setting.systemUpdate.runManualUpdate') }}
          </n-button>
        </n-space>
      </n-tab-pane>
      <n-tab-pane name="changelog" :tab="$t('page.setting.systemUpdate.changelogTab')">
        <n-space vertical>
          <div v-if="changelogLoading" class="flex items-center">
            <n-spin size="small" />
            <span style="margin-left: 8px;">{{ $t('page.setting.systemUpdate.loadingChangelogs') }}</span>
          </div>
          <n-timeline v-else>
            <n-timeline-item v-for="log in changelogs" :key="log.version" type="success">
              <template #header>
                <p class="font-bold">{{ log.version }}</p>
                <p class="text-sm text-gray-500">{{ new Date(log.published_at).toLocaleString() }}</p>
              </template>
              <template #default>
                <n-collapse>
                  <n-collapse-item :title="$t('page.setting.systemUpdate.changelog')" name="1">
                    <div v-html="renderMarkdown(log.changelog)" class="prose dark:prose-invert"></div>
                  </n-collapse-item>
                </n-collapse>
              </template>
            </n-timeline-item>
          </n-timeline>
        </n-space>
      </n-tab-pane>
    </n-tabs>
  </n-card>
</template>

<script setup lang="ts">
import { ref, computed, reactive, onMounted } from 'vue';
import { NCard, NSpin, NAlert, NButton, NCollapse, NCollapseItem, useNotification, NInput, NSpace, NForm, NFormItem, NTabs, NTabPane, useDialog, NTimeline, NTimelineItem } from 'naive-ui';
import { fetchCheckForUpdates, fetchUpdateSystem, fetchChangelogs } from '@/service/api/settings';
import MarkdownIt from 'markdown-it';
import { $t } from '@/locales';

defineOptions({
  name: 'SystemUpdate'
});

const loading = ref(false);
const updateInProgress = ref(false);
const updateInfo = ref<any>(null);
const changelogs = ref<Api.Settings.ChangelogInfo[]>([]);
const changelogLoading = ref(false);
const proxyUrl = ref('');
const manualUpdateTags = reactive({
  server: '',
  app: '',
  lsp: '',
  web: ''
});
const notification = useNotification();
const dialog = useDialog();
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true
});

const changelogHtml = computed(() => {
  if (updateInfo.value?.latest_version_info?.changelog) {
    return md.render(updateInfo.value.latest_version_info.changelog);
  }
  return '';
});

function renderMarkdown(content: string) {
  return md.render(content);
}

async function loadChangelogs() {
  changelogLoading.value = true;
  try {
    const { data } = await fetchChangelogs({ proxy: proxyUrl.value || undefined });
    changelogs.value = data || [];
  } catch (error) {
    notification.error({
      title: $t('page.setting.systemUpdate.changelogError'),
      content: $t('page.setting.systemUpdate.changelogErrorContent'),
      duration: 5000
    });
  } finally {
    changelogLoading.value = false;
  }
}

onMounted(() => {
  loadChangelogs();
});

async function checkUpdates() {
  loading.value = true;
  updateInfo.value = null;
  try {
    const { data } = await fetchCheckForUpdates({ proxy: proxyUrl.value || undefined });
    updateInfo.value = data;
  } catch (error) {
    notification.error({
      title: $t('page.setting.systemUpdate.updateError'),
      content: $t('page.setting.systemUpdate.updateErrorContent'),
      duration: 5000
    });
  } finally {
    loading.value = false;
  }
}

async function handleUpdate() {
  dialog.warning({
    title: $t('page.setting.systemUpdate.confirmUpdateTitle'),
    content: $t('page.setting.systemUpdate.confirmUpdateContent'),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      updateInProgress.value = true;
      try {
        await fetchUpdateSystem();
        notification.success({
          title: $t('page.setting.systemUpdate.updateStarted'),
          content: $t('page.setting.systemUpdate.updateStartedContent'),
          duration: 10000
        });
      } catch (error) {
        notification.error({
          title: $t('page.setting.systemUpdate.updateFailed'),
          content: $t('page.setting.systemUpdate.updateFailedContent'),
          duration: 5000
        });
      } finally {
        updateInProgress.value = false;
      }
    }
  });
}

async function handleManualUpdate() {
  dialog.warning({
    title: $t('page.setting.systemUpdate.confirmUpdateTitle'),
    content: $t('page.setting.systemUpdate.confirmUpdateContent'),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      updateInProgress.value = true;
      try {
        await fetchUpdateSystem(manualUpdateTags);
        notification.success({
          title: $t('page.setting.systemUpdate.updateStarted'),
          content: $t('page.setting.systemUpdate.updateStartedContent'),
          duration: 10000
        });
      } catch (error) {
        notification.error({
          title: $t('page.setting.systemUpdate.updateFailed'),
          content: $t('page.setting.systemUpdate.updateFailedContent'),
          duration: 5000
        });
      } finally {
        updateInProgress.value = false;
      }
    }
  });
}
</script>

<style scoped>
.prose {
  max-width: 100%;
}
</style>
