<template>
  <div class="h7-tab-adjudication-fair">
    <el-empty description="H7-1 审定表（公允价值模式） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabAdjudicationFair — H7-1 公允模式审定表 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
