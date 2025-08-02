<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useApplicationStore } from '@/store/modules/application';
import { useAppStore } from '@/store/modules/app';
import { fetchStatisticsSummary } from '@/service/api/statistics';
import SummaryCard from './modules/SummaryCard.vue';
import TrendChart from './modules/TrendChart.vue';
import RankingList from './modules/RankingList.vue';
import PieChart from './modules/pie-chart.vue';
import FunctionStatusCard from './modules/FunctionStatusCard.vue';
import UnknownRequestCard from './modules/UnknownRequestCard.vue';

const appStore = useAppStore();
const applicationStore = useApplicationStore();
const summaryData = ref<Api.Statistics.Summary | null>(null);
const loading = ref(false);

const gap = computed(() => (appStore.isMobile ? 0 : 16));

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
  <NSpace vertical :size="16">
    <!-- Row 1: Insight and Summary -->
    <NGrid :cols="12" :x-gap="gap" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="12 s:12 m:8">
        <FunctionStatusCard :loading="loading" :summary="summaryData" />
      </NGi>
      <NGi span="12 s:12 m:4">
        <UnknownRequestCard :loading="loading" :summary="summaryData" />
      </NGi>
    </NGrid>

    <!-- Row 2: Summary -->
    <SummaryCard :loading="loading" :summary="summaryData" />

    <!-- Row 3: Main Trend Chart -->
    <TrendChart :summary="summaryData" />

    <!-- Row 3: Ranking and Pie Chart -->
    <NGrid :cols="12" :x-gap="gap" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="12 s:12 m:6">
        <RankingList :summary="summaryData" />
      </NGi>
      <NGi span="12 s:12 m:6">
        <PieChart :summary="summaryData" />
      </NGi>
    </NGrid>
  </NSpace>
</template>

<style scoped></style>
