<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useClipboard } from '@vueuse/core';
import { NCard, NScrollbar, NSpace, NInputGroup, NInput, NButton, NIcon, NTabs, NTabPane, NText, NSelect, NButtonGroup, useMessage } from 'naive-ui';
import { CopyOutline, TrashBinOutline, AddOutline } from '@vicons/ionicons5';
import jsonEditor from '@/components/custom/jsonEditor.vue';
import { functionTest } from '@/service/api';
import { $t } from '@/locales';

const props = defineProps<{
  functionAddress: string;
}>();

const message = useMessage();
const { copy, isSupported } = useClipboard();

const testMethod = ref('GET');
const testHeadersList = ref<{ key: string; value: string; disabled?: boolean }[]>([{ key: '', value: '' }]);
const testQueryParamsList = ref<{ key: string; value: string }[]>([{ key: '', value: '' }]);
const testJsonBody = ref('{}');
const testResult = ref($t('page.function.clickToSend'));
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
      message.error($t('page.function.postFormatError'));
      return;
    }
  }

  try {
    requestResponse.value = $t('page.function.requesting') + '\n';
    const response = await functionTest(props.functionAddress, testMethod.value, headers, query, body);
    if (response && response.data) {
      testResult.value = JSON.stringify(response.data, null, 2);
      requestResponse.value += `${$t('page.function.requestSuccessNoData')}: ${JSON.stringify(response.data, null, 2)}`;
    } else {
      testResult.value = $t('page.function.requestSuccessNoData');
      requestResponse.value += $t('page.function.requestSuccessNoData');
    }
  } catch (error: any) {
    if (error.response) {
      const errorText = `${$t('page.function.requestFailed')}\n${JSON.stringify(error.response.data, null, 2)}`;
      testResult.value = errorText;
      requestResponse.value += errorText;
    } else {
      const errorText = `${$t('page.function.requestFailed')}\n${error.message}`;
      testResult.value = errorText;
      requestResponse.value += errorText;
    }
  }
};

const handleHeaderSelect = (value: string, index: number) => {
  const isDuplicate = testHeadersList.value.some((h, i) => i !== index && h.key === value && value !== '');
  if (isDuplicate) {
    message.warning($t('page.function.duplicateHeader', { key: value }));
    return;
  }
  testHeadersList.value[index].key = value;
};

const addHeader = () => {
  if (testHeadersList.value.some(h => h.key === '')) {
    message.warning($t('page.function.fillBlankHeader'));
    return;
  }
  testHeadersList.value.push({ key: '', value: '' });
};

const removeHeader = (index: number) => {
  if (testHeadersList.value[index].disabled) {
    message.warning($t('page.function.cannotDeleteHeader'));
    return;
  }
  testHeadersList.value.splice(index, 1);
};

const addQueryParam = () => {
  if (testQueryParamsList.value.some(p => p.key === '')) {
    message.warning($t('page.function.fillBlankQuery'));
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
    message.success($t('page.function.addressCopied'));
  } else {
    message.error($t('page.function.copyFailed'));
  }
};

const handleCopyResult = () => {
  if (isSupported.value) {
    copy(testResult.value);
    message.success($t('page.function.responseCopied'));
  } else {
    message.error($t('page.function.copyFailed'));
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
  <NCard :title="$t('page.function.functionTest')" :bordered="false" size="small" class="h-full"
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
            ]" :placeholder="$t('page.function.headerPlaceholder')" style="width: 120px" filterable tag
              @update:value="(value) => handleHeaderSelect(value, index)" :disabled="header.disabled" />
            <NInput v-model:value="header.value" :placeholder="$t('page.function.headerValuePlaceholder')" class="flex-1" :disabled="header.disabled" />
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
          <NText class="mb-2">{{ $t('page.function.queryParameters') }}</NText>
          <div v-for="(param, index) in testQueryParamsList" :key="index" class="flex gap-2 items-center">
            <NInput v-model:value="param.key" :placeholder="$t('page.function.keyPlaceholder')" style="width: 120px" />
            <NInput v-model:value="param.value" :placeholder="$t('page.function.valuePlaceholder')" class="flex-1" />
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
          <NText class="mb-2">{{ $t('page.function.bodyJson') }}</NText>
          <jsonEditor v-model:modelValue="testJsonBody" :height="300"></jsonEditor>
        </div>

        <NButton type="primary" size="large" block @click="handleTestRequest">{{ $t('page.function.sendRequest') }}</NButton>

        <div class="min-h-0 flex flex-col flex-1">
          <NText class="mb-2">{{ $t('page.function.response') }}</NText>
          <NInput v-model:value="testResult" type="textarea" :placeholder="$t('page.function.responsePlaceholder')" :rows="10" readonly class="flex-1" />
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
