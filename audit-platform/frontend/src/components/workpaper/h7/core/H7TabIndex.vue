<template>
  <div class="h7-tab-index">
    <el-empty description="H7 底稿目录 — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabIndex.vue — H7 生产性生物资产底稿目录
 *
 * 26行sheet列表 + 进度条 + 行业标识 + 计量模式指示
 * Placeholder — Phase 4 实现完整功能
 *
 * Spec: .kiro/specs/h7-biological-assets/
 * Requirements: 1.2
 */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  measurementModel?: 'cost' | 'fair_value'
  isReadonly?: boolean
}>()
</script>

<style scoped>
.h7-tab-index {
  padding: 16px;
}
</style>
