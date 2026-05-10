<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';

defineOptions({
  name: 'FunctionStatusCard'
});

interface Props {
  summary: Api.Statistics.Summary | null;
  loading: boolean;
}

const props = defineProps<Props>();

const { t } = useI18n();

const stats = computed(() => {
  const s = props.summary?.functions.requests;
  const total = s?.total ?? 0;
  const success = s?.success ?? 0;
  const unknown = s?.unknown ?? 0;
  const successRate = total - unknown > 0 ? (success / (total - unknown)) * 100 : 0;

  return [
    {
      label: t('page.apps.successCalls'),
      value: success,
      color: 'text-green-500',
      icon: 'mdi:check-circle-outline'
    },
    {
      label: t('page.apps.errorCalls'),
      value: s?.error ?? 0,
      color: 'text-red-500',
      icon: 'mdi:close-circle-outline'
    },
    {
      label: t('page.apps.unknownCalls'),
      value: unknown,
      color: 'text-gray-500',
      icon: 'mdi:help-circle-outline'
    },
    {
      label: t('page.apps.successRate'),
      value: `${successRate.toFixed(1)}%`,
      color: 'text-blue-500',
      icon: 'mdi:chart-line'
    }
  ];
});
</script>

<template>
  <div class="apple-card">
    <h3 class="apple-card-title">{{ t('page.apps.requestCount') }}</h3>
    <NSpin :show="loading">
      <div class="stats-grid">
        <div v-for="(item, index) in stats" :key="index" class="stat-item">
          <div class="stat-icon-wrap" :class="item.color">
            <SvgIcon :icon="item.icon" class="text-30px" />
          </div>
          <p class="stat-value">{{ item.value }}</p>
          <p class="stat-label">{{ item.label }}</p>
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

.stats-grid {
  display: grid;
  grid-template-columns: repeat(4, 1fr);
  gap: 16px;
}

.stat-item {
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 8px;
}

.stat-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.stat-icon-wrap.text-green-500 {
  background: rgba(34, 197, 94, 0.1);
  color: #22c55e;
}

.stat-icon-wrap.text-red-500 {
  background: rgba(239, 68, 68, 0.1);
  color: #ef4444;
}

.stat-icon-wrap.text-gray-500 {
  background: rgba(107, 114, 128, 0.1);
  color: #6b7280;
}

.stat-icon-wrap.text-blue-500 {
  background: rgba(0, 122, 255, 0.1);
  color: #007aff;
}

.stat-value {
  font-size: 22px;
  font-weight: 700;
}

.stat-label {
  font-size: 13px;
  color: #86868b;
}

@media (max-width: 640px) {
  .stats-grid {
    grid-template-columns: repeat(2, 1fr);
  }
}
</style>
