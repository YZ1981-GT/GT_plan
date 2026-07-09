<template>
  <div class="h7-tab-production-record">
    <el-empty description="产量记录（H7独有） — 待实现" :image-size="80" />
  </div>
</template>

<script setup lang="ts">
/**
 * H7TabProductionRecord — 产量记录（H7独有功能）
 *
 * 记录生物资产产出（产蛋/产奶/割胶/收获果实等）
 * 集成在 H7TabTransferReview (H7-14) 中或作为独立section使用。
 *
 * Spec: .kiro/specs/h7-biological-assets/
 * Requirements: 9.1-9.5
 */
defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly?: boolean
}>()
</script>
