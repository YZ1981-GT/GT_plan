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
        <el-tooltip v-if="tbSourceSummary" :content="tbSourceSummary" placement="top">
          <el-button
            size="small"
            type="success"
            plain
            :disabled="isReadonly || !hasTbSource"
            @click="applyTbSeed"
          >
            从四表库带入未审数
          </el-button>
        </el-tooltip>
        <el-button size="small" type="primary" plain :loading="adjPull.loading.value" @click="openBringInAdjustment">
          <el-icon><Download /></el-icon>带入调整
        </el-button>
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

    <!-- ═══ 与试算平衡表核对（四表库·本期发生额）═══ -->
    <el-alert
      v-if="tbReconcile.hasTb"
      class="tb-reconcile"
      :type="tbReconcile.hasWarning ? 'warning' : 'success'"
      :closable="false"
      show-icon
    >
      <template #title>
        {{ tbReconcile.hasWarning
          ? `审定合计与试算平衡表核对不一致（差异 ${fmtAmount(tbReconcile.diff)}）`
          : '审定合计与试算平衡表核对一致' }}
      </template>
      <template #default>
        试算平衡表数 {{ fmtAmount(tbReconcile.tbAmount) }} · 审定合计
        {{ fmtAmount(totalRow.audited) }}<span v-if="tbSourceSummary"> · {{ tbSourceSummary }}</span>
      </template>
    </el-alert>

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
        <li>「带入调整」：按科目6801拉取调整分录，逐笔选当期/递延所得税费用行累加到 AJE/RJE</li>
      </ul>
    </details>

    <!-- ═══ 带入调整 弹窗 ═══ -->
    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="6801 所得税费用"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
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
import { MagicStick, ChatDotSquare, Download } from '@element-plus/icons-vue'
import { useN5FormData } from '../../composables/useN5FormData'
import { calcAuditedAmount, parseNum } from '../../composables/useN5FormulaEngine'
import { useLmnTbReconcile } from '../../composables/useLmnTbReconcile'
import { useN5CrossSheet } from '../../composables/useN5CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'

const props = defineProps<{
  allResponses: Map<string, any>
  wpId: string
  projectId: string
  isReadonly: boolean
}>()

const openReviewDialog = inject<((section: string) => void) | undefined>('openReviewDialog', undefined)
const scheduleAutoSnapshot = inject<(() => void) | undefined>('scheduleAutoSnapshot', undefined)
const n5AdjudicationPrefill = inject<any>('n5AdjudicationPrefill', null)
const n5TrialBalance = inject<any>('n5TrialBalance', null)
const n5TbSourceCodes = inject<any>('n5TbSourceCodes', null)
const n5Year = inject<Ref<number> | undefined>('n5Year', undefined)

const wpIdRef = computed(() => props.wpId) as Ref<string>
const projectIdRef = computed(() => props.projectId) as Ref<string>
const allResponsesRef = computed(() => props.allResponses)

const formData = useN5FormData({ wpId: wpIdRef, projectId: projectIdRef, year: n5Year })
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

// ─── 带入调整（adjustment-collaboration-and-propagation） ─────────────────────
// 所得税费用审定表仅当期/递延两行，带入调整逐笔分配到目标行的 AJE/RJE 列（累加）。
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: projectIdRef as any,
  year: useAuditContext().year as any,
  subjectPrefix: '6801',
  direction: 'debit', // 损益借方：净发生额 = 借 − 贷
  subjectCode: '6801',
  wpCode: 'N5',
  subjectLabel: '所得税费用(6801)',
  rows: computed(() => [
    { rowKey: 'current', name: currentRow.value.category, aje: currentRow.value.aje, rje: currentRow.value.rje },
    { rowKey: 'deferred', name: deferredRow.value.category, aje: deferredRow.value.aje, rje: deferredRow.value.rje },
  ]),
  updateCell: (rowKey: string, field: any, value: number) => {
    const target = rowKey === 'current' ? currentRow : deferredRow
    ;(target.value as any)[field] = value
    void handleCellChange(target.value)
  },
  totalAudited: () => totalRow.value.audited,
})

// ─── 四表库：TB 核对 + 带入未审数 ─────────────────────────────────────────────

/**
 * 审定合计 vs 试算平衡表核对（复用共享件 `useLmnTbReconcile`，原全仓 0 消费方）。
 * N5 是**损益类** → `isIncome: true`（`period_amount` 即本期发生额）。
 */
const tbReconcile = useLmnTbReconcile(
  computed(() => {
    const tb = n5TrialBalance?.value
    if (!tb) return {}
    return { trial_balance: { end_balance: tb.period_amount ?? 0, begin_balance: 0 } }
  }),
  computed(() => totalRow.value.audited),
  { isIncome: true },
)

/** 取数溯源（消费后端 `tb_source_codes`，消除 dead output） */
const tbSourceSummary = computed(() => {
  const s = n5TbSourceCodes?.value
  if (!s?.codes?.length) return ''
  const basis = s.basis === 'period' ? '本期发生额' : '期末余额'
  return `科目 ${s.codes.join('、')}（报表行 ${s.row_code} · ${basis}）`
})

const hasTbSource = computed(
  () => Boolean(n5AdjudicationPrefill?.value) || tbReconcile.value.hasTb,
)

/**
 * 从四表库带入未审数（后端按 `6801.01 当期` / `6801.02 递延` 叶子拆分）。
 * 🔴 只填空不覆盖（手工优先）；无子科目时后端把总额落「当期」行。
 */
function applyTbSeed(): void {
  const prefill = n5AdjudicationPrefill?.value
  if (!prefill) {
    ElMessage.info('四表库暂无所得税费用发生额，或该科目未导入')
    return
  }
  let filled = 0
  for (const [key, row] of [['current', currentRow], ['deferred', deferredRow]] as const) {
    const src = prefill[key]
    if (!src) continue
    if (parseNum(row.value.unadjusted) !== 0) continue // 手工优先
    row.value.periodAmount = parseNum(src.periodAmount)
    row.value.unadjusted = parseNum(src.unadjusted ?? src.periodAmount)
    void handleCellChange(row.value)
    filled += 1
  }
  if (filled === 0) {
    ElMessage.info('未审数已录入，未覆盖（手工优先）')
    return
  }
  ElMessage.success(`已从四表库带入 ${filled} 行未审数（当期 / 递延按子科目拆分）`)
}

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
  // TB预填（仅无已保存数据 + 有后端预填数据时seed）
  if (!cData && !dData && n5AdjudicationPrefill?.value) {
    const prefill = n5AdjudicationPrefill.value
    if (prefill.current) Object.assign(currentRow.value, prefill.current)
    if (prefill.deferred) Object.assign(deferredRow.value, prefill.deferred)
  }
})

// ─── 保存 ────────────────────────────────────────────────────────────────────

async function handleCellChange(row: AdjRow) {
  row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
  if (row.key === 'current') await formData.setField('1', 'current-row', { ...currentRow.value })
  if (row.key === 'deferred') await formData.setField('1', 'deferred-row', { ...deferredRow.value })
  scheduleAutoSnapshot?.()
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

function handleAiAssist() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n5-adjudication',
      prompt: '请基于所得税费用底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}
function handleNotesAi() {
  import('@/utils/http').then(({ default: h }) => {
    h.post(`/api/workpapers/${props.wpId}/ai/generate-text`, {
      section: 'n5-adjudication',
      prompt: '请基于所得税费用底稿数据，给出审计分析建议',
      context: { wpId: props.wpId },
    }).catch(() => {})
  })
}
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
.audit-objective :deep(.el-alert__description) { font-size: var(--wp-font-size, 13px); line-height: 1.6; }
.n5-adjudication { padding: 12px; font-size: var(--wp-font-size, 13px); }
.methodology-context { padding: 12px 16px; margin-bottom: 16px; background: #fffbeb; border: 1px solid #fde68a; border-left: 4px solid #d97706; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #92400e; line-height: 1.7; }
.methodology-context p { margin: 0; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { display: flex; align-items: center; gap: 10px; font-size: 15px; font-weight: 600; color: #303133; }
.section-actions { display: flex; align-items: center; gap: 8px; }
.tb-reconcile { margin: 12px 0; }
.tb-reconcile :deep(.el-alert__description) { font-size: var(--wp-font-size, 13px); line-height: 1.6; }

.etr-indicator { display: flex; align-items: center; gap: 8px; padding: 10px 16px; margin-bottom: 16px; background: #f0f9eb; border: 1px solid #c2e7b0; border-radius: 6px; font-size: var(--wp-font-size, 13px); }
.etr-label { color: #606266; font-weight: 500; }
.etr-value { font-size: 16px; font-weight: 700; color: #303133; }
.etr-formula { color: #909399; font-size: 12px; }

.adjudication-table { margin-bottom: 16px; }
:deep(.adjudication-table .el-table) { font-size: var(--wp-font-size, 13px); }
.category-cell { font-weight: 500; color: #303133; }
.total-row { font-weight: 700; color: #409eff; }
.cell-input { width: 100%; }
:deep(.cell-input .el-input__inner) { text-align: right; font-size: var(--wp-font-size, 13px); }
.cell-value { font-size: var(--wp-font-size, 13px); color: #606266; }
.formula-header { border-bottom: 1px dashed #409eff; cursor: help; color: #409eff; font-weight: 600; }
.formula-cell { border-bottom: 1px dashed #909399; cursor: help; font-weight: 500; color: #303133; padding-bottom: 1px; }

.cross-validation-section { margin-bottom: 16px; padding: 14px 16px; background: #fafbfc; border: 1px solid #ebeef5; border-radius: 8px; }
.cv-title { font-size: var(--wp-font-size, 13px); font-weight: 500; color: #303133; margin-bottom: 10px; }
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
.field-label { display: block; font-size: var(--wp-font-size, 13px); font-weight: 500; color: #606266; margin-bottom: 6px; }

.n5-details-tip { margin-top: 12px; padding: 12px 16px; background: #fafafa; border: 1px solid #ebeef5; border-radius: 6px; font-size: var(--wp-font-size, 13px); color: #606266; }
.n5-details-tip summary { cursor: pointer; font-weight: 500; color: #303133; margin-bottom: 8px; }
.n5-details-tip ul { padding-left: 20px; margin: 8px 0 0; line-height: 1.8; }
</style>
