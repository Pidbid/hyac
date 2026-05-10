<script setup lang="ts">
import { computed } from 'vue';
import { NButton, NCard, NEmpty, NIcon, NList, NListItem, NScrollbar, NSpace, NTag, NThing, NTooltip } from 'naive-ui';
import { AddOutline, CubeOutline, HammerOutline, ShareSocialOutline, TrashSharp } from '@vicons/ionicons5';
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
</script>

<template>
  <NCard
    :title="$t('page.function.functionList')"
    :bordered="false"
    size="small"
    class="h-full flex flex-col"
    :content-style="{ padding: '0px', flex: 1, overflow: 'hidden' }"
  >
    <template #header-extra>
      <NButton type="primary" size="small" @click="emit('create-function')">
        <template #icon>
          <NIcon :component="AddOutline" />
        </template>
      </NButton>
    </template>
    <div class="p-2">
      <NSpace>
        <NTag
          v-for="tag in displayTags"
          :key="tag.key"
          checkable
          :checked="selectedTag === tag.key"
          @click="emit('select-tag', tag.key)"
        >
          {{ tag.label }}
        </NTag>
      </NSpace>
    </div>
    <template #footer>
      <div class="w-full flex justify-end">
        <NTooltip trigger="hover">
          <template #trigger>
            <NButton size="small" @click="emit('open-env-settings')">
              <template #icon>
                <NIcon :component="CubeOutline" />
              </template>
            </NButton>
          </template>
          {{ $t('page.function.envVariables') }}
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <NButton class="ml-2" size="small" @click="emit('open-dependency-manager')">
              <template #icon>
                <NIcon :component="HammerOutline" />
              </template>
            </NButton>
          </template>
          {{ $t('page.function.dependenceManagement') }}
        </NTooltip>
      </div>
    </template>
    <NScrollbar class="h-full">
      <NList v-if="functions.length > 0" hoverable clickable>
        <NListItem
          v-for="func in functions"
          :key="func.id"
          :class="{ 'selected-function-item': selectedFunctionId === func.id }"
          @click="emit('select-function', func)"
        >
          <NThing>
            <template #header>
              <div class="flex items-center">
                <span>{{ func.name }}</span>
                <NTooltip v-if="func.type === 'common'" trigger="hover">
                  <template #trigger>
                    <NIcon :component="ShareSocialOutline" class="ml-2" />
                  </template>
                  {{ $t('page.function.commonFunction') }}
                </NTooltip>
              </div>
            </template>
            <template #header-extra>
              <NTag size="small" type="error" :bordered="false" @click.stop="emit('delete-function', func)">
                <template #icon>
                  <NIcon :component="TrashSharp" />
                </template>
              </NTag>
            </template>
          </NThing>
        </NListItem>
      </NList>
      <NEmpty v-else :description="$t('page.function.noFunctions')" class="h-full flex items-center justify-center" />
    </NScrollbar>
  </NCard>
</template>

<style scoped>
.selected-function-item {
  background-color: #f3f3f5;
}
</style>
