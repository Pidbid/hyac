<script setup lang="ts">
import { computed } from 'vue';
import { NSkeleton } from 'naive-ui';
import { useI18n } from 'vue-i18n';

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
  <div class="apple-card">
    <h3 class="apple-card-title">{{ t('page.apps.unknownRequest.title') }}</h3>
    <div v-if="loading">
      <NSkeleton text :repeat="2" />
    </div>
    <div v-else class="unknown-content">
      <div class="unknown-main">
        <div
          class="unknown-icon-wrap"
          :style="{ background: hasUnknownRequests ? 'rgba(208,48,80,0.08)' : 'rgba(24,160,88,0.08)' }"
        >
          <SvgIcon
            :icon="hasUnknownRequests ? 'mdi:alert-circle-outline' : 'mdi:check-circle-outline'"
            class="text-30px"
            :style="{ color: hasUnknownRequests ? '#d03050' : '#18a058' }"
          />
        </div>
        <div class="unknown-stat">
          <span class="unknown-label">{{ t('page.apps.unknownRequest.label') }}</span>
          <span class="unknown-value" :style="{ color: hasUnknownRequests ? '#d03050' : '#18a058' }">
            {{ unknownRequests }}
          </span>
          <span class="unknown-unit">{{ t('page.apps.unknownRequest.unit') }}</span>
        </div>
      </div>
      <p class="unknown-desc">{{ t('page.apps.unknownRequest.description') }}</p>
    </div>
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

.unknown-content {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.unknown-main {
  display: flex;
  align-items: center;
  gap: 16px;
}

.unknown-icon-wrap {
  width: 56px;
  height: 56px;
  border-radius: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-shrink: 0;
}

.unknown-stat {
  display: flex;
  align-items: baseline;
  gap: 6px;
}

.unknown-label {
  font-size: 14px;
  color: #86868b;
}

.unknown-value {
  font-size: 24px;
  font-weight: 700;
}

.unknown-unit {
  font-size: 13px;
  color: #86868b;
}

.unknown-desc {
  font-size: 13px;
  color: #aeaeb2;
  line-height: 1.4;
}
</style>
