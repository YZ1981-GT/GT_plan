<template>
  <div class="h7-tab-adjustment">
    <el-empty description="H7-3 调整分录汇总 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabAdjustment — H7-3 调整分录 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
