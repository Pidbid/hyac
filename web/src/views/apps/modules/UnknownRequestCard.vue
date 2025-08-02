<script setup lang="ts">
import { computed } from 'vue';
import { useI18n } from 'vue-i18n';
import { NCard, NStatistic, NText, NIcon, NSkeleton, NSpace } from 'naive-ui';

interface Props {
  loading: boolean;
  summary: Api.Statistics.Summary | null;
}

const props = defineProps<Props>();
const { t } = useI18n();

const unknownRequests = computed(() => {
  return props.summary?.functions.requests.unknown ?? 0;
});

const hasUnknownRequests = computed(() => unknownRequests.value > 0);
</script>

<template>
  <NCard :title="t('page.apps.unknownRequest.title')">
    <div v-if="loading">
      <NSkeleton text :repeat="2" />
    </div>
    <div v-else>
      <NSpace align="center">
        <SvgIcon
          :icon="hasUnknownRequests ? 'mdi:alert-circle-outline' : 'mdi:check-circle-outline'"
          class="text-40px"
          :style="{ color: hasUnknownRequests ? '#d03050' : '#18a058' }"
        />
        <NStatistic>
          <template #label>
            <NText>{{ t('page.apps.unknownRequest.label') }}</NText>
          </template>
          <span :style="{ color: hasUnknownRequests ? '#d03050' : '#18a058' }">
            {{ unknownRequests }}
          </span>
          <template #suffix>
            <span>{{ t('page.apps.unknownRequest.unit') }}</span>
          </template>
        </NStatistic>
      </NSpace>
      <NText :depth="3" class="mt-2 block">
        {{ t('page.apps.unknownRequest.description') }}
      </NText>
    </div>
  </NCard>
</template>

<style scoped>
.block {
  display: block;
}
.mt-2 {
  margin-top: 0.5rem;
}
</style>
