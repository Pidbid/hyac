// lsp-client.ts
import { WebSocketMessageReader } from "vscode-ws-jsonrpc";
import {
  CloseAction,
  ErrorAction,
  MessageTransports,
} from "vscode-languageclient/browser.js";
import { WebSocketMessageWriter } from "vscode-ws-jsonrpc";
import { toSocket } from "vscode-ws-jsonrpc";
import { MonacoLanguageClient } from "monaco-languageclient";

export const initWebSocketAndStartClient = (): WebSocket => {
  const url = "ws://lsp.hyacos.top";
  const webSocket = new WebSocket(url);
  webSocket.onopen = () => {
    // creating messageTransport
    const socket = toSocket(webSocket);
    const reader = new WebSocketMessageReader(socket);
    const writer = new WebSocketMessageWriter(socket);
    // creating language client
    const languageClient = new MonacoLanguageClient({
      name: "Sample Language Client",
      clientOptions: {
        // use a language id as a document selector
        documentSelector: ["python", "json"],
        // disable the default error handler
        errorHandler: {
          error: () => ({ action: ErrorAction.Continue }),
          closed: () => ({ action: CloseAction.Restart }),
        },
      },
      // create a language client connection from the JSON RPC connection on demand
      messageTransports: {
        reader: reader,
        writer: writer,
        detached: true,
      },
    });
    languageClient.start();
    // reader.onClose(() => languageClient.stop());
  };
  return webSocket;
};
