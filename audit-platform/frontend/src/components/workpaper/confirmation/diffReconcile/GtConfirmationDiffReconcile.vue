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
        @export-template="handleExportTemplate"
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
        :total-count="data.metrics.value.total_count"
        :difference-net="data.metrics.value.difference_net_total"
        :difference-abs="data.metrics.value.difference_abs_total"
        :adjustment-count="data.metrics.value.adjustment_count"
        :analyzed-rate="data.metrics.value.analyzed_rate"
        @update-note="handleAuditNoteUpdate"
        @update-conclusion="handleConclusionUpdate"
        @update-materiality="handleMaterialityUpdate"
      />
    </template>

    <!-- D0-1 带入确认弹窗 -->
    <el-dialog v-model="showD01ImportDialog" title="从 D0-1 带入差异数据" width="520px" append-to-body>
      <div style="font-size:13px;line-height:1.8;color:#606266">
        <p style="margin:0 0 12px"><strong>操作说明：</strong></p>
        <ol style="padding-left:20px;margin:0 0 16px">
          <li>系统将从 D0-1 函证结果汇总表中，筛选<strong>相符情况为"不符"</strong>的函证记录</li>
          <li>自动带入：函证索引号、被询证单位、科目、发函金额、回函金额</li>
          <li>差异金额将自动计算（发函金额 − 回函金额）</li>
          <li>已存在相同索引号的记录不会重复导入</li>
        </ol>
        <el-alert type="info" :closable="false" show-icon style="margin-bottom:0">
          <template #title>带入后仍需补充</template>
          差异类型、是否调整、差异说明等字段需手动填写完善
        </el-alert>
      </div>
      <template #footer>
        <el-button @click="showD01ImportDialog = false">取消</el-button>
        <el-button type="primary" @click="confirmD01Import">确认带入</el-button>
      </template>
    </el-dialog>
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
  showD01ImportDialog.value = true
}

const showD01ImportDialog = ref(false)

async function confirmD01Import() {
  showD01ImportDialog.value = false
  // TODO: 调用跨底稿引用 API 获取 D0-1 不符项数据
  // const d01Rows = await fetchD01DiffRows(props.wpId, props.projectId)
  // d01Import.fetchAndImport(d01Rows)
  console.log('[GtConfirmationDiffReconcile] 执行从 D0-1 带入')
}

function handleImportExcel() {
  // TODO: 复用 useExcelIO 批量导入
  console.log('[GtConfirmationDiffReconcile] Excel 导入')
}

function handleExportExcel() {
  // TODO: 复用 useExcelIO 导出
  console.log('[GtConfirmationDiffReconcile] Excel 导出')
}

async function handleExportTemplate() {
  try {
    const { utils, writeFileXLSX } = await import('xlsx')
    const wb = utils.book_new()

    // Sheet 1: 数据模板
    const headers = ['序号', '函证索引号', '被询证单位', '科目', '发函金额', '回函金额', '差异类型', '是否调整', '差异说明']
    const example = ['1', 'D0-001', '示例公司（请删除）', '应收账款', '100000', '99000', '时间性差异', '否', '在途款项']
    const ws = utils.aoa_to_sheet([headers, example])
    ws['!cols'] = [
      { wch: 6 }, { wch: 12 }, { wch: 22 }, { wch: 12 }, { wch: 12 },
      { wch: 12 }, { wch: 12 }, { wch: 8 }, { wch: 20 },
    ]
    utils.book_append_sheet(wb, ws, '差异明细')

    // Sheet 2: 填写说明
    const instructions = [
      ['D0-4 差异调节表 — 导入模板填写说明'],
      [''],
      ['【必填列】'],
      ['  函证索引号：与 D0-1 函证汇总表索引一致（如 D0-001）'],
      ['  被询证单位：被函证公司全称'],
      ['  发函金额：账面函证金额（数字，单位：元）'],
      ['  回函金额：对方确认金额（数字，单位：元）'],
      [''],
      ['【选填列】'],
      ['  序号：自动生成（留空即可）'],
      ['  科目：涉及科目（应收账款/合同负债等，可自定义）'],
      ['  差异类型：时间性差异 / 记账差异 / 未达账项 / 其他差异'],
      ['  是否调整：填"是"或"否"，表示该差异是否需要审计调整'],
      ['  差异说明：简述差异原因（如：在途款项、截止日差异）'],
      [''],
      ['【差异金额】'],
      ['  系统自动计算：差异金额 = 发函金额 − 回函金额'],
      ['  无需手动填写'],
      [''],
      ['【注意事项】'],
      ['  1. 第一行为表头请勿修改'],
      ['  2. 示例行（第2行）请删除后再填写实际数据'],
      ['  3. 金额列请填纯数字，不要带"元"或千分位逗号'],
      ['  4. 也可使用"从 D0-1 带入"按钮自动带入不符项'],
    ]
    const instrSheet = utils.aoa_to_sheet(instructions)
    instrSheet['!cols'] = [{ wch: 60 }]
    utils.book_append_sheet(wb, instrSheet, '填写说明')

    writeFileXLSX(wb, 'D0-4差异调节导入模板.xlsx')
  } catch (e: any) {
    console.error('[DiffReconcile] Export template error:', e)
  }
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
