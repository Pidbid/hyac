<script setup lang="ts">
import { watch } from 'vue';
import { useAppStore } from '@/store/modules/app';
import { useEcharts } from '@/hooks/common/echarts';
import { $t } from '@/locales';

defineOptions({
  name: 'PieChart'
});

interface Props {
  summary: Api.Statistics.Summary | null;
}
const props = defineProps<Props>();

const appStore = useAppStore();

const { domRef, updateOptions } = useEcharts(() => ({
  tooltip: {
    trigger: 'item'
  },
  legend: {
    bottom: '1%',
    left: 'center',
    itemStyle: {
      borderWidth: 0
    }
  },
  series: [
    {
      color: ['#5da8ff', '#8e9dff', '#fedc69', '#26deca', '#ff8c9a'],
      name: $t('page.apps.top5Functions'),
      type: 'pie',
      radius: ['45%', '75%'],
      avoidLabelOverlap: false,
      itemStyle: {
        borderRadius: 10,
        borderColor: '#fff',
        borderWidth: 1
      },
      label: {
        show: false,
        position: 'center'
      },
      emphasis: {
        label: {
          show: true,
          fontSize: '12'
        }
      },
      labelLine: {
        show: false
      },
      data: [] as { name: string; value: number }[]
    }
  ]
}));

function updateLocale() {
  updateOptions((opts, factory) => {
    const originOpts = factory();
    opts.series[0].name = originOpts.series[0].name;
    // Note: Data is now dynamic, so locale change might not need to re-mock data.
    // If labels are from $t, they will update automatically.
    return opts;
  });
}

function updateChartData() {
  if (!props.summary) return;

  const data = props.summary.functions.ranking_by_count || [];
  const chartData = data.map(item => ({
    name: item.function_name || $t('page.apps.unknown'),
    value: item.count
  }));

  updateOptions(opts => {
    if (opts.series && opts.series[0]) {
      opts.series[0].data = chartData;
    }
    return opts;
  });
}

watch(
  () => appStore.locale,
  () => {
    updateLocale();
  }
);

watch(() => props.summary, updateChartData, { deep: true });
</script>

<template>
  <div class="apple-card">
    <h3 class="apple-card-title">{{ $t('page.apps.top5Functions') }}</h3>
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

.apple-card-title {
  font-size: 15px;
  font-weight: 600;
  margin-bottom: 16px;
}
</style>
