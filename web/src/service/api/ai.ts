import { getServiceBaseURL } from '@/utils/service';
import { getAuthorization } from '../request/shared';
import {localStg} from "@/utils/storage"
import {getServiceBaseUrl} from "@/utils/common"

interface Message {
  role: 'user' | 'ai';
  content: string;
}

/**
 * Fetch chat completion with stream.
 * NOTE: This uses the native `fetch` API because it provides the best support for
 * streaming responses (Server-Sent Events) in the browser. The project's default
 * `request` wrapper (based on axios) is not designed for this.
 *
 * @param messages
 * @param model
 */
export function fetchChatCompletionStream(messages: Message[], model: string = 'default') {
  const Authorization = getAuthorization();
  const baseURL = getServiceBaseUrl();
  const url = `${baseURL}/ai/chat_completions`;
  const appid = localStg.get("appId");
  return fetch(url, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      Authorization: Authorization || ''
    },
    body: JSON.stringify({
      appid: appid,
      messages: messages.map(m => ({ role: m.role, content: m.content })),
      model
    })
  });
}
