import { ref } from 'vue';
import { defineStore } from 'pinia';
import { fetchChatCompletionStream } from '@/service/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

function parseStreamLine(line: string) {
  if (!line.startsWith('data:')) {
    return { done: false, content: '' };
  }

  const jsonStr = line.substring(5).trim();
  if (jsonStr === '[DONE]') {
    return { done: true, content: '' };
  }
  if (!jsonStr) {
    return { done: false, content: '' };
  }

  try {
    const parsed = JSON.parse(jsonStr);
    if (parsed.error) {
      throw new Error(parsed.error);
    }
    return { done: false, content: parsed.content || '' };
  } catch (error) {
    return { done: true, content: `Error: ${error instanceof Error ? error.message : String(error)}` };
  }
}

export const useAiStore = defineStore('ai-assistant', () => {
  const messages = ref<Message[]>([{ role: 'assistant', content: '你好！有什么可以帮助你编写代码的吗？' }]);
  const isLoading = ref(false);

  async function sendMessage(userMessage: string) {
    if (!userMessage.trim() || isLoading.value) return;

    messages.value.push({ role: 'user', content: userMessage });
    isLoading.value = true;
    const aiMessageIndex = messages.value.length;
    messages.value.push({ role: 'assistant', content: '' });

    try {
      const response = await fetchChatCompletionStream(
        messages.value.slice(0, -1).map(m => ({ role: m.role, content: m.content }))
      );

      if (!response.ok || !response.body) {
        throw new Error(`HTTP error! status: ${response.status}`);
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let streamDone = false;
      let buffer = '';

      while (!streamDone) {
        // Streaming readers are intentionally consumed sequentially.
        // eslint-disable-next-line no-await-in-loop
        const { value, done: readerDone } = await reader.read();
        streamDone = readerDone;

        const chunk = decoder.decode(value, { stream: !streamDone });
        buffer += chunk;

        const lines = buffer.split('\n\n');
        buffer = lines.pop() || ''; // Keep the last partial line in buffer

        for (const line of lines) {
          const parsedLine = parseStreamLine(line);
          if (parsedLine.content.startsWith('Error:')) {
            messages.value[aiMessageIndex].content = parsedLine.content;
          } else {
            messages.value[aiMessageIndex].content += parsedLine.content;
          }
          if (parsedLine.done) {
            streamDone = true;
            break;
          }
        }
      }
    } catch {
      messages.value[aiMessageIndex].content = '抱歉，请求出错了。请检查控制台获取更多信息。';
    } finally {
      isLoading.value = false;
    }
  }

  return {
    messages,
    isLoading,
    sendMessage
  };
});
