<script setup lang="ts">
import { computed, onMounted, ref, watch } from 'vue';
import { useApplicationStore } from '@/store/modules/application';
import { useAppStore } from '@/store/modules/app';
import { fetchStatisticsSummary } from '@/service/api/statistics';
import CardData from './modules/card-data.vue';
import LineChart from './modules/line-chart.vue';
import PieChart from './modules/pie-chart.vue';
import ProjectNews from './modules/project-news.vue';
import CreativityBanner from './modules/creativity-banner.vue';

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
  <NSpace vertical :size="24">
    <CardData :loading="loading" :summary="summaryData" />
    <NGrid :x-gap="gap" :y-gap="16" responsive="screen" item-responsive>
      <NGi span="24 s:24 m:18">
        <NCard :bordered="false" class="card-wrapper">
          <LineChart :summary="summaryData" />
        </NCard>
      </NGi>
      <NGi span="24 s:24 m:6">
        <NCard :bordered="false" class="card-wrapper">
          <PieChart :summary="summaryData" />
        </NCard>
      </NGi>
    </NGrid>
  </NSpace>
</template>

<style scoped></style>
