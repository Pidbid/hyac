<script setup lang="ts">
import { onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor';
import { useMonaco } from 'vue-use-monaco'

const editorContainer = ref<HTMLElement>()
let editor: monaco.editor.IStandaloneCodeEditor | null = null;
const isSettingValue = ref(false);


interface Props {
  modelValue: string;
  height?: number;
  language?: string;
  fontSize?: number;
  minimap: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  language: 'python',
  height: 400,
  fontSize: 16,
  minimap: true,
});
const emit = defineEmits(['update:modelValue']);

const {
  createEditor,
  updateCode,
  setTheme,
  setLanguage,
  getCurrentTheme,
  getEditor,
  getEditorView,
  cleanupEditor
} = useMonaco({
  themes: ['github-dark', 'github-light'],
  languages: ['javascript', 'typescript', 'python', 'vue', 'json'],
  MAX_HEIGHT: 3000,
  readOnly: false,
  isCleanOnBeforeCreate: true,

  onBeforeCreate: (monaco) => {
    console.log('Monaco editor is about to be created', monaco)
    return []
  },

  fontSize: props.fontSize,
  lineNumbers: 'on',
  wordWrap: 'on',
  minimap: { enabled: props.minimap },
  scrollbar: {
    verticalScrollbarSize: 10,
    horizontalScrollbarSize: 10,
    alwaysConsumeMouseWheel: false
  },
  fontFamily: 'Courier New, monospace',
})

onMounted(async () => {
  if (editorContainer.value) {
    editor = await createEditor(
      editorContainer.value,
      props.modelValue,
      'python'
    )
    editor?.onDidChangeModelContent(() => {
      if (isSettingValue.value) return;
      const value = editor!.getValue();
      emit('update:modelValue', value);
    });

    console.log('Editor created:', editor)
  }
})

watch(
  () => props.modelValue,
  (newVal) => {
    if (editor && editor.getValue() !== newVal) {
      const selection = editor.getSelection();
      isSettingValue.value = true;
      editor.setValue(newVal);
      if (selection) {
        editor.setSelection(selection);
      }
      isSettingValue.value = false;
    }
  }
);

watch (
  () => props.fontSize,
  (newVal) => {
    if (editor) {
      console.log('Updating font size to:', newVal);
      editor.updateOptions({ fontSize: newVal });
    }
  }
)

watch (
  () => props.minimap,
  (newVal) => {
    if (editor) {
      console.log('Updating font size to:', newVal);
      editor.updateOptions({ minimap: {enabled: newVal} });
    }
  }
)
</script>

<template>
  <div>
    <div ref="editorContainer" class="editor" />
  </div>
</template>
