<template>
  <div class="h7-tab-detail-cost">
    <el-empty description="H7-2 明细表（成本模式） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDetailCost — H7-2 成本模式明细表 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
