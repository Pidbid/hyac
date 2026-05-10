<script setup lang="ts">
import { computed, ref } from 'vue';
import { NIcon, NTooltip } from 'naive-ui';
import { EaselOutline, ReaderOutline, TerminalOutline } from '@vicons/ionicons5';
import { $t } from '@/locales';

const props = defineProps<{
  logs: readonly Api.Function.FunctionLogsInfo[];
}>();

const logFilter = ref<Api.Function.LogType | 'all'>('all');

const filteredLogs = computed(() => {
  return props.logs.filter((log: Api.Function.FunctionLogsInfo) => {
    if (logFilter.value === 'all') return true;
    return log.logtype === logFilter.value;
  });
});

const getLogLevelStyle = (level: string) => {
  switch (level) {
    case 'error':
      return 'level-error';
    case 'warn':
      return 'level-warn';
    case 'info':
      return 'level-info';
    case 'debug':
      return 'level-debug';
    default:
      return 'level-default';
  }
};
</script>

<template>
  <div class="log-panel">
    <div class="log-header">
      <h3 class="log-title">
        <NIcon :component="TerminalOutline" :size="15" />
        <span>{{ $t('page.function.log') }}</span>
      </h3>
      <div class="log-filters">
        <NTooltip trigger="hover">
          <template #trigger>
            <button class="filter-btn" :class="{ active: logFilter === 'all' }" @click="logFilter = 'all'">
              <NIcon :component="TerminalOutline" :size="14" />
            </button>
          </template>
          {{ $t('page.function.allLogs') }}
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <button class="filter-btn" :class="{ active: logFilter === 'function' }" @click="logFilter = 'function'">
              <NIcon :component="EaselOutline" :size="14" />
            </button>
          </template>
          {{ $t('page.function.functionLogs') }}
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <button class="filter-btn" :class="{ active: logFilter === 'system' }" @click="logFilter = 'system'">
              <NIcon :component="ReaderOutline" :size="14" />
            </button>
          </template>
          {{ $t('page.function.systemLogs') }}
        </NTooltip>
      </div>
    </div>
    <div class="log-content">
      <div v-for="log in filteredLogs" :key="log._id" class="log-entry">
        <span class="log-time">{{ log.timestamp }}</span>
        <span v-if="log.logtype === 'function'" class="log-level" :class="getLogLevelStyle(log.level)">
          {{ log.level }}
        </span>
        <span v-if="log.logtype === 'system'" class="log-level level-system">{{ log.level }}(sys)</span>
        <span class="log-message" :class="{ 'system-message': log.logtype === 'system' }">
          {{ log.message }}
        </span>
      </div>
      <div v-if="filteredLogs.length === 0" class="empty-logs">
        <div class="empty-icon">
          <NIcon :component="TerminalOutline" :size="32" />
        </div>
        <p>{{ $t('page.function.noLogs') }}</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.log-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 12px;
  border: 1px solid rgba(0, 0, 0, 0.06);
  overflow: hidden;
}

.log-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #f9f9fb;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.log-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 12px;
  font-weight: 600;
  color: #1d1d1f;
  margin: 0;
}

.log-filters {
  display: flex;
  gap: 4px;
  padding: 2px;
  background: #f0f0f2;
  border-radius: 6px;
}

.filter-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 4px;
  background: transparent;
  color: #6e6e73;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.filter-btn:hover {
  color: #1d1d1f;
}

.filter-btn.active {
  background: #ffffff;
  color: #007aff;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.log-content {
  flex: 1;
  overflow-y: auto;
  padding: 8px;
  font-family: 'SF Mono', 'Fira Code', monospace;
}

.log-content::-webkit-scrollbar {
  width: 6px;
}

.log-content::-webkit-scrollbar-track {
  background: transparent;
}

.log-content::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 3px;
}

.log-entry {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 6px 8px;
  border-radius: 6px;
  transition: background 0.15s ease;
}

.log-entry:hover {
  background: #f5f5f7;
}

.log-time {
  font-size: 11px;
  color: #6e6e73;
  white-space: nowrap;
  flex-shrink: 0;
}

.log-level {
  font-size: 10px;
  font-weight: 600;
  padding: 1px 6px;
  border-radius: 4px;
  text-transform: uppercase;
  flex-shrink: 0;
}

.level-error {
  background: rgba(255, 59, 48, 0.15);
  color: #d70015;
}

.level-warn {
  background: rgba(255, 149, 0, 0.15);
  color: #b25000;
}

.level-info {
  background: rgba(0, 122, 255, 0.15);
  color: #0066cc;
}

.level-debug {
  background: rgba(142, 142, 147, 0.15);
  color: #8e8e93;
}

.level-system {
  background: rgba(52, 199, 89, 0.15);
  color: #248a3d;
}

.level-default {
  background: rgba(142, 142, 147, 0.1);
  color: #8e8e93;
}

.log-message {
  font-size: 12px;
  color: #1d1d1f;
  word-break: break-all;
  line-height: 1.5;
}

.log-message.system-message {
  color: #515154;
}

.empty-logs {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: #6e6e73;
}

.empty-icon {
  margin-bottom: 12px;
  opacity: 0.5;
}

.empty-logs p {
  font-size: 13px;
  font-family: -apple-system, BlinkMacSystemFont, 'SF Pro Text', 'Helvetica Neue', sans-serif;
  margin: 0;
}
</style>
