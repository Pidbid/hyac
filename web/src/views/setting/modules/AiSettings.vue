<script setup lang="ts">
import { ref, onMounted } from 'vue';
import { NForm, NFormItem, NInput, NButton, NCard, useMessage, NSelect } from 'naive-ui';
import { fetchAiConfig, updateAiConfig } from '@/service/api';
import { useAppStore } from '@/store/modules/app';
import { $t } from '@/locales';
import { localStg } from '@/utils/storage';

defineOptions({
  name: 'AiSettings'
});

const appStore = useAppStore();
const message = useMessage();

const formValue = ref({
  provider: '',
  model: '',
  api_key: '',
  base_url: ''
});

const loading = ref(false);

const providerOptions = [
  { label: 'OpenAI', value: 'openai' },
  { label: 'Azure OpenAI', value: 'azure' },
  { label: 'Vertex AI', value: 'vertex_ai' },
  { label: 'Google AI Studio', value: 'gemini' },
  { label: 'Anthropic', value: 'anthropic' },
  { label: 'AWS Sagemaker', value: 'sagemaker' },
  { label: 'Bedrock', value: 'bedrock' },
  { label: 'Mistral AI', value: 'mistral' },
  { label: 'Cohere', value: 'cohere' },
  { label: 'HuggingFace', value: 'huggingface' },
  { label: 'Databricks', value: 'databricks' },
  { label: 'Deepgram', value: 'deepgram' },
  { label: 'IBM watsonx.ai', value: 'watsonx' },
  { label: 'Predibase', value: 'predibase' },
  { label: 'Nvidia NIM', value: 'nvidia' },
  { label: 'xAI', value: 'xai' },
  { label: 'Moonshot AI', value: 'moonshot' },
  { label: 'LM Studio', value: 'lmstudio' },
  { label: 'Cerebras', value: 'cerebras' },
  { label: 'Volcano Engine', value: 'volcengine' },
  { label: 'Ollama', value: 'ollama' },
  { label: 'Perplexity AI', value: 'perplexity' },
  { label: 'Groq', value: 'groq' },
  { label: 'Deepseek', value: 'deepseek' },
  { label: 'Fireworks AI', value: 'fireworks_ai' },
  { label: 'Clarifai', value: 'clarifai' },
  { label: 'VLLM', value: 'vllm' },
  { label: 'Llamafile', value: 'llamafile' },
  { label: 'Cloudflare Workers AI', value: 'cloudflare' },
  { label: 'DeepInfra', value: 'deepinfra' },
  { label: 'AI21', value: 'ai21' },
  { label: 'NLP Cloud', value: 'nlp_cloud' },
  { label: 'Replicate', value: 'replicate' },
  { label: 'Together AI', value: 'together_ai' },
  { label: 'Voyage AI', value: 'voyage' },
  { label: 'Jina AI', value: 'jina' },
  { label: 'Aleph Alpha', value: 'aleph_alpha' },
  { label: 'Baseten', value: 'baseten' },
  { label: 'OpenRouter', value: 'openrouter' },
  { label: 'SambaNova', value: 'sambanova' },
  { label: 'Snowflake', value: 'snowflake' },
  { label: 'Dashscope', value: 'dashscope' }
];

async function getConfig() {
  loading.value = true;
  const appId = localStg.get("appId")
  if (!appId) {
    message.error('No application selected');
    loading.value = false;
    return;
  }
  try {
    const { data } = await fetchAiConfig({ appId });
    if (data) {
      formValue.value = data;
    }
  } catch (error) {
    message.error('Failed to fetch AI configuration');
  } finally {
    loading.value = false;
  }
}

async function handleUpdate() {
  loading.value = true;
  const appId = localStg.get("appId");
  if (!appId) {
    message.error('No application selected');
    loading.value = false;
    return;
  }
  try {
    await updateAiConfig({ appId, config: formValue.value });
    message.success('AI configuration updated successfully');
  } catch (error) {
    message.error('Failed to update AI configuration');
  } finally {
    loading.value = false;
  }
}

onMounted(() => {
  getConfig();
});
</script>

<template>
  <NCard :title="$t('page.setting.ai.title')">
    <NForm ref="formRef" :model="formValue" label-placement="left" label-width="auto" require-mark-placement="right-hanging">
      <NFormItem :label="$t('page.setting.ai.provider')" path="provider">
        <NSelect
          v-model:value="formValue.provider"
          :options="providerOptions"
          :placeholder="$t('page.setting.ai.providerPlaceholder')"
          filterable
        />
      </NFormItem>
      <NFormItem :label="$t('page.setting.ai.model')" path="model">
        <NInput v-model:value="formValue.model" :placeholder="$t('page.setting.ai.modelPlaceholder')" />
      </NFormItem>
      <NFormItem :label="$t('page.setting.ai.apiKey')" path="api_key">
        <NInput
          v-model:value="formValue.api_key"
          type="password"
          show-password-on="click"
          :placeholder="$t('page.setting.ai.apiKeyPlaceholder')"
        />
      </NFormItem>
      <NFormItem :label="$t('page.setting.ai.endpointUrl')" path="base_url">
        <NInput v-model:value="formValue.base_url" :placeholder="$t('page.setting.ai.endpointUrlPlaceholder')" />
      </NFormItem>
      <NFormItem>
        <NButton type="primary" :loading="loading" @click="handleUpdate">
          {{ $t('common.save') }}
        </NButton>
      </NFormItem>
    </NForm>
  </NCard>
</template>
