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
  <NCard :title="t('page.apps.requestCount')" :bordered="false" class="card-wrapper h-full">
    <NSpin :show="loading">
      <NGrid :cols="4" :x-gap="16">
        <NGi v-for="(item, index) in stats" :key="index" class="flex-col-center">
          <SvgIcon :icon="item.icon" class="text-32px" :class="item.color" />
          <p class="text-xl font-bold mt-4px">{{ item.value }}</p>
          <p class="text-gray-500">{{ item.label }}</p>
        </NGi>
      </NGrid>
    </NSpin>
  </NCard>
</template>

<style scoped></style>
