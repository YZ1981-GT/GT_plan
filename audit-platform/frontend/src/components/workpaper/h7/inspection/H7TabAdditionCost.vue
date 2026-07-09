<template>
  <div class="h7-tab-addition-cost">
    <el-empty description="H7-6 增加检查（成本模式） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabAdditionCost — H7-6 增加检查（成本） placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
