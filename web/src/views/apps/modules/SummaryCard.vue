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
  const functions = props.summary?.functions;
  const requests = functions?.requests;

  return [
    {
      key: 'functionCount',
      title: $t('page.apps.functionCount'),
      value: functions?.count ?? 0,
      icon: 'ant-design:function-outlined',
      color: '#3f8eff'
    },
    {
      key: 'databaseCount',
      title: $t('page.apps.databaseCount'),
      value: props.summary?.database.count ?? 0,
      icon: 'ant-design:database-outlined',
      color: '#3f8eff'
    },
    {
      key: 'storageCount',
      title: $t('page.apps.storageCount'),
      value: `${props.summary?.storage.total_usage_mb.toFixed(2) ?? 0} MB`,
      icon: 'ant-design:cloud-server-outlined',
      color: '#3f8eff'
    },
    {
      key: 'avgExecutionTime',
      title: $t('page.apps.avgExecutionTime'),
      value: `${functions?.overall_average_execution_time.toFixed(2) ?? 0} ms`,
      icon: 'ant-design:field-time-outlined',
      color: '#3f8eff'
    }
  ];
});
</script>

<template>
  <NCard :title="$t('page.apps.coreMetrics')" :loading="props.loading" :bordered="false" class="card-wrapper h-full">
    <NGrid :cols="12" :x-gap="16" :y-gap="16" responsive="screen" item-responsive>
      <NGi v-for="item in summaryData" :key="item.key" span="12 s:6 m:4 l:3">
        <div class="flex items-center">
          <SvgIcon :icon="item.icon" class="text-32px" :style="{ color: item.color }" />
          <div class="ml-12px">
            <p class="text-18px font-bold">{{ item.value }}</p>
            <p class="text-14px text-gray-500">{{ item.title }}</p>
          </div>
        </div>
      </NGi>
    </NGrid>
  </NCard>
</template>

<style scoped></style>
