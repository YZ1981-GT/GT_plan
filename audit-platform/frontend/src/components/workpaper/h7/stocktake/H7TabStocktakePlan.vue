<template>
  <div class="h7-tab-stocktake-plan">
    <el-empty description="H7-8 监盘计划 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabStocktakePlan — H7-8 监盘计划 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
