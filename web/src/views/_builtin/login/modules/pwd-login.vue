<script setup lang="ts">
import { computed, onMounted, reactive } from 'vue';
import { fetchCaptcha } from '@/service/api/auth';
import { useAuthStore } from '@/store/modules/auth';
import { useThemeStore } from '@/store/modules/theme';
import { useFormRules, useNaiveForm } from '@/hooks/common/form';
import { $t } from '@/locales';

defineOptions({
  name: 'PwdLogin'
});

const authStore = useAuthStore();
const themeStore = useThemeStore();
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
    <NFormItem path="username" class="form-item">
      <NInput
        v-model:value="model.username"
        :placeholder="$t('page.login.common.userNamePlaceholder')"
        :input-props="{ autocomplete: 'username' }"
      />
    </NFormItem>

    <NFormItem path="password" class="form-item">
      <NInput
        v-model:value="model.password"
        type="password"
        show-password-on="click"
        :placeholder="$t('page.login.common.passwordPlaceholder')"
        :input-props="{ autocomplete: 'current-password' }"
      />
    </NFormItem>

    <NFormItem path="captcha" class="form-item">
      <div class="w-full flex items-center gap-12px">
        <NInput
          v-model:value="model.captcha"
          :placeholder="$t('page.login.common.captchaPlaceholder')"
          class="flex-1"
        />
        <div
          class="captcha-box h-40px w-120px flex-shrink-0 cursor-pointer overflow-hidden rounded-10px"
          :class="themeStore.darkMode ? 'bg-white/6' : 'bg-black/3'"
          @click="fetchCaptchaImage"
        >
          <div v-if="captcha.loading" class="size-full flex-center">
            <NSpin :show="true" :size="16" />
          </div>
          <NImage v-else :src="captcha.image" :width="120" :height="40" :preview-disabled="true" object-fit="cover" />
        </div>
      </div>
    </NFormItem>

    <NButton
      type="primary"
      size="large"
      block
      :loading="authStore.loginLoading"
      class="submit-btn"
      @click="handleSubmit"
    >
      {{ $t('route.login') }}
    </NButton>
  </NForm>
</template>

<style scoped>
.form-item {
  margin-bottom: 14px;
}

.form-item:last-of-type {
  margin-bottom: 20px;
}

:deep(.n-input) {
  border-radius: 10px;
  transition: all 0.2s ease;
}

:deep(.n-input--focus) {
  box-shadow: 0 0 0 4px rgba(0, 122, 255, 0.12);
}

:deep(.n-input__border) {
  transition: border-color 0.2s ease;
}

.captcha-box {
  border: 1px solid v-bind(themeStore.darkMode ? 'rgba(255,255,255,0.12)': 'rgba(0,0,0,0.08)');
  transition: border-color 0.2s ease;
}

.captcha-box:hover {
  border-color: v-bind(themeStore.darkMode ? 'rgba(255,255,255,0.2)': 'rgba(0,0,0,0.15)');
}

.submit-btn {
  height: 44px;
  border-radius: 10px;
  font-size: 16px;
  font-weight: 500;
  background-color: #007aff;
  border: none;
  transition:
    background-color 0.15s ease,
    transform 0.15s ease;
}

.submit-btn:hover {
  background-color: #0071e3;
}

.submit-btn:active {
  background-color: #006edb;
  transform: scale(0.98);
}
</style>
