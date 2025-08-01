<script setup lang="ts">
import { computed } from 'vue';
import { $t } from '@/locales';

defineOptions({
  name: 'InsightCard'
});

interface Props {
  summary: Api.Statistics.Summary | null;
}

const props = defineProps<Props>();

const insights = computed(() => props.summary?.insights || []);

function getIcon(type: Api.Statistics.InsightItem['type']) {
  switch (type) {
    case 'info':
      return 'ant-design:info-circle-outlined';
    case 'warning':
      return 'ant-design:warning-outlined';
    case 'error':
      return 'ant-design:close-circle-outlined';
    default:
      return 'ant-design:info-circle-outlined';
  }
}

function getIconColor(type: Api.Statistics.InsightItem['type']) {
  switch (type) {
    case 'info':
      return '#409eff';
    case 'warning':
      return '#e6a23c';
    case 'error':
      return '#f56c6c';
    default:
      return '#409eff';
  }
}
</script>

<template>
  <NCard :title="$t('page.apps.insights')" :bordered="false" class="card-wrapper h-full">
    <NSpace vertical v-if="insights.length > 0">
      <div v-for="(item, index) in insights" :key="index" class="flex items-start">
        <SvgIcon :icon="getIcon(item.type)" class="text-18px mt-4px mr-8px" :style="{ color: getIconColor(item.type) }" />
        <span>{{ item.message }}</span>
      </div>
    </NSpace>
    <NEmpty v-else :description="$t('page.apps.noInsights')" />
  </NCard>
</template>

<style scoped></style>
