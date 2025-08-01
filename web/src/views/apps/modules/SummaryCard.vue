<script setup lang="ts">
import { computed } from 'vue';
import { $t } from '@/locales';

defineOptions({
  name: 'SummaryCard'
});

interface Props {
  loading: boolean;
  summary: Api.Statistics.Summary | null;
}

const props = defineProps<Props>();

interface SummaryData {
  key: string;
  title: string;
  value: string | number;
  icon: string;
  color: string;
}

const summaryData = computed<SummaryData[]>(() => {
  const successRate =
    props.summary?.functions.requests.total === 0
      ? 0
      : ((props.summary?.functions.requests.success ?? 0) / (props.summary?.functions.requests.total ?? 1)) * 100;

  return [
    {
      key: 'requestCount',
      title: $t('page.apps.requestCount'),
      value: `${props.summary?.functions.requests.total ?? 0} (${successRate.toFixed(1)}% ${$t('page.apps.successRate')})`,
      icon: 'ant-design:bar-chart-outlined',
      color: '#409eff'
    },
    {
      key: 'functionCount',
      title: $t('page.apps.functionCount'),
      value: props.summary?.functions.count ?? 0,
      icon: 'ant-design:function-outlined',
      color: '#67c23a'
    },
    {
      key: 'databaseCount',
      title: $t('page.apps.databaseCount'),
      value: props.summary?.database.count ?? 0,
      icon: 'ant-design:database-outlined',
      color: '#e6a23c'
    },
    {
      key: 'storageCount',
      title: $t('page.apps.storageCount'),
      value: `${props.summary?.storage.total_usage_mb.toFixed(2) ?? 0} MB`,
      icon: 'ant-design:cloud-server-outlined',
      color: '#f56c6c'
    }
  ];
});
</script>

<template>
  <NCard :title="$t('page.apps.coreMetrics')" :loading="props.loading" :bordered="false" class="card-wrapper h-full">
    <NGrid :cols="2" :x-gap="16" :y-gap="16" responsive="screen">
      <NGi v-for="item in summaryData" :key="item.key">
        <div class="flex items-center">
          <SvgIcon :icon="item.icon" class="text-24px" :style="{ color: item.color }" />
          <div class="ml-12px">
            <p class="text-16px font-bold">{{ item.value }}</p>
            <p class="text-12px text-gray-500">{{ item.title }}</p>
          </div>
        </div>
      </NGi>
    </NGrid>
  </NCard>
</template>

<style scoped></style>
