<script setup lang="ts">
import { ref, watch, nextTick, onMounted, onBeforeUnmount } from 'vue';
import { NCard, NButton, NIcon } from 'naive-ui';
import { CheckmarkOutline, SaveOutline, InformationCircleOutline, BrushOutline } from '@vicons/ionicons5';
import Editor from './editor.vue'; // 假设 editor.vue 在同一目录下

interface editorConfigT {
  language: string;
  fontSize: number;
  minimap: boolean;
}

const props = defineProps<{
  func: Api.Function.FunctionInfo;
  codeChanged: boolean;
  editorConfig:editorConfigT;
  theme: 'github-light' | 'github-dark';
}>();

const emit = defineEmits(['save-code', 'open-history', 'update:code', 'open-editor-settings']);

const editorFullRef = ref<HTMLElement | null>(null);
const editorHeight = ref(0);

const editorConfig = ref({
  language: 'python',
  fontSize: 14,
  minimap: true,
  theme: 'github-light'
});

const updateEditorHeight = () => {
  if (editorFullRef.value) {
    // 减去顶部和底部间距, 这里的 40 是 NCard header 的高度
    editorHeight.value = editorFullRef.value.clientHeight - 40;
  }
};

onMounted(() => {
  nextTick(() => {
    updateEditorHeight();
  });
  window.addEventListener('resize', updateEditorHeight);
});

onBeforeUnmount(() => {
  window.removeEventListener('resize', updateEditorHeight);
});

watch(() => props.func, () => {
  nextTick(() => {
    updateEditorHeight();
  });
});

</script>

<template>
  <NCard :title="func.name || '函数编辑区域'" :bordered="false" size="small" class="h-full flex-1"
    :content-style="{ padding: '0px', display: 'flex', flexDirection: 'column' }">
    <template #header-extra>
      <div class="flex flex-row gap-2">
        <NButton v-if="codeChanged" type="primary" size="small" @click="emit('save-code')">
          <template #icon>
            <NIcon :component="CheckmarkOutline" />
          </template>
          发布
        </NButton>
        <NButton v-else type="default" size="small" disabled>
          <template #icon>
            <NIcon :component="SaveOutline" />
          </template>
          已发布
        </NButton>
        <NButton type="default" size="small" @click="emit('open-history')">
          <template #icon>
            <NIcon :component="InformationCircleOutline" />
          </template>
        </NButton>
        <NButton type="default" size="small" @click="emit('open-editor-settings')">
          <template #icon>
            <NIcon :component="BrushOutline" />
          </template>
        </NButton>
      </div>
    </template>
    <div ref="editorFullRef" class="flex-1 min-h-0 overflow-hidden p-4">
      <Editor :model-value="func.code" @update:modelValue="$emit('update:code', $event)" :height="editorHeight"
        :language="props.editorConfig.language" :font-size="props.editorConfig.fontSize" :minimap="props.editorConfig.minimap" :theme="props.editorConfig.theme" />
    </div>
  </NCard>
</template>

<style scoped>
</style>
