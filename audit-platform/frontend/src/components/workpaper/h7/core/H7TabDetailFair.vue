<template>
  <div class="h7-tab-detail-fair">
    <el-empty description="H7-2 明细表（公允价值模式） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDetailFair — H7-2 公允模式明细表 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
