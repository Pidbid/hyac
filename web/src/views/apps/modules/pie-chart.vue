<script setup lang="ts">
import { watch } from 'vue';
import { useAppStore } from '@/store/modules/app';
import { useEcharts } from '@/hooks/common/echarts';
import { $t } from '@/locales';
import { fetchTopFunctions } from '@/service/api/statistics';
import { useRoute } from 'vue-router';

defineOptions({
  name: 'PieChart'
});

const appStore = useAppStore();
const route = useRoute();
const appId = route.query.appId as string;

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
      name: 'Top 5 Functions',
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

async function getChartData() {
  if (!appId) return;
  const { data } = await fetchTopFunctions({ appId });
  if (data) {
    updateOptions(opts => {
      const chartData = data.map(item => ({
        name: item.function_name || 'Unknown',
        value: item.count
      }));

      if (opts.series && opts.series[0]) {
        opts.series[0].data = chartData;
      }

      return opts;
    });
  }
}

watch(
  () => appStore.locale,
  () => {
    updateLocale();
  }
);

getChartData();
</script>

<template>
  <NCard :bordered="false" class="card-wrapper">
    <div ref="domRef" class="h-360px overflow-hidden"></div>
  </NCard>
</template>

<style scoped></style>
