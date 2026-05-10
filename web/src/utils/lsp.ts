import { type Ref, ref } from 'vue';
import * as monaco from 'monaco-editor';
import { ensureVscodeServicesInitialized } from './vscode-init';

type JsonRpcMessage = {
  id?: number;
  method?: string;
  result?: any;
  error?: { message?: string };
};

const documentUri = 'inmemory:///tmp/function.py';

let socket: WebSocket | null = null;
let activeUrl = '';
let readyPromise: Promise<void> | null = null;
let requestId = 1;
let documentVersion = 1;
let getCurrentText: (() => string) | null = null;
let pending = new Map<number, { resolve: (value: any) => void; reject: (reason?: any) => void }>();

export const lspStatus: Ref<'disconnected' | 'initializing' | 'connecting' | 'connected' | 'error'> =
  ref('disconnected');

function send(message: JsonRpcMessage) {
  if (!socket || socket.readyState !== WebSocket.OPEN) {
    throw new Error('LSP WebSocket is not connected');
  }
  socket.send(JSON.stringify({ jsonrpc: '2.0', ...message }));
}

function sendNotification(method: string, params?: any) {
  send({ method, ...(params === undefined ? {} : { params }) });
}

function sendRequest(method: string, params?: any) {
  const id = requestId;
  requestId += 1;
  send({ id, method, ...(params === undefined ? {} : { params }) });

  return new Promise<any>((resolve, reject) => {
    const timer = window.setTimeout(() => {
      pending.delete(id);
      reject(new Error(`LSP request timed out: ${method}`));
    }, 8000);

    pending.set(id, {
      resolve: value => {
        window.clearTimeout(timer);
        resolve(value);
      },
      reject: reason => {
        window.clearTimeout(timer);
        reject(reason);
      }
    });
  });
}

function handleMessage(event: MessageEvent<string>) {
  let message: JsonRpcMessage;
  try {
    message = JSON.parse(event.data);
  } catch {
    return;
  }

  if (typeof message.id !== 'number') {
    return;
  }

  const handler = pending.get(message.id);
  if (!handler) {
    return;
  }

  pending.delete(message.id);
  if (message.error) {
    handler.reject(new Error(message.error.message || 'LSP request failed'));
  } else {
    handler.resolve(message.result);
  }
}

function lspKindToMonaco(kind?: number) {
  const kinds = monaco.languages.CompletionItemKind;
  switch (kind) {
    case 2:
      return kinds.Method;
    case 3:
      return kinds.Function;
    case 4:
      return kinds.Constructor;
    case 5:
      return kinds.Field;
    case 6:
      return kinds.Variable;
    case 7:
      return kinds.Class;
    case 8:
      return kinds.Interface;
    case 9:
      return kinds.Module;
    case 10:
      return kinds.Property;
    case 13:
      return kinds.Enum;
    case 14:
      return kinds.Keyword;
    case 15:
      return kinds.Snippet;
    default:
      return kinds.Text;
  }
}

function lspRangeToMonaco(range: any) {
  if (!range?.start || !range?.end) {
    return undefined;
  }
  return new monaco.Range(range.start.line + 1, range.start.character + 1, range.end.line + 1, range.end.character + 1);
}

function getInsertText(item: any) {
  if (typeof item.textEdit?.newText === 'string') {
    return item.textEdit.newText;
  }
  if (typeof item.insertText === 'string') {
    return item.insertText;
  }
  if (typeof item.label === 'string') {
    return item.label;
  }
  return item.label?.label || '';
}

function mapCompletionItems(result: any, model: monaco.editor.ITextModel, position: monaco.Position) {
  let items: any[] = [];
  if (Array.isArray(result)) {
    items = result;
  } else if (Array.isArray(result?.items)) {
    items = result.items;
  }
  const fallbackWord = model.getWordUntilPosition(position);
  const fallbackRange = new monaco.Range(
    position.lineNumber,
    fallbackWord.startColumn,
    position.lineNumber,
    fallbackWord.endColumn
  );

  return items.map((item: any) => {
    const label = typeof item.label === 'string' ? item.label : item.label?.label || '';
    const range = lspRangeToMonaco(item.textEdit?.range) || fallbackRange;

    return {
      label,
      kind: lspKindToMonaco(item.kind),
      detail: item.detail,
      documentation: typeof item.documentation === 'string' ? item.documentation : item.documentation?.value,
      insertText: getInsertText(item),
      range
    } satisfies monaco.languages.CompletionItem;
  });
}

async function initializeSession() {
  lspStatus.value = 'initializing';
  await sendRequest('initialize', {
    processId: null,
    rootUri: 'inmemory:///tmp',
    capabilities: {
      textDocument: {
        synchronization: { didSave: false, dynamicRegistration: false, willSave: false, willSaveWaitUntil: false },
        completion: {
          completionItem: {
            documentationFormat: ['markdown', 'plaintext'],
            snippetSupport: true
          }
        }
      },
      workspace: { workspaceFolders: true }
    },
    workspaceFolders: [{ uri: 'inmemory:///tmp', name: 'tmp' }]
  });
  sendNotification('initialized', {});
  sendNotification('textDocument/didOpen', {
    textDocument: {
      uri: documentUri,
      languageId: 'python',
      version: documentVersion,
      text: getCurrentText?.() || ''
    }
  });
  lspStatus.value = 'connected';
}

export async function connectLsp(url: string, getText?: () => string) {
  getCurrentText = getText || getCurrentText;
  if (socket && activeUrl === url && socket.readyState <= WebSocket.OPEN) {
    return readyPromise;
  }

  disconnectLsp();
  activeUrl = url;
  await ensureVscodeServicesInitialized();

  lspStatus.value = 'connecting';
  readyPromise = new Promise((resolve, reject) => {
    socket = new WebSocket(url);
    socket.onmessage = handleMessage;
    socket.onerror = () => {
      lspStatus.value = 'error';
      reject(new Error('LSP WebSocket connection failed'));
    };
    socket.onclose = () => {
      pending.forEach(handler => handler.reject(new Error('LSP WebSocket closed')));
      pending.clear();
      if (lspStatus.value !== 'disconnected') {
        lspStatus.value = 'disconnected';
      }
    };
    socket.onopen = () => {
      initializeSession()
        .then(resolve)
        .catch(error => {
          lspStatus.value = 'error';
          reject(error);
        });
    };
  });

  return readyPromise;
}

export async function requestLspCompletionItems(model: monaco.editor.ITextModel, position: monaco.Position) {
  if (!readyPromise) {
    return [];
  }

  await readyPromise;
  documentVersion += 1;
  sendNotification('textDocument/didChange', {
    textDocument: { uri: documentUri, version: documentVersion },
    contentChanges: [{ text: model.getValue() }]
  });

  const result = await sendRequest('textDocument/completion', {
    textDocument: { uri: documentUri },
    position: { line: position.lineNumber - 1, character: position.column - 1 },
    context: { triggerKind: 1 }
  });

  return mapCompletionItems(result, model, position);
}

export function disconnectLsp() {
  if (socket) {
    socket.onopen = null;
    socket.onmessage = null;
    socket.onerror = null;
    socket.onclose = null;
    socket.close();
    socket = null;
  }
  pending.forEach(handler => handler.reject(new Error('LSP disconnected')));
  pending = new Map();
  activeUrl = '';
  readyPromise = null;
  lspStatus.value = 'disconnected';
}
