<template>
  <div class="h1-tab-dep-straight">
    <el-alert type="info" :closable="false" class="objective-alert" style="margin-bottom:12px"
      title="审计目标：按直线法独立测算本期折旧（原值×(1−残值率)÷年限÷12×本期月数），与账面计提比较；无减值资产适用本表。" />

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-12" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      <el-tag v-if="periodEnd" size="small">截止日 {{ periodEnd }}</el-tag>
      <el-tag v-if="significantDiffRows.length" size="small" type="danger">差异行 {{ significantDiffRows.length }}</el-tag>
    </div>

    <div class="methodology-context">
      <p>
        CAS4/税法：投入使用<strong>次月</strong>起提折旧。测算月折旧＝原值×(1−残值率)÷使用月限；
        本期折旧＝测算月折旧×本期折旧月份；累计测算＝测算月折旧×期末已提月份。
        有减值请切换「含减值/多次减值」，或点「按减值联动切分支」。
      </p>
    </div>

    <H1DepreciationActions
      :is-readonly="isReadonly"
      :importing="importing"
      :has-rows="rows.length > 0"
      :current-branch="branch"
      :recommendation="branchRecommendation"
      :dashboard="advancedDashboard"
      @import-detail="onImportDetail"
      @import-file="onImportFile"
      @recalc="recalcAll"
      @apply-branch="onApplyBranch"
      @add-row="addRow"
      @sync-h18="onSyncH18"
      @sync-h14="onSyncH14"
      @sync-h17="onSyncH17"
      @sample="onSample"
      @clear-sample="onClearSample"
      @draft-note="onDraftNote"
    />

    <el-card shadow="never">
      <template #header>
        <div class="section-title">
          <span>H1-12(A) 折旧测算 — 不含减值·直线法</span>
          <el-button size="small" type="default" link @click="handleReview('H1-12-A')">💬 复核</el-button>
        </div>
      </template>

      <el-table :data="displayRows" border stripe size="small" max-height="520" class="dep-table"
        :row-class-name="rowClass">
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="类别" width="90" fixed />
        <el-table-column prop="assetNo" label="编号" width="90" />
        <el-table-column prop="assetName" label="名称" min-width="120" show-overflow-tooltip />
        <el-table-column prop="depMethod" label="方法" width="80" show-overflow-tooltip />
        <el-table-column prop="originalCost" label="原值(期末)" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.originalCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="bookAccDepEnd" label="账面累计折旧" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookAccDepEnd) }}</span></template>
        </el-table-column>
        <el-table-column prop="startDate" label="开始使用" width="100" />
        <el-table-column prop="disposalDate" label="处置日" width="100" />
        <el-table-column prop="usefulLife" label="年限" width="50" align="right" />
        <el-table-column label="残值率" width="70" align="right">
          <template #default="{ row }">{{ pct(row.salvageRate) }}</template>
        </el-table-column>
        <el-table-column prop="bookMonthly" label="账面月折旧" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookMonthly) }}</span></template>
        </el-table-column>
        <el-table-column label="使用月限" width="70" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.usefulLifeMonths }}</span></template>
        </el-table-column>
        <el-table-column label="满折日" width="100">
          <template #default="{ row }"><span class="formula-cell">{{ row.fullDepDate || '-' }}</span></template>
        </el-table-column>
        <el-table-column label="已提月份" width="70" align="right">
          <template #default="{ row }"><span class="formula-cell" title="期末已提折旧月份">{{ row.monthsAtEnd }}</span></template>
        </el-table-column>
        <el-table-column label="本期月数" width="70" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.periodMonths }}</span></template>
        </el-table-column>
        <el-table-column label="测算月折旧" width="100" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="原值×(1-残值率)÷年限÷12">{{ fmtAmt(row.calcMonthly) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="当期折旧费用" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="测算月折旧×本期月数">{{ fmtAmt(row.periodTotal) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="月折旧差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', sevClass(row.diffSeverity)]">{{ fmtAmt(row.monthlyDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="测算累计折旧" width="110" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.calcAccDep) }}</span></template>
        </el-table-column>
        <el-table-column label="累计差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', sevClass(row.diffSeverity)]">{{ fmtAmt(row.accDepDiff) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="bookDepreciation" label="账面本期折旧" width="110" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookDepreciation) }}</span></template>
        </el-table-column>
        <el-table-column label="本期差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', sevClass(row.diffSeverity)]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="差异归因" min-width="160" show-overflow-tooltip>
          <template #default="{ row }">
            <span class="attr-cell" :title="(row.diffAttribution?.labels || []).join('；')">
              {{ row.diffAttribution?.primary || (row.beginAccCheck && !row.beginAccCheck.ok ? row.beginAccCheck.message : '') || '-' }}
            </span>
          </template>
        </el-table-column>
        <el-table-column v-if="!isReadonly" label="操作" width="60" fixed="right">
          <template #default="{ row }">
            <el-button link type="danger" size="small" @click="removeRow(row.rowId)">删</el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- 分类小计（对齐底稿「其中」） -->
      <div v-if="categorySubtotals.length" class="cat-subtotals">
        <span class="cat-label">其中：</span>
        <span v-for="c in categorySubtotals" :key="c.category" class="cat-item">
          {{ c.category }} 测算 {{ fmtAmt(c.periodTotal) }} / 账面 {{ fmtAmt(c.bookDepreciation) }}
        </span>
      </div>

      <div class="totals-bar">
        <span>测算本期合计: <b class="amount-cell">{{ fmtAmt(summary.calculatedTotal) }}</b></span>
        <span>账面本期合计: <b class="amount-cell">{{ fmtAmt(summary.bookTotal) }}</b></span>
        <span>本期差异: <b :class="['amount-cell', { 'error-amount': Math.abs(summary.totalDifference) > 0.01 }]">{{ fmtAmt(summary.totalDifference) }}</b></span>
        <span>累计差异: <b :class="['amount-cell', { 'error-amount': Math.abs(summary.accDepDiffTotal) > 0.01 }]">{{ fmtAmt(summary.accDepDiffTotal) }}</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input v-model="depNote" type="textarea" :autosize="{ minRows: 4 }" :disabled="isReadonly"
        placeholder="说明差异原因（含本期减少对累计折旧的影响）、抽测范围、与 H1-2/H1-13 勾稽情况..."
        @change="saveDepNote" />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计结论</span></template>
      <el-input v-model="auditConclusionText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="折旧计提是否公允反映..." @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>优先「从 H1-2 带入」或「一键导入企业台账」→ 自动推荐分支并测算</li>
        <li>差异＝账面−测算；红色表示 |差异|&gt;0.01，需追查政策变更/处置/停用/错提</li>
        <li>需单独考虑本期固定资产减少对累计折旧的影响</li>
        <li>本表不含减值；若行上有减值余额，系统会提示切换 B/C 分支</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useH1Depreciation } from '../../composables/useH1Depreciation'
import GtIndexChip from '../../GtIndexChip.vue'
import H1DepreciationActions from './H1DepreciationActions.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  periodEnd?: string
}>()

const emit = defineEmits<{ (e: 'branch-change', branch: 'A' | 'B' | 'C'): void }>()

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})
const saveResponse = inject<(id: string, val: any) => void>('saveResponse', () => {})
const allResponsesRef = computed(() => props.allResponses)
const periodEndRef = computed(() => props.periodEnd || '')

const depNote = ref('')
const auditConclusionText = ref('')
const NOTE_KEY = 'H1-12-audit-note-straight'
const CONCLUSION_KEY = 'H1-12-audit-conclusion-straight'

function saveDepNote() { saveResponse(NOTE_KEY, depNote.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, auditConclusionText.value) }

onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) depNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) auditConclusionText.value = c.remark
})

const {
  branch,
  rows,
  displayRows,
  summary,
  categorySubtotals,
  branchRecommendation,
  significantDiffRows,
  advancedDashboard,
  importing,
  auditNote,
  recalcAll,
  importFromDetail,
  importEnterpriseLedger,
  applyRecommendedBranch,
  syncFromDisposalH18,
  syncFromImpairmentH14,
  syncFromAdditionH7,
  applySampling,
  clearSampling,
  applyAuditNoteDraft,
  addRow,
  removeRow,
} = useH1Depreciation(
  toRef(props, 'wpId'),
  toRef(props, 'projectId'),
  allResponsesRef as any,
  {
    periodEnd: periodEndRef,
    onSave: (id, val) => saveResponse(id, val),
    onBranchChange: (b) => emit('branch-change', b),
  },
)

watch(branch, (b) => emit('branch-change', b))
watch(auditNote, (v) => { if (v) depNote.value = v })

function onImportDetail() {
  const r = importFromDetail()
  ElMessage.success(`已从 H1-2 带入 ${r.imported} 项，已切至「${branchLabel(r.branch)}」并完成测算`)
  emit('branch-change', r.branch)
}

async function onImportFile(file: File) {
  const preview = await importEnterpriseLedger(file, true)
  if (!preview) {
    ElMessage.error('导入失败：请检查表头是否含原值/名称/年限等关键列')
    return
  }
  const warn = preview.warnings.length ? `（提示：${preview.warnings.join('；')}）` : ''
  ElMessage.success(`已导入 ${preview.rowCount} 项并测算，分支：${branchLabel(preview.branch)}${warn}`)
  emit('branch-change', preview.branch)
}

function onApplyBranch() {
  const b = applyRecommendedBranch()
  ElMessage.info(`已切换至推荐分支：${branchLabel(b)}`)
  emit('branch-change', b)
}

function onSyncH18() {
  const r = syncFromDisposalH18()
  ElMessage.success(`已勾稽 H1-8 处置 ${r.linked} 项${r.notes.length ? '；' + r.notes.slice(0, 2).join('；') : ''}`)
}

function onSyncH14() {
  const r = syncFromImpairmentH14()
  ElMessage.success(`已勾稽 H1-14 减值 ${r.linked} 项${r.notes.length ? '；' + r.notes.slice(0, 2).join('；') : ''}`)
}

function onSyncH17() {
  const r = syncFromAdditionH7()
  ElMessage.success(`已勾稽 H1-7 折旧起算 ${r.linked} 项${r.notes.length ? '；' + r.notes.slice(0, 2).join('；') : ''}`)
}

function onSample(coverage: number) {
  const r = applySampling(coverage)
  ElMessage.success(`抽样完成：${r.selected.length}/${rows.value.length} 项，原值覆盖 ${(r.costCoverage * 100).toFixed(1)}%`)
}

function onClearSample() {
  clearSampling()
  ElMessage.info('已恢复全量测算')
}

function onDraftNote() {
  applyAuditNoteDraft()
  depNote.value = auditNote.value
  saveDepNote()
  ElMessage.success('已写入审计说明草稿（含水印/处置/抽样/重大差异）')
}

function branchLabel(b: string) {
  return b === 'A' ? '不含减值' : b === 'B' ? '含减值' : '多次减值'
}

function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function pct(rate: number): string {
  return `${((rate > 1 ? rate : rate * 100)).toFixed(2)}%`.replace(/\.00%/, '%')
}
function sevClass(sev: string) {
  if (sev === 'material') return 'error-amount'
  if (sev === 'review') return 'warn-amount'
  if (sev === 'rounding') return 'round-amount'
  return ''
}
function rowClass({ row }: { row: any }) {
  if (row.diffSeverity === 'material') return 'diff-row-material'
  if (row.diffSeverity === 'review' || Math.abs(row.difference) > 0.01) return 'diff-row'
  if (row.beginAccCheck && !row.beginAccCheck.ok) return 'begin-fail-row'
  return ''
}
</script>

<style scoped>
.h1-tab-dep-straight { padding: 16px; font-size: var(--wp-font-size, 13px); }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.dep-table { font-size: 12px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.attr-cell { font-size: 11px; color: var(--el-text-color-secondary); }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.warn-amount { color: var(--el-color-warning-dark-2); font-weight: 600; }
.round-amount { color: var(--el-color-info); }
.totals-bar { display: flex; flex-wrap: wrap; gap: 20px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; }
.cat-subtotals { display: flex; flex-wrap: wrap; gap: 12px; padding: 8px 4px; font-size: 12px; color: var(--el-text-color-secondary); }
.cat-label { font-weight: 600; color: var(--el-text-color-primary); }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.diff-row) { background: var(--el-color-danger-light-9) !important; }
:deep(.diff-row-material) { background: #fde2e2 !important; }
:deep(.begin-fail-row) { background: #fdf6ec !important; }
</style>
