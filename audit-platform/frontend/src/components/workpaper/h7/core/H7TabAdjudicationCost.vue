<template>
  <div class="h7-tab-adjudication-cost">
    <el-empty description="H7-1 审定表（成本模式） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabAdjudicationCost — H7-1 成本模式审定表 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
