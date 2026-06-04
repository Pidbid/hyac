<script setup lang="ts">
import RuntimeLogPanel from '@/views/log/modules/RuntimeLogPanel.vue';

defineProps<{
  appId?: string | null;
  funcId?: string | null;
  compact?: boolean;
}>();

const emit = defineEmits<{
  collapse: [];
  expand: [];
}>();
</script>

<template>
  <RuntimeLogPanel
    :key="funcId || 'runtime-log-panel'"
    :app-id="appId"
    :func-id="funcId"
    :tail="0"
    :compact="compact"
    :title="$t('page.function.log')"
    @collapse="emit('collapse')"
    @expand="emit('expand')"
  />
</template>
