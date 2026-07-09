<template>
  <div class="h7-tab-stocktake-check">
    <el-empty description="H7-9 盘点检查 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabStocktakeCheck — H7-9 盘点检查 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
