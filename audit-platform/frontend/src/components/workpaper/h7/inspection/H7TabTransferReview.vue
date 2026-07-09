<template>
  <div class="h7-tab-transfer-review">
    <el-empty description="H7-14 互转审核 + 产量记录 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabTransferReview — H7-14 互转审核 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
