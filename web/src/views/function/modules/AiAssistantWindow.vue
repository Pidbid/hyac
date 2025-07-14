<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useDraggable, useStorage } from '@vueuse/core';
import { NInput, NButton, NIcon, NScrollbar, NSpin } from 'naive-ui';
import { CloseOutline, PaperPlaneOutline, SparklesOutline } from '@vicons/ionicons5';
import { useThemeStore } from '@/store/modules/theme';

const props = defineProps<{ show: boolean }>();
const emit = defineEmits(['close']);

const themeStore = useThemeStore();

// --- 持久化位置和尺寸 ---
const initialPos = { x: window.innerWidth - 450, y: 80 };
const savedPosition = useStorage('ai-assistant-position', initialPos);

const windowEl = ref<HTMLElement | null>(null);
const handleEl = ref<HTMLElement | null>(null);
const { x, y, isDragging } = useDraggable(windowEl, {
  initialValue: savedPosition,
  handle: handleEl,
});

// 监听拖动并更新存储
watch(
  () => [x.value, y.value],
  ([newX, newY]) => {
    savedPosition.value = { x: newX, y: newY };
  }
);

const windowStyle = computed(() => ({
  position: 'fixed' as const,
  zIndex: 999,
  left: `${x.value}px`,
  top: `${y.value}px`,
  backgroundColor: themeStore.darkMode ? 'rgb(24, 24, 28)' : '#fff',
  border: `1px solid ${themeStore.darkMode ? 'rgb(42, 42, 46)' : 'rgb(224, 224, 230)'}`,
  color: themeStore.darkMode ? 'rgba(255, 255, 255, 0.82)' : 'rgb(51, 54, 57)',
  resize: 'both' as const,
  overflow: 'hidden',
}));

const headerStyle = computed(() => ({
  cursor: isDragging.value ? 'grabbing' : 'move',
  userSelect: 'none' as const,
}));

// --- 对话逻辑 ---
const isLoading = ref(false);
const userInput = ref('');
const messages = ref([
  { role: 'ai', content: '你好！有什么可以帮助你编写代码的吗？' },
  { role: 'user', content: '请给我一个python hello world的例子' }
]);

const handleSend = async () => {
  if (!userInput.value.trim()) return;
  messages.value.push({ role: 'user', content: userInput.value });
  const userMessage = userInput.value;
  userInput.value = '';
  isLoading.value = true;

  await new Promise(resolve => setTimeout(resolve, 1500));
  const aiResponse = `当然，这里是你需要的 \`Python\` 示例代码：\n\`\`\`python\nprint("Hello, AI Assistant!")\n\`\`\``;

  messages.value.push({ role: 'ai', content: aiResponse });
  isLoading.value = false;
};
</script>

<template>
  <div v-if="props.show" ref="windowEl" :style="windowStyle" class="custom-card">
    <!-- Header -->
    <div ref="handleEl" :style="headerStyle" class="custom-card-header">
      <div class="header-title">
        <NIcon :component="SparklesOutline" class="mr-2" />
        AI 代码助手
      </div>
      <div class="header-actions">
        <NButton quaternary circle size="small" @click="emit('close')">
          <NIcon :component="CloseOutline" />
        </NButton>
      </div>
    </div>

    <!-- Content -->
    <div class="custom-card-content">
      <NScrollbar class="flex-1 pr-2">
        <div v-for="(msg, index) in messages" :key="index" class="message-row" :class="msg.role === 'user' ? 'justify-end' : 'justify-start'">
          <div class="message-bubble" :class="`bubble-${msg.role}`">
            <div style="white-space: pre-wrap;">{{ msg.content }}</div>
          </div>
        </div>
      </NScrollbar>

      <!-- Input -->
      <div class="mt-4">
        <NSpin :show="isLoading">
          <NInput
            v-model:value="userInput"
            type="textarea"
            placeholder="输入你的问题..."
            :autosize="{ minRows: 2, maxRows: 5 }"
            @keydown.enter.prevent="handleSend"
          />
          <NButton type="primary" block class="mt-2" @click="handleSend" :disabled="isLoading">
            发送
            <template #icon>
              <NIcon :component="PaperPlaneOutline" />
            </template>
          </NButton>
        </NSpin>
      </div>
    </div>
  </div>
</template>

<style scoped>
.custom-card {
  width: 400px;
  height: 900px;
  border-radius: 8px;
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
  display: flex;
  flex-direction: column;
  min-width: 300px;
  min-height: 200px;
}

.custom-card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 8px 12px;
  border-bottom: 1px solid;
  border-color: inherit;
  font-weight: 600;
  flex-shrink: 0;
}

.custom-card-content {
  padding: 12px;
  flex-grow: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.message-row {
  display: flex;
  margin-bottom: 12px;
}

.justify-start {
  justify-content: flex-start;
}

.justify-end {
  justify-content: flex-end;
}

.message-bubble {
  padding: 8px 12px;
  border-radius: 8px;
  max-width: 80%;
  word-wrap: break-word;
}

.bubble-ai {
  background-color: #f0f2f5;
  color: #333;
}

.bubble-user {
  background-color: #18a058;
  color: #fff;
}

.dark .bubble-ai {
  background-color: rgb(44, 44, 50);
  color: #fff;
}
</style>
