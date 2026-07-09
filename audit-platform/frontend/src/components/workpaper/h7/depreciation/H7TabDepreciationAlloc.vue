<template>
  <div class="h7-tab-depreciation-alloc">
    <el-empty description="H7-12 折旧分配分析表 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDepreciationAlloc — H7-12 折旧分配 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
