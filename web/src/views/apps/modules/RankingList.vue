<script setup lang="ts">
import { computed, ref } from 'vue';
import { $t } from '@/locales';

defineOptions({
  name: 'RankingList'
});

interface Props {
  summary: Api.Statistics.Summary | null;
}

const props = defineProps<Props>();

type RankingType = 'count' | 'time';

const rankingType = ref<RankingType>('count');

const rankingData = computed(() => {
  if (!props.summary) return [];

  if (rankingType.value === 'count') {
    const data = props.summary.functions.ranking_by_count || [];
    return data.map(item => ({
      name: item.function_name === 'Unknown' ? `${$t('page.apps.unknown')} ${item.function_id}` : item.function_name,
      value: `${item.count} ${$t('page.apps.requestCountUnit')}`
    }));
  }

  const data = props.summary.functions.ranking_by_time || [];
  return data.map(item => ({
    name: item.function_name || $t('page.apps.unknown'),
    value: `${item.average_execution_time?.toFixed(2) ?? 0} ms`
  }));
});

const title = computed(() => {
  return rankingType.value === 'count' ? $t('page.apps.top5FunctionsByCount') : $t('page.apps.top5FunctionsByTime');
});
</script>

<template>
  <div class="apple-card">
    <div class="card-header">
      <h3 class="apple-card-title">{{ title }}</h3>
      <NRadioGroup v-model:value="rankingType" size="small">
        <NRadioButton value="count">{{ $t('page.apps.byCount') }}</NRadioButton>
        <NRadioButton value="time">{{ $t('page.apps.byTime') }}</NRadioButton>
      </NRadioGroup>
    </div>
    <div class="ranking-list">
      <div v-for="(item, index) in rankingData" :key="index" class="ranking-item">
        <span class="ranking-name">
          <span class="ranking-index">{{ index + 1 }}.</span>
          <a class="cursor-pointer text-primary hover:underline">{{ item.name }}</a>
        </span>
        <span class="ranking-value">{{ item.value }}</span>
      </div>
    </div>
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

.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.apple-card-title {
  font-size: 15px;
  font-weight: 600;
}

.ranking-list {
  display: flex;
  flex-direction: column;
}

.ranking-item {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 0;
  border-bottom: 1px solid rgba(0, 0, 0, 0.04);
}

.ranking-item:last-child {
  border-bottom: none;
}

.ranking-name {
  font-size: 14px;
}

.ranking-index {
  margin-right: 8px;
  color: #86868b;
}

.ranking-value {
  font-weight: 600;
  font-size: 14px;
}
</style>
