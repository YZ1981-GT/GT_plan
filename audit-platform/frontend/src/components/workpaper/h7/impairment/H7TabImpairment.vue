<template>
  <div class="h7-tab-impairment">
    <el-empty description="H7-15 减值测算 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/** H7TabImpairment — H7-15 减值测算 placeholder */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
