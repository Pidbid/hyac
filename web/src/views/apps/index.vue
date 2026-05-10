<script setup lang="ts">
import { onMounted, ref, watch } from 'vue';
import { fetchStatisticsSummary } from '@/service/api/statistics';
import { useApplicationStore } from '@/store/modules/application';
import SummaryCard from './modules/SummaryCard.vue';
import TrendChart from './modules/TrendChart.vue';
import RankingList from './modules/RankingList.vue';
import PieChart from './modules/pie-chart.vue';
import FunctionStatusCard from './modules/FunctionStatusCard.vue';
import UnknownRequestCard from './modules/UnknownRequestCard.vue';

const applicationStore = useApplicationStore();
const summaryData = ref<Api.Statistics.Summary | null>(null);
const loading = ref(false);

async function getSummary() {
  if (!applicationStore.appId) return;
  loading.value = true;
  try {
    const { data } = await fetchStatisticsSummary(applicationStore.appId);
    if (data) {
      summaryData.value = data;
    }
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  applicationStore.getApplicationInfo();
  if (applicationStore.appId) {
    getSummary();
  }
});

watch(
  () => applicationStore.appId,
  newValue => {
    if (newValue) {
      getSummary();
    }
  }
);
</script>

<template>
  <div class="apps-page">
    <!-- Row 1: Insight and Summary -->
    <div class="apps-row apps-row-2col">
      <FunctionStatusCard :loading="loading" :summary="summaryData" />
      <UnknownRequestCard :loading="loading" :summary="summaryData" />
    </div>

    <!-- Row 2: Summary -->
    <SummaryCard :loading="loading" :summary="summaryData" />

    <!-- Row 3: Main Trend Chart -->
    <TrendChart :summary="summaryData" />

    <!-- Row 4: Ranking and Pie Chart -->
    <div class="apps-row apps-row-2col">
      <RankingList :summary="summaryData" />
      <PieChart :summary="summaryData" />
    </div>
  </div>
</template>

<style scoped>
.apps-page {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 24px;
  height: 100%;
  overflow: auto;
}

.apps-row {
  display: flex;
  gap: 16px;
}

.apps-row-2col > * {
  flex: 1;
  min-width: 0;
}

@media (max-width: 768px) {
  .apps-page {
    padding: 16px;
  }

  .apps-row-2col {
    flex-direction: column;
  }
}
</style>
