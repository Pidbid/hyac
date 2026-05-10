import { type Ref, ref } from 'vue';
import { MonacoLanguageClient } from 'monaco-languageclient';
import { WebSocketMessageReader, WebSocketMessageWriter, toSocket } from 'vscode-ws-jsonrpc';
import { URI } from '@codingame/monaco-vscode-api/vscode/vs/base/common/uri';
import { waitServicesReady } from '@codingame/monaco-vscode-api/lifecycle';
import ReconnectingWebSocket from 'reconnecting-websocket';
import { ensureVscodeServicesInitialized } from './vscode-init';

let languageClient: MonacoLanguageClient | null = null;
let socket: ReconnectingWebSocket | null = null;

export const lspStatus: Ref<'disconnected' | 'initializing' | 'connecting' | 'connected' | 'error'> =
  ref('disconnected');

function createLanguageClient(reader: WebSocketMessageReader, writer: WebSocketMessageWriter): MonacoLanguageClient {
  return new MonacoLanguageClient({
    name: 'Hyac Python Language Client',
    clientOptions: {
      documentSelector: ['python'],
      workspaceFolder: { uri: URI.parse('inmemory:///tmp'), name: 'tmp', index: 0 }
    },
    messageTransports: { reader, writer }
  });
}

export async function connectLsp(url: string) {
  if (socket) {
    disconnectLsp();
  }

  ensureVscodeServicesInitialized();
  await waitServicesReady();

  lspStatus.value = 'connecting';
  socket = new ReconnectingWebSocket(url);

  socket.onopen = () => {
    lspStatus.value = 'initializing';

    const webSocket = toSocket(socket as unknown as WebSocket);
    const reader = new WebSocketMessageReader(webSocket);
    const writer = new WebSocketMessageWriter(webSocket);

    languageClient = createLanguageClient(reader, writer);
    reader.listen(() => {});

    languageClient
      .start()
      .then(() => {
        lspStatus.value = 'connected';
      })
      .catch(() => {
        lspStatus.value = 'error';
      });
  };

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
  if (languageClient) {
    languageClient.dispose();
    languageClient = null;
  }
  if (socket) {
    socket.onopen = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.close();
    socket = null;
  }
  lspStatus.value = 'disconnected';
}
