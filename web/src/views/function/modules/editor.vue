<template>
  <div ref="editorContainer" style="height: 100%;"></div>
</template>

<script setup lang="ts">
import { ref, onMounted, onBeforeUnmount, watch, nextTick, computed } from 'vue';
import { monaco, initMonaco } from '@/utils/monaco';
// LSP 相关
import { MonacoLanguageClient } from 'monaco-languageclient';
import { toSocket, WebSocketMessageReader, WebSocketMessageWriter } from 'vscode-ws-jsonrpc';
import ReconnectingWebSocket from 'reconnecting-websocket';
import { convertDomain } from "@/utils/common"

interface Props {
  modelValue: string;
  language?: string;
  fontSize?: number;
  tabSize?: number;
  minimap?: boolean;
  theme?: string;
}

const props = withDefaults(defineProps<Props>(), {
  modelValue: "",
  language: 'python',
  fontSize: 16,
  tabSize: 4,
  minimap: true,
  theme: 'Default Dark Modern'
});
const emit = defineEmits(['update:modelValue']);

const editorContainer = ref<HTMLDivElement | null>(null);
let editor: monaco.editor.IStandaloneCodeEditor | null = null;
let languageClient: MonacoLanguageClient | null = null;
let socket: any = null;
const lspStatus = ref<'disconnected' | 'connecting' | 'connected' | 'error'>('disconnected');

const isSettingValue = ref(false);

// 创建编辑器实例
function createEditorInstance() {
  if (!editorContainer.value) return;

  editor = monaco.editor.create(editorContainer.value, {
    value: props.modelValue,
    language: props.language,
    theme: props.theme,
    automaticLayout: true,
    fontSize: props.fontSize,
    tabSize: props.tabSize,
    minimap: { enabled: props.minimap },
    fontFamily: 'Courier New, monospace',
    scrollBeyondLastLine: false,
    lineNumbers: 'on',
    lineNumbersMinChars: 4,
    overviewRulerLanes: 0,
    formatOnPaste: true,
    // 配置滚动条行为
    scrollbar: {
      verticalScrollbarSize: 4,
      horizontalScrollbarSize: 8
    }
  });

  // v-model 双向绑定
  editor.onDidChangeModelContent(() => {
    if (isSettingValue.value) return; // 避免 setValue 时触发 emit
    const value = editor!.getValue();
    emit('update:modelValue', value);
  });
}

// 连接到 LSP 服务
function connectToLsp(url: string) {
  if (props.language !== 'python' || !url) return;

  lspStatus.value = 'connecting';
  socket = new ReconnectingWebSocket(url);

  socket.onopen = () => {
    console.log('LSP WebSocket connection opened.');
    lspStatus.value = 'connected';
    const socketAdapter = toSocket(socket!);
    const reader = new WebSocketMessageReader(socketAdapter);
    const writer = new WebSocketMessageWriter(socketAdapter);
    languageClient = new MonacoLanguageClient({
      name: 'Python Language Client',
      clientOptions: {
        documentSelector: ['python'],
        errorHandler: {
          error: () => {
            lspStatus.value = 'error';
            return { action: 1 }; // Continue
          },
          closed: () => {
            lspStatus.value = 'disconnected';
            return { action: 2 }; // DoNotRestart
          }
        }
      },
      messageTransports: { reader, writer }
    });
    languageClient.start();
    reader.onClose(() => {
      languageClient?.stop().catch(() => console.error('Failed to stop language client on close.'));
      lspStatus.value = 'disconnected';
    });
  };

  socket.onerror = (error: Event) => {
    console.error('LSP WebSocket error:', error);
    lspStatus.value = 'error';
    socket?.close();
  };

  socket.onclose = (event: CloseEvent) => {
    console.log('LSP WebSocket connection closed:', event);
    lspStatus.value = 'disconnected';
    languageClient?.stop().catch(() => console.error('Failed to stop language client on close.'));
  };
}

// 设置所有的 watch
function setupWatchers() {
  // 外部 modelValue 变化时同步到编辑器
  watch(
    () => props.modelValue,
    newVal => {
      if (editor && editor.getValue() !== newVal) {
        const selection = editor.getSelection();
        isSettingValue.value = true;
        editor.setValue(newVal)
        if (selection) {
          editor.setSelection(selection);
        }
        isSettingValue.value = false;
      }
    }
  );

  // 监听编辑器选项变化
  watch(
    () => props.fontSize,
    newSize => {
      editor?.updateOptions({ fontSize: newSize });
    }
  );

  watch(
    () => props.tabSize,
    newTabSize => {
      editor?.updateOptions({ tabSize: newTabSize });
    }
  );

  watch(
    () => props.minimap,
    enabled => {
      editor?.updateOptions({ minimap: { enabled } });
    }
  );

  watch(
    () => props.theme,
    newTheme => {
      if (newTheme) {
        monaco.editor.setTheme(newTheme);
      }
    }
  );
}

// 重新加载视图
function reloadView() {
  editor?.render(true);
}

const lspUrl = computed(() => {
  // 在开发环境下，连接到本地的 LSP 服务
  // if (import.meta.env.DEV) {
  //   return 'ws://localhost:8765';
  // }
  const baseUrl = import.meta.env.VITE_SERVICE_BASE_URL;
  return convertDomain(baseUrl, "wss", "lsp")
});

onMounted(async () => {
  await initMonaco();
  createEditorInstance();
  connectToLsp(lspUrl.value);
  setupWatchers();
  // 捕获并阻止某些无害的 LSP 错误
  const unhandledRejectionListener = (event: PromiseRejectionEvent) => {
    if (event?.reason?.message?.includes('Unable to resolve nonexistent file')) {
      event.preventDefault();
    }
  };
  window.addEventListener('unhandledrejection', unhandledRejectionListener);

  onBeforeUnmount(() => {
    window.removeEventListener('unhandledrejection', unhandledRejectionListener);
  });
});

onBeforeUnmount(() => {
  editor?.dispose();
  if (languageClient && languageClient.isRunning()) {
    languageClient.stop().catch(() => console.error('Failed to stop language client.'));
  }
  if (socket) {
    socket.close();
  }
});
</script>
