<script setup lang="ts">
import { NButton, NCard, NIcon } from 'naive-ui';
import {
  BrushOutline,
  CheckmarkOutline,
  CreateOutline,
  InformationCircleOutline,
  SaveOutline
} from '@vicons/ionicons5';
import { $t } from '@/locales';
import EditorMonaco from './EditorMonaco.vue';

interface editorConfigT {
  language: string;
  fontSize: number;
  minimap: boolean;
  themeName: string;
  lineNumbers: boolean;
}

const props = defineProps<{
  func: Api.Function.FunctionInfo;
  codeChanged: boolean;
  editorConfig: editorConfigT;
  isSaving: boolean;
}>();

const emit = defineEmits(['save-code', 'open-history', 'update:code', 'open-editor-settings', 'edit-meta']);
</script>

<template>
  <NCard
    :bordered="false"
    size="small"
    class="h-full flex-1"
    :content-style="{ padding: '0px', display: 'flex', flexDirection: 'column', position: 'relative' }"
  >
    <template #header>
      <div class="flex flex-col">
        <div class="flex flex-row items-center">
          <span class="text-lg">{{ func.name || $t('page.function.functionEditor') }}</span>
          <NButton quaternary circle size="small" class="ml-2" @click="emit('edit-meta')">
            <template #icon>
              <NIcon :component="CreateOutline" />
            </template>
          </NButton>
        </div>
        <span class="text-sm text-gray-500">{{ func.description }}</span>
      </div>
    </template>
    <template #header-extra>
      <div class="flex flex-row items-center gap-2">
        <NButton
          :type="codeChanged ? 'primary' : 'default'"
          size="small"
          :loading="props.isSaving"
          :disabled="!props.codeChanged || props.isSaving"
          @click="emit('save-code')"
        >
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
    <EditorMonaco
      :key="func.id"
      :code="func.code"
      :show-minimap="editorConfig.minimap"
      :font-size="editorConfig.fontSize"
      :theme-name="editorConfig.themeName"
      :tab-size="4"
      :show-line-numbers="editorConfig.lineNumbers"
      @update:code="$emit('update:code', $event)"
    />
  </NCard>
</template>

<style scoped></style>
