<script setup lang="ts">
import { ref, computed } from 'vue';
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
      name: item.function_name == 'Unknown' ? `${$t('page.apps.unknown')} ${item.function_id}` : item.function_name,
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
  return rankingType.value === 'count'
    ? $t('page.apps.top5FunctionsByCount')
    : $t('page.apps.top5FunctionsByTime');
});
</script>

<template>
  <NCard :title="title" :bordered="false" class="card-wrapper">
    <template #header-extra>
      <NRadioGroup v-model:value="rankingType" size="small">
        <NRadioButton value="count">{{ $t('page.apps.byCount') }}</NRadioButton>
        <NRadioButton value="time">{{ $t('page.apps.byTime') }}</NRadioButton>
      </NRadioGroup>
    </template>
    <NList>
      <NListItem v-for="(item, index) in rankingData" :key="index">
        <div class="flex justify-between items-center">
          <span>
            <span class="mr-8px">{{ index + 1 }}.</span>
            <a class="text-primary hover:underline cursor-pointer">{{ item.name }}</a>
          </span>
          <span class="font-bold">{{ item.value }}</span>
        </div>
      </NListItem>
    </NList>
  </NCard>
</template>

<style scoped></style>
