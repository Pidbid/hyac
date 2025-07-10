import { defineStore } from 'pinia';
import { useAuthStore } from './auth';
import { useApplicationStore } from './application';
import dayjs from 'dayjs';

interface LogState {
  ws: WebSocket | null;
  isConnected: boolean;
  logs: Api.Function.FunctionLogsInfo[];
  currentFuncId: string | null;
  messageQueue: string[]; // 消息队列，用于存储连接建立前待发送的消息
}

export const useLogStore = defineStore('log-store', {
  state: (): LogState => ({
    ws: null,
    isConnected: false,
    logs: [],
    currentFuncId: null,
    messageQueue: [],
  }),
  actions: {
    connect() {
      const authStore = useAuthStore();
      const applicationStore = useApplicationStore();

      // 如果正在连接或已连接，则不执行任何操作
      if (this.ws) {
        console.log("WebSocket is already connected or connecting.");
        return;
      }

      if (!applicationStore.appId) {
        console.error('Application ID not found, cannot connect to log service.');
        return;
      }

      const token = authStore.token;
      if (!token) {
        console.error('Authentication failed, cannot connect to log service.');
        return;
      }

      // 清空旧日志
      this.logs = [];

      const wsUrl = `ws://localhost:9527/proxy-default/logs/websocket_logs/${applicationStore.appId}?token=${token}`;
      this.ws = new WebSocket(wsUrl);

      this.ws.onopen = () => {
        this.isConnected = true;
        console.info("Global WebSocket connection established");
        // 连接建立后，发送队列中的所有消息
        this.messageQueue.forEach(message => this.ws?.send(message));
        this.messageQueue = []; // 清空队列
      };

      this.ws.onmessage = (event) => {
        try {
          const logData = JSON.parse(event.data);
          if (logData.error) {
            console.error('WebSocket message error:', logData.error);
            return;
          }
          const formattedLog: Api.Function.FunctionLogsInfo = {
            _id: logData._id,
            timestamp: dayjs(logData.timestamp).format('YYYY-MM-DD HH:mm:ss'),
            level: logData.level,
            message: logData.message,
            app_id: logData.app_id,
            function_id: logData.function_id,
            logtype: logData.logtype
          };
          this.logs.unshift(formattedLog);
        } catch (e) {
          console.error("Failed to parse log message:", e);
        }
      };

      this.ws.onerror = (error) => {
        console.error('Global WebSocket Error:', error);
        this.isConnected = false;
        this.ws = null; // 在出错时也应该清理ws实例
      };

      this.ws.onclose = () => {
        this.isConnected = false;
        this.ws = null;
        this.currentFuncId = null;
        this.messageQueue = []; // 连接关闭时清空队列
        console.log('Global WebSocket connection closed');
      };
    },

    disconnect() {
      if (this.ws) {
        this.ws.close();
        // onclose will handle the state cleanup
      }
    },

    // 内部方法，用于发送或排队消息
    _sendMessage(message: object) {
      const messageStr = JSON.stringify(message);
      if (this.ws && this.isConnected) {
        this.ws.send(messageStr);
      } else {
        this.messageQueue.push(messageStr);
        this.connect(); // 如果未连接，则尝试连接
      }
    },

    subscribe(funcId: string) {
      // 如果已经订阅了同一个函数，并且连接正常，则不重复订阅
      if (this.currentFuncId === funcId && this.isConnected) {
        return;
      }
      this.currentFuncId = funcId;
      this.logs = []; // 切换订阅时清空旧日志
      this._sendMessage({ type: 'subscribe', funcId });
    },

    unsubscribe() {
      if (this.currentFuncId) {
        this._sendMessage({ type: 'unsubscribe' });
        this.currentFuncId = null;
        this.logs = [];
      }
    }
  }
});
