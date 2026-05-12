<script setup lang="ts">
import { computed, nextTick, onBeforeUnmount, ref, watch } from 'vue';
import { NButton, NCard, NEmpty, NIcon, NInput, NLog, NScrollbar, NSpace, NTag, useMessage } from 'naive-ui';
import { PauseCircleOutline, PlayCircleOutline, ReloadOutline, TrashOutline } from '@vicons/ionicons5';
import { useI18n } from 'vue-i18n';
import { getAuthorization } from '@/service/request/shared';
import { getServiceBaseUrl } from '@/utils/common';

const props = defineProps<{
  appId?: string | null;
}>();

const { t } = useI18n();
const message = useMessage();

const chunks = ref<string[]>([]);
const search = ref('');
const loading = ref(false);
const connected = ref(false);
const paused = ref(false);
const errorText = ref('');
const scrollbarRef = ref<any>(null);
const abortController = ref<AbortController | null>(null);

const status = computed(() => {
  if (errorText.value) return { type: 'error' as const, text: errorText.value };
  if (loading.value) return { type: 'warning' as const, text: t('page.log.runtimeConnecting') };
  if (connected.value) return { type: 'success' as const, text: t('page.log.runtimeConnected') };
  return { type: 'default' as const, text: t('page.log.runtimeDisconnected') };
});

const logText = computed(() => {
  const text = chunks.value.join('');
  const keyword = search.value.trim().toLowerCase();
  if (!keyword) return text;

  return text
    .split('\n')
    .filter(line => line.toLowerCase().includes(keyword))
    .join('\n');
});

function appendLog(data: string) {
  const normalized = data.endsWith('\n') ? data : `${data}\n`;
  chunks.value = [...chunks.value, normalized].slice(-2000);
}

function buildLogUrl() {
  const baseUrl = getServiceBaseUrl()?.replace(/\/$/, '') || '';
  const params = new URLSearchParams({ tail: '1000' });
  return `${baseUrl}/logs/runtime_stream/${props.appId}?${params.toString()}`;
}

function handleSseBlock(block: string) {
  const lines = block.split(/\r?\n/);
  const dataLines: string[] = [];
  let event = 'message';

  for (const line of lines) {
    if (line.startsWith('event:')) {
      event = line.slice(6).trim();
    } else if (line.startsWith('data:')) {
      dataLines.push(line.slice(5).replace(/^ /, ''));
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

async function scrollToBottom() {
  if (paused.value) return;
  await nextTick();
  scrollbarRef.value?.scrollTo({ top: Number.MAX_SAFE_INTEGER });
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

function stopStream() {
  abortController.value?.abort();
  abortController.value = null;
  connected.value = false;
  loading.value = false;
}

async function startStream() {
  if (!props.appId) {
    message.warning(t('page.log.selectAppFirst'));
    return;
  }

  stopStream();
  loading.value = true;
  errorText.value = '';

  const controller = new AbortController();
  abortController.value = controller;

  try {
    const Authorization = getAuthorization();
    const response = await fetch(buildLogUrl(), {
      headers: Authorization ? { Authorization } : undefined,
      signal: controller.signal
    });

    if (!response.ok || !response.body) {
      throw new Error(`${response.status} ${response.statusText}`);
    }

    connected.value = true;
    loading.value = false;
    await consumeStream(response.body.getReader());
  } catch (error: any) {
    if (error?.name !== 'AbortError') {
      errorText.value = error?.message || String(error);
      message.error(t('page.log.runtimeStreamFailed', { message: errorText.value }));
    }
  } finally {
    if (abortController.value === controller) {
      abortController.value = null;
      connected.value = false;
      loading.value = false;
    }
  }
}

function clearLogs() {
  chunks.value = [];
}

watch(
  () => props.appId,
  () => {
    stopStream();
    chunks.value = [];
    if (props.appId) {
      startStream();
    }
  },
  { immediate: true }
);

watch(logText, scrollToBottom);

onBeforeUnmount(stopStream);
</script>

<template>
  <NCard class="runtime-panel" :bordered="false" :content-style="{ padding: '0px', height: '100%' }">
    <div class="runtime-toolbar">
      <NSpace align="center">
        <NInput
          v-model:value="search"
          :placeholder="t('page.log.runtimeSearch')"
          clearable
          size="small"
          class="runtime-search"
        />
        <NTag :type="status.type" size="small">
          {{ status.text }}
        </NTag>
        <NButton size="small" @click="paused = !paused">
          <template #icon>
            <NIcon :component="paused ? PlayCircleOutline : PauseCircleOutline" />
          </template>
          {{ paused ? t('page.log.resume') : t('page.log.pause') }}
        </NButton>
        <NButton size="small" @click="clearLogs">
          <template #icon>
            <NIcon :component="TrashOutline" />
          </template>
          {{ t('page.log.clear') }}
        </NButton>
        <NButton type="primary" size="small" :loading="loading" @click="startStream">
          <template #icon>
            <NIcon :component="ReloadOutline" />
          </template>
          {{ t('page.log.reconnect') }}
        </NButton>
      </NSpace>
    </div>

    <div class="runtime-log-shell">
      <NScrollbar ref="scrollbarRef" class="runtime-scroll">
        <NLog v-if="logText" :log="logText" :rows="34" class="runtime-log" />
        <NEmpty
          v-else
          :description="loading ? t('page.log.runtimeConnecting') : t('page.log.runtimeEmpty')"
          class="h-full flex-center"
        />
      </NScrollbar>
    </div>
  </NCard>
</template>

<style scoped>
.runtime-panel {
  flex: 1;
  min-height: 0;
  border-radius: 8px;
  overflow: hidden;
  border: 1px solid rgba(0, 0, 0, 0.06);
  background: #ffffff;
}

.runtime-toolbar {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
  background: #f9f9fb;
}

.runtime-search {
  width: 260px;
}

.runtime-log-shell {
  height: calc(100% - 49px);
  min-height: 0;
  background: #0f172a;
}

.runtime-scroll {
  height: 100%;
}

.runtime-log {
  min-height: 100%;
  padding: 12px 14px;
  background: #0f172a;
  color: #dbeafe;
  font-family: 'SF Mono', 'Fira Code', 'JetBrains Mono', monospace;
}

.flex-center {
  display: flex;
  flex-direction: column;
  justify-content: center;
  align-items: center;
}
</style>
