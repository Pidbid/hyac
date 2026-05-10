<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useClipboard } from '@vueuse/core';
import { NIcon, NSelect, useMessage } from 'naive-ui';
import {
  AddOutline,
  ClipboardOutline,
  CopyOutline,
  DocumentTextOutline,
  ReaderOutline,
  ReturnDownBackOutline,
  SendOutline,
  TrashBinOutline
} from '@vicons/ionicons5';
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

const testResultStatusCode = ref<number | null>(null);
const testResultHeaders = ref<Record<string, string> | null>(null);
const testResultContent = ref<string>($t('page.function.clickToSend'));

const activeTab = ref('params');
const activeResponseTab = ref<'body' | 'headers'>('body');

const handleTestRequest = async () => {
  const headers = testHeadersList.value.reduce(
    (acc, cur) => {
      if (cur.key) {
        acc[cur.key] = cur.value;
      }
      return acc;
    },
    {} as Record<string, string>
  );

  const query = testQueryParamsList.value.reduce(
    (acc, cur) => {
      if (cur.key) {
        acc[cur.key] = cur.value;
      }
      return acc;
    },
    {} as Record<string, string>
  );

  let body = {};
  if (testMethod.value === 'POST' && testJsonBody.value) {
    try {
      body = JSON.parse(testJsonBody.value);
    } catch {
      message.error($t('page.function.postFormatError'));
      return;
    }
  }

  try {
    testResultContent.value = $t('page.function.requesting');
    const response = await functionTest(props.functionAddress, testMethod.value, headers, query, body);
    if (response && response.data) {
      const { status_code, headers: responseHeaders, content } = response.data;
      testResultStatusCode.value = status_code;
      testResultHeaders.value = responseHeaders;
      try {
        const parsedContent = JSON.parse(content);
        testResultContent.value = JSON.stringify(parsedContent, null, 2);
      } catch {
        testResultContent.value = content;
      }
    } else {
      testResultStatusCode.value = null;
      testResultHeaders.value = null;
      testResultContent.value = $t('page.function.requestSuccessNoData');
    }
  } catch (error: any) {
    testResultStatusCode.value = error.response?.status || null;
    testResultHeaders.value = error.response?.headers || null;
    if (error.response) {
      testResultContent.value = `${$t('page.function.requestFailed')}\n${JSON.stringify(error.response.data, null, 2)}`;
    } else {
      testResultContent.value = `${$t('page.function.requestFailed')}\n${error.message}`;
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
    const content =
      activeResponseTab.value === 'body' ? testResultContent.value : JSON.stringify(testResultHeaders.value, null, 2);
    copy(content);
    message.success($t('page.function.responseCopied'));
  } else {
    message.error($t('page.function.copyFailed'));
  }
};

const statusCodeClass = computed(() => {
  if (!testResultStatusCode.value) return '';
  if (testResultStatusCode.value >= 200 && testResultStatusCode.value < 300) {
    return 'status-success';
  }
  if (testResultStatusCode.value >= 400) {
    return 'status-error';
  }
  return '';
});

watch(
  testMethod,
  newMethod => {
    const contentTypeHeader = { key: 'Content-Type', value: 'application/json', disabled: true };
    const existingContentTypeIndex = testHeadersList.value.findIndex(h => h.key === 'Content-Type');

    if (newMethod === 'POST') {
      if (existingContentTypeIndex === -1) {
        testHeadersList.value.unshift(contentTypeHeader);
      } else {
        testHeadersList.value[existingContentTypeIndex] = contentTypeHeader;
      }
    } else if (existingContentTypeIndex !== -1 && testHeadersList.value[existingContentTypeIndex].disabled) {
      testHeadersList.value.splice(existingContentTypeIndex, 1);
    }
  },
  { immediate: true }
);
</script>

<template>
  <div class="test-panel">
    <div class="address-bar">
      <div class="address-input" @click="handleCopyAddress">
        <span class="method-badge" :class="testMethod.toLowerCase()">{{ testMethod }}</span>
        <span class="address-text">{{ functionAddress }}</span>
        <NIcon :component="CopyOutline" :size="14" class="copy-icon" />
      </div>
    </div>

    <div class="method-selector">
      <button
        v-for="method in ['GET', 'POST']"
        :key="method"
        class="method-btn"
        :class="{ active: testMethod === method }"
        @click="testMethod = method"
      >
        {{ method }}
      </button>
    </div>

    <div class="config-tabs">
      <button
        v-for="tab in ['params', 'headers', 'body']"
        :key="tab"
        class="tab-btn"
        :class="{ active: activeTab === tab }"
        @click="activeTab = tab"
      >
        {{
          tab === 'params'
            ? $t('page.function.queryParameters')
            : tab === 'headers'
              ? 'Headers'
              : $t('page.function.bodyJson')
        }}
      </button>
    </div>

    <div class="config-content">
      <div v-if="activeTab === 'params'" class="params-section">
        <div v-for="(param, index) in testQueryParamsList" :key="index" class="param-row">
          <input v-model="param.key" :placeholder="$t('page.function.keyPlaceholder')" class="key param-input" />
          <input v-model="param.value" :placeholder="$t('page.function.valuePlaceholder')" class="param-input value" />
          <button class="remove-btn" @click="removeQueryParam(index)">
            <NIcon :component="TrashBinOutline" :size="14" />
          </button>
        </div>
        <button class="add-param-btn" @click="addQueryParam">
          <NIcon :component="AddOutline" :size="14" />
          <span>Query</span>
        </button>
      </div>

      <div v-if="activeTab === 'headers'" class="headers-section">
        <div v-for="(header, index) in testHeadersList" :key="index" class="header-row">
          <NSelect
            v-model:value="header.key"
            :options="[
              { label: 'User-Agent', value: 'User-Agent' },
              { label: 'Host', value: 'Host' },
              { label: 'Content-Type', value: 'Content-Type' },
              { label: 'Accept', value: 'Accept' },
              { label: 'Authorization', value: 'Authorization' }
            ]"
            :placeholder="$t('page.function.headerPlaceholder')"
            class="header-select"
            filterable
            tag
            :disabled="header.disabled"
            @update:value="value => handleHeaderSelect(value, index)"
          />
          <input
            v-model="header.value"
            :placeholder="$t('page.function.headerValuePlaceholder')"
            class="param-input value"
            :disabled="header.disabled"
          />
          <button v-if="!header.disabled" class="remove-btn" @click="removeHeader(index)">
            <NIcon :component="TrashBinOutline" :size="14" />
          </button>
        </div>
        <button class="add-param-btn" @click="addHeader">
          <NIcon :component="AddOutline" :size="14" />
          <span>Header</span>
        </button>
      </div>

      <div v-if="activeTab === 'body'" class="body-section">
        <textarea v-model="testJsonBody" class="body-editor" placeholder='{ "key": "value" }' spellcheck="false" />
      </div>
    </div>

    <button class="send-btn" @click="handleTestRequest">
      <NIcon :component="SendOutline" :size="16" />
      <span>{{ $t('page.function.sendRequest') }}</span>
    </button>

    <div class="response-section">
      <div class="response-header">
        <span class="response-title">
          <NIcon :component="ReturnDownBackOutline" :size="15" />
          <span>{{ $t('page.function.response') }}</span>
        </span>
        <span v-if="testResultStatusCode" class="status-code" :class="statusCodeClass">
          {{ testResultStatusCode }}
        </span>
      </div>
      <div class="response-tabs">
        <button class="tab-btn" :class="{ active: activeResponseTab === 'body' }" @click="activeResponseTab = 'body'">
          <NIcon :component="DocumentTextOutline" :size="14" />
          <span>Body</span>
        </button>
        <button
          class="tab-btn"
          :class="{ active: activeResponseTab === 'headers' }"
          @click="activeResponseTab = 'headers'"
        >
          <NIcon :component="ReaderOutline" :size="14" />
          <span>Headers</span>
        </button>
      </div>
      <div class="response-body">
        <pre class="response-content">{{
          activeResponseTab === 'body' ? testResultContent : JSON.stringify(testResultHeaders, null, 2)
        }}</pre>
        <button class="copy-result-btn" @click="handleCopyResult">
          <NIcon :component="activeResponseTab === 'body' ? CopyOutline : ClipboardOutline" :size="14" />
        </button>
      </div>
    </div>
  </div>
</template>

<style scoped>
.test-panel {
  height: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 12px;
  overflow: hidden;
  padding: 16px;
  gap: 12px;
  box-sizing: border-box;
}

.address-bar {
  display: flex;
  min-width: 0;
}

.address-input {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 10px 14px;
  background: #f5f5f7;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.address-input:hover {
  background: #ececee;
}

.method-badge {
  flex-shrink: 0;
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
  text-transform: uppercase;
}

.method-badge.get {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}

.method-badge.post {
  background: rgba(0, 122, 255, 0.12);
  color: #007aff;
}

.address-text {
  flex: 1;
  min-width: 0;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: #1d1d1f;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.copy-icon {
  color: #8e8e93;
  flex-shrink: 0;
}

.method-selector {
  display: flex;
  min-width: 0;
  gap: 4px;
  padding: 3px;
  background: #f5f5f7;
  border-radius: 8px;
}

.method-btn {
  flex: 1;
  min-width: 0;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 600;
  border-radius: 6px;
  background: transparent;
  color: #6e6e73;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.method-btn.active {
  background: #ffffff;
  color: #1d1d1f;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.config-tabs {
  display: flex;
  min-width: 0;
  gap: 2px;
  padding: 3px;
  background: #f5f5f7;
  border-radius: 8px;
}

.tab-btn {
  flex: 1;
  min-width: 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  gap: 5px;
  padding: 6px 12px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
  background: transparent;
  color: #6e6e73;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  text-transform: capitalize;
  line-height: 1;
}

.tab-btn :deep(.n-icon) {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  line-height: 1;
}

.tab-btn.active {
  background: #ffffff;
  color: #1d1d1f;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.config-content {
  flex: 1;
  min-height: 0;
  overflow-y: auto;
}

.params-section,
.headers-section {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.param-row,
.header-row {
  display: grid;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.param-row {
  grid-template-columns: minmax(0, 120px) minmax(0, 1fr) 28px;
}

.header-row {
  grid-template-columns: minmax(0, 140px) minmax(0, 1fr) 28px;
}

.param-input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 8px 12px;
  font-size: 13px;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 8px;
  background: #fafafa;
  color: #1d1d1f;
  transition: all 0.2s ease;
}

.param-input:focus {
  outline: none;
  border-color: #007aff;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}

.param-input.key {
  width: 100%;
}

.param-input.value {
  width: 100%;
}

.param-input:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.header-select {
  width: 100%;
  min-width: 0;
}

.remove-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: transparent;
  color: #ff3b30;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.remove-btn:hover {
  background: rgba(255, 59, 48, 0.1);
}

.add-param-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 6px;
  background: rgba(0, 122, 255, 0.06);
  color: #007aff;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  align-self: flex-end;
}

.add-param-btn:hover {
  background: rgba(0, 122, 255, 0.12);
}

.body-section {
  height: 100%;
}

.body-editor {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  height: 150px;
  padding: 12px;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  border: 1px solid rgba(0, 0, 0, 0.08);
  border-radius: 10px;
  background: #fafafa;
  color: #1d1d1f;
  resize: vertical;
  transition: all 0.2s ease;
}

.body-editor:focus {
  outline: none;
  border-color: #007aff;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}

.send-btn {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: center;
  gap: 8px;
  padding: 12px;
  font-size: 14px;
  font-weight: 600;
  border-radius: 10px;
  background: #007aff;
  color: white;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.send-btn:hover {
  background: #0066d6;
  transform: translateY(-1px);
  box-shadow: 0 4px 12px rgba(0, 122, 255, 0.3);
}

.send-btn:active {
  transform: translateY(0);
}

.response-section {
  flex: 1;
  min-height: 0;
  min-width: 0;
  display: flex;
  flex-direction: column;
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 10px;
  overflow: hidden;
}

.response-header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  background: #f9f9fb;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.response-title {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
  font-size: 12px;
  font-weight: 600;
  color: #1d1d1f;
}

.status-code {
  padding: 2px 8px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 4px;
}

.status-code.status-success {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}

.status-code.status-error {
  background: rgba(255, 59, 48, 0.12);
  color: #ff3b30;
}

.response-tabs {
  display: flex;
  min-width: 0;
  gap: 2px;
  padding: 6px 10px;
  background: #f9f9fb;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.response-body {
  flex: 1;
  min-height: 0;
  min-width: 0;
  position: relative;
  overflow: auto;
}

.response-content {
  min-width: 0;
  padding: 14px;
  font-size: 12px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  color: #1d1d1f;
  white-space: pre-wrap;
  word-break: break-all;
  margin: 0;
}

.copy-result-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: rgba(255, 255, 255, 0.9);
  color: #6e6e73;
  border: 1px solid rgba(0, 0, 0, 0.08);
  cursor: pointer;
  transition: all 0.2s ease;
  opacity: 0;
}

.response-body:hover .copy-result-btn {
  opacity: 1;
}

.copy-result-btn:hover {
  background: #ffffff;
  color: #007aff;
}
</style>
