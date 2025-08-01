<script setup lang="ts">
import { ref, watch, computed } from 'vue';
import { useAppStore } from '@/store/modules/app';
import { useEcharts } from '@/hooks/common/echarts';
import { $t } from '@/locales';
import { fetchFunctionRequests } from '@/service/api/statistics';
import { useApplicationStore } from '@/store/modules/application';

defineOptions({
  name: 'TrendChart'
});

interface Props {
  summary: Api.Statistics.Summary | null;
}

const props = defineProps<Props>();

const appStore = useAppStore();
const applicationStore = useApplicationStore();
const appId = computed(() => applicationStore.appId);
const timeRange = ref(7); // Default to 7 days

const { domRef, updateOptions } = useEcharts(() => ({
  tooltip: {
    trigger: 'axis',
    axisPointer: {
      type: 'cross',
      label: {
        backgroundColor: '#6a7985'
      }
    }
  },
  legend: {
    data: [$t('page.apps.requestCount')]
  },
  grid: {
    left: '3%',
    right: '4%',
    bottom: '3%',
    containLabel: true
  },
  xAxis: {
    type: 'category',
    boundaryGap: false,
    data: [] as string[]
  },
  yAxis: {
    type: 'value'
  },
  series: [
    {
      color: '#8e9dff',
      name: $t('page.apps.requestCount'),
      type: 'line',
      smooth: true,
      stack: 'Total',
      areaStyle: {
        color: {
          type: 'linear',
          x: 0,
          y: 0,
          x2: 0,
          y2: 1,
          colorStops: [
            {
              offset: 0.25,
              color: '#8e9dff'
            },
            {
              offset: 1,
              color: '#fff'
            }
          ]
        }
      },
      emphasis: {
        focus: 'series'
      },
      data: [] as number[]
    }
  ]
}));

async function getChartData() {
  if (!appId.value) return;
  const { data } = await fetchFunctionRequests(appId.value, timeRange.value);
  if (data) {
    updateOptions(opts => {
      opts.xAxis.data = data.map(item => item.date);
      opts.series[0].data = data.map(item => item.count);
      return opts;
    });
  }
}

watch(
  () => appStore.locale,
  () => {
    updateOptions((opts, factory) => {
      const originOpts = factory();
      opts.legend.data = originOpts.legend.data;
      opts.series[0].name = originOpts.series[0].name;
      return opts;
    });
  }
);

watch([appId, timeRange], getChartData, { immediate: true });
</script>

<template>
  <NCard :title="$t('page.apps.requestTrend')" :bordered="false" class="card-wrapper">
    <template #header-extra>
      <NRadioGroup v-model:value="timeRange" size="small">
        <NRadioButton :value="1">24H</NRadioButton>
        <NRadioButton :value="7">7 Days</NRadioButton>
        <NRadioButton :value="30">30 Days</NRadioButton>
      </NRadioGroup>
    </template>
    <div ref="domRef" class="h-360px overflow-hidden"></div>
  </NCard>
</template>

<style scoped></style>
