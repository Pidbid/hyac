<script setup lang="ts">
import { NButton, NIcon, NCard, NList, NListItem, NThing, NTag, NEmpty, NTooltip, NScrollbar } from 'naive-ui';
import { AddOutline, TrashSharp, CubeOutline, BrushOutline, HammerOutline } from '@vicons/ionicons5';

defineProps<{
  functions: Api.Function.FunctionInfo[];
  selectedFunctionId: string | null;
}>();

const emit = defineEmits(['create-function', 'select-function', 'delete-function', 'open-env-settings', 'open-dependency-manager']);

</script>

<template>
  <NCard title="云函数列表" :bordered="false" size="small" class="h-full flex flex-col"
    :content-style="{ padding: '0px', flex: 1, overflow: 'hidden' }">
    <template #header-extra>
      <NButton type="primary" size="small" @click="emit('create-function')">
        <template #icon>
          <NIcon :component="AddOutline" />
        </template>
      </NButton>
    </template>
    <template #footer>
      <div class="flex justify-end w-full">
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
            <NButton class="ml-2" size="small" @click="emit('open-dependency-manager')">
              <template #icon>
                <NIcon :component="HammerOutline" />
              </template>
            </NButton>
          </template>
          依赖管理
        </n-tooltip>
      </div>
    </template>
    <NScrollbar class="h-full">
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
    </NScrollbar>
  </NCard>
</template>

<style scoped>
.selected-function-item {
  background-color: #f3f3f5;
}
</style>
