<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { fetchFunctionRequests } from '@/service/api/statistics';
import { useAppStore } from '@/store/modules/app';
import { useApplicationStore } from '@/store/modules/application';
import { useEcharts } from '@/hooks/common/echarts';
import { $t } from '@/locales';

defineOptions({
  name: 'TrendChart'
});

interface Props {
  // eslint-disable-next-line vue/no-unused-properties
  summary: Api.Statistics.Summary | null;
}

defineProps<Props>();

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
  <div class="apple-card">
    <div class="chart-header">
      <h3 class="apple-card-title">{{ $t('page.apps.requestTrend') }}</h3>
      <NRadioGroup v-model:value="timeRange" size="small">
        <NRadioButton :value="1">24H</NRadioButton>
        <NRadioButton :value="7">7 Days</NRadioButton>
        <NRadioButton :value="30">30 Days</NRadioButton>
      </NRadioGroup>
    </div>
    <div ref="domRef" class="h-360px overflow-hidden"></div>
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

.chart-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 16px;
}

.apple-card-title {
  font-size: 15px;
  font-weight: 600;
}
</style>
