<template>
  <div class="g5-reversal-writeoff">
    <div class="section-head">
      <h3 class="sheet-title">G5-11 减值准备转回（收回）、核销检查表</h3>
      <div class="head-actions tab-toolbar">
        <GtIndexChip value="wp:G5-11" />
        <GtReviewTrigger section-id="g5-11-reversal-writeoff" />
        <G5ImportExportDropdown :wp-id="props.wpId" sheet="G5-11" :disabled="!!props.readonly" @imported="onImported" />
      </div>
    </div>

    <div class="method-context">
      <p><strong>编制思路</strong>：识别本期重要转回/收回与核销 → 核对金额（转回≤累计计提）与审批程序 → 做合理性分析（尤其关联方）→ 回填 G5-3 本期转回/核销并支撑审定。</p>
    </div>

    <el-alert type="info" :closable="false" show-icon class="audit-objective">
      <template #title>一、审计目标</template>
      确定长期应收款已按企业会计准则规定恰当计价，减值准备的转回（收回）与核销已恰当记录；关注转回上限、核销审批及关联交易异常。
    </el-alert>

    <div class="proc-block">
      <div class="proc-title">二、审计过程</div>
      <ol>
        <li>获取本期重要减值准备转回/收回及核销清单，与账务记录核对。</li>
        <li>逐笔核实原因、原计提依据、收回方式或核销程序，完成合理性分析（可弹窗判断）。</li>
        <li>汇总金额与 G5-3 坏账准备变动表「本期转回 / 本期核销」勾稽。</li>
      </ol>
    </div>

    <!-- （一）转回 -->
    <div class="section-card">
      <div class="section-head-row">
        <span class="section-title">（一）本期重要的减值准备转回或收回检查</span>
        <div class="row-actions">
          <el-tag size="small" type="info" effect="plain">{{ rw.reversalRows.value.length }} 笔</el-tag>
          <el-button size="small" type="primary" plain :disabled="props.readonly" @click="openCreate('reversal')">+ 新增转回</el-button>
        </div>
      </div>
      <el-table
        :data="rw.reversalRows.value"
        border
        stripe
        size="small"
        style="width:100%"
        max-height="320"
        empty-text="本期无重要转回/收回；如有请新增并完成合理性分析"
        :row-class-name="reversalRowClass"
        show-summary
        :summary-method="reversalSummary"
      >
        <el-table-column prop="seq" label="序号" width="48" align="center" />
        <el-table-column label="单位名称" min-width="110" prop="debtor" show-overflow-tooltip />
        <el-table-column label="转回原因" min-width="110" prop="reason" show-overflow-tooltip />
        <el-table-column label="收回方式" width="100" prop="recoveryMethod" show-overflow-tooltip />
        <el-table-column label="原减值依据" min-width="120" prop="originalBasis" show-overflow-tooltip />
        <el-table-column label="转回/收回金额" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.reversalAmount) }}</template>
        </el-table-column>
        <el-table-column label="转回前累计计提" width="120" align="right">
          <template #default="{ row }">{{ fmt(row.accumulatedProvision) }}</template>
        </el-table-column>
        <el-table-column label="合理性分析" min-width="140" prop="reasonableness" show-overflow-tooltip />
        <el-table-column label="关联" width="56" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isRelatedParty" type="warning" size="small">是</el-tag>
            <span v-else class="muted">否</span>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="70" prop="indexRef" />
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit('reversal', row)">分析</el-button>
            <el-button v-if="!props.readonly" size="small" link type="danger" @click="rw.removeReversalRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- （二）核销 -->
    <div class="section-card">
      <div class="section-head-row">
        <span class="section-title">（二）本期重要的核销检查</span>
        <div class="row-actions">
          <el-tag size="small" type="info" effect="plain">{{ rw.writeoffRows.value.length }} 笔</el-tag>
          <el-button size="small" type="primary" plain :disabled="props.readonly" @click="openCreate('writeoff')">+ 新增核销</el-button>
        </div>
      </div>
      <el-table
        :data="rw.writeoffRows.value"
        border
        stripe
        size="small"
        style="width:100%"
        max-height="320"
        empty-text="本期无重要核销；如有请新增并核对审批程序"
        :row-class-name="writeoffRowClass"
        show-summary
        :summary-method="writeoffSummary"
      >
        <el-table-column prop="seq" label="序号" width="48" align="center" />
        <el-table-column label="单位名称" min-width="110" prop="debtor" show-overflow-tooltip />
        <el-table-column label="应收款性质" width="110" prop="nature" show-overflow-tooltip />
        <el-table-column label="核销金额" width="110" align="right">
          <template #default="{ row }">{{ fmt(row.writeoffAmount) }}</template>
        </el-table-column>
        <el-table-column label="核销原因" min-width="110" prop="reason" show-overflow-tooltip />
        <el-table-column label="履行的核销程序" min-width="130" prop="procedures" show-overflow-tooltip />
        <el-table-column label="关联交易" width="80" align="center">
          <template #default="{ row }">
            <el-tag v-if="row.isRelatedParty" type="warning" size="small">是</el-tag>
            <span v-else class="muted">否</span>
          </template>
        </el-table-column>
        <el-table-column label="合理性分析" min-width="140" prop="reasonableness" show-overflow-tooltip />
        <el-table-column label="审批" width="72" align="center">
          <template #default="{ row }">
            <el-tag :type="row.approvalComplete ? 'success' : 'danger'" size="small" effect="plain">
              {{ row.approvalComplete ? '完整' : '缺' }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="索引" width="70" prop="indexRef" />
        <el-table-column label="操作" width="120" fixed="right" align="center">
          <template #default="{ row }">
            <el-button size="small" link type="primary" @click="openEdit('writeoff', row)">分析</el-button>
            <el-button v-if="!props.readonly" size="small" link type="danger" @click="rw.removeWriteoffRow(row.id)">删</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="totals-bar">
      转回合计 {{ fmt(rw.totals.value.reversalAmount) }}
      （对应累计计提合计 {{ fmt(rw.totals.value.accumulatedProvision) }}）
      · 核销合计 {{ fmt(rw.totals.value.writeoffAmount) }}
      <span v-if="rw.invalidReversals.value.length" class="err-text"> · ⚠ {{ rw.invalidReversals.value.length }} 条转回超累计计提</span>
      <span v-if="rw.incompleteWriteoffs.value.length" class="err-text"> · ⚠ {{ rw.incompleteWriteoffs.value.length }} 条核销审批不完整</span>
      <span v-if="relatedCount" class="warn-text"> · 关联方 {{ relatedCount }} 笔</span>
    </div>

    <G5AuditTextCards
      :wp-id="props.wpId"
      :is-readonly="!!props.readonly"
      :note="auditNote"
      :conclusion="auditConclusion"
      conclusion-title="四、审计结论"
      conclusion-ai-section="reversal-writeoff-conclusion"
      note-placeholder="三、审计说明：概述本期重要转回/核销核查情况、超累计计提或审批缺失事项、关联交易关注及与 G5-3 勾稽结果。"
      conclusion-placeholder="填写审计结论：评价转回与核销是否恰当，按 A/B/C 口径表述。"
      @update:note="saveAuditNote"
      @update:conclusion="saveAuditConclusion"
    />

    <details class="prep-hint">
      <summary>📋 编制提示</summary>
      <ul>
        <li>转回金额不得超过转回前累计已计提减值准备（CAS 22），超出红色标记</li>
        <li>核销须有完整审批手续；程序栏与合理性分析检查项「审批」联动</li>
        <li>关联交易转回/核销橙色标记，警惕调节利润</li>
        <li>本表合计应与 G5-3「本期转回 / 本期核销」勾稽后支撑 G5-1 审定</li>
      </ul>
    </details>

    <G5ReversalWriteoffDialog
      v-model="dialogVisible"
      :mode="dialogMode"
      :row="editingRow"
      :readonly="!!props.readonly"
      @save="onDialogSave"
    />
  </div>
</template>

<script setup lang="ts">
import { computed, ref, toRef, onMounted, watch } from 'vue'
import {
  useG5ReversalWriteoff,
  emptyReversalRow,
  emptyWriteoffRow,
  type ReversalRow,
  type WriteoffRow,
} from '../../composables/useG5ReversalWriteoff'
import { useInjectedG5FormData } from '../../composables/useG5LonRecFormData'
import { G5_ITEM_IDS, readCanonicalRaw } from '../../composables/g5StorageContract'
import G5ImportExportDropdown from '../G5ImportExportDropdown.vue'
import G5AuditTextCards from '../G5AuditTextCards.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import GtReviewTrigger from '../../GtReviewTrigger.vue'
import G5ReversalWriteoffDialog from './G5ReversalWriteoffDialog.vue'

const props = defineProps<{ htmlData?: any; wpId: string; projectId: string; readonly?: boolean }>()
const emit = defineEmits<{ imported: [] }>()
const rw = useG5ReversalWriteoff()

const dialogVisible = ref(false)
const dialogMode = ref<'reversal' | 'writeoff'>('reversal')
const editingRow = ref<ReversalRow | WriteoffRow | null>(null)

const relatedCount = computed(
  () => rw.relatedReversals.value.length + rw.relatedWriteoffs.value.length,
)

function openCreate(mode: 'reversal' | 'writeoff'): void {
  dialogMode.value = mode
  editingRow.value = mode === 'reversal' ? emptyReversalRow() : emptyWriteoffRow()
  dialogVisible.value = true
}
function openEdit(mode: 'reversal' | 'writeoff', row: ReversalRow | WriteoffRow): void {
  dialogMode.value = mode
  editingRow.value = mode === 'reversal'
    ? { ...(row as ReversalRow), checks: (row as ReversalRow).checks.map(c => ({ ...c })) }
    : { ...(row as WriteoffRow), checks: (row as WriteoffRow).checks.map(c => ({ ...c })) }
  dialogVisible.value = true
}
function onDialogSave(payload: { mode: 'reversal' | 'writeoff'; row: ReversalRow | WriteoffRow }): void {
  if (payload.mode === 'reversal') rw.upsertReversal(payload.row as ReversalRow)
  else rw.upsertWriteoff(payload.row as WriteoffRow)
}

function reversalRowClass({ row }: { row: ReversalRow }): string {
  if (!row.isValid) return 'row-error'
  if (row.isRelatedParty) return 'row-related'
  return ''
}
function writeoffRowClass({ row }: { row: WriteoffRow }): string {
  if (row.writeoffAmount > 0 && !row.approvalComplete) return 'row-error'
  if (row.isRelatedParty) return 'row-related'
  return ''
}

function reversalSummary({ columns, data }: { columns: any[]; data: ReversalRow[] }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    if (col.label === '转回/收回金额') return fmt(data.reduce((s, r) => s + (Number(r.reversalAmount) || 0), 0))
    if (col.label === '转回前累计计提') return fmt(data.reduce((s, r) => s + (Number(r.accumulatedProvision) || 0), 0))
    return ''
  })
}
function writeoffSummary({ columns, data }: { columns: any[]; data: WriteoffRow[] }) {
  return columns.map((col, i) => {
    if (i === 0) return '合计'
    if (col.label === '核销金额') return fmt(data.reduce((s, r) => s + (Number(r.writeoffAmount) || 0), 0))
    return ''
  })
}

// ─── 持久化 ───
const g5Notes = useInjectedG5FormData({ wpId: toRef(props, 'wpId'), projectId: toRef(props, 'projectId') })
const auditNote = ref('')
const auditConclusion = ref('')
const G5_NOTE_KEY = 'G5-11-audit-note'
const G5_CONCLUSION_KEY = 'G5-11-audit-conclusion'

function saveAuditNote(val: string): void {
  if (props.readonly) return
  auditNote.value = val
  void g5Notes.saveImmediate(G5_NOTE_KEY, { conclusion: null, remark: val })
}
function saveAuditConclusion(val: string): void {
  if (props.readonly) return
  auditConclusion.value = val
  void g5Notes.saveImmediate(G5_CONCLUSION_KEY, { conclusion: null, remark: val })
}

function loadRowsFromRemark(saved: string | null | undefined): void {
  if (!saved) return
  try {
    const parsed = JSON.parse(saved)
    if (Array.isArray(parsed?.reversal)) rw.loadReversalRows(parsed.reversal)
    if (Array.isArray(parsed?.writeoff)) rw.loadWriteoffRows(parsed.writeoff)
    else if (Array.isArray(parsed)) {
      const reversal = parsed.filter((r: any) => r.section === 'reversal' || r.checkZone === 'reversal')
      const writeoff = parsed.filter((r: any) => r.section === 'writeoff' || r.checkZone === 'writeoff')
      if (reversal.length) rw.loadReversalRows(reversal)
      if (writeoff.length) rw.loadWriteoffRows(writeoff)
      if (!reversal.length && !writeoff.length) rw.loadReversalRows(parsed)
    }
  } catch { /* ignore */ }
}

onMounted(async () => {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  const n = g5Notes.allResponses.value.get(G5_NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = g5Notes.allResponses.value.get(G5_CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
  loadRowsFromRemark(readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_11_ROWS)))
})

watch(
  [() => rw.reversalRows.value, () => rw.writeoffRows.value],
  () => {
    if (props.readonly) return
    const json = JSON.stringify({
      reversal: rw.reversalRows.value,
      writeoff: rw.writeoffRows.value,
    })
    g5Notes.debouncedSave(G5_ITEM_IDS.G5_11_ROWS, { remark: json, conclusion: json })
  },
  { deep: true },
)

async function onImported() {
  try { await g5Notes.loadAll() } catch { /* ignore */ }
  loadRowsFromRemark(readCanonicalRaw(g5Notes.allResponses.value.get(G5_ITEM_IDS.G5_11_ROWS)))
  emit('imported')
}

function fmt(v: number) {
  const n = Number(v) || 0
  if (Math.abs(n) < 0.005) return '—'
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.g5-reversal-writeoff { font-size: var(--wp-font-size, 13px); }
.section-head { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; gap: 8px; flex-wrap: wrap; }
.sheet-title { margin: 0; font-size: 15px; }
.head-actions { display: flex; gap: 8px; align-items: center; flex-wrap: wrap; }
.method-context { margin-bottom: 10px; padding: 8px 12px; border-left: 3px solid #e6a23c; background: #fdf6ec; font-size: 12px; color: #865c0a; line-height: 1.7; }
.audit-objective { margin-bottom: 10px; }
.proc-block { margin-bottom: 12px; padding: 8px 12px; background: #f5f7fa; border-radius: 4px; font-size: 12px; color: #606266; }
.proc-title { font-weight: 600; color: #303133; margin-bottom: 4px; }
.proc-block ol { margin: 0; padding-left: 18px; line-height: 1.8; }
.section-card { margin-bottom: 14px; }
.section-head-row { display: flex; justify-content: space-between; align-items: center; gap: 8px; margin-bottom: 6px; flex-wrap: wrap; }
.section-title { font-size: 13px; font-weight: 600; color: #303133; }
.row-actions { display: flex; align-items: center; gap: 8px; }
.muted { color: #c0c4cc; font-size: 12px; }
.totals-bar { margin: 8px 0 12px; padding: 8px 12px; background: #f5f7fa; font-size: 12px; }
.err-text { color: #f56c6c; font-weight: 600; }
.warn-text { color: #e6a23c; font-weight: 600; }
.prep-hint { margin-top: 12px; font-size: 12px; color: #909399; }
.prep-hint summary { cursor: pointer; font-weight: 500; }
.prep-hint ul { margin: 6px 0 0; padding-left: 18px; line-height: 1.8; }
:deep(.row-error) { background-color: #fef0f0 !important; }
:deep(.row-related) { background-color: #fdf6ec !important; }
</style>
