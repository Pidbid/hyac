import { defineStore } from 'pinia';
import { ref } from 'vue';
import { fetchChatCompletionStream } from '@/service/api';

interface Message {
  role: 'user' | 'assistant';
  content: string;
}

export const useAiStore = defineStore('ai-assistant', () => {
  const messages = ref<Message[]>([
    { role: 'assistant', content: '你好！有什么可以帮助你编写代码的吗？' }
  ]);
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
      let done = false;
      let buffer = '';

      while (!done) {
        const { value, done: readerDone } = await reader.read();
        done = readerDone;

        const chunk = decoder.decode(value, { stream: !done });
        buffer += chunk;

        const lines = buffer.split('\n\n');
        buffer = lines.pop() || ''; // Keep the last partial line in buffer

        for (const line of lines) {
          if (line.startsWith('data:')) {
            const jsonStr = line.substring(5).trim();
            if (jsonStr === '[DONE]') {
              done = true;
              break;
            }
            if (jsonStr) {
              try {
                const parsed = JSON.parse(jsonStr);
                if (parsed.content) {
                  // Directly update the content for reactivity
                  messages.value[aiMessageIndex].content += parsed.content;
                }
                if (parsed.error) {
                  throw new Error(parsed.error);
                }
              } catch (e) {
                console.error('Failed to parse JSON chunk:', jsonStr, e);
                // Display error in the message bubble
                messages.value[aiMessageIndex].content = `Error: ${e instanceof Error ? e.message : String(e)}`;
                done = true; // Stop processing on error
                break;
              }
            }
          }
        }
      }
    } catch (error) {
      console.error('Error during chat completion:', error);
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
