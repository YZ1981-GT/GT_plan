<template>
  <div class="gt-confirmation-diff-reconcile">
    <!-- 旧格式降级 -->
    <template v-if="!isNewFormat">
      <div class="gt-confirmation-diff-reconcile__legacy-notice">
        <el-alert type="info" :closable="false" show-icon>
          此底稿使用旧格式，仅支持只读查看。如需编辑请联系管理员升级格式。
        </el-alert>
      </div>
      <GtGridSheet :html-data="htmlDataRef" :readonly="true" />
    </template>

    <!-- 新格式：diff-reconcile-v1 -->
    <template v-else>
      <!-- 看板 -->
      <DiffReconcileDashboard
        :metrics="data.metrics.value"
        :subject-summary="data.subjectSummary.value"
        :unclassified-count="analysis.unclassifiedCount.value"
        :has-materiality-config="!!data.materialityConfig.value.performance_materiality"
      />

      <!-- 差异明细网格 -->
      <DiffReconcileMaster
        :rows="data.rows.value"
        :readonly="readonly"
        :is-dirty="data.isDirty.value"
        :subject-options="subjectOptions"
        :diff-type-options="diffTypeOptions"
        :subject-summary="data.subjectSummary.value"
        :is-over-materiality="data.isOverMateriality"
        @add="handleAdd"
        @delete="handleDelete"
        @save="handleSave"
        @update="handleUpdate"
        @import-d01="handleImportD01"
        @import-excel="handleImportExcel"
        @export-excel="handleExportExcel"
        @jump-d01="handleJumpD01"
      />

      <!-- 差异原因分析表 -->
      <DiffReconcileAnalysis
        :analysis-groups="analysis.analysisGroups.value"
        :totals="analysis.analysisTotals.value"
        :unclassified-count="analysis.unclassifiedCount.value"
        :readonly="readonly"
        @update-note="analysis.updateAnalysisNote"
        @update-action="analysis.updateAnalysisAction"
      />

      <!-- 审计说明 + 结论 + 重要性配置 -->
      <DiffReconcileConclusion
        :audit-note="data.auditNote.value"
        :conclusion="data.conclusion.value"
        :materiality-config="data.materialityConfig.value"
        :readonly="readonly"
        :has-unresolved="analysis.unclassifiedCount.value > 0"
        @update-note="handleAuditNoteUpdate"
        @update-conclusion="handleConclusionUpdate"
        @update-materiality="handleMaterialityUpdate"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, defineAsyncComponent } from 'vue'
import { useDiffReconcileData } from './composables/useDiffReconcileData'
import { useDiffAnalysis } from './composables/useDiffAnalysis'
import { useD01DiffImport } from './composables/useD01DiffImport'
import type { DiffReconcileRow } from './diffReconcileTypes'

import DiffReconcileDashboard from './DiffReconcileDashboard.vue'
import DiffReconcileMaster from './DiffReconcileMaster.vue'
import DiffReconcileAnalysis from './DiffReconcileAnalysis.vue'
import DiffReconcileConclusion from './DiffReconcileConclusion.vue'

const GtGridSheet = defineAsyncComponent(() => import('../../GtGridSheet.vue'))

const props = defineProps<{
  htmlData: any
  readonly: boolean
  wpId?: string
  projectId?: string
  wpCode?: string
  year?: string
}>()

const emit = defineEmits<{
  (e: 'save', payload: any): void
}>()

// ─── 格式检测 ────────────────────────────────────────────────────────────────

const htmlDataRef = computed(() => props.htmlData)
const isNewFormat = computed(() => props.htmlData?._format === 'diff-reconcile-v1')

// ─── 数据核心 ────────────────────────────────────────────────────────────────

const data = useDiffReconcileData({
  htmlData: () => props.htmlData,
  readonly: props.readonly,
})

// ─── 分析层 ──────────────────────────────────────────────────────────────────

const analysis = useDiffAnalysis({
  rows: data.rows,
  analysisNotes: data.analysisNotes,
  computeDifference: data.computeDifference,
})

// ─── D0-1 带入 ──────────────────────────────────────────────────────────────

const d01Import = useD01DiffImport({
  existingIndexes: () => new Set(
    data.rows.value.map((r) => r.confirm_index).filter(Boolean) as string[]
  ),
  onImport: data.importRows,
})

// ─── 字典选项 ────────────────────────────────────────────────────────────────

// TODO: 从 useDictStore 获取（暂用硬编码默认值）
const subjectOptions = computed(() => [
  { value: '应收账款', label: '应收账款' },
  { value: '合同负债', label: '合同负债' },
  { value: '销售收入', label: '销售收入' },
  { value: '应收票据', label: '应收票据' },
  { value: '合同资产', label: '合同资产' },
  { value: '预付账款', label: '预付账款' },
  { value: '应付账款', label: '应付账款' },
  { value: '预收账款', label: '预收账款' },
  { value: '其他应收款', label: '其他应收款' },
  { value: '其他应付款', label: '其他应付款' },
  { value: '银行存款', label: '银行存款' },
  { value: '短期借款', label: '短期借款' },
  { value: '长期借款', label: '长期借款' },
])

const diffTypeOptions = computed(() => [
  { value: 'time', label: '时间性差异' },
  { value: 'accounting', label: '记账差异' },
  { value: 'unrecorded', label: '未达账项' },
  { value: 'other', label: '其他差异' },
])

// ─── 事件处理 ────────────────────────────────────────────────────────────────

function handleAdd() {
  data.addRow()
}

function handleDelete() {
  // TODO: 获取选中行 ID
}

function handleSave() {
  const payload = data.buildPayload()
  emit('save', payload)
}

function handleUpdate(rowId: string, field: string, value: any) {
  data.updateField(rowId, field, value)
}

function handleImportD01() {
  // TODO: 调用跨底稿引用机制获取 D0-1 数据
  // d01Import.fetchAndImport(d01Rows)
  console.log('[GtConfirmationDiffReconcile] 从 D0-1 带入（待接入跨底稿引用）')
}

function handleImportExcel() {
  // TODO: 复用 useExcelIO 批量导入
  console.log('[GtConfirmationDiffReconcile] Excel 导入')
}

function handleExportExcel() {
  // TODO: 复用 useExcelIO 导出
  console.log('[GtConfirmationDiffReconcile] Excel 导出')
}

function handleJumpD01(confirmIndex: string) {
  // TODO: 跨底稿跳转 D0-1
  console.log('[GtConfirmationDiffReconcile] 跳转 D0-1:', confirmIndex)
}

function handleAuditNoteUpdate(field: string, value: string) {
  ;(data.auditNote.value as any)[field] = value
  data.isDirty.value = true
}

function handleConclusionUpdate(field: string, value: any) {
  ;(data.conclusion.value as any)[field] = value
  data.isDirty.value = true
}

function handleMaterialityUpdate(value: number) {
  data.materialityConfig.value.performance_materiality = value
  data.materialityConfig.value.is_overridden = true
  data.materialityConfig.value.source = 'manual'
  data.isDirty.value = true
}
</script>

<style scoped>
.gt-confirmation-diff-reconcile {
  padding: 8px 0;
}

.gt-confirmation-diff-reconcile__legacy-notice {
  margin-bottom: 12px;
}
</style>
