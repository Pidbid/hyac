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
  <div class="apple-card">
    <h3 class="apple-card-title">{{ $t('page.apps.coreMetrics') }}</h3>
    <NSpin :show="props.loading">
      <div class="metrics-grid">
        <div v-for="item in summaryData" :key="item.key" class="metric-item">
          <div class="metric-icon-wrap">
            <SvgIcon :icon="item.icon" class="text-28px text-[#007aff]" />
          </div>
          <div class="metric-info">
            <p class="metric-value">{{ item.value }}</p>
            <p class="metric-label">{{ item.title }}</p>
          </div>
        </div>
      </div>
    </NSpin>
  </div>
</template>

<style scoped>
.apple-card {
  padding: 20px;
  border-radius: 12px;
  background: var(--n-color);
  border: 1px solid rgba(0, 0, 0, 0.04);
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.apple-card-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 16px;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.metric-item {
  display: flex;
  align-items: center;
  gap: 14px;
}

.metric-icon-wrap {
  width: 52px;
  height: 52px;
  border-radius: 12px;
  background: rgba(0, 122, 255, 0.08);
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.metric-value {
  font-size: 18px;
  font-weight: 700;
}

.metric-label {
  font-size: 13px;
  color: #86868b;
}

@media (max-width: 768px) {
  .metrics-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
