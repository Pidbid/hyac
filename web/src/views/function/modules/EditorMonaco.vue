<script setup lang="ts">
import { onBeforeUnmount, onMounted, ref, watch } from 'vue';
import '@/utils/monaco-worker';
import * as monaco from 'monaco-editor';
import { useApplicationStore } from '@/store/modules/application';
import { ensureVscodeServicesInitialized } from '@/utils/vscode-init';
import { connectLsp, disconnectLsp, requestLspCompletionItems, requestLspFormattingEdits } from '@/utils/lsp';
import { convertDomain, getServiceBaseUrl } from '@/utils/common';
import { localStg } from '@/utils/storage';

interface Props {
  code?: string;
  showMinimap?: boolean;
  tabSize?: number;
  fontSize?: number;
  themeName?: string;
  showLineNumbers?: boolean;
}

const props = withDefaults(defineProps<Props>(), {
  code: 'import os\n\nprint("Hello, World!")',
  showMinimap: true,
  tabSize: 4,
  fontSize: 14,
  themeName: 'vs-dark',
  showLineNumbers: true
});

const emit = defineEmits<{
  'update:code': [value: string];
}>();

const editorRef = ref<HTMLElement | null>(null);
let editor: monaco.editor.IStandaloneCodeEditor | null = null;
let editorModel: monaco.editor.ITextModel | null = null;
let connectedLspUri = '';

const hyacContextOptions = [
  { label: 'app_id', detail: 'str' },
  { label: 'func_id', detail: 'str' },
  { label: 'logger', detail: 'loguru.Logger' },
  { label: 'pymongo_db', detail: 'pymongo.database.Database' },
  { label: 'async_db', detail: 'pymongo.asynchronous.database.AsyncDatabase' },
  { label: 'db', detail: 'pymongo.asynchronous.database.AsyncDatabase' },
  { label: 'motor_db', detail: 'deprecated alias for async_db' },
  { label: 'sync_db', detail: 'pymongo.database.Database' },
  { label: 'env', detail: 'EnvContext' },
  { label: 'common', detail: 'SimpleNamespace' },
  { label: 'notification', detail: 'NotificationManager' },
  { label: 'minio', detail: 'MinioContext' }
];

const applicationStore = useApplicationStore();

let monacoRegistered = false;

function getCurrentAppId() {
  return applicationStore.appId || applicationStore.appInfo.appId || localStg.get('appId') || '';
}

function syncLspConnection() {
  if (!editor) return;

  const appId = getCurrentAppId();
  if (!appId) return;

  const baseUrl = getServiceBaseUrl();
  const lspUri = `${convertDomain(baseUrl, 'wss', appId)}/__lsp__`;
  if (lspUri === connectedLspUri) return;

  connectedLspUri = lspUri;
  connectLsp(lspUri, () => editor?.getValue() || '');
}

function createPythonModel(value: string) {
  const uri = monaco.Uri.parse('inmemory:///tmp/function.py');
  monaco.editor.getModel(uri)?.dispose();
  editorModel = monaco.editor.createModel(value, 'python', uri);
  return editorModel;
}

function syncEditorCode(value: string) {
  if (!editorModel || editorModel.getValue() === value) return;
  const position = editor?.getPosition();
  editorModel.setValue(value);
  if (position) {
    const lineNumber = Math.min(position.lineNumber, editorModel.getLineCount());
    const column = Math.min(position.column, editorModel.getLineMaxColumn(lineNumber));
    editor?.setPosition({ lineNumber, column });
  }
}

function registerPythonLanguage() {
  if (monacoRegistered) return;
  monacoRegistered = true;

  try {
    monaco.languages.register({ id: 'python', extensions: ['.py'], aliases: ['Python', 'python', 'py'] });
  } catch {
    // ignore
  }

  try {
    monaco.languages.setLanguageConfiguration('python', {
      comments: { lineComment: '#', blockComment: ['"""', '"""'] },
      brackets: [
        ['{', '}'],
        ['[', ']'],
        ['(', ')']
      ],
      autoClosingPairs: [
        { open: '{', close: '}' },
        { open: '[', close: ']' },
        { open: '(', close: ')' },
        { open: '"', close: '"', notIn: ['string'] },
        { open: "'", close: "'", notIn: ['string'] },
        { open: '`', close: '`', notIn: ['string'] }
      ],
      surroundingPairs: [
        { open: '{', close: '}' },
        { open: '[', close: ']' },
        { open: '(', close: ')' },
        { open: '"', close: '"' },
        { open: "'", close: "'" },
        { open: '`', close: '`' }
      ],
      folding: { offSide: true }
    });
  } catch {
    // Monaco internal services may not be fully available; skip gracefully.
  }

  try {
    monaco.languages.setMonarchTokensProvider('python', {
      defaultToken: '',
      tokenizer: {
        root: [
          [
            /\b(import|from|as|def|class|lambda|return|yield|raise|if|elif|else|for|while|try|except|finally|with|pass|break|continue|in|is|not|and|or|global|nonlocal|del|assert|async|await)\b/,
            'keyword'
          ],
          [/\b(True|False|None)\b/, 'number'],
          [/\b(self|cls)\b/, 'variable'],
          [
            /\b(print|len|range|type|int|float|str|list|dict|tuple|set|bool|enumerate|zip|map|filter|sorted|reversed|isinstance|hasattr|getattr|setattr|super|open|input|abs|all|any|bin|chr|dir|divmod|eval|exec|format|hex|id|max|min|next|oct|ord|pow|repr|round|sum|vars)\b/,
            'keyword'
          ],
          [/@\w+/, 'tag'],
          [/0[xX][0-9a-fA-F]+/, 'number'],
          [/0[oO][0-7]+/, 'number'],
          [/0[bB][01]+/, 'number'],
          [/\b\d+(\.\d+)?([eE][+-]?\d+)?\b/, 'number'],
          [/[rfb]?(?:'''|"""|'|")/, { token: 'string', next: '@stringState' }],
          [/#.*/, 'comment'],
          [/[{}()[\]]/, 'delimiter'],
          [/[+\-*/%=<>!&|^~]+/, 'operator']
        ],
        stringState: [
          [/[^\\'"]+/, 'string'],
          [/\\./, 'string.escape'],
          [/('''|"""|'|")/, { token: 'string', next: '@pop' }]
        ]
      }
    });
  } catch {
    // Monaco internal services may not be fully available; skip gracefully.
  }

  try {
    monaco.languages.registerCompletionItemProvider('python', {
      triggerCharacters: ['.'],
      provideCompletionItems: async (model, position) => {
        const textUntilPosition = model.getValueInRange({
          startLineNumber: position.lineNumber,
          startColumn: 1,
          endLineNumber: position.lineNumber,
          endColumn: position.column
        });

        const match = textUntilPosition.match(/(?:ctx|context)\.(\w*)$/);
        if (match) {
          const wordStart = position.column - match[1].length;
          return {
            suggestions: hyacContextOptions.map(item => ({
              label: item.label,
              kind: monaco.languages.CompletionItemKind.Property,
              detail: item.detail,
              insertText: item.label,
              range: new monaco.Range(position.lineNumber, wordStart, position.lineNumber, position.column)
            }))
          };
        }

        try {
          return { suggestions: await requestLspCompletionItems(model, position) };
        } catch {
          return { suggestions: [] };
        }
      }
    });
  } catch {
    // Monaco internal services may not be fully available; skip gracefully.
  }

  try {
    monaco.languages.registerDocumentFormattingEditProvider('python', {
      provideDocumentFormattingEdits: async model => {
        try {
          return await requestLspFormattingEdits(model);
        } catch {
          return [];
        }
      }
    });
  } catch {
    // Monaco internal services may not be fully available; skip gracefully.
  }
}

onMounted(async () => {
  if (!editorRef.value) return;

  await ensureVscodeServicesInitialized();
  registerPythonLanguage();

  editor = monaco.editor.create(editorRef.value, {
    model: createPythonModel(props.code),
    theme: props.themeName,
    fontSize: props.fontSize,
    tabSize: props.tabSize,
    insertSpaces: true,
    minimap: { enabled: props.showMinimap },
    lineNumbers: props.showLineNumbers ? 'on' : 'off',
    automaticLayout: false,
    scrollBeyondLastLine: false,
    wordWrap: 'on',
    fontFamily: "'Courier New', monospace",
    bracketPairColorization: { enabled: true },
    folding: true,
    renderLineHighlight: 'all',
    matchBrackets: 'always',
    autoClosingBrackets: 'always',
    autoClosingQuotes: 'always',
    autoSurround: 'brackets',
    acceptSuggestionOnEnter: 'on',
    wordBasedSuggestions: 'currentDocument',
    suggestOnTriggerCharacters: true,
    suggest: { snippetsPreventQuickSuggestions: false, selectionMode: 'always' },
    quickSuggestions: { other: true, comments: false, strings: false }
  });

  editor.onDidChangeModelContent(() => {
    emit('update:code', editor?.getValue() || '');
  });

  editor.layout();
  syncLspConnection();
});

defineExpose({
  layout() {
    editor?.layout();
  }
});

onBeforeUnmount(() => {
  connectedLspUri = '';
  disconnectLsp();
  if (editor) {
    editor.dispose();
    editor = null;
  }
  if (editorModel) {
    editorModel.dispose();
    editorModel = null;
  }
});

watch(
  () => props.fontSize,
  val => {
    editor?.updateOptions({ fontSize: val });
  }
);
watch(
  () => props.tabSize,
  val => {
    editor?.updateOptions({ tabSize: val });
  }
);
watch(
  () => props.themeName,
  val => {
    monaco.editor.setTheme(val);
  }
);
watch(
  () => props.showMinimap,
  val => {
    editor?.updateOptions({ minimap: { enabled: val } });
  }
);
watch(
  () => props.showLineNumbers,
  val => {
    editor?.updateOptions({ lineNumbers: val ? 'on' : 'off' });
  }
);
watch(
  () => [applicationStore.appId, applicationStore.appInfo.appId],
  () => {
    syncLspConnection();
  }
);
watch(
  () => props.code,
  value => {
    syncEditorCode(value ?? '');
  }
);
</script>

<template>
  <div ref="editorRef" class="editor-container"></div>
</template>

<style scoped>
.editor-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
}
</style>
