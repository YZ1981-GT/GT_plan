<template>
  <div class="i2-tab-policy-check">
    <p>I2-4 会计政策检查 — 待实现 (Task 4.6)</p>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()
</script>
