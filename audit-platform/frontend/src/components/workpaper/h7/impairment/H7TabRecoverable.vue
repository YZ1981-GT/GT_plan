<template>
  <div class="h7-tab-recoverable">
    <el-empty description="H7-16 可收回金额测试 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabRecoverable — H7-16 可收回金额 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
