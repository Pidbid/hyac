// lsp-client.ts
import { ref, type Ref } from 'vue';
import { MonacoLanguageClient } from 'monaco-languageclient';
import { toSocket, WebSocketMessageReader, WebSocketMessageWriter } from 'vscode-ws-jsonrpc';
import ReconnectingWebSocket from 'reconnecting-websocket';
import { CloseAction, ErrorAction, type MessageTransports } from 'vscode-languageclient/browser.js';

// --- State ---
let languageClient: MonacoLanguageClient | null = null;
let socket: ReconnectingWebSocket | null = null;
export const lspStatus: Ref<'disconnected' | 'connecting' | 'connected' | 'error'> = ref('disconnected');

/**
 * Connects to a Language Server Protocol (LSP) service via WebSocket.
 * @param url The WebSocket URL of the LSP server.
 * @param language The language ID (e.g., 'python') for the document selector.
 */
export function connectToLsp(url: string, language: string) {
  // Prevent multiple connections to the same URL
  if ((socket || lspStatus.value === 'connecting' || lspStatus.value === 'connected') && socket?.url === url) {
    console.warn('LSP client is already connected or connecting to the same URL.');
    return;
  }
  // If URL is different, disconnect first
  if (socket) {
    disconnectFromLsp();
  }

  lspStatus.value = 'connecting';
  socket = new ReconnectingWebSocket(url);

  socket.onopen = () => {
    console.log(`LSP WebSocket connection opened for ${language}.`);
    lspStatus.value = 'connected';
    const socketAdapter = toSocket(socket as any);
    const reader = new WebSocketMessageReader(socketAdapter);
    const writer = new WebSocketMessageWriter(socketAdapter);
    const messageTransports: MessageTransports = { reader, writer };

    languageClient = new MonacoLanguageClient({
      name: `${language.charAt(0).toUpperCase() + language.slice(1)} Language Client`,
      clientOptions: {
        documentSelector: [language],
        errorHandler: {
          error: () => {
            lspStatus.value = 'error';
            return { action: ErrorAction.Continue };
          },
          closed: () => {
            lspStatus.value = 'disconnected';
            return { action: CloseAction.DoNotRestart };
          }
        }
      },
      messageTransports
    });

    languageClient.start();

    reader.onClose(() => {
      languageClient?.stop().catch(() => console.error('Failed to stop language client on close.'));
      if (lspStatus.value !== 'disconnected') {
        lspStatus.value = 'disconnected';
      }
    });
  };

  socket.onerror = (error: any) => {
    console.error('LSP WebSocket error:', error);
    lspStatus.value = 'error';
    socket?.close(); // Ensure socket is closed on error
  };

  socket.onclose = (event: any) => {
    console.log('LSP WebSocket connection closed:', event);
    if (lspStatus.value !== 'disconnected') {
      lspStatus.value = 'disconnected';
    }
  };
}

/**
 * Disconnects from the LSP service and cleans up resources.
 */
export function disconnectFromLsp() {
  if (languageClient && languageClient.isRunning()) {
    languageClient.stop().catch(() => console.error('Failed to stop language client.'));
  }
  if (socket) {
    // Remove listeners to prevent reconnection attempts after explicit disconnection
    socket.onopen = null;
    socket.onclose = null;
    socket.onerror = null;
    socket.close();
  }
  languageClient = null;
  socket = null;
  if (lspStatus.value !== 'disconnected') {
    lspStatus.value = 'disconnected';
  }
  console.log('LSP client disconnected.');
}
