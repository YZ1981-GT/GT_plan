<template>
  <div class="h7-tab-disposal-fair">
    <el-empty description="H7-7 减少检查（公允价值模式） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabDisposalFair — H7-7 减少检查（公允） placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
