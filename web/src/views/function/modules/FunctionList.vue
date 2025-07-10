<script setup lang="ts">
import { NButton, NIcon, NCard, NList, NListItem, NThing, NTag, NEmpty, NTooltip } from 'naive-ui';
import { AddOutline, TrashSharp, CubeOutline, BrushOutline, HammerOutline } from '@vicons/ionicons5';

defineProps<{
  functions: Api.Function.FunctionInfo[];
  selectedFunctionId: string | null;
}>();

const emit = defineEmits(['create-function', 'select-function', 'delete-function', 'open-env-settings', 'open-editor-settings', 'open-dependency-manager']);

</script>

<template>
  <NCard title="云函数列表" :bordered="false" size="small" class="h-full">
    <template #header-extra>
      <NButton type="primary" size="small" @click="emit('create-function')">
        <template #icon>
          <NIcon :component="AddOutline" />
        </template>
      </NButton>
    </template>
    <template #footer>
      <n-tooltip trigger="hover">
        <template #trigger>
          <NButton size="small" @click="emit('open-env-settings')">
            <template #icon>
              <NIcon :component="CubeOutline" />
            </template>
          </NButton>
        </template>
        环境变量
      </n-tooltip>
      <n-tooltip trigger="hover">
        <template #trigger>
          <NButton class="ml-2" size="small" @click="emit('open-editor-settings')">
            <template #icon>
              <NIcon :component="BrushOutline" />
            </template>
          </NButton>
        </template>
        外观
      </n-tooltip>
      <n-tooltip trigger="hover">
        <template #trigger>
          <NButton class="ml-2" size="small" @click="emit('open-dependency-manager')">
            <template #icon>
              <NIcon :component="HammerOutline" />
            </template>
          </NButton>
        </template>
        依赖管理
      </n-tooltip>
    </template>
    <div class="function-list-container">
      <NList v-if="functions.length > 0" hoverable clickable>
        <NListItem v-for="func in functions" :key="func.id" @click="emit('select-function', func)"
          :class="{ 'selected-function-item': selectedFunctionId === func.id }">
          <NThing :title="func.name">
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
      <NEmpty v-else description="暂无函数" class="h-full flex items-center justify-center" />
    </div>
  </NCard>
</template>

<style scoped>
.function-list-container {
  max-height: calc(100% - 48px);
  /* 减去NCard的header高度，NCard的header默认高度是48px */
  overflow-y: auto;
}

.selected-function-item {
  background-color: #f3f3f5;
}
</style>
