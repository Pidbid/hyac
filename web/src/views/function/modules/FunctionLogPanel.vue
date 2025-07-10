<script setup lang="ts">
import { ref, computed } from 'vue';
import { NCard, NButtonGroup, NTooltip, NButton, NIcon, NScrollbar, NFlex } from 'naive-ui';
import { TerminalOutline, EaselOutline, ReaderOutline } from '@vicons/ionicons5';

const props = defineProps<{
  logs: Api.Function.FunctionLogsInfo[];
}>();

const logFilter = ref<Api.Function.LogType | 'all'>('all');

const filteredLogs = computed(() => {
  // This computed property will need to be in the parent component (index.vue)
  // as it depends on the logStore. For now, we just filter the passed logs prop.
  return props.logs.filter((log: Api.Function.FunctionLogsInfo) => {
    if (logFilter.value === 'all') return true;
    return log.logtype === logFilter.value;
  });
});

</script>

<template>
  <NCard title="日志" :bordered="false" size="small" class="h-full"
    :content-style="{ padding: '0px', height: 'calc(100% - 40px)' }">
    <template #header-extra>
      <NButtonGroup>
        <NTooltip trigger="hover">
          <template #trigger>
            <NButton circle size="small" :type="logFilter === 'all' ? 'primary' : 'default'"
              @click="logFilter = 'all'">
              <template #icon>
                <NIcon :component="TerminalOutline" />
              </template>
            </NButton>
          </template>
          全部日志
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <NButton circle size="small" :type="logFilter === 'function' ? 'primary' : 'default'"
              @click="logFilter = 'function'">
              <template #icon>
                <NIcon :component="EaselOutline" />
              </template>
            </NButton>
          </template>
          函数日志
        </NTooltip>
        <NTooltip trigger="hover">
          <template #trigger>
            <NButton circle size="small" :type="logFilter === 'system' ? 'primary' : 'default'"
              @click="logFilter = 'system'">
              <template #icon>
                <NIcon :component="ReaderOutline" />
              </template>
            </NButton>
          </template>
          系统日志
        </NTooltip>
      </NButtonGroup>
    </template>
    <NScrollbar class="h-full">
      <NFlex v-for="log in filteredLogs" :key="log._id">
        <div class="color-info">{{ log.timestamp }}</div>
        <div v-if="log.logtype === 'function'" class="`color-${log.level}`">{{ log.level }}</div>
        <div v-if="log.logtype === 'system'" class="`color-${log.level}`">{{ log.level }}(system)</div>
        <div v-if="log.logtype === 'function'" class="color-blue">{{ log.message }}</div>
        <div v-if="log.logtype === 'system'" class="color-black">{{ log.message }}</div>
      </NFlex>
    </NScrollbar>
  </NCard>
</template>

<style scoped>
/* Add any specific styles for the log panel here */
</style>
