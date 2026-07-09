<template>
  <div class="h7-tab-analysis">
    <el-empty description="H7-5 分析表 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabAnalysis — H7-5 分析表 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
