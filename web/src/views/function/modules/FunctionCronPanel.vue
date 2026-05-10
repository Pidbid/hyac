<script setup lang="ts">
import { onMounted, reactive, ref, watch } from 'vue';
import { NIcon, NSelect, NSwitch, useDialog, useMessage } from 'naive-ui';
import { AddOutline, PlayOutline, SaveOutline, TrashOutline } from '@vicons/ionicons5';
import {
  deleteTaskForFunction,
  getTaskForFunction,
  triggerTaskForFunction,
  upsertTaskForFunction
} from '@/service/api';
import { useApplicationStore } from '@/store/modules/application';
import { $t } from '@/locales';

const props = defineProps<{
  func: Api.Function.FunctionInfo;
}>();

const message = useMessage();
const dialog = useDialog();
const applicationStore = useApplicationStore();
const isLoading = ref(true);
const taskExists = ref(false);

const formBody = ref('{}');
const queryParamsList = ref<{ key: string; value: string }[]>([{ key: '', value: '' }]);

const defaultFormData = () => ({
  name: `${props.func.name}-task`,
  trigger: 'interval' as Api.Scheduler.TriggerType,
  trigger_config: { seconds: 30 } as any,
  params: {},
  body: {},
  enabled: false,
  description: ''
});

const formData = reactive(defaultFormData());

const intervalValue = ref(30);
const intervalUnit = ref('seconds');
const cronValues = reactive({
  minute: '*',
  hour: '*',
  day: '*',
  month: '*',
  day_of_week: '*'
});

const resetState = () => {
  Object.assign(formData, defaultFormData());
  formBody.value = '{}';
  queryParamsList.value = [{ key: '', value: '' }];
  intervalValue.value = 30;
  intervalUnit.value = 'seconds';
  Object.assign(cronValues, {
    minute: '*',
    hour: '*',
    day: '*',
    month: '*',
    day_of_week: '*'
  });
  taskExists.value = false;
};

const fetchTask = async () => {
  if (!props.func.id) return;
  isLoading.value = true;
  const { data, error } = await getTaskForFunction(applicationStore.appId, props.func.id);
  if (!error) {
    if (data) {
      Object.assign(formData, data);
      formBody.value = JSON.stringify(data.body, null, 2);
      queryParamsList.value = Object.entries(data.params || {}).map(([key, value]) => ({ key, value: String(value) }));
      if (queryParamsList.value.length === 0) {
        queryParamsList.value.push({ key: '', value: '' });
      }
      taskExists.value = true;
      if (data.trigger === 'interval') {
        const unit = Object.keys(data.trigger_config)[0] || 'seconds';
        intervalUnit.value = unit;
        intervalValue.value = data.trigger_config[unit];
      } else if (data.trigger === 'cron') {
        Object.assign(cronValues, data.trigger_config);
      }
    } else {
      Object.assign(formData, defaultFormData());
      formBody.value = '{}';
      queryParamsList.value = [{ key: '', value: '' }];
      taskExists.value = false;
    }
  } else {
    message.error($t('page.function.fetchTasksFailed'));
  }
  isLoading.value = false;
};

const handleSave = async () => {
  try {
    formData.body = JSON.parse(formBody.value);
    formData.params = queryParamsList.value.reduce(
      (acc, cur) => {
        if (cur.key) {
          acc[cur.key] = cur.value;
        }
        return acc;
      },
      {} as Record<string, string>
    );
  } catch {
    message.error($t('page.function.invalidJsonFormat'));
    return;
  }

  if (formData.trigger === 'interval') {
    formData.trigger_config = { [intervalUnit.value]: intervalValue.value };
  } else {
    formData.trigger_config = { ...cronValues };
  }

  isLoading.value = true;
  const upsertData = { ...formData, appId: applicationStore.appId, functionId: props.func.id };
  const { error } = await upsertTaskForFunction(upsertData);
  if (!error) {
    message.success($t('common.saveSuccess'));
    await fetchTask();
  } else {
    message.error($t('common.saveFailed'));
  }
  isLoading.value = false;
};

const handleDelete = () => {
  dialog.warning({
    title: $t('page.function.confirmDeleteTask'),
    content: $t('page.function.deleteConfirm', { name: formData.name }),
    positiveText: $t('common.delete'),
    negativeText: $t('common.cancel'),
    onPositiveClick: async () => {
      isLoading.value = true;
      const { error } = await deleteTaskForFunction(applicationStore.appId, props.func.id);
      if (!error) {
        message.success($t('common.deleteSuccess'));
        await fetchTask();
      } else {
        message.error($t('common.deleteFailed'));
      }
      isLoading.value = false;
    }
  });
};

const handleTrigger = async () => {
  isLoading.value = true;
  const { error } = await triggerTaskForFunction(applicationStore.appId, props.func.id);
  if (!error) {
    message.success($t('page.function.taskTriggered'));
  } else {
    message.error($t('page.function.taskTriggerFailed'));
  }
  isLoading.value = false;
};

const addQueryParam = () => {
  if (queryParamsList.value.some(p => p.key === '')) {
    message.warning($t('page.function.fillBlankQuery'));
    return;
  }
  queryParamsList.value.push({ key: '', value: '' });
};

const removeQueryParam = (index: number) => {
  queryParamsList.value.splice(index, 1);
};

onMounted(() => {
  fetchTask();
});

watch(
  () => props.func.id,
  () => {
    resetState();
    fetchTask();
  }
);
</script>

<template>
  <div class="cron-panel">
    <div class="cron-header">
      <h3 class="cron-title">{{ $t('page.function.cronJobs') }}</h3>
      <div v-if="!taskExists" class="status-badge warning">
        {{ $t('page.function.taskNotCreated') }}
      </div>
      <div v-else class="status-badge success">
        {{ formData.enabled ? 'Active' : 'Inactive' }}
      </div>
    </div>

    <div class="cron-content" :class="{ loading: isLoading }">
      <div class="form-section">
        <label class="form-label">{{ $t('page.function.taskName') }}</label>
        <input v-model="formData.name" class="form-input" :placeholder="$t('page.function.taskNamePlaceholder')" />
      </div>

      <div class="form-section">
        <label class="form-label">{{ $t('page.function.triggerType') }}</label>
        <div class="trigger-selector">
          <button
            class="trigger-btn"
            :class="{ active: formData.trigger === 'interval' }"
            @click="formData.trigger = 'interval'"
          >
            {{ $t('page.function.intervalTrigger') }}
          </button>
          <button
            class="trigger-btn"
            :class="{ active: formData.trigger === 'cron' }"
            @click="formData.trigger = 'cron'"
          >
            {{ $t('page.function.cronTrigger') }}
          </button>
        </div>
      </div>

      <div v-if="formData.trigger === 'interval'" class="form-section">
        <label class="form-label">{{ $t('page.function.intervalSettings') }}</label>
        <div class="interval-config">
          <input v-model.number="intervalValue" type="number" min="1" class="form-input small" />
          <NSelect
            v-model:value="intervalUnit"
            :options="
              ['seconds', 'minutes', 'hours', 'days'].map(u => ({ label: $t(`page.function.units.${u}`), value: u }))
            "
            class="unit-select"
          />
        </div>
      </div>

      <div v-if="formData.trigger === 'cron'" class="form-section">
        <label class="form-label">{{ $t('page.function.cronSettings') }}</label>
        <div class="cron-config">
          <div class="cron-field">
            <input
              v-model="cronValues.minute"
              class="form-input cron-input"
              :placeholder="$t('page.function.cronPlaceholders.minute')"
            />
            <span class="cron-label">{{ $t('page.function.units.minutes') }}</span>
          </div>
          <div class="cron-field">
            <input
              v-model="cronValues.hour"
              class="form-input cron-input"
              :placeholder="$t('page.function.cronPlaceholders.hour')"
            />
            <span class="cron-label">{{ $t('page.function.units.hours') }}</span>
          </div>
          <div class="cron-field">
            <input
              v-model="cronValues.day"
              class="form-input cron-input"
              :placeholder="$t('page.function.cronPlaceholders.day')"
            />
            <span class="cron-label">{{ $t('page.function.units.days') }}</span>
          </div>
          <div class="cron-field">
            <input
              v-model="cronValues.month"
              class="form-input cron-input"
              :placeholder="$t('page.function.cronPlaceholders.month')"
            />
            <span class="cron-label">{{ $t('page.function.units.months') }}</span>
          </div>
          <div class="cron-field">
            <input
              v-model="cronValues.day_of_week"
              class="form-input cron-input"
              :placeholder="$t('page.function.cronPlaceholders.day_of_week')"
            />
            <span class="cron-label">{{ $t('page.function.units.day_of_week') }}</span>
          </div>
        </div>
      </div>

      <div class="form-section">
        <label class="form-label">{{ $t('page.function.queryParameters') }}</label>
        <div class="params-list">
          <div v-for="(param, index) in queryParamsList" :key="index" class="param-row">
            <input v-model="param.key" :placeholder="$t('page.function.keyPlaceholder')" class="form-input key" />
            <input v-model="param.value" :placeholder="$t('page.function.valuePlaceholder')" class="form-input value" />
            <button class="remove-btn" @click="removeQueryParam(index)">
              <NIcon :component="TrashOutline" :size="14" />
            </button>
          </div>
          <button class="add-btn" @click="addQueryParam">
            <NIcon :component="AddOutline" :size="14" />
            <span>Query</span>
          </button>
        </div>
      </div>

      <div class="form-section">
        <label class="form-label">{{ $t('page.function.requestBody') }}</label>
        <textarea v-model="formBody" class="form-textarea" placeholder='{ "key": "value" }' />
      </div>

      <div class="form-section">
        <label class="form-label">{{ $t('page.function.taskDescription') }}</label>
        <textarea v-model="formData.description" class="form-textarea small" />
      </div>

      <div class="form-section inline">
        <label class="form-label">{{ $t('common.enable') }}</label>
        <NSwitch v-model:value="formData.enabled" />
      </div>
    </div>

    <div class="cron-actions">
      <button class="action-btn primary" @click="handleSave">
        <NIcon :component="SaveOutline" :size="16" />
        <span>{{ $t('common.save') }}</span>
      </button>
      <button class="action-btn success" :disabled="!taskExists" @click="handleTrigger">
        <NIcon :component="PlayOutline" :size="16" />
        <span>{{ $t('common.trigger') }}</span>
      </button>
      <button class="action-btn danger" :disabled="!taskExists" @click="handleDelete">
        <NIcon :component="TrashOutline" :size="16" />
        <span>{{ $t('common.delete') }}</span>
      </button>
    </div>
  </div>
</template>

<style scoped>
.cron-panel {
  height: 100%;
  min-width: 0;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 12px;
  overflow: hidden;
  box-sizing: border-box;
}

.cron-header {
  display: flex;
  min-width: 0;
  align-items: center;
  justify-content: space-between;
  padding: 14px 16px;
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.cron-title {
  min-width: 0;
  font-size: 15px;
  font-weight: 600;
  color: #1d1d1f;
  margin: 0;
}

.status-badge {
  padding: 3px 10px;
  font-size: 11px;
  font-weight: 600;
  border-radius: 6px;
}

.status-badge.warning {
  background: rgba(255, 149, 0, 0.12);
  color: #ff9500;
}

.status-badge.success {
  background: rgba(52, 199, 89, 0.12);
  color: #34c759;
}

.cron-content {
  flex: 1;
  min-width: 0;
  overflow-y: auto;
  padding: 16px;
  display: flex;
  flex-direction: column;
  gap: 16px;
  opacity: 1;
  transition: opacity 0.2s ease;
}

.cron-content.loading {
  opacity: 0.6;
  pointer-events: none;
}

.form-section {
  display: flex;
  flex-direction: column;
  gap: 6px;
  min-width: 0;
}

.form-section.inline {
  flex-direction: row;
  align-items: center;
  gap: 12px;
}

.form-label {
  font-size: 12px;
  font-weight: 600;
  color: #6e6e73;
  text-transform: uppercase;
  letter-spacing: 0.02em;
}

.form-input {
  width: 100%;
  min-width: 0;
  box-sizing: border-box;
  padding: 10px 12px;
  font-size: 14px;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  background: #fafafa;
  color: #1d1d1f;
  transition: all 0.2s ease;
}

.form-input:focus {
  outline: none;
  border-color: #007aff;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}

.form-input.small {
  width: 100px;
}

.form-input.cron-input {
  width: 80px;
  text-align: center;
}

.trigger-selector {
  display: flex;
  min-width: 0;
  gap: 4px;
  padding: 3px;
  background: #f5f5f7;
  border-radius: 8px;
}

.trigger-btn {
  flex: 1;
  min-width: 0;
  padding: 8px 12px;
  font-size: 13px;
  font-weight: 500;
  border-radius: 6px;
  background: transparent;
  color: #6e6e73;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.trigger-btn.active {
  background: #ffffff;
  color: #1d1d1f;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.08);
}

.interval-config {
  display: flex;
  min-width: 0;
  gap: 8px;
  align-items: center;
}

.unit-select {
  flex: 1;
  min-width: 0;
}

.cron-config {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  min-width: 0;
}

.cron-field {
  display: flex;
  align-items: center;
  gap: 4px;
}

.cron-label {
  font-size: 11px;
  color: #8e8e93;
}

.params-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
  min-width: 0;
}

.param-row {
  display: grid;
  grid-template-columns: minmax(0, 120px) minmax(0, 1fr) 28px;
  gap: 8px;
  align-items: center;
  min-width: 0;
}

.form-input.key {
  width: 100%;
}

.form-input.value {
  width: 100%;
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

.add-btn {
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

.add-btn:hover {
  background: rgba(0, 122, 255, 0.12);
}

.form-textarea {
  width: 100%;
  max-width: 100%;
  box-sizing: border-box;
  min-height: 80px;
  padding: 10px 12px;
  font-size: 13px;
  font-family: 'SF Mono', 'Fira Code', monospace;
  border: 1px solid rgba(0, 0, 0, 0.1);
  border-radius: 8px;
  background: #fafafa;
  color: #1d1d1f;
  resize: vertical;
  transition: all 0.2s ease;
}

.form-textarea:focus {
  outline: none;
  border-color: #007aff;
  background: #ffffff;
  box-shadow: 0 0 0 3px rgba(0, 122, 255, 0.12);
}

.form-textarea.small {
  min-height: 60px;
}

.cron-actions {
  display: flex;
  min-width: 0;
  gap: 8px;
  padding: 14px 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.action-btn {
  flex: 1;
  min-width: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  padding: 10px 16px;
  font-size: 13px;
  font-weight: 600;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.action-btn span {
  min-width: 0;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.action-btn.primary {
  background: #007aff;
  color: white;
}

.action-btn.primary:hover:not(:disabled) {
  background: #0066d6;
}

.action-btn.success {
  background: #34c759;
  color: white;
}

.action-btn.success:hover:not(:disabled) {
  background: #2db84e;
}

.action-btn.danger {
  background: #ff3b30;
  color: white;
}

.action-btn.danger:hover:not(:disabled) {
  background: #e0332a;
}
</style>
