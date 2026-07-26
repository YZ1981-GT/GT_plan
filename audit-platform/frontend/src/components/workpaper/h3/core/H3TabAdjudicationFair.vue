<template>
  <div class="h3-tab-adjudication-fair">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为投资性房地产审定表（公允价值模式），单区块列示公允价值变动，期末公允 = 期初 + 增加 − 减少 ± 转换 + 公允价值变动。</p>
        <p>2. 公允价值模式下不计提折旧与减值（CAS3）；公允价值变动计入当期损益。</p>
        <p>3. 未审数取自试算表（科目 1503），审定数 = 未审 + AJE + RJE；采用公允价值模式须满足有活跃交易市场且可获取同类价格信息。</p>
        <p>4. 若企业采用成本模式，请切换至成本模式版本填报。</p>
        <p>5.「带入调整」：从集中登记按科目 1503 拉取调整分录（资产借方净额=借−贷），逐笔分配到各分类的 AJE/RJE，带入后审定数自动更新并联动附注。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="审计目标：核实投资性房地产（公允价值模式，科目 1503）期末公允价值的存在、准确与计量恰当，验证公允价值变动损益的合理性，为报表及附注披露提供审定依据。"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="openFillDialog">从 H3-2 回填</el-button>
      <el-button
        size="small"
        type="warning"
        :disabled="isReadonly || !hasDetailFairDiff"
        @click="alignFromH32"
      >
        {{ hasDetailFairDiff ? '一键对齐 H3-2' : '已与 H3-2 勾稽' }}
      </el-button>
      <el-button
        size="small"
        :disabled="isReadonly || !hasTransferDiff"
        @click="onFillTransferFromH36"
      >
        {{ hasTransferDiff ? '从 H3-6 回填转换' : '转换已勾稽' }}
      </el-button>
      <el-button size="small" type="primary" plain :disabled="isReadonly" :loading="adjPull.loading.value" @click="openBringInAdjustment">
        <el-icon><Download /></el-icon>带入调整
      </el-button>
      <span class="chip-wrap"><GtIndexChip value="wp:H3-1" :context-project-id="projectId" /></span>
      <el-tag v-if="h38Reconcile.matched" size="small" type="success">H3-8勾稽一致</el-tag>
      <el-tag v-else-if="h38Reconcile.hasH38Data" size="small" type="danger">H3-8差异</el-tag>
      <el-tag v-else size="small" type="info">H3-8待编制</el-tag>
      <el-tag size="small" type="info">共 {{ fairRows.length }} 行</el-tag>
      <el-tag v-if="h32CategoryMatch.unmatchedCount > 0" size="small" type="warning">
        H3-2 非标准类别 {{ h32CategoryMatch.unmatchedCount }} 行
      </el-tag>
    </div>

    <el-dialog v-model="fillDialogVisible" title="从 H3-2 回填 H3-1" width="720px" destroy-on-close>
      <el-radio-group v-model="fillMode" class="fill-mode-group">
        <el-radio value="book">仅账面+未审（保留 AJE/RJE，推荐）</el-radio>
        <el-radio value="full">完整覆盖（含明细 AJE/RJE）</el-radio>
      </el-radio-group>
      <p v-if="fillPreview.unmatchedCount" class="fill-warn">
        注意：H3-2 有 {{ fillPreview.unmatchedCount }} 行非标准类别，金额 {{ fmtNum(fillPreview.unmatchedEnd) }} 将归入归一后类别。
      </p>
      <el-table :data="fillPreview.diffs" border size="small" max-height="360" empty-text="无差异（已与 H3-2 一致）">
        <el-table-column prop="category" label="类别" width="110" />
        <el-table-column prop="block" label="区块" width="70" />
        <el-table-column prop="field" label="字段" width="90" />
        <el-table-column prop="before" label="回填前" align="right" min-width="100">
          <template #default="{ row }">{{ fmtNum(row.before) }}</template>
        </el-table-column>
        <el-table-column prop="after" label="回填后" align="right" min-width="100">
          <template #default="{ row }">{{ fmtNum(row.after) }}</template>
        </el-table-column>
        <el-table-column prop="delta" label="差异" align="right" min-width="100">
          <template #default="{ row }">
            <span :class="{ 'text-danger': Math.abs(row.delta) >= 0.01 }">{{ fmtNum(row.delta) }}</span>
          </template>
        </el-table-column>
      </el-table>
      <template #footer>
        <el-button @click="fillDialogVisible = false">取消</el-button>
        <el-button type="primary" :disabled="fillPreview.empty" @click="confirmFillFromH32">确认回填</el-button>
      </template>
    </el-dialog>

    <!-- H3-8 反向勾稽 -->
    <el-card shadow="never" class="reconcile-card">
      <template #header>
        <div class="section-title">
          <span>与 H3-8 公允价值复核勾稽</span>
          <el-button size="small" link @click="emit('navigate-sheet', 'H3-8 公允价值复核')">打开 H3-8 →</el-button>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="H3-1 审定数合计">{{ fmtNum(h38Reconcile.h31Audited) }}</el-descriptions-item>
        <el-descriptions-item label="H3-8 期末余额合计">
          <span :class="{ 'text-danger': h38Reconcile.hasH38Data && !h38Reconcile.matched }">
            {{ h38Reconcile.hasH38Data ? fmtNum(h38Reconcile.h38Ending) : '-' }}
          </span>
        </el-descriptions-item>
        <el-descriptions-item label="勾稽差异">
          <el-tag
            :type="h38Reconcile.matched ? 'success' : (h38Reconcile.hasH38Data ? 'danger' : 'info')"
            size="small"
          >
            {{ h38Reconcile.hasH38Data ? fmtNum(h38Reconcile.diffAudited) : '待编制' }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="H3-8 复核公允合计" :span="3">
          {{ h38Reconcile.h38AuditorFv ? fmtNum(h38Reconcile.h38AuditorFv) : '-' }}
        </el-descriptions-item>
      </el-descriptions>
      <p class="reconcile-note">{{ h38Reconcile.note }}</p>
    </el-card>

    <!-- 单区块：投资性房地产（公允价值） -->
    <el-card shadow="never" class="section-card">
      <template #header>
        <div class="section-title">
          <span>投资性房地产 — 公允价值模式</span>
        </div>
      </template>
      <el-table :data="fairRows" border size="small" class="audit-table" show-summary :summary-method="getFairSummary">
        <el-table-column prop="category" label="项目" min-width="120" fixed />
        <el-table-column prop="beginFair" label="期初公允" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.beginFair" size="small" :disabled="isReadonly" @change="onCellChange(row, 'beginFair')" />
          </template>
        </el-table-column>
        <el-table-column prop="increase" label="本期增加" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.increase" size="small" :disabled="isReadonly" @change="onCellChange(row, 'increase')" />
          </template>
        </el-table-column>
        <el-table-column prop="decrease" label="本期减少" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.decrease" size="small" :disabled="isReadonly" @change="onCellChange(row, 'decrease')" />
          </template>
        </el-table-column>
        <el-table-column prop="transfer" label="转换" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.transfer" size="small" :disabled="isReadonly" @change="onCellChange(row, 'transfer')" />
          </template>
        </el-table-column>
        <el-table-column prop="fairValueChange" label="公允价值变动" min-width="120" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.fairValueChange" size="small" :disabled="isReadonly" @change="onCellChange(row, 'fairValueChange')" />
          </template>
        </el-table-column>
        <el-table-column label="期末公允" min-width="110" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="期初+增加-减少±转换+公允变动">{{ fmtNum(row.endFair) }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="unadjusted" label="未审数" min-width="100" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.unadjusted" size="small" :disabled="isReadonly" @change="onCellChange(row, 'unadjusted')" />
          </template>
        </el-table-column>
        <el-table-column prop="aje" label="AJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.aje" size="small" :disabled="isReadonly" @change="onCellChange(row, 'aje')" />
          </template>
        </el-table-column>
        <el-table-column prop="rje" label="RJE" min-width="90" align="right">
          <template #default="{ row }">
            <el-input v-model.number="row.rje" size="small" :disabled="isReadonly" @change="onCellChange(row, 'rje')" />
          </template>
        </el-table-column>
        <el-table-column label="审定数" min-width="100" align="right" class-name="formula-col">
          <template #default="{ row }">
            <span class="formula-value" title="未审+AJE+RJE">{{ fmtNum(row.audited) }}</span>
          </template>
        </el-table-column>
      </el-table>
    </el-card>

    <!-- 公允价值变动损益汇总 -->
    <el-card shadow="never" class="summary-card">
      <div class="summary-row">
        <span>公允价值变动损益合计</span>
        <span class="summary-amount">{{ fmtNum(totalFairValueChange) }}</span>
      </div>
    </el-card>

    <!-- 跨表勾稽：H3-2 明细 / H3-6 互转 / H3-8 公允变动 -->
    <el-card shadow="never" class="reconcile-card">
      <template #header>
        <div class="section-title">
          <span>跨表勾稽（H3-2 / H3-6 / H3-8）</span>
          <div class="chip-row-inline">
            <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-2')">打开 H3-2</el-tag>
            <el-tag size="small" class="nav-chip" @click="emit('navigate-sheet', 'H3-6 互转审核')">打开 H3-6</el-tag>
          </div>
        </div>
      </template>
      <el-descriptions :column="3" border size="small">
        <el-descriptions-item label="H3-1 审定数">{{ fmtNum(fairTotal.audited) }}</el-descriptions-item>
        <el-descriptions-item label="H3-2 期末公允">
          <span :class="{ 'text-danger': hasDetailFairDiff }">{{ fmtNum(detailFairAudited) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="明细差异">
          <el-tag :type="hasDetailFairDiff ? 'danger' : 'success'" size="small">{{ fmtNum(detailFairDiff) }}</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="H3-1 公允变动">{{ fmtNum(totalFairValueChange) }}</el-descriptions-item>
        <el-descriptions-item label="H3-8 公允变动">
          <span :class="{ 'text-danger': hasFvChangeDiff }">{{ fmtNum(h38FairChange) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="变动差异">
          <el-tag :type="hasFvChangeDiff ? 'danger' : 'success'" size="small">{{ fmtNum(fvChangeDiff) }}</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="H3-1 转换列">{{ fmtNum(fairTotal.transfer) }}</el-descriptions-item>
        <el-descriptions-item label="H3-6 净转入">
          <span :class="{ 'text-danger': hasTransferDiff }">{{ fmtNum(transferNet) }}</span>
        </el-descriptions-item>
        <el-descriptions-item label="转换差异">
          <el-tag :type="hasTransferDiff ? 'danger' : 'success'" size="small">{{ fmtNum(transferDiff) }}</el-tag>
        </el-descriptions-item>

        <el-descriptions-item label="H3-3 AJE(1503)">{{ fmtNum(adjustmentSync.aje1503) }}</el-descriptions-item>
        <el-descriptions-item label="H3-3 RJE(1503)">{{ fmtNum(adjustmentSync.rje1503) }}</el-descriptions-item>
        <el-descriptions-item label="H3-3 AJE/RJE合计">{{ fmtNum(adjustmentSync.totalAje) }} / {{ fmtNum(adjustmentSync.totalRje) }}</el-descriptions-item>
      </el-descriptions>
      <p class="reconcile-note">{{ crossSheetNote }}</p>
      <div v-if="hasDetailFairDiff" class="align-row">
        <el-button size="small" type="warning" :disabled="isReadonly" @click="alignFromH32">差异一键对齐（账面模式）</el-button>
      </div>
    </el-card>

    <!-- 审计说明 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header">
          <span>审计说明</span>
          <span class="action-btns">
            <el-button size="small" @click="generateAI('H3-1-fair')">AI</el-button>
            <el-button size="small" circle @click="openReview('H3-1-fair')">💬</el-button>
          </span>
        </div>
      </template>
      <el-input :model-value="auditNote" type="textarea" :autosize="{ minRows: 5 }" placeholder="填写审计说明：程序执行情况、公允价值来源与合理性、公允价值变动损益核对、拟调整与未调整事项及其影响。" :disabled="isReadonly" @change="saveAuditNote" />
    </el-card>

    <!-- 审计结论 -->
    <el-card shadow="never" class="audit-note-card">
      <template #header>
        <div class="card-header"><span>审计结论</span></div>
      </template>
      <el-input :model-value="auditConclusion" type="textarea" :autosize="{ minRows: 3 }" placeholder="填写审计结论：A、未见异常。B、除上述调整事项外未见异常。C、存在重大未调整事项（或审计范围受限），不可确认。" :disabled="isReadonly" @change="saveAuditConclusion" />
    </el-card>

    <AdjudicationBringInDialog
      v-model="bringInVisible"
      :matches="adjPull.matches.value"
      :row-options="bringInRowOptions"
      subject-label="1503 投资性房地产（公允价值模式）"
      :loading="adjPull.loading.value"
      @apply="onBringInApply"
    />
  </div>
</template>

<script setup lang="ts">
/**
 * H3TabAdjudicationFair.vue — H3-1 审定表（公允价值模式）
 * 单区块公允+公允变动+TB回写+AI+💬复核
 */
import { ref, computed, inject, toRef, onMounted, watch } from 'vue'
import { Download } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import { useH3AdjudicationFair } from '../../composables/useH3AdjudicationFair'
import type { H3FillDiffRow, H3FillMode } from '../../composables/h3FillFromDetail'
import { useH3FormData } from '../../composables/useH3FormData'
import { useH3CrossSheet } from '../../composables/useH3CrossSheet'
import { useAuditContext } from '@/composables/useAuditContext'
import { useAdjudicationBringIn } from '../../composables/useAdjudicationBringIn'
import AdjudicationBringInDialog from '@/components/adjustment/AdjudicationBringInDialog.vue'
import GtIndexChip from '../../GtIndexChip.vue'
import { generateH3AI, h3AiLoading } from '../useH3AiGenerate'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'navigate-sheet', sheetName: string): void
}>()

const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const { getValue, setValue, saveImmediate } = useH3FormData({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  measurementModel: ref('fair_value'),
})

const {
  rows: fairRows,
  total: fairTotal,
  fairValueChangePL: totalFairValueChange,
  h38Reconcile,
  h32CategoryMatch,
  updateCell: updateFairCell,
  previewFillFromH32,
  fillFromH32Detail,
  fillTransferFromH36,
} = useH3AdjudicationFair({
  allResponses: computed(() => props.allResponses) as any,
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  getValue, setValue, saveImmediate,
})

// ─── 从集中登记带入调整（1503 投资性房地产，公允价值模式，资产借方；带入AJE/RJE） ───
const bringInRows = computed(() =>
  fairRows.value.map((r) => ({ rowKey: r.rowId, name: r.category, aje: r.aje, rje: r.rje })),
)
const {
  adjPull,
  visible: bringInVisible,
  rowOptions: bringInRowOptions,
  open: openBringInAdjustment,
  apply: onBringInApply,
} = useAdjudicationBringIn({
  projectId: toRef(props, 'projectId') as any,
  year: useAuditContext().year as any,
  subjectPrefix: '1503',
  direction: 'debit',
  subjectCode: '1503',
  wpCode: 'H3',
  subjectLabel: '投资性房地产(1503·公允)',
  rows: bringInRows,
  updateCell: (rowKey: string, field: any, value: number) => updateFairCell(rowKey, field, value),
  totalAudited: () => fairTotal.value.audited,
})

const fillDialogVisible = ref(false)
const fillMode = ref<H3FillMode>('book')
const fillPreview = ref<{ diffs: H3FillDiffRow[]; unmatchedCount: number; unmatchedEnd: number; empty: boolean }>({
  diffs: [], unmatchedCount: 0, unmatchedEnd: 0, empty: true,
})

function refreshFillPreview() {
  fillPreview.value = previewFillFromH32(fillMode.value)
}
function openFillDialog() {
  refreshFillPreview()
  if (fillPreview.value.empty) {
    ElMessage.warning('H3-2 公允明细尚无数据，请先编制 H3-2')
    return
  }
  fillDialogVisible.value = true
}
watch(fillMode, () => { if (fillDialogVisible.value) refreshFillPreview() })

function confirmFillFromH32() {
  const r = fillFromH32Detail(fillMode.value)
  fillDialogVisible.value = false
  ElMessage.success(
    `已按类别回填 ${r.filled} 行（${fillMode.value === 'book' ? '保留AJE/RJE' : '完整覆盖'}）`,
  )
}
function alignFromH32() {
  const r = fillFromH32Detail('book')
  if (!r.filled) {
    ElMessage.warning('H3-2 公允明细尚无数据')
    return
  }
  ElMessage.success('已按账面模式对齐 H3-2（保留 AJE/RJE）')
}
function onFillTransferFromH36() {
  const r = fillTransferFromH36(transferNet.value)
  ElMessage.success(`已按权重分摊 H3-6 净转入至转换列（${r.filled} 行）`)
}

const measurementModel = ref('fair_value')
const { adjudicationFromDetail, transferSummary, detailTotals, fairValueChangeTotal, adjustmentSync } = useH3CrossSheet(
  computed(() => props.allResponses) as any,
  measurementModel,
)

const detailFairAudited = computed(() => {
  const v = adjudicationFromDetail.value
  return 'fairAudited' in v ? v.fairAudited : detailTotals.value.assetEnd
})
const detailFairDiff = computed(() => fairTotal.value.audited - detailFairAudited.value)
const hasDetailFairDiff = computed(() => Math.abs(detailFairDiff.value) >= 0.01)

const h38FairChange = computed(() => fairValueChangeTotal.value)
const fvChangeDiff = computed(() => totalFairValueChange.value - h38FairChange.value)
const hasFvChangeDiff = computed(() => Math.abs(fvChangeDiff.value) >= 0.01)

const transferNet = computed(
  () => transferSummary.value.fromH1 + transferSummary.value.fromH2 - transferSummary.value.toH1,
)
const transferDiff = computed(() => fairTotal.value.transfer - transferNet.value)
const hasTransferDiff = computed(() => Math.abs(transferDiff.value) >= 0.01)

const crossSheetNote = computed(() => {
  if (!hasDetailFairDiff.value && !hasFvChangeDiff.value && !hasTransferDiff.value) {
    return 'H3-1 与 H3-2 明细、H3-6 互转、H3-8 公允变动勾稽一致。'
  }
  const parts: string[] = []
  if (hasDetailFairDiff.value) parts.push(`明细差 ${detailFairDiff.value.toLocaleString('zh-CN')}`)
  if (hasFvChangeDiff.value) parts.push(`公允变动差 ${fvChangeDiff.value.toLocaleString('zh-CN')}`)
  if (hasTransferDiff.value) parts.push(`转换差 ${transferDiff.value.toLocaleString('zh-CN')}`)
  return `存在勾稽差异：${parts.join('；')}。请核对明细、互转或公允复核表。`
})

// ─── 审计说明 / 审计结论（标准 checklist_responses 持久化） ───────────────────
const NOTE_KEY = 'H3-1-fair-audit-note'
const CONCLUSION_KEY = 'H3-1-fair-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')
onMounted(() => {
  const n = props.allResponses.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = props.allResponses.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
function saveAuditNote(val: string) {
  if (props.isReadonly) return
  auditNote.value = val
  props.allResponses.set(NOTE_KEY, { item_id: NOTE_KEY, conclusion: null, remark: val })
  void saveImmediate(NOTE_KEY, val)
}
function saveAuditConclusion(val: string) {
  if (props.isReadonly) return
  auditConclusion.value = val
  props.allResponses.set(CONCLUSION_KEY, { item_id: CONCLUSION_KEY, conclusion: null, remark: val })
  void saveImmediate(CONCLUSION_KEY, val)
}

function onCellChange(row: any, field: string) {
  updateFairCell(row.rowId, field, row[field])
}

function fmtNum(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getFairSummary({ columns }: { columns: any[] }) {
  return columns.map((_, idx) => {
    if (idx === 0) return '小计'
    const key = ['', 'beginFair', 'increase', 'decrease', 'transfer', 'fairValueChange', 'endFair', 'unadjusted', 'aje', 'rje', 'audited'][idx]
    return key ? fmtNum((fairTotal.value as any)[key] ?? 0) : ''
  })
}

const _h3AiLoading = h3AiLoading
async function generateAI(section: string) {
  await generateH3AI(props.wpId, section)
}
function openReview(section: string) { openReviewDialog(section) }
</script>

<style scoped>
.h3-tab-adjudication-fair { padding: 16px; font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; }
.guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-content p { margin: 2px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar { display: flex; justify-content: flex-start; align-items: center; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.tab-toolbar .chip-wrap { margin-left: auto; }
.chip-wrap { display: inline-flex; align-items: center; }
.audit-note-card { margin-top: 16px; }
.audit-note-card .card-header { display: flex; justify-content: space-between; align-items: center; font-weight: 500; }
.section-card { margin-bottom: 16px; }
.section-title { display: flex; align-items: center; justify-content: space-between; }
.audit-table { font-size: var(--wp-font-size, 13px); }
.audit-table :deep(.formula-col) { background: var(--el-fill-color-lighter); }
.formula-value { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.summary-card { margin-bottom: 16px; }
.summary-row { display: flex; align-items: center; justify-content: space-between; padding: 8px 0; font-weight: 600; }
.summary-amount { font-size: 16px; color: var(--el-color-warning); }
.conclusion-card { margin-bottom: 16px; }
.action-btns { display: flex; gap: 4px; }
.reconcile-card { margin-bottom: 16px; }
.reconcile-note { margin: 8px 0 0; font-size: 12px; color: #909399; line-height: 1.5; }
.align-row { margin-top: 8px; }
.fill-mode-group { display: flex; flex-direction: column; gap: 8px; margin-bottom: 12px; }
.fill-warn { color: var(--el-color-warning); font-size: 12px; margin: 0 0 8px; }
.text-danger { color: var(--el-color-danger); font-weight: 500; }
.chip-row-inline { display: flex; gap: 8px; }
.nav-chip { cursor: pointer; }
</style>
