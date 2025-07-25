import { defineStore } from 'pinia';
import { useAuthStore } from '../auth';
import { useApplicationStore } from '../application';
import dayjs from 'dayjs';
import { ref, readonly } from 'vue';
import { getServiceBaseUrl } from '@/utils/common';

export const useLogStore = defineStore('log-store', () => {
  // State
  const ws = ref<WebSocket | null>(null);
  const isConnected = ref(false);
  const logs = ref<Api.Function.FunctionLogsInfo[]>([]);
  const currentFuncId = ref<string | null>(null);
  const messageQueue = ref<string[]>([]);

  // Actions
  function _sendMessage(message: object) {
    const messageStr = JSON.stringify(message);
    if (ws.value && isConnected.value) {
      ws.value.send(messageStr);
    } else {
      messageQueue.value.push(messageStr);
    }
  }

  function connect() {
    const authStore = useAuthStore();
    const applicationStore = useApplicationStore();

    if (ws.value) {
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

    logs.value = [];

    const baseUrl = getServiceBaseUrl();
    const wsProtocol = window.location.protocol === 'https:' ? 'wss' : 'ws';
    // Extract host from baseUrl, removing http/https protocol and any trailing slash
    const host = baseUrl.replace(/^(http|https):\/\//, '').replace(/\/$/, '');
    const wsUrl = `${wsProtocol}://${host}/logs/websocket_logs/${applicationStore.appId}?token=${token}`;
    ws.value = new WebSocket(wsUrl);

    ws.value.onopen = () => {
      isConnected.value = true;
      console.info("Global WebSocket connection established");
      messageQueue.value.forEach(message => ws.value?.send(message));
      messageQueue.value = [];
    };

    ws.value.onmessage = (event) => {
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
        logs.value.unshift(formattedLog);
      } catch (e) {
        console.error("Failed to parse log message:", e);
      }
    };

    ws.value.onerror = (error) => {
      console.error('Global WebSocket Error:', error);
      isConnected.value = false;
      ws.value = null;
    };

    ws.value.onclose = () => {
      isConnected.value = false;
      ws.value = null;
      currentFuncId.value = null;
      messageQueue.value = [];
      console.log('Global WebSocket connection closed');
    };
  }

  function disconnect() {
    if (ws.value) {
      ws.value.close();
    }
  }

  function subscribe(funcId: string) {
    // If we are already subscribed to this function, do nothing.
    if (currentFuncId.value === funcId) {
      return;
    }

    // If we were subscribed to a different function, unsubscribe from it first.
    if (currentFuncId.value) {
      _sendMessage({ type: 'unsubscribe' });
    }

    // Now, subscribe to the new function.
    currentFuncId.value = funcId;
    logs.value = []; // Clear logs for the new function
    _sendMessage({ type: 'subscribe', funcId });
  }

  function unsubscribe() {
    if (currentFuncId.value) {
      _sendMessage({ type: 'unsubscribe' });
      currentFuncId.value = null;
      logs.value = [];
    }
  }

  return {
    isConnected: readonly(isConnected),
    logs: readonly(logs),
    currentFuncId: readonly(currentFuncId),
    connect,
    disconnect,
    subscribe,
    unsubscribe
  };
});
