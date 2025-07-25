<script setup lang="ts">
import { onMounted, reactive, computed } from 'vue';
import { loginModuleRecord } from '@/constants/app';
import { fetchCaptcha } from '@/service/api/auth';
import { useAuthStore } from '@/store/modules/auth';
import { useRouterPush } from '@/hooks/common/router';
import { useFormRules, useNaiveForm } from '@/hooks/common/form';
import { $t } from '@/locales';

defineOptions({
  name: 'PwdLogin'
});

const authStore = useAuthStore();
const { toggleLoginModule } = useRouterPush();
const { formRef, validate } = useNaiveForm();

interface FormModel {
  username: string;
  password: string;
  captcha: string;
}

const model: FormModel = reactive({
  username: '',
  password: '',
  captcha: ''
});

interface CaptchaModel {
  image: string;
  loading: boolean;
}
const captcha: CaptchaModel = reactive({
  image: '',
  loading: true
});

const rules = computed<Record<keyof FormModel, App.Global.FormRule[]>>(() => {
  // inside computed to make locale reactive, if not apply i18n, you can define it without computed
  const { formRules } = useFormRules();

  return {
    username: formRules.userName,
    password: formRules.pwd,
    captcha: [{ required: true, message: '请输入验证码' }]
  };
});

async function handleSubmit() {
  await validate();
  const success = await authStore.login(model.username, model.password, model.captcha);
  if (!success) {
    model.username = '';
    model.password = '';
    model.captcha = '';
    await fetchCaptchaImage();
  }
}

type AccountKey = 'super' | 'admin' | 'user';

interface Account {
  key: AccountKey;
  label: string;
  username: string;
  password: string;
}

async function fetchCaptchaImage() {
  captcha.loading = true;
  const { data, error } = await fetchCaptcha();
  if (!error) {
    captcha.image = data;
  }
  captcha.loading = false;
}

onMounted(async () => {
  await fetchCaptchaImage();
});
</script>

<template>
  <NForm ref="formRef" :model="model" :rules="rules" size="large" :show-label="false" @keyup.enter="handleSubmit">
    <NFormItem path="username">
      <NInput v-model:value="model.username" :placeholder="$t('page.login.common.userNamePlaceholder')" />
    </NFormItem>
    <NFormItem path="password">
      <NInput v-model:value="model.password" type="password" show-password-on="click"
        :placeholder="$t('page.login.common.passwordPlaceholder')" />
    </NFormItem>
    <NFormItem path="captcha">
      <NGrid cols="4">
        <NGi :span="3">
          <NInput v-model:value="model.captcha" :placeholder="$t('page.login.common.captchaPlaceholder')" />
        </NGi>
        <NGi>
          <div v-if="captcha.loading" class="flex-center h-full bg-gray-100/40">
            <NSpin :show="true" />
          </div>
          <NImage
            v-else
            :src="captcha.image"
            :width="200"
            :height="40"
            :preview-disabled="true"
            @click="fetchCaptchaImage"
          />
        </NGi>
      </NGrid>
    </NFormItem>
    <NSpace vertical :size="24">
      <div class="flex-y-center justify-between">
        <NCheckbox>{{ $t('page.login.pwdLogin.rememberMe') }}</NCheckbox>
        <!-- <NButton quaternary @click="toggleLoginModule('reset-pwd')">
          {{ $t('page.login.pwdLogin.forgetPassword') }}
        </NButton> -->
      </div>
      <NButton type="primary" size="large" round block :loading="authStore.loginLoading" @click="handleSubmit">
        {{ $t('common.confirm') }}
      </NButton>
      <!-- <div class="flex-y-center justify-between gap-12px">
        <NButton class="flex-1" block @click="toggleLoginModule('code-login')">
          {{ $t(loginModuleRecord['code-login']) }}
        </NButton>
        <NButton class="flex-1" block @click="toggleLoginModule('register')">
          {{ $t(loginModuleRecord.register) }}
        </NButton>
      </div>
      <NDivider class="text-14px text-#666 !m-0">{{ $t('page.login.pwdLogin.otherAccountLogin') }}</NDivider>
      <div class="flex-center gap-12px">
        <NButton v-for="item in accounts" :key="item.key" type="primary" @click="handleAccountLogin(item)">
          {{ item.label }}
        </NButton>
      </div> -->
    </NSpace>
  </NForm>
</template>

<style scoped></style>
