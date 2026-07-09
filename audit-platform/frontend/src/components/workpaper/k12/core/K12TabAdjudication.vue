<template>
  <div class="k12-tab-adjudication">
    <!-- ═══ 跨底稿引用（GtIndexChip：K12-1 → TB） ═══ -->
    <div class="cross-ref-bar">
      <span class="cross-refs-label">关联引用：</span>
      <GtIndexChip value="TB" :context-project-id="props.projectId" />
      <GtIndexChip value="K12-2" :context-project-id="props.projectId" />
      <GtIndexChip value="K12-3" :context-project-id="props.projectId" />
    </div>

    <el-empty description="K12-1 审定表（损益类6301发生额） — 待实现 (Task 4.2)" />
  </div>
</template>

<script setup lang="ts">
/**
 * K12TabAdjudication.vue — K12-1 营业外收入审定表
 * 损益类！取发生额非余额（6301贷方科目）
 * GtIndexChip跨底稿引用：K12-1 → TB(试算表) / K12-2(明细) / K12-3(调整)
 * Stub: Task 4.2 实现完整逻辑
 */
import { defineAsyncComponent } from 'vue'

const GtIndexChip = defineAsyncComponent(() => import('../../GtIndexChip.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  tbData: { unadjusted6301: number; audited6301: number }
  isReadonly: boolean
}>()

defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()
</script>

<style scoped>
.k12-tab-adjudication { padding: 16px; }
.cross-ref-bar {
  display: flex; align-items: center; gap: 6px; flex-wrap: wrap;
  margin-bottom: 12px; padding: 6px 12px;
  background: #f5f7fa; border-radius: 6px;
}
.cross-refs-label { color: #909399; font-size: 12px; white-space: nowrap; }
</style>
