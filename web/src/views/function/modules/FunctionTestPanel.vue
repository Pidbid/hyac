<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useClipboard } from '@vueuse/core';
import { NCard, NScrollbar, NSpace, NInputGroup, NInput, NButton, NIcon, NTabs, NTabPane, NText, NSelect, NButtonGroup, useMessage } from 'naive-ui';
import { CopyOutline, TrashBinOutline, AddOutline } from '@vicons/ionicons5';
import JsonEditor from '@/components/custom/JsonEditor.vue';
import { functionTest } from '@/service/api';

const props = defineProps<{
  functionAddress: string;
}>();

const message = useMessage();
const { copy, isSupported } = useClipboard();

const testMethod = ref('GET');
const testHeadersList = ref<{ key: string; value: string; disabled?: boolean }[]>([{ key: '', value: '' }]);
const testQueryParamsList = ref<{ key: string; value: string }[]>([{ key: '', value: '' }]);
const testJsonBody = ref('{}');
const testResult = ref('点击"发送请求"进行测试...');
const requestResponse = ref('');

const handleTestRequest = async () => {
  const headers = testHeadersList.value.reduce((acc, cur) => {
    if (cur.key) {
      acc[cur.key] = cur.value;
    }
    return acc;
  }, {} as Record<string, string>);

  const query = testQueryParamsList.value.reduce((acc, cur) => {
    if (cur.key) {
      acc[cur.key] = cur.value;
    }
    return acc;
  }, {} as Record<string, string>);

  let body = {};
  if (testMethod.value === 'POST' && testJsonBody.value) {
    try {
      body = JSON.parse(testJsonBody.value);
    } catch (e) {
      message.error('POST 请求格式不正确');
      return;
    }
  }

  try {
    requestResponse.value = '请求中...\n';
    const response = await functionTest(props.functionAddress, testMethod.value, headers, query, body);
    if (response && response.data) {
      testResult.value = JSON.stringify(response.data, null, 2);
      requestResponse.value += `请求成功: ${JSON.stringify(response.data, null, 2)}`;
    } else {
      testResult.value = '请求成功，但没有返回数据。';
      requestResponse.value += '请求成功，但没有返回数据。';
    }
  } catch (error: any) {
    if (error.response) {
      const errorText = `请求失败:\n${JSON.stringify(error.response.data, null, 2)}`;
      testResult.value = errorText;
      requestResponse.value += errorText;
    } else {
      const errorText = `请求失败:\n${error.message}`;
      testResult.value = errorText;
      requestResponse.value += errorText;
    }
  }
};

const handleHeaderSelect = (value: string, index: number) => {
  const isDuplicate = testHeadersList.value.some((h, i) => i !== index && h.key === value && value !== '');
  if (isDuplicate) {
    message.warning(`已存在相同的Header键: ${value}`);
    return;
  }
  testHeadersList.value[index].key = value;
};

const addHeader = () => {
  if (testHeadersList.value.some(h => h.key === '')) {
    message.warning('请先填写当前空白的Header键值对');
    return;
  }
  testHeadersList.value.push({ key: '', value: '' });
};

const removeHeader = (index: number) => {
  if (testHeadersList.value[index].disabled) {
    message.warning('无法删除此Header');
    return;
  }
  testHeadersList.value.splice(index, 1);
};

const addQueryParam = () => {
  if (testQueryParamsList.value.some(p => p.key === '')) {
    message.warning('请先填写当前空白的Query参数键值对');
    return;
  }
  testQueryParamsList.value.push({ key: '', value: '' });
};

const removeQueryParam = (index: number) => {
  testQueryParamsList.value.splice(index, 1);
};

const handleCopyAddress = () => {
  if (isSupported.value) {
    copy(props.functionAddress);
    message.success('地址已复制');
  } else {
    message.error('您的浏览器不支持复制功能');
  }
};

const handleCopyResult = () => {
  if (isSupported.value) {
    copy(testResult.value);
    message.success('响应结果已复制');
  } else {
    message.error('您的浏览器不支持复制功能');
  }
};

watch(testMethod, (newMethod) => {
  const contentTypeHeader = { key: 'Content-Type', value: 'application/json', disabled: true };
  const existingContentTypeIndex = testHeadersList.value.findIndex(h => h.key === 'Content-Type');

  if (newMethod === 'POST') {
    if (existingContentTypeIndex === -1) {
      testHeadersList.value.unshift(contentTypeHeader);
    } else {
      testHeadersList.value[existingContentTypeIndex] = contentTypeHeader;
    }
  } else {
    if (existingContentTypeIndex !== -1 && testHeadersList.value[existingContentTypeIndex].disabled) {
      testHeadersList.value.splice(existingContentTypeIndex, 1);
    }
  }
}, { immediate: true });

</script>

<template>
  <NCard title="函数测试" :bordered="false" size="small" class="h-full"
    :content-style="{ padding: '0px', height: 'calc(100% - 40px)' }">
    <NScrollbar class="h-full p-4">
      <NSpace vertical class="h-full">
        <NInputGroup>
          <NInput :value="functionAddress" readonly />
          <NButton type="primary" @click="handleCopyAddress">
            <template #icon>
              <NIcon :component="CopyOutline" />
            </template>
          </NButton>
        </NInputGroup>

        <NTabs v-model:value="testMethod" type="segment" class="w-full">
          <NTabPane name="GET" tab="GET"></NTabPane>
          <NTabPane name="POST" tab="POST"></NTabPane>
        </NTabs>

        <div class="flex flex-col gap-2">
          <NText class="mb-2">Headers</NText>
          <div v-for="(header, index) in testHeadersList" :key="index" class="flex gap-2 items-center">
            <NSelect v-model:value="header.key" :options="[
              { label: 'User-Agent', value: 'User-Agent' },
              { label: 'Host', value: 'Host' },
              { label: 'Content-Type', value: 'Content-Type' },
              { label: 'Accept', value: 'Accept' },
              { label: 'Authorization', value: 'Authorization' },
            ]" placeholder="选择或输入Header" style="width: 120px" filterable tag
              @update:value="(value) => handleHeaderSelect(value, index)" :disabled="header.disabled" />
            <NInput v-model:value="header.value" placeholder="Header Value" class="flex-1" :disabled="header.disabled" />
            <NButton v-if="!header.disabled" quaternary circle @click="removeHeader(index)">
              <template #icon>
                <NIcon :component="TrashBinOutline" />
              </template>
            </NButton>
          </div>
          <NButton type="tertiary" size="tiny" class="self-end" @click="addHeader">
            <template #icon>
              <NIcon :component="AddOutline" />
            </template>
            Header
          </NButton>
        </div>

        <div v-if="testMethod === 'GET'" class="flex flex-col gap-2">
          <NText class="mb-2">Query Parameters</NText>
          <div v-for="(param, index) in testQueryParamsList" :key="index" class="flex gap-2 items-center">
            <NInput v-model:value="param.key" placeholder="Key" style="width: 120px" />
            <NInput v-model:value="param.value" placeholder="Value" class="flex-1" />
            <NButton quaternary circle @click="removeQueryParam(index)">
              <template #icon>
                <NIcon :component="TrashBinOutline" />
              </template>
            </NButton>
          </div>
          <NButton type="tertiary" size="tiny" class="self-end" @click="addQueryParam">
            <template #icon>
              <NIcon :component="AddOutline" />
            </template>
            Query
          </NButton>
        </div>

        <div v-else class="flex flex-col gap-2">
          <NText class="mb-2">Body (JSON)</NText>
          <JsonEditor v-model:modelValue="testJsonBody" :height="300"></JsonEditor>
        </div>

        <NButton type="primary" size="large" block @click="handleTestRequest">发送请求</NButton>

        <div class="min-h-0 flex flex-col flex-1">
          <NText class="mb-2">响应</NText>
          <NInput v-model:value="testResult" type="textarea" placeholder="响应结果" :rows="10" readonly class="flex-1" />
          <NButtonGroup class="self-end">
            <NButton quaternary circle class="mt-2" @click="handleCopyResult">
              <template #icon>
                <NIcon :component="CopyOutline" />
              </template>
            </NButton>
            <NButton quaternary circle class="mt-2" @click="testResult = ''">
              <template #icon>
                <NIcon :component="TrashBinOutline" />
              </template>
            </NButton>
          </NButtonGroup>
        </div>
      </NSpace>
    </NScrollbar>
  </NCard>
</template>

<style scoped>
</style>
