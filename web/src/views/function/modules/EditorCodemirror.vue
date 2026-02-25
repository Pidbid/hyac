<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch, defineEmits, computed } from 'vue';
import { EditorView, keymap, highlightSpecialChars, drawSelection } from '@codemirror/view';
import { EditorState, Compartment } from '@codemirror/state';
import { indentUnit, indentOnInput, syntaxHighlighting, defaultHighlightStyle } from '@codemirror/language';
import { defaultKeymap, history, historyKeymap, indentWithTab } from '@codemirror/commands';
import {
  closeBrackets,
  closeBracketsKeymap,
  autocompletion,
  completionKeymap,
  type Completion,
  type CompletionContext
} from '@codemirror/autocomplete';
import { gutter, GutterMarker, lineNumbers } from '@codemirror/view';
import { python, pythonLanguage } from '@codemirror/lang-python';
import { LSPClient, languageServerSupport } from '@codemirror/lsp-client';
import type { Transport } from '@codemirror/lsp-client';
import { showMinimap } from '@replit/codemirror-minimap';
import ReconnectingWebSocket from 'reconnecting-websocket';

import { getServiceBaseUrl, convertDomain} from '@/utils/common'
import { useApplicationStore } from '@/store/modules/application';
import { useFunctionStore } from '@/store/modules/function';

// Import all themes
import { basicLight } from '@fsegurai/codemirror-theme-basic-light';
import { basicDark } from '@fsegurai/codemirror-theme-basic-dark';
import { githubLight } from '@fsegurai/codemirror-theme-github-light';
import { githubDark } from '@fsegurai/codemirror-theme-github-dark';
import { gruvboxLight } from '@fsegurai/codemirror-theme-gruvbox-light';
import { gruvboxDark } from '@fsegurai/codemirror-theme-gruvbox-dark';
import { materialLight } from '@fsegurai/codemirror-theme-material-light';
import { materialDark } from '@fsegurai/codemirror-theme-material-dark';
import { solarizedLight } from '@fsegurai/codemirror-theme-solarized-light';
import { solarizedDark } from '@fsegurai/codemirror-theme-solarized-dark';
import { tokyoNightDay } from '@fsegurai/codemirror-theme-tokyo-night-day';
import { tokyoNightStorm } from '@fsegurai/codemirror-theme-tokyo-night-storm';
import { vsCodeLight } from '@fsegurai/codemirror-theme-vscode-light';
import { vsCodeDark } from '@fsegurai/codemirror-theme-vscode-dark';

const applicationStore = useApplicationStore();
const functionStore = useFunctionStore();

const props = defineProps({
  code: {
    type: String,
    default: 'import os\n\nprint("Hello, World!")'
  },
  showMinimap: {
    type: Boolean,
    default: true
  },
  tabSize: {
    type: Number,
    default: 4
  },
  fontSize: {
    type: Number,
    default: 14
  },
  themeName: {
    type: String,
    default: 'github'
  },
  themeMode: {
    type: String,
    default: 'light'
  },
  showLineNumbers: {
    type: Boolean,
    default: true
  }
});

const emit = defineEmits(['update:code']);

const themes: Record<string, { light: any; dark: any }> = {
  github: { light: githubLight, dark: githubDark },
  basic: { light: basicLight, dark: basicDark },
  gruvbox: { light: gruvboxLight, dark: gruvboxDark },
  material: { light: materialLight, dark: materialDark },
  solarized: { light: solarizedLight, dark: solarizedDark },
  tokyoNight: { light: tokyoNightDay, dark: tokyoNightStorm },
  vscode: { light: vsCodeLight, dark: vsCodeDark }
};

const editorRef = ref<HTMLElement | null>(null);
let transport: ClosableTransport | null = null;
let view: EditorView;
let themeCompartment = new Compartment();
let minimapCompartment = new Compartment();
let tabSizeCompartment = new Compartment();
let fontSizeCompartment = new Compartment();
let lineNumbersCompartment = new Compartment();

type ClosableTransport = Transport & { close?: () => void };

const selectedTheme = computed(() => {
  const themeSet = themes[props.themeName] || themes.github;
  return props.themeMode === 'dark' ? themeSet.dark : themeSet.light;
});

const hyacContextOptions: Completion[] = [
  { label: 'app_id', type: 'property', detail: 'str' },
  { label: 'func_id', type: 'property', detail: 'str' },
  { label: 'logger', type: 'property', detail: 'loguru.Logger' },
  { label: 'pymongo_db', type: 'property', detail: 'pymongo.database.Database' },
  { label: 'motor_db', type: 'property', detail: 'motor.AsyncIOMotorDatabase' },
  { label: 'db', type: 'property', detail: 'motor.AsyncIOMotorDatabase' },
  { label: 'sync_db', type: 'property', detail: 'pymongo.database.Database' },
  { label: 'env', type: 'property', detail: 'EnvContext' },
  { label: 'common', type: 'property', detail: 'SimpleNamespace' },
  { label: 'notification', type: 'property', detail: 'NotificationManager' },
  { label: 'minio', type: 'property', detail: 'MinioContext' }
];

function hyacContextCompletionSource(context: CompletionContext) {
  const match = context.matchBefore(/(?:ctx|context)\.\w*/);
  if (!match) return null;
  if (!context.explicit && match.from === match.to) return null;
  const dotIndex = match.text.indexOf('.');
  if (dotIndex < 0) return null;
  return {
    from: match.from + dotIndex + 1,
    options: hyacContextOptions,
    validFor: /^\w*$/
  };
}

const hyacContextCompletions = pythonLanguage.data.of({
  autocomplete: hyacContextCompletionSource
});

function createWebSocketTransport(url: string): ClosableTransport {
  const socket = new ReconnectingWebSocket(url);
  let handlers: ((value: string) => void)[] = [];

  socket.addEventListener('message', event => {
    for (const handler of handlers) {
      handler(event.data);
    }
  });

  return {
    send(message: string) {
      socket.send(message);
    },
    subscribe(handler: (value: string) => void) {
      handlers.push(handler);
    },
    unsubscribe(handler: (value: string) => void) {
      handlers = handlers.filter(h => h !== handler);
    },
    close() {
      socket.close();
    }
  };
}

onMounted(() => {
  if (editorRef.value) {
    const lspExtensions: any[] = [];

    try {
      const client = new LSPClient({
        rootUri: 'inmemory:///tmp',
        timeout: 10000
      });

      const baseUrl = getServiceBaseUrl();
      const lspUri = `${convertDomain(baseUrl, "wss", applicationStore.appId)}/__lsp__`;
      transport = createWebSocketTransport(lspUri);
      client.connect(transport);
      lspExtensions.push(
        languageServerSupport(client, `inmemory:///tmp/${functionStore.funcInfo?.id}.py`, 'python')
      );
    } catch (error) {
      console.warn('[EditorCodemirror] LSP init failed, fallback to local editor only.', error);
    }

    view = new EditorView({
      state: EditorState.create({
        doc: props.code,
        extensions: [
          EditorView.updateListener.of(update => {
            if (update.docChanged) {
              emit('update:code', update.state.doc.toString());
            }
          }),
          highlightSpecialChars(),
          history(),
          drawSelection(),
          indentOnInput(),
          syntaxHighlighting(defaultHighlightStyle, { fallback: true }),
          closeBrackets(),
          autocompletion({ activateOnTyping: true }),
          keymap.of([...closeBracketsKeymap, ...completionKeymap, ...defaultKeymap, ...historyKeymap, indentWithTab]),
          python(),
          hyacContextCompletions,
          themeCompartment.of(selectedTheme.value),
          minimapCompartment.of(
            props.showMinimap
              ? showMinimap.compute([], () => ({
                  create: () => {
                    const dom = document.createElement('div');
                    return { dom };
                  },
                  displayText: 'blocks'
                }))
              : []
          ),
          tabSizeCompartment.of(indentUnit.of(' '.repeat(props.tabSize))),
          fontSizeCompartment.of(
            EditorView.theme({
              '.cm-content': {
                fontSize: `${props.fontSize}px`,
                fontFamily: `'Courier New', monospace`
              }
            })
          ),
          ...lspExtensions,
          lineNumbersCompartment.of(props.showLineNumbers ? lineNumbers() : []),
          EditorView.theme({
            '&': { height: '100%' },
            '.cm-scroller': { height: '100%', overflow: 'auto' }
          })
        ]
      }),
      parent: editorRef.value
    });
  }
});

onUnmounted(() => {
  if (transport && transport.close) {
    transport.close();
  }
});

watch(selectedTheme, newTheme => {
  if (view) {
    view.dispatch({
      effects: themeCompartment.reconfigure(newTheme)
    });
  }
});

watch(
  () => props.showMinimap,
  newValue => {
    if (view) {
      view.dispatch({
        effects: minimapCompartment.reconfigure(
          newValue
            ? showMinimap.compute([], () => ({
                create: () => {
                  const dom = document.createElement('div');
                  dom.style.cssText = 'position: absolute; top: 0; right: 0; height: 100%; width: 100px; z-index: 1;';
                  return { dom };
                },
                displayText: 'blocks'
              }))
            : []
        )
      });
    }
  }
);

watch(() => props.tabSize, (newValue) => {
  if (view) {
    view.dispatch({
      effects: tabSizeCompartment.reconfigure(indentUnit.of(' '.repeat(newValue))),
    });
  }
});

watch(() => props.fontSize, (newValue) => {
  if (view) {
    view.dispatch({
      effects: fontSizeCompartment.reconfigure(EditorView.theme({
        '.cm-content': {
          fontSize: `${newValue}px`,
          fontFamily: `'Courier New', monospace`,
        },
      })),
    });
  }
});

watch(() => props.showLineNumbers, (newValue) => {
  if (view) {
    view.dispatch({
      effects: lineNumbersCompartment.reconfigure(newValue ? lineNumbers() : []),
    });
  }
});
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
  border: 1px solid #ccc;
}
</style>
