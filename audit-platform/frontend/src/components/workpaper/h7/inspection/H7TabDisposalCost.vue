<template>
  <div class="h7-tab-disposal-cost">
    <el-empty description="H7-7 减少检查（成本模式） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDisposalCost — H7-7 减少检查（成本） placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
