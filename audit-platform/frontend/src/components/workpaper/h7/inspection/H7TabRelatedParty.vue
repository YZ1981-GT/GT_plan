<template>
  <div class="h7-tab-related-party">
    <el-empty description="H7-17 关联交易检查 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabRelatedParty — H7-17 关联交易 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
