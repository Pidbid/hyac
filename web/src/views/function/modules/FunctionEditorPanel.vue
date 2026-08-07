<script setup lang="ts">
import { ref } from 'vue';
import { NIcon } from 'naive-ui';
import {
  BrushOutline,
  CheckmarkOutline,
  CreateOutline,
  InformationCircleOutline,
  SaveOutline
} from '@vicons/ionicons5';
import { $t } from '@/locales';
import EditorMonaco from './EditorMonaco.vue';

const editorMonacoRef = ref<InstanceType<typeof EditorMonaco> | null>(null);

defineExpose({
  layoutEditor() {
    editorMonacoRef.value?.layout();
  }
});

interface editorConfigT {
  language: string;
  fontSize: number;
  minimap: boolean;
  themeName: string;
  lineNumbers: boolean;
}

defineProps<{
  func: Api.Function.FunctionInfo;
  codeChanged: boolean;
  editorConfig: editorConfigT;
  isSaving: boolean;
}>();

const emit = defineEmits(['save-code', 'open-history', 'update:code', 'open-editor-settings', 'edit-meta']);
</script>

<template>
  <div class="editor-panel">
    <div class="editor-header">
      <div class="header-left">
        <div class="function-title">
          <h3>{{ func.name || $t('page.function.functionEditor') }}</h3>
          <button class="edit-btn" @click="emit('edit-meta')">
            <NIcon :component="CreateOutline" :size="14" />
          </button>
        </div>
        <p v-if="func.description" class="function-desc">{{ func.description }}</p>
      </div>
      <div class="header-actions">
        <button
          class="action-btn"
          :class="{ 'publish-btn': codeChanged, 'saved-btn': !codeChanged }"
          :disabled="!codeChanged || isSaving"
          @click="emit('save-code')"
        >
          <NIcon :component="codeChanged ? CheckmarkOutline : SaveOutline" :size="15" />
          <span>{{ codeChanged ? $t('page.function.publish') : $t('page.function.published') }}</span>
          <div v-if="isSaving" class="saving-spinner" />
        </button>
        <button class="icon-btn" @click="emit('open-history')">
          <NIcon :component="InformationCircleOutline" :size="18" />
        </button>
        <button class="icon-btn" @click="emit('open-editor-settings')">
          <NIcon :component="BrushOutline" :size="18" />
        </button>
      </div>
    </div>
    <div class="editor-content">
      <EditorMonaco
        ref="editorMonacoRef"
        :key="func.id"
        :code="func.code"
        :show-minimap="editorConfig.minimap"
        :font-size="editorConfig.fontSize"
        :theme-name="editorConfig.themeName"
        :tab-size="4"
        :show-line-numbers="editorConfig.lineNumbers"
        @update:code="$emit('update:code', $event)"
      />
    </div>
  </div>
</template>

<style scoped>
.editor-panel {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #ffffff;
  border-radius: 12px;
  overflow: hidden;
}

.editor-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  padding: 14px 16px;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid rgba(0, 0, 0, 0.06);
}

.header-left {
  min-width: 0;
  flex: 1;
}

.function-title {
  display: flex;
  align-items: center;
  gap: 6px;
}

.function-title h3 {
  font-size: 15px;
  font-weight: 600;
  color: #1d1d1f;
  margin: 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.edit-btn {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 6px;
  background: transparent;
  color: #8e8e93;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
  flex-shrink: 0;
}

.edit-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #007aff;
}

.function-desc {
  font-size: 12px;
  color: #8e8e93;
  margin: 2px 0 0;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.header-actions {
  display: flex;
  align-items: center;
  gap: 6px;
  flex-shrink: 0;
}

.action-btn {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 6px 12px;
  font-size: 12px;
  font-weight: 500;
  border-radius: 8px;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.publish-btn {
  background: #007aff;
  color: white;
}

.publish-btn:hover {
  background: #0066d6;
}

.saved-btn {
  background: rgba(0, 0, 0, 0.04);
  color: #8e8e93;
}

.action-btn:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.saving-spinner {
  width: 12px;
  height: 12px;
  border: 2px solid rgba(255, 255, 255, 0.3);
  border-top-color: white;
  border-radius: 50%;
  animation: spin 0.6s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.icon-btn {
  width: 32px;
  height: 32px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: transparent;
  color: #6e6e73;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.icon-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #1d1d1f;
}

.editor-content {
  position: relative;
  flex: 1;
  min-height: 0;
}
</style>
