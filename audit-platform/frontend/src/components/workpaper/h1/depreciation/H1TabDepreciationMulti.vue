<template>
  <div class="h1-tab-dep-multi">
    <el-alert type="info" :closable="false" style="margin-bottom:12px"
      title="审计目标：验证多次减值各时点后折旧重新测算准确；每段按新基数/剩余月数计月折旧，累计与账面勾稽；CAS8 减值不得转回。" />

    <div class="tab-toolbar">
      <GtIndexChip value="wp:H1-12" :context-project-id="projectId" />
      <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      <el-tag v-if="periodEnd" size="small">截止日 {{ periodEnd }}</el-tag>
    </div>

    <div class="methodology-context">
      <p>
        多次减值：按减值时点切段；每段月折旧＝(原值−段初累计折旧−累计减值−残值)÷剩余月数。
        本期折旧为各段在本期内的月数×对应月折旧之和。点击行查看减值时间线。
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
          <span>H1-12(C) 折旧测算 — 多次减值</span>
          <el-button size="small" link @click="handleReview('H1-12-C')">💬 复核</el-button>
        </div>
      </template>

      <el-table
        :data="displayRows" border stripe size="small" max-height="420" class="dep-table"
        highlight-current-row
        :row-class-name="rowClass"
        @current-change="onSelectRow"
      >
        <el-table-column type="index" width="40" fixed />
        <el-table-column prop="category" label="类别" width="90" fixed />
        <el-table-column prop="assetName" label="名称" min-width="110" show-overflow-tooltip />
        <el-table-column prop="originalCost" label="原值" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.originalCost) }}</span></template>
        </el-table-column>
        <el-table-column prop="usefulLife" label="原年限" width="55" align="right" />
        <el-table-column label="减值次数" width="70" align="center">
          <template #default="{ row }">{{ row.impairmentEvents?.length ?? 0 }}</template>
        </el-table-column>
        <el-table-column label="累计减值" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(totalImpairment(row)) }}</span></template>
        </el-table-column>
        <el-table-column label="当前月折旧" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.postImpairmentMonthlyDep || row.monthlyDep) }}</span></template>
        </el-table-column>
        <el-table-column label="本期月数" width="70" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ row.periodMonths }}</span></template>
        </el-table-column>
        <el-table-column label="当期折旧" width="100" align="right">
          <template #default="{ row }"><span class="formula-cell">{{ fmtAmt(row.periodTotal) }}</span></template>
        </el-table-column>
        <el-table-column prop="bookDepreciation" label="账面" width="100" align="right">
          <template #default="{ row }"><span class="amount-cell">{{ fmtAmt(row.bookDepreciation) }}</span></template>
        </el-table-column>
        <el-table-column label="差异" width="90" align="right">
          <template #default="{ row }">
            <span :class="['formula-cell', { 'error-amount': Math.abs(row.difference) > 0.01 }]">{{ fmtAmt(row.difference) }}</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="impairment-timeline" v-if="selectedRow">
        <h4>{{ selectedRow.assetName || selectedRow.category }} — 减值事件时间线</h4>
        <el-timeline v-if="selectedRow.impairmentEvents?.length">
          <el-timeline-item
            v-for="(evt, idx) in selectedRow.impairmentEvents"
            :key="idx"
            :timestamp="evt.eventDate || `时点${idx + 1}`"
            placement="top"
          >
            <el-card shadow="never" class="timeline-card">
              <p>
                减值金额: <b>{{ fmtAmt(evt.amount) }}</b>
                | 剩余年限: {{ evt.remainingLife }} 年
                | 新月折旧: <b class="formula-cell">{{ fmtAmt(evt.newMonthlyDep) }}</b>
              </p>
            </el-card>
          </el-timeline-item>
        </el-timeline>
        <el-empty v-else description="暂无减值事件明细，请补充或从台账导入" :image-size="64" />
      </div>

      <div class="totals-bar">
        <span>测算合计: <b class="amount-cell">{{ fmtAmt(summary.calculatedTotal) }}</b></span>
        <span>差异合计: <b :class="['amount-cell', { 'error-amount': Math.abs(summary.totalDifference) > 0.01 }]">{{ fmtAmt(summary.totalDifference) }}</b></span>
      </div>
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header><span>三、审计说明</span></template>
      <el-input v-model="depNote" type="textarea" :autosize="{ minRows: 4 }" :disabled="isReadonly"
        placeholder="说明各减值时点依据及折旧重算过程..." @change="saveDepNote" />
    </el-card>
    <el-card shadow="never" class="note-card">
      <template #header><span>四、审计结论</span></template>
      <el-input v-model="auditConclusionText" type="textarea" :autosize="{ minRows: 2 }" :disabled="isReadonly"
        placeholder="填写审计结论..." @change="saveAuditConclusion" />
    </el-card>

    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>每次减值后重算：新基数＝原值−累计折旧−累计减值−残值，÷剩余月数</li>
        <li>点击行查看减值事件时间线</li>
        <li>期初已减值且本期再提减值 → 系统自动推荐本分支</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, inject, toRef, onMounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import { useH1Depreciation, type DepreciationRow } from '../../composables/useH1Depreciation'
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
const selectedRow = ref<DepreciationRow | null>(null)
const NOTE_KEY = 'H1-12-audit-note-multi'
const CONCLUSION_KEY = 'H1-12-audit-conclusion-multi'
function saveDepNote() { saveResponse(NOTE_KEY, depNote.value) }
function saveAuditConclusion() { saveResponse(CONCLUSION_KEY, auditConclusionText.value) }
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY); if (n?.remark) depNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY); if (c?.remark) auditConclusionText.value = c.remark
})

const {
  branch, rows, displayRows, summary, branchRecommendation, advancedDashboard, importing, auditNote,
  recalcAll, importFromDetail, importEnterpriseLedger, applyRecommendedBranch,
  syncFromDisposalH18, syncFromImpairmentH14, syncFromAdditionH7, applySampling, clearSampling, applyAuditNoteDraft, addRow,
} = useH1Depreciation(
  toRef(props, 'wpId'), toRef(props, 'projectId'), allResponsesRef as any,
  {
    periodEnd: periodEndRef,
    onSave: (id, val) => saveResponse(id, val),
    onBranchChange: (b) => emit('branch-change', b),
  },
)
watch(branch, (b) => emit('branch-change', b))
watch(auditNote, (v) => { if (v) depNote.value = v })

function totalImpairment(row: DepreciationRow): number {
  if (row.impairmentEvents?.length) {
    return row.impairmentEvents.reduce((s, e) => s + (e.amount || 0), 0)
  }
  return row.impairmentAmount || row.impairmentEnd || 0
}
function onSelectRow(row: DepreciationRow | null) { selectedRow.value = row }

function onImportDetail() {
  const r = importFromDetail()
  ElMessage.success(`已从 H1-2 带入 ${r.imported} 项 → ${branchLabel(r.branch)}`)
  emit('branch-change', r.branch)
}
async function onImportFile(file: File) {
  const preview = await importEnterpriseLedger(file, true)
  if (!preview) { ElMessage.error('导入失败'); return }
  ElMessage.success(`已导入 ${preview.rowCount} 项 → ${branchLabel(preview.branch)}`)
  emit('branch-change', preview.branch)
}
function onApplyBranch() {
  const b = applyRecommendedBranch()
  ElMessage.info(`已切换：${branchLabel(b)}`)
  emit('branch-change', b)
}
function onSyncH18() {
  ElMessage.success(`H1-8 处置勾稽 ${syncFromDisposalH18().linked} 项`)
}
function onSyncH14() {
  ElMessage.success(`H1-14 减值勾稽 ${syncFromImpairmentH14().linked} 项`)
}
function onSyncH17() {
  ElMessage.success(`H1-7 折旧起算勾稽 ${syncFromAdditionH7().linked} 项`)
}
function onSample(c: number) {
  const r = applySampling(c)
  ElMessage.success(`抽样 ${r.selected.length} 项`)
}
function onClearSample() { clearSampling(); ElMessage.info('已恢复全量') }
function onDraftNote() {
  applyAuditNoteDraft()
  depNote.value = auditNote.value
  saveDepNote()
  ElMessage.success('已生成说明草稿')
}
function branchLabel(b: string) {
  return b === 'A' ? '不含减值' : b === 'B' ? '含减值' : '多次减值'
}
function handleReview(id: string) { openReviewDialog(id) }
function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
function rowClass({ row }: { row: any }) {
  return Math.abs(row.difference) > 0.01 ? 'diff-row' : ''
}
</script>

<style scoped>
.h1-tab-dep-multi { padding: 16px; font-size: var(--wp-font-size, 13px); }
.tab-toolbar { display: flex; justify-content: flex-end; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.methodology-context { border-left: 3px solid var(--el-color-warning); background: #fffbe6; padding: 10px 14px; margin-bottom: 12px; border-radius: 4px; font-size: 12px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.dep-table { font-size: 12px; }
.amount-cell { text-align: right; font-variant-numeric: tabular-nums; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; font-variant-numeric: tabular-nums; }
.error-amount { color: var(--el-color-danger); font-weight: 600; }
.impairment-timeline { margin-top: 16px; padding: 12px; background: var(--el-fill-color-lighter); border-radius: 6px; }
.impairment-timeline h4 { font-size: var(--wp-font-size, 13px); margin-bottom: 12px; }
.timeline-card { font-size: 12px; }
.totals-bar { display: flex; gap: 24px; padding: 10px 12px; margin-top: 12px; background: var(--el-fill-color-light); border-radius: 4px; flex-wrap: wrap; }
.note-card { margin-top: 12px; }
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
:deep(.diff-row) { background: var(--el-color-danger-light-9) !important; }
</style>
