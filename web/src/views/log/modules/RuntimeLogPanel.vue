<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { NButton, NCard, NEmpty, NIcon, NInput, NScrollbar, NTag, NTooltip, useMessage } from 'naive-ui';
import {
  ChevronDownOutline,
  ChevronUpOutline,
  PauseCircleOutline,
  PlayCircleOutline,
  TrashOutline
} from '@vicons/ionicons5';
import { useI18n } from 'vue-i18n';
import { getAuthorization } from '@/service/request/shared';
import { getServiceBaseUrl } from '@/utils/common';

const LOG_ENTRY_LIMIT = 4000;
const timestampedLogLinePattern = /^\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3}\s+\|\s+[A-Z]+\s+\|/;
const logCache = new Map<string, string[]>();

const props = defineProps<{
  appId?: string | null;
  funcId?: string | null;
  tail?: number;
  title?: string;
  compact?: boolean;
}>();

const emit = defineEmits<{
  collapse: [];
  expand: [];
}>();

const { t } = useI18n();
const message = useMessage();

const logEntries = ref<string[]>([]);
const search = ref('');
const loading = ref(false);
const connected = ref(false);
const paused = ref(false);
const pendingChunks = ref<string[]>([]);
const errorText = ref('');
const scrollbarRef = ref<any>(null);
const abortController = ref<AbortController | null>(null);
const reconnectTimer = ref<number | null>(null);
const reconnectAttempts = ref(0);
const manualStop = ref(false);
const panelTitle = computed(() => props.title || t('page.function.log'));

const cacheKey = computed(() => `${props.appId || 'unknown'}:${props.funcId || 'all'}`);

const statusDot = computed(() => {
  if (connected.value) {
    return { className: 'is-connected', label: t('page.log.runtimeConnected') };
  }

  if (loading.value || reconnectTimer.value !== null) {
    return { className: 'is-reconnecting', label: t('page.log.runtimeReconnecting') };
  }

  if (errorText.value) {
    return { className: 'is-error', label: errorText.value };
  }

  return { className: 'is-idle', label: t('page.log.runtimeDisconnected') };
});

const displayEntries = computed(() => [...logEntries.value].reverse().map(formatLogEntry));

const visibleText = computed(() => {
  const keyword = search.value.trim().toLowerCase();
  if (!keyword) {
    return displayEntries.value.join('\n');
  }

  return displayEntries.value.filter(entry => entry.toLowerCase().includes(keyword)).join('\n');
});

const lineCount = computed(() => {
  if (!visibleText.value) return 0;
  return visibleText.value.split('\n').length;
});

const latestLine = computed(() => {
  const latest = [...logEntries.value].reverse().find(entry => entry.trim());
  if (latest) return formatLogEntry(latest).split('\n').find(line => line.trim()) || '';
  if (loading.value) return t('page.log.runtimeConnecting');
  return t('page.log.runtimeEmpty');
});

const currentFilterLabel = computed(() => {
  if (props.funcId) {
    return `${t('page.log.function')}: ${props.funcId}`;
  }
  return t('page.log.allFunctions');
});

function buildLogUrl(tail: number) {
  const baseUrl = getServiceBaseUrl()?.replace(/\/$/, '') || '';
  const params = new URLSearchParams({ tail: String(tail) });
  if (props.funcId) {
    params.set('func_id', props.funcId);
  }
  return `${baseUrl}/logs/runtime_stream/${props.appId}?${params.toString()}`;
}

function clearReconnectTimer() {
  if (reconnectTimer.value !== null) {
    window.clearTimeout(reconnectTimer.value);
    reconnectTimer.value = null;
  }
}

function normalizeChunk(data: string) {
  return data.replace(/\r\n/g, '\n').replace(/\r/g, '\n').trimEnd();
}

function formatLogLine(line: string) {
  return line.replace(
    /^(\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}:\d{2}\.\d{3})\s+\|\s+([A-Z]+)\s+\|\s+[^|]*?\s+-\s+(?:\[func:[^\]]+\]\s*)?/,
    '$1 | $2 | '
  );
}

function formatLogEntry(entry: string) {
  return entry.split('\n').map(formatLogLine).join('\n');
}

function mergeLogChunk(entries: string[], data: string) {
  const normalized = normalizeChunk(data);
  if (!normalized) return entries;

  const nextEntries = [...entries];

  for (const line of normalized.split('\n')) {
    if (timestampedLogLinePattern.test(line) || nextEntries.length === 0) {
      nextEntries.push(line);
    } else {
      nextEntries[nextEntries.length - 1] = `${nextEntries[nextEntries.length - 1]}\n${line}`;
    }
  }

  return nextEntries.slice(-LOG_ENTRY_LIMIT);
}

function appendLog(data: string) {
  const normalized = normalizeChunk(data);
  if (!normalized) return;

  if (paused.value) {
    pendingChunks.value = [...pendingChunks.value, normalized].slice(-LOG_ENTRY_LIMIT);
    return;
  }

  logEntries.value = mergeLogChunk(logEntries.value, normalized);
  logCache.set(cacheKey.value, logEntries.value);
}

function handleSseBlock(block: string) {
  const rows = block.split(/\r?\n/);
  const dataLines: string[] = [];
  let event = 'message';

  for (const row of rows) {
    if (row.startsWith('event:')) {
      event = row.slice(6).trim();
    } else if (row.startsWith('data:')) {
      dataLines.push(row.slice(5).replace(/^ /, ''));
    }
  }

  const data = dataLines.join('\n');
  if (!data) return;

  if (event === 'error') {
    errorText.value = data;
    return;
  }

  appendLog(data);
}

async function scrollToTop() {
  if (paused.value) return;
  await nextTick();
  scrollbarRef.value?.scrollTo({ top: 0 });
}

function stopStream() {
  abortController.value?.abort();
  abortController.value = null;
  connected.value = false;
  loading.value = false;
}

function scheduleReconnect() {
  if (manualStop.value || !props.appId) return;
  clearReconnectTimer();
  reconnectAttempts.value += 1;
  const delay = Math.min(5000, 1000 * reconnectAttempts.value);
  reconnectTimer.value = window.setTimeout(() => {
    startStream({ preserveLogs: true, isReconnect: true });
  }, delay);
}

async function consumeStream(reader: ReadableStreamDefaultReader<Uint8Array>) {
  const decoder = new TextDecoder();
  let buffer = '';

  while (true) {
    const { done, value } = await reader.read();
    if (done) break;

    buffer += decoder.decode(value, { stream: true });
    const blocks = buffer.split(/\r?\n\r?\n/);
    buffer = blocks.pop() || '';
    blocks.forEach(handleSseBlock);
  }

  if (buffer.trim()) {
    handleSseBlock(buffer);
  }
}

async function startStream(options?: { preserveLogs?: boolean; isReconnect?: boolean; tail?: number }) {
  if (!props.appId) {
    message.warning(t('page.log.selectAppFirst'));
    return;
  }

  const preserveLogs = options?.preserveLogs ?? false;
  const isReconnect = options?.isReconnect ?? false;

  manualStop.value = false;
  stopStream();
  clearReconnectTimer();
  loading.value = true;
  errorText.value = '';
  if (!preserveLogs) {
    logEntries.value = [];
    reconnectAttempts.value = 0;
  }

  const controller = new AbortController();
  abortController.value = controller;

  try {
    const Authorization = getAuthorization();
    const response = await fetch(buildLogUrl(isReconnect ? 0 : (options?.tail ?? props.tail ?? 0)), {
      headers: Authorization ? { Authorization } : undefined,
      signal: controller.signal
    });

    if (!response.ok || !response.body) {
      throw new Error(`${response.status} ${response.statusText}`);
    }

    connected.value = true;
    loading.value = false;
    errorText.value = '';
    if (!isReconnect) {
      reconnectAttempts.value = 0;
    }
    await consumeStream(response.body.getReader());
    if (!controller.signal.aborted) {
      connected.value = false;
      errorText.value = t('page.log.runtimeDisconnected');
      scheduleReconnect();
    }
  } catch (error: any) {
    if (error?.name !== 'AbortError') {
      connected.value = false;
      errorText.value = error?.message || String(error);
      scheduleReconnect();
    }
  } finally {
    if (abortController.value === controller) {
      abortController.value = null;
      loading.value = false;
    }
  }
}

function clearLogs() {
  logEntries.value = [];
  pendingChunks.value = [];
  logCache.delete(cacheKey.value);
}

function togglePaused() {
  paused.value = !paused.value;
  if (!paused.value && pendingChunks.value.length > 0) {
    logEntries.value = pendingChunks.value.reduce(mergeLogChunk, logEntries.value);
    pendingChunks.value = [];
    logCache.set(cacheKey.value, logEntries.value);
  }
}

watch(
  () => [props.appId, props.funcId],
  () => {
    clearReconnectTimer();
    stopStream();
    const cachedEntries = logCache.get(cacheKey.value) || [];
    logEntries.value = cachedEntries;
    pendingChunks.value = [];
    reconnectAttempts.value = 0;
    if (props.appId) {
      startStream({ preserveLogs: true, tail: cachedEntries.length > 0 ? 0 : (props.tail ?? 0) });
    }
  },
  { immediate: true }
);

watch(visibleText, scrollToTop);

onBeforeUnmount(() => {
  manualStop.value = true;
  clearReconnectTimer();
  stopStream();
});
</script>

<template>
  <NCard
    class="runtime-panel"
    :class="{ compact: compact }"
    :bordered="false"
    :content-style="{ padding: '0px', height: '100%', display: 'flex', flexDirection: 'column' }"
  >
    <div v-if="!compact" class="runtime-toolbar">
      <div class="toolbar-main">
        <div class="toolbar-title">
          <span class="title-text">{{ panelTitle }}</span>
          <NTooltip trigger="hover">
            <template #trigger>
              <span class="status-dot" :class="statusDot.className" :aria-label="statusDot.label" role="status" />
            </template>
            {{ statusDot.label }}
          </NTooltip>
        </div>
        <div class="toolbar-actions">
          <div class="toolbar-meta">
            <NTag size="small" type="info" round class="meta-pill">
              {{ currentFilterLabel }}
            </NTag>
            <span class="line-count">{{ t('page.log.entryCount', { count: lineCount }) }}</span>
          </div>
          <NInput
            v-model:value="search"
            :placeholder="t('page.log.runtimeSearch')"
            clearable
            size="small"
            class="runtime-search"
          />
          <NTooltip trigger="hover">
            <template #trigger>
              <NButton quaternary circle size="small" @click="togglePaused">
                <NIcon :component="paused ? PlayCircleOutline : PauseCircleOutline" />
              </NButton>
            </template>
            {{ paused ? t('page.log.resume') : t('page.log.pause') }}
          </NTooltip>
          <NTooltip trigger="hover">
            <template #trigger>
              <NButton quaternary circle size="small" @click="clearLogs">
                <NIcon :component="TrashOutline" />
              </NButton>
            </template>
            {{ t('page.log.clear') }}
          </NTooltip>
          <NTooltip trigger="hover">
            <template #trigger>
              <NButton quaternary circle size="small" class="collapse-trigger" @click="emit('collapse')">
                <NIcon :component="ChevronDownOutline" />
              </NButton>
            </template>
            {{ t('icon.collapseLog') }}
          </NTooltip>
        </div>
      </div>
    </div>

    <div v-if="!compact" class="runtime-log-shell">
      <NScrollbar ref="scrollbarRef" class="runtime-scroll">
        <pre v-if="visibleText" class="runtime-log-text">{{ visibleText }}</pre>
        <div v-else class="runtime-empty">
          <NEmpty :description="loading ? t('page.log.runtimeConnecting') : t('page.log.runtimeEmpty')" />
        </div>
      </NScrollbar>
    </div>

    <div v-else class="runtime-collapsed-bar">
      <span class="collapsed-preview">{{ latestLine }}</span>
      <NTooltip trigger="hover">
        <template #trigger>
          <NButton quaternary circle size="small" @click="emit('expand')">
            <NIcon :component="ChevronUpOutline" />
          </NButton>
        </template>
        {{ t('icon.expand') }}
      </NTooltip>
    </div>
  </NCard>
</template>

<style scoped>
.runtime-panel {
  display: flex;
  flex-direction: column;
  flex: 1;
  height: 100%;
  min-height: 0;
  border-radius: 18px;
  overflow: hidden;
  border: 1px solid rgba(148, 163, 184, 0.18);
  background: radial-gradient(
    circle at top left,
    rgba(255, 255, 255, 0.96),
    rgba(245, 247, 251, 0.9) 52%,
    rgba(239, 244, 250, 0.95) 100%
  );
  box-shadow:
    0 18px 40px rgba(15, 23, 42, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
  transition:
    border-radius 350ms cubic-bezier(0.175, 0.885, 0.32, 1.1),
    box-shadow 350ms cubic-bezier(0.175, 0.885, 0.32, 1.1),
    transform 350ms cubic-bezier(0.175, 0.885, 0.32, 1.1),
    opacity 300ms ease;
}

.runtime-panel.compact {
  border-radius: 14px;
  transform: translateY(0);
  box-shadow:
    0 10px 24px rgba(15, 23, 42, 0.06),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.runtime-toolbar {
  flex: none;
  padding: 12px 16px;
  border-bottom: 1px solid rgba(148, 163, 184, 0.14);
  background: rgba(255, 255, 255, 0.74);
  backdrop-filter: blur(18px);
}

.toolbar-main {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}

.toolbar-title {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.title-text {
  font-size: 14px;
  font-weight: 700;
  color: #0f172a;
}

.toolbar-actions {
  display: flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
}

.toolbar-meta {
  display: flex;
  align-items: center;
  gap: 8px;
}

.line-count {
  font-size: 12px;
  color: #64748b;
  white-space: nowrap;
  font-variant-numeric: tabular-nums;
}

.runtime-search {
  width: 216px;
}

.runtime-log-shell {
  flex: 1;
  min-height: 0;
  background: transparent;
  animation: runtime-panel-in 350ms cubic-bezier(0.175, 0.885, 0.32, 1.1);
}

.runtime-scroll {
  height: 100%;
}

.runtime-scroll :deep(.n-scrollbar-content) {
  height: 100%;
}

.runtime-log-text {
  margin: 0;
  min-height: 100%;
  padding: 12px 16px 18px;
  background: transparent;
  color: #0f172a;
  white-space: pre-wrap;
  word-break: break-word;
  line-height: 1.62;
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
}

.runtime-empty {
  height: 100%;
  min-height: 180px;
  display: flex;
  align-items: center;
  justify-content: center;
  background: transparent;
}

.runtime-collapsed-bar {
  flex: 1;
  display: flex;
  align-items: center;
  gap: 12px;
  min-height: 44px;
  padding: 8px 12px;
  background: rgba(255, 255, 255, 0.52);
  backdrop-filter: blur(14px);
  animation: runtime-bar-in 350ms cubic-bezier(0.175, 0.885, 0.32, 1.1);
}

.collapsed-preview {
  flex: 1;
  min-width: 0;
  overflow: hidden;
  color: #334155;
  font-size: 12px;
  line-height: 1.5;
  white-space: nowrap;
  text-overflow: ellipsis;
  font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
  font-variant-numeric: tabular-nums;
}

.meta-pill {
  border-color: transparent;
}

.collapse-trigger {
  opacity: 0.78;
}

.collapse-trigger:hover {
  opacity: 1;
}

.status-dot {
  flex: none;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  background: #cbd5e1;
  box-shadow: 0 0 0 4px rgba(203, 213, 225, 0.28);
}

.status-dot.is-connected {
  background: #22c55e;
  box-shadow: 0 0 0 4px rgba(34, 197, 94, 0.18);
}

.status-dot.is-error {
  background: #ef4444;
  box-shadow: 0 0 0 4px rgba(239, 68, 68, 0.16);
}

.status-dot.is-reconnecting {
  background: #f59e0b;
  box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.16);
  animation: runtime-pulse 1.2s ease-in-out infinite;
}

@keyframes runtime-pulse {
  0%,
  100% {
    opacity: 1;
    transform: scale(1);
    box-shadow: 0 0 0 4px rgba(245, 158, 11, 0.16);
  }

  50% {
    opacity: 0.55;
    transform: scale(0.9);
    box-shadow: 0 0 0 7px rgba(245, 158, 11, 0.08);
  }
}

@keyframes runtime-panel-in {
  from {
    opacity: 0;
    transform: translateY(8px) scale(0.98);
  }

  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@keyframes runtime-bar-in {
  from {
    opacity: 0;
    transform: translateY(6px) scale(0.98);
  }

  to {
    opacity: 1;
    transform: translateY(0) scale(1);
  }
}

@media (prefers-reduced-motion: reduce) {
  .runtime-panel,
  .runtime-log-shell,
  .runtime-collapsed-bar {
    animation: none;
    transition: none;
  }
}

@media (max-width: 900px) {
  .toolbar-main {
    flex-direction: column;
    align-items: stretch;
  }

  .toolbar-actions {
    flex-wrap: wrap;
  }

  .runtime-search {
    width: 100%;
  }
}
</style>
