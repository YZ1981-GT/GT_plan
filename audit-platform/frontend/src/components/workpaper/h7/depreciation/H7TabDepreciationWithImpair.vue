<template>
  <div class="h7-tab-depreciation-with-impair">
    <el-empty description="H7-11 折旧测算（含减值） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDepreciationWithImpair — H7-11(B) 含减值 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
