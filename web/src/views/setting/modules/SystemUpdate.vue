<template>
  <n-card :title="$t('page.setting.systemUpdate.title')" :bordered="false">
    <n-grid :x-gap="16" :y-gap="16" :cols="3">
      <n-gi :span="1">
        <n-card :title="$t('page.setting.systemUpdate.versionInfo')">
          <n-spin :show="versionsLoading">
            <n-descriptions label-placement="left" :column="1" bordered>
              <n-descriptions-item :label="$t('page.setting.systemUpdate.currentServerVersion')">
                {{ versions.server_version || 'N/A' }}
              </n-descriptions-item>
              <n-descriptions-item :label="$t('page.setting.systemUpdate.currentAppVersion')">
                {{ versions.app_version || 'N/A' }}
              </n-descriptions-item>
              <n-descriptions-item :label="$t('page.setting.systemUpdate.currentWebVersion')">
                {{ versions.web_version || 'N/A' }}
              </n-descriptions-item>
            </n-descriptions>
          </n-spin>
        </n-card>
      </n-gi>
      <n-gi :span="2">
        <n-card :title="$t('page.setting.systemUpdate.changelogTab')">
          <n-spin :show="changelogLoading">
            <n-timeline>
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
          </n-spin>
        </n-card>
      </n-gi>
    </n-grid>
  </n-card>
</template>

<script setup lang="ts">
import { ref, onMounted, reactive } from 'vue';
import {
  NCard,
  NSpin,
  NCollapse,
  NCollapseItem,
  useNotification,
  NTimeline,
  NTimelineItem,
  NDescriptions,
  NDescriptionsItem,
  NGrid,
  NGi
} from 'naive-ui';
import { fetchChangelogs, fetchSystemVersions } from '@/service/api/settings';
import MarkdownIt from 'markdown-it';
import { $t } from '@/locales';

defineOptions({
  name: 'SystemUpdate'
});

const changelogs = ref<Api.Settings.ChangelogInfo[]>([]);
const versions = reactive<Api.Settings.SystemVersions>({
  server_version: '',
  web_version: '',
  app_version: ''
});
const changelogLoading = ref(false);
const versionsLoading = ref(false);
const notification = useNotification();
const md = new MarkdownIt({
  html: true,
  linkify: true,
  typographer: true
});

function renderMarkdown(content: string) {
  return md.render(content);
}

async function loadChangelogs() {
  changelogLoading.value = true;
  try {
    const { data } = await fetchChangelogs();
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

async function loadVersions() {
  versionsLoading.value = true;
  try {
    const { data } = await fetchSystemVersions();
    if (data) {
      versions.server_version = data.server_version;
      versions.web_version = data.web_version;
      versions.app_version = data.app_version;
    }
  } catch (error) {
    notification.error({
      title: 'Error',
      content: 'Failed to fetch system versions.',
      duration: 5000
    });
  } finally {
    versionsLoading.value = false;
  }
}

onMounted(() => {
  loadChangelogs();
  loadVersions();
});
</script>

<style scoped>
.prose {
  max-width: 100%;
}
</style>
