<script setup lang="ts">
import { ref, watch, nextTick } from 'vue';
import { NCard, NButton, NIcon } from 'naive-ui';
import { CheckmarkOutline, SaveOutline, InformationCircleOutline, BrushOutline, CreateOutline } from '@vicons/ionicons5';
import { $t } from '@/locales';
import Editor from './editor.vue'; // 假设 editor.vue 在同一目录下

interface editorConfigT {
  language: string;
  fontSize: number;
  minimap: boolean;
  theme: "github-light" | "github-dark";
}

const props = defineProps<{
  func: Api.Function.FunctionInfo;
  codeChanged: boolean;
  editorConfig:editorConfigT;
  isSaving: boolean;
}>();

const emit = defineEmits(['save-code', 'open-history', 'update:code', 'open-editor-settings', 'edit-meta']);


const editorConfig = ref({
  language: 'python',
  fontSize: 14,
  minimap: true,
  theme: 'github-light'
});


</script>

<template>
  <NCard :bordered="false" size="small" class="h-full flex-1"
    :content-style="{ padding: '0px', display: 'flex', flexDirection: 'column' }">
    <template #header>
      <div class="flex flex-col">
        <div class="flex flex-row items-center">
          <span class="text-lg">{{ func.name || $t('page.function.functionEditor') }}</span>
          <NButton quaternary circle size="small" @click="emit('edit-meta')" class="ml-2">
            <template #icon>
              <NIcon :component="CreateOutline" />
            </template>
          </NButton>
        </div>
        <span class="text-sm text-gray-500">{{ func.description }}</span>
      </div>
    </template>
    <template #header-extra>
      <div class="flex flex-row gap-2 items-center">
        <NButton :type="codeChanged ? 'primary' : 'default'" size="small" @click="emit('save-code')" :loading="props.isSaving" :disabled="!props.codeChanged || props.isSaving">
          <template #icon>
            <NIcon :component="codeChanged ? CheckmarkOutline : SaveOutline" />
          </template>
          {{ codeChanged ? $t('page.function.publish') : $t('page.function.published') }}
        </NButton>
        <NButton type="default" size="small" @click="emit('open-history')">
          <template #icon>
            <NIcon :component="InformationCircleOutline" />
          </template>
        </NButton>
        <NButton type="default" size="small" @click="emit('open-editor-settings')">
          <template #icon>
            <NIcon :component="BrushOutline" />
          </template>
        </NButton>
      </div>
    </template>
    <div class="flex-1 min-h-0">
      <Editor :model-value="func.code" @update:modelValue="$emit('update:code', $event)"
        :language="props.editorConfig.language" :font-size="props.editorConfig.fontSize" :minimap="props.editorConfig.minimap" :theme="props.editorConfig.theme" />
    </div>
  </NCard>
</template>

<style scoped>
</style>
