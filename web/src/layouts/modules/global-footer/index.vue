<script setup lang="ts">
defineOptions({
  name: 'GlobalFooter'
});

const currentYear = new Date().getFullYear();
</script>

<template>
  <DarkModeContainer class="h-full flex-center">
    <a href="https://github.com/pidbid/hyac" target="_blank" rel="noopener noreferrer">
      Copyright MIT © {{ currentYear }} Hyac
    </a>
  </DarkModeContainer>
</template>

<style scoped></style>
