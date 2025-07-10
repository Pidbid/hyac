<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import * as monaco from 'monaco-editor';
import JsonWorker from 'monaco-editor/esm/vs/language/json/json.worker?worker';

window.MonacoEnvironment = {
  getWorker(_workerId: any, label: string) {
    return new JsonWorker();
  },
};
interface Props {
  modelValue: string;
  height?: number;
}

const props = withDefaults(defineProps<Props>(), {
  readOnly: false,
  height: 400, // 设置 height 的默认值
});



const emit = defineEmits(['update:modelValue']); // 移除 update:height 事件

const editorRef = ref<HTMLElement | null>(null);
let editorInstance: monaco.editor.IStandaloneCodeEditor | null = null;

const initMonaco = () => {
  if (editorRef.value) {
    editorInstance = monaco.editor.create(editorRef.value, {
      value: props.modelValue,
      language: "json",
      readOnly: false,
      minimap: { enabled: false },
      fontSize: 14,
      tabSize: 2,
      insertSpaces: true,
      scrollBeyondLastLine: false,
      wordWrap: 'on',
      lineNumbers: 'off',
      automaticLayout: true,
      fontFamily: 'Courier New, monospace',
    });

    editorInstance.onDidChangeModelContent(() => {
      emit('update:modelValue', editorInstance?.getValue() || '');
    });
  }
};

watch(
  () => [props.fontSize, props.tabSize],
  () => {
    if (editorInstance) {
      editorInstance.updateOptions({
        fontSize: props.fontSize,
        tabSize: props.tabSize,
      });
    }
  },
);

watch(
  () => props.modelValue,
  (value) => {
    // 防止改变编辑器内容时光标重定向
    if (value !== editorInstance?.getValue()) {
      editorInstance?.setValue(value);
    }
  },
);

// 监听 height prop 变化，手动触发布局
watch(
  () => props.height,
  newHeight => {
    if (editorInstance && newHeight !== undefined) {
      editorInstance.layout();
    }
  }
);

onMounted(() => {
  initMonaco();
});

onBeforeUnmount(() => {
  if (editorInstance) {
    editorInstance.dispose();
  }
});

</script>

<template>
  <div ref="editorRef" :style="{ height: height ? `${height}px` : '100%' }"></div>
</template>

<style scoped>
/* 可以添加一些样式，如果需要的话 */
</style>
