<template>
  <div class="n5-adjudication">
    <!-- ═══ 审计目标 ═══ -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标"
      description="确认所得税费用（6801）本期发生额的准确性与完整性：当期所得税（应纳税所得额×税率）与递延所得税费用（递延税负债增减、递延税资产增减）计算正确，有效税率合理，与 N5-4 当期计算表/N5-8 递延核对表勾稽一致并计入利润表。"
    />

    <!-- ═══ 方法论上下文（琥珀色左边线+浅黄背景） ═══ -->
    <div class="methodology-context">
      <p><strong>所得税费用(6801)</strong>：损益类借方科目，取本期发生额。所得税费用 = 当期所得税 + 递延所得税费用。当期所得税=应纳税所得额×税率；递延=递延税负债增−递延税资产增。</p>
    </div>

    <!-- ═══ Section Header ═══ -->
    <div class="section-header">
      <div class="section-title">
        <span>所得税费用审定表 N5-1</span>
        <el-tag type="warning" size="small">损益类·借方·取发生额</el-tag>
      </div>
      <div class="section-actions">
        <el-button size="small" @click="handleAiAssist">
          <el-icon><MagicStick /></el-icon>AI辅助
        </el-button>
        <el-button size="small" @click="handleReview">
          <el-icon><ChatDotSquare /></el-icon>复核
        </el-button>
      </div>
    </div>

    <!-- ═══ 有效税率指标 ═══ -->
    <div class="etr-indicator">
      <span class="etr-label">有效税率 =</span>
      <span class="etr-value">{{ etr.rate != null ? fmtPercent(etr.rate) : '—' }}</span>
      <span class="etr-formula">（所得税费用 / 会计利润）</span>
      <el-tag v-if="etr.rate != null && etr.rate > 0.3" type="danger" size="small">偏高</el-tag>
      <el-tag v-else-if="etr.rate != null && etr.rate < 0.1" type="warning" size="small">偏低</el-tag>
    </div>

    <!-- ═══ 主数据表格 ═══ -->
    <el-table :data="tableData" border size="small" show-summary :summary-method="getSummaries" class="adjudication-table">
      <el-table-column prop="category" label="项目" min-width="180" fixed>
        <template #default="{ row }">
          <span :class="['category-cell', { 'total-row': row.isTotal }]">{{ row.category }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="periodAmount" label="本期发生额" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="损益类：从tb_ledger取借方发生−贷方发生">本期发生额</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="损益类：本期发生额=借方发生−贷方发生" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.periodAmount) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="unadjusted" label="未审数" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isTotal" v-model="row.unadjusted" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleCellChange(row)" />
          <span v-else class="cell-value">{{ fmtAmount(row.unadjusted) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="aje" label="AJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isTotal" v-model="row.aje" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleCellChange(row)" />
          <span v-else class="cell-value">{{ fmtAmount(row.aje) }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="rje" label="RJE" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isTotal" v-model="row.rje" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleCellChange(row)" />
          <span v-else class="cell-value">{{ fmtAmount(row.rje) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="审定数" min-width="120" align="right">
        <template #header>
          <span class="formula-header" title="审定数 = 未审 + AJE + RJE">审定数</span>
        </template>
        <template #default="{ row }">
          <el-tooltip content="审定数 = 未审数 + AJE + RJE" placement="top">
            <span class="formula-cell">{{ fmtAmount(row.audited) }}</span>
          </el-tooltip>
        </template>
      </el-table-column>
      <el-table-column prop="priorPeriod" label="上期数" min-width="110" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly && !row.isTotal" v-model="row.priorPeriod" :controls="false" :precision="2" size="small" class="cell-input" @change="() => handleCellChange(row)" />
          <span v-else class="cell-value">{{ fmtAmount(row.priorPeriod) }}</span>
        </template>
      </el-table-column>
    </el-table>

    <!-- ═══ N5-4/N5-8取数交叉验证 ═══ -->
    <div class="cross-validation-section">
      <div class="cv-title">交叉验证（N5-4当期所得税 / N5-8递延所得税费用）</div>
      <div class="cv-indicators">
        <div class="cv-item" :class="cvCurrentMatch ? 'cv-match' : 'cv-diff'">
          <span class="cv-label">当期所得税：N5-1审定 vs N5-4计算</span>
          <span class="cv-badge" :class="cvCurrentMatch ? 'cv-badge-ok' : 'cv-badge-err'">
            {{ cvCurrentMatch ? '✓ 一致' : '⚠ 差异 ' + fmtAmount(cvCurrentDiff) }}
          </span>
        </div>
        <div class="cv-item" :class="cvDeferredMatch ? 'cv-match' : 'cv-diff'">
          <span class="cv-label">递延所得税费用：N5-1审定 vs N5-8核对</span>
          <span class="cv-badge" :class="cvDeferredMatch ? 'cv-badge-ok' : 'cv-badge-err'">
            {{ cvDeferredMatch ? '✓ 一致' : '⚠ 差异 ' + fmtAmount(cvDeferredDiff) }}
          </span>
        </div>
      </div>
    </div>

    <!-- ═══ TB回写按钮 ═══ -->
    <div class="action-bar">
      <el-button type="primary" size="small" :disabled="isReadonly" :loading="writebackLoading" @click="handleWritebackTB">
        回写审定数 → TB(6801·本期发生额)
      </el-button>
      <span class="action-hint">损益类科目回写本期发生额口径</span>
    </div>

    <!-- ═══ 审计说明+结论 ═══ -->
    <el-card shadow="never" class="audit-notes-card">
      <template #header>
        <div class="notes-header">
          <span>审计说明与结论</span>
          <el-button size="small" @click="handleNotesAi"><el-icon><MagicStick /></el-icon>AI辅助</el-button>
        </div>
      </template>
      <div class="notes-field">
        <label class="field-label">审计说明</label>
        <el-input v-model="auditNotes" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" placeholder="请输入审计说明..." :disabled="isReadonly" @change="handleNotesSave" />
      </div>
      <div class="notes-field">
        <label class="field-label">审计结论</label>
        <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" placeholder="请输入审计结论..." :disabled="isReadonly" @change="handleConclusionSave" />
      </div>
    </el-card>

    <!-- ═══ 编制提示 ═══ -->
    <details class="n5-details-tip">
      <summary>编制提示</summary>
      <ul>
        <li>所得税费用(6801)为<strong>损益类借方科目</strong>，取本期发生额（非余额）</li>
        <li>审定数 = 未审数 + AJE + RJE</li>
        <li>所得税费用 = 当期所得税费用 + 递延所得税费用</li>
        <li>当期所得税取自N5-4计算表，递延所得税费用取自N5-8核对表</li>
        <li>"回写审定数"回写试算表（科目6801，本期发生额口径）</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * N5TabAdjudication — 所得税费用审定表N5-1
 *
 * 36公式+损益类发生额取数+当期/递延/合计分行+N5-4/N5-8取数+TB回写+有效税率
 *
 * Spec: .kiro/specs/n5-income-tax-expense/ Task 4.2
 * Requirements: 2.1-2.8
 */
import { ref, computed, inject, onMounted, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { MagicStick, ChatDotSquare } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { calcAuditedAmount } from '../../composables/useN5FormulaEngine'
import { useN5CrossSheet } from '../../composables/useN5CrossSheet'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const allResponsesRef = computed(() => props.allResponses)

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef })
const { adjudicationVsCalc, effectiveTaxRate } = useN5CrossSheet(allResponsesRef, { wpId: wpIdRef, projectId: projectIdRef })

const etr = effectiveTaxRate
const writebackLoading = ref(false)
const auditNotes = ref('')
const auditConclusion = ref('')

// ─── 审定表行数据 ────────────────────────────────────────────────────────────

interface AdjRow {
  key: string
  category: string
  periodAmount: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
  priorPeriod: number
  isTotal: boolean
}

const currentRow = ref<AdjRow>({ key: 'current', category: '一、当期所得税费用', periodAmount: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0, priorPeriod: 0, isTotal: false })
const deferredRow = ref<AdjRow>({ key: 'deferred', category: '二、递延所得税费用', periodAmount: 0, unadjusted: 0, aje: 0, rje: 0, audited: 0, priorPeriod: 0, isTotal: false })
const totalRow = computed<AdjRow>(() => ({
  key: 'total', category: '三、所得税费用合计', periodAmount: currentRow.value.periodAmount + deferredRow.value.periodAmount,
  unadjusted: currentRow.value.unadjusted + deferredRow.value.unadjusted,
  aje: currentRow.value.aje + deferredRow.value.aje, rje: currentRow.value.rje + deferredRow.value.rje,
  audited: calcAuditedAmount(currentRow.value.unadjusted + deferredRow.value.unadjusted, currentRow.value.aje + deferredRow.value.aje, currentRow.value.rje + deferredRow.value.rje),
  priorPeriod: currentRow.value.priorPeriod + deferredRow.value.priorPeriod, isTotal: true,
}))

const tableData = computed<AdjRow[]>(() => {
  // 实时计算审定数
  currentRow.value.audited = calcAuditedAmount(currentRow.value.unadjusted, currentRow.value.aje, currentRow.value.rje)
  deferredRow.value.audited = calcAuditedAmount(deferredRow.value.unadjusted, deferredRow.value.aje, deferredRow.value.rje)
  return [currentRow.value, deferredRow.value, totalRow.value]
})

// ─── 交叉验证 ────────────────────────────────────────────────────────────────

const cvCurrentDiff = computed(() => currentRow.value.audited - adjudicationVsCalc.value.current)
const cvCurrentMatch = computed(() => Math.abs(cvCurrentDiff.value) < 0.01)
const cvDeferredDiff = computed(() => deferredRow.value.audited - adjudicationVsCalc.value.deferred)
const cvDeferredMatch = computed(() => Math.abs(cvDeferredDiff.value) < 0.01)

// ─── 数据加载 ────────────────────────────────────────────────────────────────

onMounted(async () => {
  await formData.loadData()
  // 从已保存数据恢复
  const cData = formData.getField('1', 'current-row')
  if (cData) { Object.assign(currentRow.value, cData) }
  const dData = formData.getField('1', 'deferred-row')
  if (dData) { Object.assign(deferredRow.value, dData) }
  auditNotes.value = formData.getField('1', 'audit-notes') ?? ''
  auditConclusion.value = formData.getField('1', 'audit-conclusion') ?? ''
  // 从tb_ledger取本期发生额seed
  if (formData.tbOccurrence.value.net !== 0) {
    currentRow.value.periodAmount = formData.tbOccurrence.value.net
  }
})

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleCellChange(row: AdjRow) {
  row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
  if (row.key === 'current') await formData.setField('1', 'current-row', { ...currentRow.value })
  if (row.key === 'deferred') await formData.setField('1', 'deferred-row', { ...deferredRow.value })
}

async function handleWritebackTB() {
  writebackLoading.value = true
  try {
    await formData.writebackTB(totalRow.value.audited)
    ElMessage.success('审定数已回写试算表（科目6801·本期发生额）')
  } catch { ElMessage.error('回写失败') }
  finally { writebackLoading.value = false }
}

async function handleNotesSave() { await formData.setField('1', 'audit-notes', auditNotes.value) }
async function handleConclusionSave() { await formData.setField('1', 'audit-conclusion', auditConclusion.value) }

function handleAiAssist() { ElMessage.info('AI辅助分析所得税费用审定表...') }
function handleNotesAi() { ElMessage.info('AI辅助生成审计说明...') }
function handleReview() { openReviewDialog ? openReviewDialog('N5-1-审定表') : ElMessage.info('复核对话未配置') }

function getSummaries({ columns }: { columns: any[] }) {
  return columns.map((_c: any, idx: number) => idx === 0 ? '合计' : (idx >= 1 ? fmtAmount((totalRow.value as any)[['periodAmount','unadjusted','aje','rje','audited','priorPeriod'][idx-1] as string] ?? 0) : ''))
}

function fmtAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function fmtPercent(val: number | null | undefined): string {
  if (val == null) return '—'
  return (val * 100).toFixed(2) + '%'
}
</script>

<style scoped>
.audit-objective { margin-bottom: 16px; }
.audit-objective :deep(.el-alert__description) { font-size: 13px; line-height: 1.6; }
.n5-adjudication { padding: 12px; font-size: 13px; }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: 13px; color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }

.etr-indicator { display: flex; align-items: center; gap: 8px; padding: 10px 16px; margin-bottom: 16px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 6px; font-size: 13px; }
.etr-label { color: #606266; font-weight: 500; }
.etr-value { font-size: 16px; font-weight: 700; color: #303133; }
.etr-formula { color: #909399; font-size: 12px; }

.adjudication-table { margin-bottom: 16px; }
:deep(.adjudication-table .el-table) { font-size: 13px; }
.category-cell { font-weight: 500; color: #303133; }
.total-row { font-weight: 700; color: #409eff; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: 13px; }
.cell-value { font-size: 13px; color: #606266; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }

.cross-validation-section { margin-bottom: 16px; padding: 14px 16px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; }
.cv-title { font-size: 13px; font-weight: 500; color: #303133; margin-bottom: 10px; }
.cv-indicators { display: flex; flex-wrap: wrap; gap: 10px; }
.cv-item { display: flex; align-items: center; gap: 8px; padding: 6px 12px; border-radius: 6px; font-size: 12px; }
.cv-match { background: #e8f5e9; border: 1px solid #a5d6a7; }
.cv-diff { background: #fef0f0; border: 1px solid #fab6b6; }
.cv-label { color: #606266; }
.cv-badge { font-weight: 600; font-size: 12px; }
.cv-badge-ok { color: #43a047; }
.cv-badge-err { color: #f56c6c; }

.action-bar { display: flex; align-items: center; gap: 16px; margin-bottom: 16px; padding: 10px 16px; background: #f5f7fa; border-radius: 6px; }
.action-hint { font-size: 12px; color: #909399; }

.audit-notes-card { margin-bottom: 16px; }
.notes-header { display: flex; align-items: center; justify-content: space-between; font-size: 14px; font-weight: 500; }
.notes-field { margin-bottom: 12px; }
.notes-field:last-child { margin-bottom: 0; }
.field-label { display: block; font-size: 13px; font-weight: 500; color: #606266; margin-bottom: 6px; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: 13px; color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
