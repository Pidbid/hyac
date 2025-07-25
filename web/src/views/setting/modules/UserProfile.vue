<script setup lang="ts">
import { reactive, computed } from 'vue';
import { NCard, NForm, NFormItem, NInput, NButton, useMessage, NIcon, useDialog } from 'naive-ui';
import { SaveOutline } from '@vicons/ionicons5';
import { useRouter } from 'vue-router';
import { $t } from '@/locales';
import { fetchUpdateMe } from '@/service/api';
import { localStg } from '@/utils/storage';
import { useFormRules, useNaiveForm } from '@/hooks/common/form';
import { useAppStore } from '@/store/modules/app';

 defineOptions({
   name: 'UserProfile'
});

const message = useMessage();
const dialog = useDialog();
const router = useRouter();
const appStore = useAppStore();

 const { formRef, validate } = useNaiveForm();

interface FormModel {
  username: string;
  password: string;
  confirmPassword: string;
}

const model: FormModel = reactive({
  username: '',
  password: '',
  confirmPassword: ''
});

const rules = computed<Record<keyof FormModel, App.Global.FormRule[]>>(() => {
  const { patternRules } = useFormRules();

  return {
    username: [patternRules.userName],
    password: [patternRules.pwd],
    confirmPassword: [
      {
        validator: (_rule: any, value: string) => {
          if (model.password) {
            if (!value) {
              return new Error($t('form.confirmPwd.required'));
            }
            if (value !== model.password) {
              return new Error($t('page.setting.userProfile.passwordsDoNotMatch'));
            }
          }
          return true;
        },
        trigger: ['blur', 'input']
      }
    ]
  };
});

const handleUpdate = async (payload: Api.Auth.UpdateMePayload) => {
  const { error } = await fetchUpdateMe(payload);
  if (!error) {
    message.success($t('common.updateSuccess'));
    model.password = ''; // Clear password after successful update
    model.confirmPassword = '';
    localStg.remove('token');
    localStg.remove('refreshToken');
    router.push('/login');
  }
};

const handleValidateClick = async () => {
  await validate();

  const payload: Api.Auth.UpdateMePayload = {};
  if (model.username) {
    payload.username = model.username;
  }
  if (model.password && model.password === model.confirmPassword) {
    payload.password = model.password;
  }

  if (Object.keys(payload).length === 0) {
    message.warning($t('page.setting.userProfile.noChanges'));
    return;
  }

  dialog.warning({
    title: $t('common.warning'),
    content: $t('page.setting.userProfile.confirmUpdate'),
    positiveText: $t('common.confirm'),
    negativeText: $t('common.cancel'),
    onPositiveClick: () => handleUpdate(payload)
  });
};
</script>

<template>
  <NCard :title="$t('page.setting.userProfile.title')">
    <NForm ref="formRef" :model="model" :rules="rules" label-placement="left" label-width="auto">
      <NFormItem :label="$t('page.setting.userProfile.username')" path="username">
        <NInput
          v-model:value="model.username"
          :placeholder="$t('page.setting.userProfile.usernamePlaceholder')"
          :disabled="appStore.isDemoMode"
        />
        <template #feedback>
          <div class="text-xs text-gray-400">{{ $t('page.setting.userProfile.usernameHelp') }}</div>
        </template>
      </NFormItem>
      <NFormItem :label="$t('page.setting.userProfile.password')" path="password">
        <NInput
          v-model:value="model.password"
          type="password"
          show-password-on="mousedown"
          :placeholder="$t('page.setting.userProfile.passwordPlaceholder')"
          :disabled="appStore.isDemoMode"
        />
        <template #feedback>
          <div class="text-xs text-gray-400">{{ $t('page.setting.userProfile.passwordHelp') }}</div>
        </template>
      </NFormItem>
      <NFormItem :label="$t('page.setting.userProfile.confirmPassword')" path="confirmPassword">
        <NInput
          v-model:value="model.confirmPassword"
          type="password"
          show-password-on="mousedown"
          :placeholder="$t('page.setting.userProfile.confirmPasswordPlaceholder')"
          :disabled="appStore.isDemoMode"
        />
      </NFormItem>
      <NFormItem>
        <NButton type="primary" :disabled="appStore.isDemoMode" @click="handleValidateClick">
          <template #icon>
            <NIcon :component="SaveOutline" />
          </template>
          {{ $t('common.save') }}
        </NButton>
      </NFormItem>
    </NForm>
  </NCard>
</template>

<style scoped></style>
