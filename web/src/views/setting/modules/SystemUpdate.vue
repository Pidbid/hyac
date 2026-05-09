<script setup lang="ts">
import { onMounted, reactive, ref } from 'vue';
import {
  NCard,
  NCollapse,
  NCollapseItem,
  NDescriptions,
  NDescriptionsItem,
  NGi,
  NGrid,
  NSpin,
  NTimeline,
  NTimelineItem,
  useNotification
} from 'naive-ui';
import MarkdownIt from 'markdown-it';
import { fetchChangelogs, fetchSystemVersions } from '@/service/api/settings';
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

<template>
  <NCard :title="$t('page.setting.systemUpdate.title')" :bordered="false">
    <NGrid :x-gap="16" :y-gap="16" :cols="3">
      <NGi :span="1">
        <NCard :title="$t('page.setting.systemUpdate.versionInfo')">
          <NSpin :show="versionsLoading">
            <NDescriptions label-placement="left" :column="1" bordered>
              <NDescriptionsItem :label="$t('page.setting.systemUpdate.currentServerVersion')">
                {{ versions.server_version || 'N/A' }}
              </NDescriptionsItem>
              <NDescriptionsItem :label="$t('page.setting.systemUpdate.currentAppVersion')">
                {{ versions.app_version || 'N/A' }}
              </NDescriptionsItem>
              <NDescriptionsItem :label="$t('page.setting.systemUpdate.currentWebVersion')">
                {{ versions.web_version || 'N/A' }}
              </NDescriptionsItem>
            </NDescriptions>
          </NSpin>
        </NCard>
      </NGi>
      <NGi :span="2">
        <NCard :title="$t('page.setting.systemUpdate.changelogTab')">
          <NSpin :show="changelogLoading">
            <NTimeline>
              <NTimelineItem v-for="log in changelogs" :key="log.version" type="success">
                <template #header>
                  <p class="font-bold">{{ log.version }}</p>
                  <p class="text-sm text-gray-500">{{ new Date(log.published_at).toLocaleString() }}</p>
                </template>
                <template #default>
                  <NCollapse>
                    <NCollapseItem :title="$t('page.setting.systemUpdate.changelog')" name="1">
                      <div class="prose dark:prose-invert" v-html="renderMarkdown(log.changelog)"></div>
                    </NCollapseItem>
                  </NCollapse>
                </template>
              </NTimelineItem>
            </NTimeline>
          </NSpin>
        </NCard>
      </NGi>
    </NGrid>
  </NCard>
</template>

<style scoped>
.prose {
  max-width: 100%;
}
</style>
