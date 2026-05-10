<script setup lang="ts">
import { computed } from 'vue';
import { NIcon, NTooltip } from 'naive-ui';
import { AddOutline, CodeSlashOutline, CubeOutline, HammerOutline, ShareSocialOutline, TrashSharp } from '@vicons/ionicons5';
import { $t } from '@/locales';

const props = defineProps<{
  functions: Api.Function.FunctionInfo[];
  selectedFunctionId: string | null;
  tags: string[];
  selectedTag: string;
}>();

const emit = defineEmits([
  'create-function',
  'select-function',
  'delete-function',
  'open-env-settings',
  'open-dependency-manager',
  'select-tag'
]);

const displayTags = computed(() => {
  const fixedTags = [
    { key: 'all', label: $t('page.function.tagsGroup.all') },
    { key: 'api', label: $t('page.function.tagsGroup.api') },
    { key: 'common', label: $t('page.function.tagsGroup.common') }
  ];
  const dynamicTags = props.tags.map(tag => ({ key: tag, label: tag }));
  return [...fixedTags, ...dynamicTags];
});

const getStatusColor = (status: string) => {
  return status === 'published' ? 'bg-emerald-500' : 'bg-amber-500';
};
</script>

<template>
  <div class="function-sidebar">
    <div class="sidebar-header">
      <h2 class="sidebar-title">
        <NIcon :component="CodeSlashOutline" :size="16" />
        <span>{{ $t('page.function.functionList') }}</span>
      </h2>
      <button class="add-btn" @click="emit('create-function')">
        <NIcon :component="AddOutline" :size="18" />
      </button>
    </div>

    <div class="tag-filter">
      <button
        v-for="tag in displayTags"
        :key="tag.key"
        class="tag-chip"
        :class="{ active: selectedTag === tag.key }"
        @click="emit('select-tag', tag.key)"
      >
        {{ tag.label }}
      </button>
    </div>

    <div class="function-list">
      <div
        v-for="func in functions"
        :key="func.id"
        class="function-item"
        :class="{ selected: selectedFunctionId === func.id }"
        @click="emit('select-function', func)"
      >
        <div class="function-item-content">
          <div class="function-info">
            <div class="function-name">
              <span class="status-dot" :class="getStatusColor(func.status)" />
              <span>{{ func.name }}</span>
            </div>
            <NTooltip v-if="func.type === 'common'" trigger="hover">
              <template #trigger>
                <NIcon :component="ShareSocialOutline" :size="14" class="text-slate-400" />
              </template>
              {{ $t('page.function.commonFunction') }}
            </NTooltip>
          </div>
          <button class="delete-btn" @click.stop="emit('delete-function', func)">
            <NIcon :component="TrashSharp" :size="14" />
          </button>
        </div>
      </div>

      <div v-if="functions.length === 0" class="empty-state">
        <div class="empty-icon">ƒ</div>
        <p>{{ $t('page.function.noFunctions') }}</p>
      </div>
    </div>

    <div class="sidebar-footer">
      <NTooltip trigger="hover">
        <template #trigger>
          <button class="tool-btn" @click="emit('open-env-settings')">
            <NIcon :component="CubeOutline" :size="18" />
          </button>
        </template>
        {{ $t('page.function.envVariables') }}
      </NTooltip>
      <NTooltip trigger="hover">
        <template #trigger>
          <button class="tool-btn" @click="emit('open-dependency-manager')">
            <NIcon :component="HammerOutline" :size="18" />
          </button>
        </template>
        {{ $t('page.function.dependenceManagement') }}
      </NTooltip>
    </div>
  </div>
</template>

<style scoped>
.function-sidebar {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: rgba(255, 255, 255, 0.72);
  backdrop-filter: blur(20px) saturate(180%);
  -webkit-backdrop-filter: blur(20px) saturate(180%);
  border: 1px solid rgba(0, 0, 0, 0.06);
  border-radius: 12px;
  overflow: hidden;
}

.sidebar-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 16px 16px 12px;
}

.sidebar-title {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
  font-weight: 600;
  color: #1d1d1f;
  letter-spacing: -0.01em;
}

.add-btn {
  width: 28px;
  height: 28px;
  display: flex;
  align-items: center;
  justify-content: center;
  border-radius: 8px;
  background: #007aff;
  color: white;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.add-btn:hover {
  background: #0066d6;
  transform: scale(1.05);
}

.tag-filter {
  display: flex;
  flex-wrap: wrap;
  gap: 6px;
  padding: 0 16px 12px;
}

.tag-chip {
  padding: 4px 10px;
  font-size: 11px;
  font-weight: 500;
  border-radius: 6px;
  background: rgba(0, 0, 0, 0.04);
  color: #6e6e73;
  border: none;
  cursor: pointer;
  transition: all 0.2s ease;
}

.tag-chip:hover {
  background: rgba(0, 0, 0, 0.08);
}

.tag-chip.active {
  background: #007aff;
  color: white;
}

.function-list {
  flex: 1;
  overflow-y: auto;
  padding: 0 8px;
}

.function-list::-webkit-scrollbar {
  width: 4px;
}

.function-list::-webkit-scrollbar-track {
  background: transparent;
}

.function-list::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.15);
  border-radius: 2px;
}

.function-item {
  padding: 10px 12px;
  margin-bottom: 2px;
  border-radius: 10px;
  cursor: pointer;
  transition: all 0.2s ease;
}

.function-item:hover {
  background: rgba(0, 0, 0, 0.04);
}

.function-item.selected {
  background: rgba(0, 122, 255, 0.08);
}

.function-item-content {
  display: flex;
  align-items: center;
  justify-content: space-between;
}

.function-info {
  display: flex;
  align-items: center;
  gap: 6px;
  min-width: 0;
}

.function-name {
  display: flex;
  align-items: center;
  gap: 8px;
  font-size: 13px;
  font-weight: 500;
  color: #1d1d1f;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.status-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  flex-shrink: 0;
}

.delete-btn {
  opacity: 0;
  width: 24px;
  height: 24px;
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

.function-item:hover .delete-btn {
  opacity: 1;
}

.delete-btn:hover {
  background: rgba(255, 59, 48, 0.1);
}

.empty-state {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 40px 16px;
  color: #8e8e93;
}

.empty-icon {
  font-size: 32px;
  font-weight: 700;
  color: #c7c7cc;
  margin-bottom: 8px;
}

.empty-state p {
  font-size: 13px;
  margin: 0;
}

.sidebar-footer {
  display: flex;
  justify-content: flex-end;
  gap: 4px;
  padding: 12px 16px;
  border-top: 1px solid rgba(0, 0, 0, 0.06);
}

.tool-btn {
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

.tool-btn:hover {
  background: rgba(0, 0, 0, 0.06);
  color: #1d1d1f;
}
</style>
