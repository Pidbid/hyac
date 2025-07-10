<script setup lang="ts">
import { ref, watch } from 'vue';
import dayjs from 'dayjs';
import { NModal, NCard, NGrid, NGridItem, NScrollbar, NList, NListItem, NThing, NEmpty, NButton } from 'naive-ui';
import { CodeDiff } from 'v-code-diff';

const props = defineProps<{
  show: boolean;
  historyData: Api.Function.FunctionHistoryInfo[];
}>();

const emit = defineEmits(['update:show', 'rollback']);

const selectedHistory = ref<Api.Function.FunctionHistoryInfo | undefined>(props.historyData.length > 0 ? props.historyData[0] : undefined);

watch(() => props.historyData, (newData) => {
  if (newData.length > 0 && !selectedHistory.value) {
    selectedHistory.value = newData[0];
  }
});

const handleRollback = () => {
  if (selectedHistory.value) {
    emit('rollback', selectedHistory.value);
  }
};

</script>

<template>
  <NModal :show="show" @update:show="(value) => emit('update:show', value)" preset="card" title="函数历史记录"
    style="width: 60%; height: 80vh" :bordered="false" :segmented="{ content: 'soft' }">
    <div class="h-full flex flex-col">
      <div class="flex-1 min-h-0">
        <NGrid x-gap="12" :cols="24" class="h-full">
          <NGridItem :span="4" class="h-full">
            <NCard :bordered="false" class="h-full" :content-style="{ padding: 0, height: '100%' }">
              <NScrollbar class="h-full">
                <NList hoverable clickable bordered>
                  <NListItem v-for="history in historyData" :key="history._id" @click="selectedHistory = history"
                    :class="{ 'selected-history-item': selectedHistory?._id === history._id }">
                    <NThing :content="dayjs(history.updated_at).format('YYYY-MM-DD HH:mm:ss')"></NThing>
                  </NListItem>
                </NList>
              </NScrollbar>
            </NCard>
          </NGridItem>
          <NGridItem :span="20" class="h-full">
            <NCard :bordered="false" class="h-full"
              :content-style="{ padding: 0, height: '100%', overflow: 'hidden' }">
              <CodeDiff v-if="selectedHistory" :old-string="selectedHistory.old_code"
                :new-string="selectedHistory.new_code" output-format="side-by-side" language="python" :context="50"
                maxHeight="calc(80vh - 180px)" />
              <NEmpty v-else description="请在左侧选择一个历史版本" class="h-full flex items-center justify-center" />
            </NCard>
          </NGridItem>
        </NGrid>
      </div>
    </div>
    <template #footer>
      <div class="flex justify-end gap-2">
        <NButton @click="emit('update:show', false)">取消</NButton>
        <NButton type="primary" :disabled="!selectedHistory" @click="handleRollback">回退到此版本</NButton>
      </div>
    </template>
  </NModal>
</template>

<style scoped>
.selected-history-item {
  background-color: var(--primary-color-pressed);
  color: #fff;
}

.selected-history-item .n-thing-header__title,
.selected-history-item .n-thing-header__extra {
  color: #fff;
}

.selected-history-item .n-thing-header__content {
  color: #fff;
}
</style>
