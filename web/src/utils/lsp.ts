import * as monaco from 'monaco-editor';
import ReconnectingWebSocket from 'reconnecting-websocket';
import { ref, type Ref } from 'vue';

let socket: ReconnectingWebSocket | null = null;
let model: monaco.editor.ITextModel | null = null;
let modelVersion = 0;
let diagnosticsMap = new Map<string, monaco.editor.IMarkerData[]>();
export const lspStatus: Ref<'disconnected' | 'connecting' | 'connected' | 'error'> = ref('disconnected');

const callbacks = new Map<number | string, (result: any) => void>();
let nextId = 1;

function send(method: string, params: any, callback?: (result: any) => void) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  const id = nextId++;
  socket.send(JSON.stringify({ jsonrpc: '2.0', id, method, params }));
  if (callback) callbacks.set(id, callback);
}

function sendNotification(method: string, params: any) {
  if (!socket || socket.readyState !== WebSocket.OPEN) return;
  socket.send(JSON.stringify({ jsonrpc: '2.0', method, params }));
}

const LSP_KIND_TO_MONACO: Record<number, monaco.languages.CompletionItemKind> = {
  1: 18,  // Text
  2: 0,   // Method
  3: 1,   // Function
  4: 2,   // Constructor
  5: 3,   // Field
  6: 4,   // Variable
  7: 5,   // Class
  8: 7,   // Interface
  9: 8,   // Module
  10: 9,  // Property
  11: 12, // Unit
  12: 13, // Value
  13: 15, // Enum
  14: 17, // Keyword
  15: 27, // Snippet
  16: 19, // Color
  17: 20, // File
  18: 21, // Reference
  19: 23, // Folder
  20: 16, // EnumMember
  21: 14, // Constant
  22: 6,  // Struct
  23: 10, // Event
  24: 11, // Operator
  25: 24  // TypeParameter
};

export function lspComplete(
  position: monaco.Position,
): Promise<monaco.languages.CompletionItem[]> {
  return new Promise((resolve) => {
    if (!socket || socket.readyState !== WebSocket.OPEN || !model) {
      resolve([]);
      return;
    }
    const timeout = setTimeout(() => resolve([]), 3000);
    send('textDocument/completion', {
      textDocument: { uri: `inmemory:///tmp/${model.uri?.path?.replace(/^\//, '') || 'python.py'}` },
      position: {
        line: position.lineNumber - 1,
        character: position.column - 1
      }
    }, (result) => {
      clearTimeout(timeout);
      if (!result?.items && !Array.isArray(result)) {
        resolve([]);
        return;
      }
      const items = Array.isArray(result) ? result : (result.items || []);
      resolve(items.map((item: any) => {
        let insertText = item.insertText || item.textEdit?.newText || item.label;
        let isSnippet = item.insertTextFormat === 2;

        if (!isSnippet && (item.kind === 2 || item.kind === 3) && !insertText.includes('(')) {
          insertText = `${insertText}($1)`;
          isSnippet = true;
        }

        // Handle both TextEdit (range) and InsertReplaceEdit (insert/replace)
        let range: monaco.IRange;
        if (item.textEdit?.range) {
          range = {
            startLineNumber: item.textEdit.range.start.line + 1,
            startColumn: item.textEdit.range.start.character + 1,
            endLineNumber: item.textEdit.range.end.line + 1,
            endColumn: item.textEdit.range.end.character + 1
          };
        } else if (item.textEdit?.insert) {
          range = {
            startLineNumber: item.textEdit.insert.start.line + 1,
            startColumn: item.textEdit.insert.start.character + 1,
            endLineNumber: item.textEdit.insert.end.line + 1,
            endColumn: item.textEdit.insert.end.character + 1
          };
        } else {
          const word = model!.getWordUntilPosition(position);
          range = new monaco.Range(position.lineNumber, word.startColumn, position.lineNumber, position.column);
        }

        // Handle documentation format (MarkupContent vs IMarkdownString)
        let documentation: any = item.documentation;
        if (documentation && typeof documentation === 'object' && 'value' in documentation) {
          documentation = { value: documentation.value };
        }

        const monacoItem: monaco.languages.CompletionItem = {
          label: item.label,
          kind: LSP_KIND_TO_MONACO[item.kind] ?? monaco.languages.CompletionItemKind.Text,
          detail: item.detail || '',
          documentation,
          insertText,
          sortText: item.sortText,
          filterText: item.filterText,
          insertTextRules: isSnippet ? 4 : void 0,
          range
        };
        return monacoItem;
      }));
    });
  });
}

export function lspFormat(
  tabSize: number,
  insertSpaces: boolean,
): Promise<monaco.languages.TextEdit[]> {
  return new Promise((resolve) => {
    if (!socket || socket.readyState !== WebSocket.OPEN || !model) {
      resolve([]);
      return;
    }
    const timeout = setTimeout(() => resolve([]), 5000);
    send('textDocument/formatting', {
      textDocument: { uri: `inmemory:///tmp/${model.uri?.path?.replace(/^\//, '') || 'python.py'}` },
      options: { tabSize, insertSpaces }
    }, (result) => {
      clearTimeout(timeout);
      if (!Array.isArray(result)) {
        resolve([]);
        return;
      }
      resolve(result.map((edit: any) => ({
        range: {
          startLineNumber: edit.range.start.line + 1,
          startColumn: edit.range.start.character + 1,
          endLineNumber: edit.range.end.line + 1,
          endColumn: edit.range.end.character + 1
        },
        text: edit.newText
      })));
    });
  });
}

export function connectLsp(url: string, editorModel: monaco.editor.ITextModel) {
  if (socket) {
    disconnectLsp();
  }

  model = editorModel;
  lspStatus.value = 'connecting';

  socket = new ReconnectingWebSocket(url);

  function uri() {
    const path = model?.uri?.path?.replace(/^\//, '') || 'python.py';
    return `inmemory:///tmp/${path}`;
  }

  socket.onopen = () => {
    lspStatus.value = 'connected';

    send('initialize', {
      processId: null,
      rootUri: 'file:///',
      capabilities: {
        textDocument: {
          hover: { contentFormat: ['markdown', 'plaintext'] },
          completion: { completionItem: { snippetSupport: true } },
          diagnostic: {},
          publishDiagnostics: { relatedInformation: true },
          formatting: {}
        }
      }
    }, () => {
      sendNotification('initialized', {});
      sendNotification('textDocument/didOpen', {
        textDocument: {
          uri: uri(),
          languageId: 'python',
          version: modelVersion,
          text: model!.getValue()
        }
      });
    });

    model!.onDidChangeContent(() => {
      modelVersion++;
      sendNotification('textDocument/didChange', {
        textDocument: { uri: uri(), version: modelVersion },
        contentChanges: [{ text: model!.getValue() }]
      });
    });
  };

  socket.onmessage = (event) => {
    try {
      const msg = JSON.parse(event.data);
      if (msg.id && callbacks.has(msg.id)) {
        callbacks.get(msg.id)!(msg.result);
        callbacks.delete(msg.id);
        return;
      }
      handleNotification(msg);
    } catch {
    }
  };

  function handleNotification(msg: any) {
    const method = msg.method;
    if (method === 'textDocument/publishDiagnostics') {
      const params = msg.params;
      const uri = params.uri;
      const markers: monaco.editor.IMarkerData[] = (params.diagnostics || []).map((d: any) => ({
        severity: d.severity === 1 ? monaco.MarkerSeverity.Error
          : d.severity === 2 ? monaco.MarkerSeverity.Warning
          : d.severity === 3 ? monaco.MarkerSeverity.Info
          : monaco.MarkerSeverity.Hint,
        message: d.message,
        startLineNumber: (d.range.start.line || 0) + 1,
        startColumn: (d.range.start.character || 0) + 1,
        endLineNumber: (d.range.end.line || 0) + 1,
        endColumn: (d.range.end.character || 0) + 1,
        source: d.source,
        code: d.code?.value || d.code?.toString(),
        relatedInformation: (d.relatedInformation || []).map((r: any) => ({
          resource: monaco.Uri.parse(r.location.uri),
          message: r.message,
          startLineNumber: (r.location.range.start.line || 0) + 1,
          startColumn: (r.location.range.start.character || 0) + 1,
          endLineNumber: (r.location.range.end.line || 0) + 1,
          endColumn: (r.location.range.end.character || 0) + 1
        }))
      }));
      diagnosticsMap.set(uri, markers);
      if (model) {
        monaco.editor.setModelMarkers(model, 'lsp', markers);
      }
    }
  }

  socket.onerror = () => {
    lspStatus.value = 'error';
  };

  socket.onclose = () => {
    if (lspStatus.value !== 'disconnected') {
      lspStatus.value = 'disconnected';
    }
  };
}

export function disconnectLsp() {
  if (socket) {
    if (socket.readyState === WebSocket.OPEN && model) {
      socket.send(JSON.stringify({
        jsonrpc: '2.0',
        method: 'textDocument/didClose',
        params: { textDocument: { uri: `inmemory:///tmp/${model.uri?.path?.replace(/^\//, '') || 'python.py'}` } }
      }));
    }
    socket.onopen = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.onmessage = null;
    socket.close();
  }
  if (model) {
    monaco.editor.setModelMarkers(model, 'lsp', []);
  }
  socket = null;
  model = null;
  diagnosticsMap.clear();
  lspStatus.value = 'disconnected';
}
