<template>
  <div class="h9-tab-index">
    <el-empty description="H9 底稿目录 — 待实现 (Phase 4)" />
  </div>
</template>

<script setup lang="ts">
/**
 * H9TabIndex.vue — H9 底稿目录
 * Phase 4 实现：~10行+进度条+H8联动状态
 */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  h8LinkageStatus?: { isConsistent: boolean; diff: number; message: string }
}>()

defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()
</script>
