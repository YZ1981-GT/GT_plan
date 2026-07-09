<template>
  <div class="h7-tab-stocktake-summary">
    <el-empty description="H7-10 监盘小结 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabStocktakeSummary — H7-10 监盘小结 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
