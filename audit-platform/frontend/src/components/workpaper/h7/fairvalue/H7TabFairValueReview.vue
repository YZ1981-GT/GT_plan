<template>
  <div class="h7-tab-fair-value-review">
    <el-empty description="H7-13 公允价值复核 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabFairValueReview — H7-13 公允价值复核 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
