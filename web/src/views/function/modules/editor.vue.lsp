<script setup lang="ts">
import type { MonacoLanguage, MonacoTheme } from 'vue-use-monaco'
import { onMounted, ref, watch } from 'vue'
import * as monaco from 'monaco-editor';
import { useMonaco } from 'vue-use-monaco'


// language server protocol start
// VSCode API & 扩展服务
import { initialize } from '@codingame/monaco-vscode-api';

// @ts-ignore
import getLanguagesServiceOverride from '@codingame/monaco-vscode-languages-service-override';
// @ts-ignore
import getThemeServiceOverride from '@codingame/monaco-vscode-theme-service-override';
// @ts-ignore
import getTextMateServiceOverride from '@codingame/monaco-vscode-textmate-service-override';
// @ts-ignore
import '@codingame/monaco-vscode-python-default-extension';
// @ts-ignore
import '@codingame/monaco-vscode-theme-defaults-default-extension';
// language server protocol end

// LSP 相关
import { MonacoLanguageClient } from 'monaco-languageclient';
import { toSocket, WebSocketMessageReader, WebSocketMessageWriter } from 'vscode-ws-jsonrpc';
import ReconnectingWebSocket from 'reconnecting-websocket';

const editorContainer = ref<HTMLElement>()
let editor: monaco.editor.IStandaloneCodeEditor | null = null;
const isSettingValue = ref(false);


interface Props {
  modelValue: string;
  height?: number;
  language?: string;
  fontSize?: number;
  tabSize: number;
  minimap: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  language: 'python',
  height: 400,
  fontSize: 16,
  tabSize: 4,
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
  // 主题配置 - 至少需要两个主题（暗色/亮色）
  themes: ['github-dark', 'github-light'],

  // 支持的语言列表
  languages: ['python', 'json'],

  // 编辑器最大高度
  MAX_HEIGHT: 500,

  // 是否只读
  readOnly: false,

  // 是否在创建前清理之前的资源
  isCleanOnBeforeCreate: true,

  // 创建前的钩子函数
  onBeforeCreate: (monaco) => {
    // 可以在这里注册自定义语言、主题等
    console.log('Monaco editor is about to be created', monaco)
    return [] // 返回需要清理的 disposable 对象数组
  },

  // Monaco 编辑器原生配置
  fontSize: props.fontSize,
  tabSize: props.tabSize,
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

let socket: any = null;
let languageClient: MonacoLanguageClient | null = null;

const lsp_connection = async() => {
  socket = new ReconnectingWebSocket('ws://lsp.hyacos.top');
  socket.onopen = () => {
    const socketAdapter = toSocket(socket!);
    const reader = new WebSocketMessageReader(socketAdapter);
    const writer = new WebSocketMessageWriter(socketAdapter);
    languageClient = new MonacoLanguageClient({
      name: 'Python Language Client',
      clientOptions: {
        documentSelector: ['python'],
        errorHandler: {
          error: () => ({ action: 1 }), // Continue
          closed: () => ({ action: 2 }) // DoNotRestart
        },
      },
      messageTransports: { reader, writer },
    });
    languageClient.start();
    reader.onClose(() => languageClient?.stop());
  };
}

onMounted(async () => {
  if (editorContainer.value) {
    await initialize({
      // ...getTextMateServiceOverride(),
      // ...getThemeServiceOverride(),
      ...getLanguagesServiceOverride(),
    });
    editor = await createEditor(
      editorContainer.value,
      props.modelValue,
      'python'
    )
    await lsp_connection();
    // v-model 双向绑定
    editor?.onDidChangeModelContent(() => {
      if (isSettingValue.value) return; // 避免 setValue 时触发 emit
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
      // 记录当前光标
      const selection = editor.getSelection();
      isSettingValue.value = true;
      editor.setValue(newVal);
      // 恢复光标
      if (selection) {
        editor.setSelection(selection);
      }
      isSettingValue.value = false;
    }
  }
);
</script>

<template>
  <div>
    <div ref="editorContainer" class="editor" />
  </div>
</template>
