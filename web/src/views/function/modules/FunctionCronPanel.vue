<script setup lang="ts">
import { ref, onMounted, reactive, watch } from 'vue';
import { NButton, NIcon, NSpace, useDialog, useMessage, NForm, NFormItem, NInput, NSelect, NSwitch, NCard, NSpin, NInputNumber, NDivider, NInputGroup, NInputGroupLabel, NText, NTag } from 'naive-ui';
import { SaveOutline, TrashOutline, PlayOutline, AddOutline } from '@vicons/ionicons5';
import { getTaskForFunction, upsertTaskForFunction, deleteTaskForFunction, triggerTaskForFunction } from '@/service/api';
import { $t } from '@/locales';
import { useApplicationStore } from '@/store/modules/application';

const props = defineProps<{
  func: Api.Function.FunctionInfo;
}>();

const message = useMessage();
const dialog = useDialog();
const applicationStore = useApplicationStore();
const isLoading = ref(true);
const taskExists = ref(false);
const formRef = ref<any>(null);

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
      taskExists.value = false; // Still false, but we will show the form
    }
  } else {
    message.error($t('page.function.fetchTasksFailed'));
  }
  isLoading.value = false;
};

const handleSave = async () => {
  formRef.value?.validate(async (errors: any) => {
    if (errors) return;

    try {
      formData.body = JSON.parse(formBody.value);
      formData.params = queryParamsList.value.reduce((acc, cur) => {
        if (cur.key) {
          acc[cur.key] = cur.value;
        }
        return acc;
      }, {} as Record<string, string>);
    } catch (e) {
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
  });
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

const rules = {
  name: { required: true, message: $t('page.function.taskNamePlaceholder'), trigger: 'blur' },
};

onMounted(() => {
  fetchTask();
});

watch(() => props.func.id, () => {
  resetState();
  fetchTask();
});

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

</script>

<template>
  <NCard :title="$t('page.function.cronJobs')" class="h-full">
    <template #header-extra>
      <NTag v-if="!taskExists" type="warning" size="small">
        {{ $t('page.function.taskNotCreated') }}
      </NTag>
    </template>
    <NSpin :show="isLoading">
      <NForm ref="formRef" :model="formData" :rules="rules" label-placement="left" label-width="auto">
        <NFormItem :label="$t('page.function.taskName')" path="name">
          <NInput v-model:value="formData.name" />
        </NFormItem>
        <NFormItem :label="$t('page.function.triggerType')">
          <NSelect v-model:value="formData.trigger" :options="[{ label: $t('page.function.intervalTrigger'), value: 'interval' }, { label: $t('page.function.cronTrigger'), value: 'cron' }]" />
        </NFormItem>

        <!-- Interval Trigger -->
        <NFormItem v-if="formData.trigger === 'interval'" :label="$t('page.function.intervalSettings')">
          <NInputGroup>
            <NInputNumber v-model:value="intervalValue" :min="1" style="width: 150px" />
            <NSelect v-model:value="intervalUnit" :options="['seconds', 'minutes', 'hours', 'days'].map(u => ({label: $t(`page.function.units.${u}`), value: u}))" style="width: 120px" />
          </NInputGroup>
        </NFormItem>

        <!-- Cron Trigger -->
        <NFormItem v-if="formData.trigger === 'cron'" :label="$t('page.function.cronSettings')">
          <NSpace>
            <NInputGroup style="width: 120px;">
              <NInput v-model:value="cronValues.minute" :placeholder="$t('page.function.cronPlaceholders.minute')" />
              <NInputGroupLabel>{{ $t('page.function.units.minutes') }}</NInputGroupLabel>
            </NInputGroup>
            <NInputGroup style="width: 120px;">
              <NInput v-model:value="cronValues.hour" :placeholder="$t('page.function.cronPlaceholders.hour')" />
              <NInputGroupLabel>{{ $t('page.function.units.hours') }}</NInputGroupLabel>
            </NInputGroup>
            <NInputGroup style="width: 120px;">
              <NInput v-model:value="cronValues.day" :placeholder="$t('page.function.cronPlaceholders.day')" />
              <NInputGroupLabel>{{ $t('page.function.units.days') }}</NInputGroupLabel>
            </NInputGroup>
            <NInputGroup style="width: 120px;">
              <NInput v-model:value="cronValues.month" :placeholder="$t('page.function.cronPlaceholders.month')" />
              <NInputGroupLabel>{{ $t('page.function.units.months') }}</NInputGroupLabel>
            </NInputGroup>
            <NInputGroup style="width: 120px;">
              <NInput v-model:value="cronValues.day_of_week" :placeholder="$t('page.function.cronPlaceholders.day_of_week')" />
              <NInputGroupLabel>{{ $t('page.function.units.day_of_week') }}</NInputGroupLabel>
            </NInputGroup>
          </NSpace>
        </NFormItem>

        <NFormItem :label="$t('page.function.queryParameters')">
          <div class="w-full flex flex-col gap-2">
            <div v-for="(param, index) in queryParamsList" :key="index" class="flex gap-2 items-center">
              <NInput v-model:value="param.key" :placeholder="$t('page.function.keyPlaceholder')" />
              <NInput v-model:value="param.value" :placeholder="$t('page.function.valuePlaceholder')" />
              <NButton quaternary circle @click="removeQueryParam(index)">
                <template #icon>
                  <NIcon :component="TrashOutline" />
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
        </NFormItem>
        <NFormItem :label="$t('page.function.requestBody')">
          <NInput type="textarea" v-model:value="formBody" placeholder='{ "key": "value" }' resizable />
        </NFormItem>
        <NFormItem :label="$t('page.function.taskDescription')">
          <NInput type="textarea" v-model:value="formData.description" />
        </NFormItem>
        <NFormItem :label="$t('common.enable')">
          <NSwitch v-model:value="formData.enabled" />
        </NFormItem>
        <NDivider />
        <NSpace justify="end">
          <NButton type="primary" @click="handleSave">
            <template #icon><NIcon :component="SaveOutline" /></template>
            {{ $t('common.save') }}
          </NButton>
          <NButton type="success" @click="handleTrigger" :disabled="!taskExists">
            <template #icon><NIcon :component="PlayOutline" /></template>
            {{ $t('common.trigger') }}
          </NButton>
          <NButton type="error" @click="handleDelete" :disabled="!taskExists">
            <template #icon><NIcon :component="TrashOutline" /></template>
            {{ $t('common.delete') }}
          </NButton>
        </NSpace>
      </NForm>
    </NSpin>
  </NCard>
</template>
