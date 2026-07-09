<template>
  <div class="h7-tab-depreciation-no-impair">
    <el-empty description="H7-11 折旧测算（不含减值-直线法） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDepreciationNoImpair — H7-11(A) 不含减值 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
