<template>
  <div class="i6-cutoff-forward">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <div class="section-header">
      <span class="section-title">I6-5 截止性测试（账簿→单据）</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="一、审计目标：确认研发费用（6602）已记录于正确的会计期间（从记账凭证追查至支出凭单，关注多记/提前入账）。"
    />

    <el-card shadow="never" class="sample-card">
      <template #header><span>二、样本选取标准与规模</span></template>
      <div class="sample-form">
        <div class="sample-row">
          <span>抽取资产负债表日</span>
          <el-date-picker
            :model-value="criteria.cutoffDate"
            type="date"
            size="small"
            value-format="YYYY-MM-DD"
            placeholder="截止日"
            style="width:150px"
            :disabled="isReadonly"
            @update:model-value="(v: string) => updateForwardCriteria({ cutoffDate: v || '' })"
          />
          <span>前</span>
          <el-input-number
            :model-value="criteria.daysBefore"
            size="small"
            :min="1"
            :max="90"
            :controls="false"
            style="width:64px"
            :disabled="isReadonly"
            @change="(v: number | undefined) => updateForwardCriteria({ daysBefore: Number(v) || 5 })"
          />
          <span>天、后</span>
          <el-input-number
            :model-value="criteria.daysAfter"
            size="small"
            :min="1"
            :max="90"
            :controls="false"
            style="width:64px"
            :disabled="isReadonly"
            @change="(v: number | undefined) => updateForwardCriteria({ daysAfter: Number(v) || 5 })"
          />
          <span>天内、金额大于</span>
          <el-input-number
            :model-value="criteria.amountThreshold"
            size="small"
            :min="0"
            :precision="2"
            :controls="false"
            style="width:120px"
            :disabled="isReadonly"
            @change="(v: number | undefined) => updateForwardCriteria({ amountThreshold: Number(v) || 0 })"
          />
          <span>元的研发费用记账凭证，与支出凭单核对。</span>
          <el-button v-if="suggestedThreshold" size="small" type="primary" link :disabled="isReadonly" @click="applyMaterialityThreshold">
            采用建议门槛 {{ fmtAmount(suggestedThreshold) }}（约 PM×5%）
          </el-button>
        </div>
        <div v-if="criteria.firstYearClient && priorPeriodCutoffDate" class="sample-row first-year">
          <el-alert type="error" :closable="false" show-icon
            :title="`首年承接：请对上期期末（${priorPeriodCutoffDate}）执行截止测试，可在 I6-6 扩大窗口或复制本期标准后测试。`" />
        </div>
        <div class="sample-row first-year">
          <el-checkbox
            :model-value="criteria.firstYearClient"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateForwardCriteria({ firstYearClient: Boolean(v) })"
          >
            对首次接受委托的客户，对上期期末执行截止性测试（适用于首次接受委托）
          </el-checkbox>
        </div>
        <el-alert
          type="warning"
          :closable="false"
          show-icon
          title="提示：如果存在跨期舞弊风险，或者所检查样本中发现有跨期的，应扩大测试期间和样本量，甚至可以考虑将截止测试期间扩大至审计报告日，同时考虑是否存在内部控制缺陷。"
        />
      </div>
    </el-card>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <span class="flow-hint">编制流程：①设截止日 → ②抽期末记账凭证 → ③追查支出凭单 → ④判断跨期 → ⑤填说明结论</span>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:I6-5" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ forwardRows.length }} 行</el-tag>
        <GtIndexChip value="I2-13" @click="emit('navigate-sheet', 'I2-13')" />
      </div>
    </div>

    <I6CutoffCrossCheck :summary="crossCheckSummary" />

    <div class="stats-card">
      <div class="stat-item">
        <span class="stat-label">样本总数</span>
        <span class="stat-value">{{ forwardRows.length }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">跨期笔数</span>
        <span class="stat-value" :class="{ 'stat-danger': forwardCrossPeriodCount > 0 }">{{ forwardCrossPeriodCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">跨期金额</span>
        <span class="stat-value" :class="{ 'stat-danger': forwardCrossPeriodAmount > 0 }">{{ fmtAmount(forwardCrossPeriodAmount) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">跨期比例</span>
        <span class="stat-value" :class="{ 'stat-danger': forwardCrossPeriodCount > 0 }">
          {{ forwardRows.length > 0 ? ((forwardCrossPeriodCount / forwardRows.length) * 100).toFixed(1) + '%' : '—' }}
        </span>
      </div>
      <div class="stat-item">
        <span class="stat-label">金额不一致</span>
        <span class="stat-value" :class="{ 'stat-warn': amountMismatchCount > 0 }">{{ amountMismatchCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">滞后异常</span>
        <span class="stat-value" :class="{ 'stat-warn': lagAnomalyCount > 0 }">{{ lagAnomalyCount }}</span>
      </div>
    </div>

    <el-alert
      v-if="capitalizationHints.length > 0"
      type="warning"
      :closable="false"
      show-icon
      class="cap-alert"
      :title="`有 ${capitalizationHints.length} 笔摘要涉及资本化/开发支出，建议同步查阅 I2-13/I2-14 截止底稿。`"
    />

    <div class="test-block">
      <div class="block-header">
        <span class="block-title">三、测试 — 截止日期前样本</span>
        <span class="block-hint">记账日期 ≤ 截止日，追查支出凭单是否属于本期</span>
      </div>
      <I2CutoffSampleTable
        direction="forward"
        :rows="forwardBeforeRows"
        :is-readonly="isReadonly"
        show-extended
        @update="onUpdate"
        @remove="onRemove"
      />
    </div>

    <div class="cutoff-divider">—— 截止日期：{{ criteria.cutoffDate || '20XX年12月31日' }} ——</div>

    <div class="test-block">
      <div class="block-header">
        <span class="block-title">截止日期后样本</span>
        <span class="block-hint">记账日期 &gt; 截止日，核查是否漏记本期应确认的费用</span>
      </div>
      <I2CutoffSampleTable
        direction="forward"
        :rows="forwardAfterRows"
        :is-readonly="isReadonly"
        show-extended
        @update="onUpdate"
        @remove="onRemove"
      />
    </div>

    <div v-if="forwardUnsortedRows.length > 0" class="test-block">
      <div class="block-header">
        <span class="block-title">待归类样本</span>
        <span class="block-hint">请填写记账日期与截止日后自动归入截止日前/后</span>
      </div>
      <I2CutoffSampleTable
        direction="forward"
        :rows="forwardUnsortedRows"
        :is-readonly="isReadonly"
        show-extended
        @update="onUpdate"
        @remove="onRemove"
      />
    </div>

    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addForwardRow()">+ 新增行</el-button>
      <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handleAutoSampling">序时账自动提取</el-button>
      <el-button size="small" type="success" plain :disabled="isReadonly" @click="showCutoffPanel = !showCutoffPanel">截止模块取数</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="showSamplingDialog = true">抽凭引擎</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="syncCriteriaToPeer('forward')">同步标准→I6-6</el-button>
      <el-button size="small" plain :disabled="isReadonly || isExporting" @click="exportData('I6-5')">导出</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="triggerImport">导入</el-button>
      <el-button size="small" :disabled="isReadonly" @click="syncCutoffDateFromProject()">同步截止日</el-button>
      <el-button size="small" type="danger" plain :disabled="isReadonly || forwardCrossPeriodCount === 0" @click="expandTestWindow('forward', 30)">扩大窗口至±30天</el-button>
      <el-button size="small" type="danger" plain :disabled="isReadonly || forwardCrossPeriodCount === 0" @click="handleDraftAje">跨期→I6-3草稿</el-button>
      <el-button size="small" @click="emit('navigate-sheet', 'I6-6')">对照 I6-6 →</el-button>
      <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
    </div>

    <GtCutoffAutoSampling
      v-if="showCutoffPanel"
      account-code="6602"
      cutoff-direction="post_cutoff"
      :default-conditions="cutoffPanelDefaults"
      :workpaper-id="wpId"
      :project-id="projectId"
      :year="currentYear"
      :readonly="isReadonly"
      @filled="handleCutoffFilled"
      @applied="saveAuditNote"
    />

    <el-dialog v-model="showSamplingDialog" title="抽凭引擎（6602 研发费用 · I6-5）" width="720px" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog"
        :project-id="projectId"
        :workpaper-id="wpId"
        account-code="6602"
        phase="final"
        :year="currentYear"
        @filled="handleVoucherFilled"
      />
    </el-dialog>

    <input ref="importInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onImportFile" />

    <el-alert
      v-if="forwardCrossPeriodCount > 0"
      type="error"
      :closable="false"
      show-icon
      class="expand-alert"
      title="已发现跨期样本：请扩大测试期间与样本量（可扩至审计报告日），并与 I6-6（单据→账）交叉评价；必要时生成 I6-3 调整草稿。"
    />

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>四、审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }" placeholder="记录样本选取依据、检查范围、发现的跨期事项及处理..." @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>五、审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="基于测试结果，判断研发费用截止认定是否恰当..." @change="saveAuditConclusion" />
    </el-card>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为「账簿→单据」方向：从期末前后6602记账凭证出发，追查支出凭单（领料单、工时单、委外结算单等）真实性与期间归属。</p>
        <p>2. 跨期判定：支出凭单日期与记账日期分处截止日两侧即为跨期；跨期金额取记账/单据金额。</p>
        <p>3. 本期入账但单据属下期 → 跨期多记；下期入账但单据属本期 → 本期少计。</p>
        <p>4. 发现跨期时应与 I6-6（单据→账）综合评价，并考虑扩大样本；依据企业会计准则及相关研发支出指引。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { inject, toRef, ref, watch, computed, defineAsyncComponent, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import I2CutoffSampleTable from '../../i2/cutoff/I2CutoffSampleTable.vue'
import I6CutoffCrossCheck from './I6CutoffCrossCheck.vue'
import { useI6Cutoff } from '../../composables/useI6Cutoff'
import type { CutoffRow } from '../../composables/useCycleCutoff'
import type { ExtractedVoucher, FillMode } from '../../composables/useCutoffAutoSampling'
import { useCutoffMaterialityHint } from '../../composables/useCutoffMaterialityHint'
import { useI6ImportExport } from '../../composables/useI6ImportExport'
import { suggestsCapitalization } from '../../composables/cutoffRowHelpers'
import WpSamplingMethodologyBar from '../../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist, buildChecklistDirectPersist } from '../../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../../composables/shared/samplingFillTarget'

const GtCutoffAutoSampling = defineAsyncComponent(() => import('../../cutoff/GtCutoffAutoSampling.vue'))
const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  wpId: string
  projectId: string
  year?: number
  allResponses: Map<string, any>
  saveResponse: (sheetCode: string, data: Record<string, any>) => Promise<void>
  isReadonly?: boolean
}>()

const emit = defineEmits<{ save: []; 'navigate-sheet': [sheetName: string] }>()
const openReviewDialog = inject<(section: string) => void>('openReviewDialog', () => {})

const {
  forwardRows,
  forwardCriteria,
  forwardBeforeRows,
  forwardAfterRows,
  forwardUnsortedRows,
  forwardCrossPeriodCount,
  forwardCrossPeriodAmount,
  amountMismatchCount,
  lagAnomalyCount,
  crossCheckSummary,
  priorPeriodCutoffDate,
  updateForwardCriteria,
  addForwardRow,
  removeForwardRow,
  updateForwardRow,
  loadFromAutoSampling,
  importExtractedVouchers,
  save: saveCutoff,
  syncCutoffDateFromProject,
  expandTestWindow,
  draftAjeFromCrossPeriod,
  persistCompletion,
  syncCriteriaToPeer,
  flushAutoSave,
} = useI6Cutoff({
  allResponses: toRef(props, 'allResponses'),
  saveResponses: props.saveResponse,
  projectId: toRef(props, 'projectId'),
  year: toRef(props, 'year'),
})

const criteria = computed(() => forwardCriteria.value)
const showCutoffPanel = ref(false)
const showSamplingDialog = ref(false)
const importInputRef = ref<HTMLInputElement | null>(null)
const currentYear = computed(() => props.year ?? new Date().getFullYear())
const { suggestedThreshold, fetchHint } = useCutoffMaterialityHint(toRef(props, 'projectId'))
const { exportData, importData, isExporting } = useI6ImportExport({
  wpId: toRef(props, 'wpId'),
  onImported: () => emit('save'),
})
const capitalizationHints = computed(() =>
  forwardRows.value.filter((r) => suggestsCapitalization(r.description)),
)
const cutoffPanelDefaults = computed(() => ({
  cutoffDate: criteria.value.cutoffDate,
  daysBefore: criteria.value.daysBefore,
  daysAfter: criteria.value.daysAfter,
  amountThreshold: criteria.value.amountThreshold,
}))

const AUDIT_NOTE_KEY = 'I6-5-audit-note'
const AUDIT_CONCLUSION_KEY = 'I6-5-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function readRemark(key: string): string {
  const raw = props.allResponses.get(key)
  if (raw == null) return ''
  return typeof raw === 'string' ? raw : (raw.remark ?? '')
}
function hydrateAudit() {
  auditNote.value = readRemark(AUDIT_NOTE_KEY)
  auditConclusion.value = readRemark(AUDIT_CONCLUSION_KEY)
}
function saveAuditNote(val: string) {
  auditNote.value = val
  void props.saveResponse('I6-5', { [AUDIT_NOTE_KEY]: val })
}
function saveAuditConclusion(val: string) {
  auditConclusion.value = val
  void props.saveResponse('I6-5', { [AUDIT_CONCLUSION_KEY]: val })
}
watch(() => props.allResponses, () => hydrateAudit(), { immediate: true })
onMounted(() => {
  hydrateAudit()
  void fetchHint()
})
onBeforeUnmount(() => { void flushAutoSave() })

function applyMaterialityThreshold() {
  if (suggestedThreshold.value == null) return
  updateForwardCriteria({ amountThreshold: suggestedThreshold.value })
  ElMessage.success(`已采用建议金额门槛 ${suggestedThreshold.value}`)
}

function triggerImport() {
  importInputRef.value?.click()
}
async function onImportFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  await importData(file, 'I6-5')
  ;(e.target as HTMLInputElement).value = ''
}

function rowIndex(row: CutoffRow): number {
  return forwardRows.value.indexOf(row)
}
function onUpdate(row: CutoffRow, field: string, value: any) {
  const idx = rowIndex(row)
  if (idx < 0) return
  updateForwardRow(idx, field, value)
}
function onRemove(row: CutoffRow) {
  const idx = rowIndex(row)
  if (idx < 0) return
  removeForwardRow(idx)
}
async function handleAutoSampling() {
  await loadFromAutoSampling('forward')
}
const rawMethodologyPersist = buildChecklistDirectPersist({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
})
const methodologyDirectPersist = rawMethodologyPersist
/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'I6',
  allResponses: toRef(props, 'allResponses') as never,
  persist: methodologyDirectPersist,
  isReadonly: computed(() => props.isReadonly === true),
})

function handleCutoffFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }) {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  const items = payload.samples.map((v) => ({
    voucher_date: v.voucherDate,
    voucher_no: v.voucherNo,
    summary: v.summary,
    amount: v.debitAmount ? parseFloat(v.debitAmount) : (v.creditAmount ? parseFloat(v.creditAmount) : 0),
  }))
  importExtractedVouchers('forward', items, { fillDocumentDate: false })
  showCutoffPanel.value = false
  ElMessage.success(`截止模块已填入 ${items.length} 笔样本（单据日期请查原件后补填）`)
}
function handleVoucherFilled(payload: any) {
  const vouchers = payload?.samples ?? []
  importExtractedVouchers('forward', vouchers.map((v: any) => ({
    voucher_date: v.voucherDate ?? v.voucher_date,
    voucher_no: v.voucherNo ?? v.voucher_no,
    summary: v.summary,
    amount: Number(v.debitAmount ?? v.debit_amount ?? 0),
  })), { fillDocumentDate: false })
  showSamplingDialog.value = false
  if (vouchers.length) ElMessage.success(`抽凭已填入 ${vouchers.length} 笔`)
}
async function handleDraftAje() {
  await draftAjeFromCrossPeriod('forward')
  emit('navigate-sheet', 'I6-3')
}
async function handleSave() {
  await saveCutoff('forward')
  await persistCompletion('forward')
  emit('save')
  ElMessage.success('账簿→单据截止性测试已保存')
}
function handleReview() {
  openReviewDialog('I6-5-截止性测试-账到单据')
}
function fmtAmount(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i6-cutoff-forward { font-size: var(--wp-font-size, 13px); padding: 16px; }
.section-header { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.section-title { font-size: 15px; font-weight: 600; color: #1f2937; }
.section-actions { display: flex; align-items: center; gap: 4px; }
.objective-alert { margin-bottom: 12px; }
.sample-card { margin-bottom: 14px; }
.sample-card :deep(.el-card__header) { padding: 10px 16px; background: #fafafa; font-weight: 600; }
.sample-form { display: flex; flex-direction: column; gap: 10px; }
.sample-row { display: flex; flex-wrap: wrap; align-items: center; gap: 6px; line-height: 1.8; color: #374151; }
.sample-row.first-year { color: #b91c1c; }
.tab-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 10px; gap: 8px; flex-wrap: wrap; }
.toolbar-left { flex: 1; min-width: 0; }
.toolbar-right { display: flex; align-items: center; gap: 8px; }
.flow-hint { font-size: 12px; color: #059669; }
.stats-card { display: flex; gap: 24px; padding: 12px 16px; background: #f9fafb; border: 1px solid #e5e7eb; border-radius: 8px; margin-bottom: 14px; flex-wrap: wrap; }
.stat-item { display: flex; flex-direction: column; align-items: center; min-width: 72px; }
.stat-label { font-size: 12px; color: #6b7280; }
.stat-value { font-size: 18px; font-weight: 700; color: #1f2937; }
.stat-danger { color: #dc2626; }
.stat-warn { color: #d97706; }
.cap-alert { margin-bottom: 12px; }
.test-block { margin-bottom: 8px; }
.block-header { display: flex; align-items: baseline; gap: 10px; margin-bottom: 8px; flex-wrap: wrap; }
.block-title { font-size: 14px; font-weight: 600; color: #1f2937; }
.block-hint { font-size: 12px; color: #6b7280; }
.cutoff-divider {
  margin: 14px 0;
  text-align: center;
  font-weight: 600;
  color: #1d4ed8;
  border-top: 2px solid #93c5fd;
  border-bottom: 2px solid #93c5fd;
  padding: 8px 0;
  background: #eff6ff;
}
.table-actions { display: flex; gap: 8px; margin-top: 10px; flex-wrap: wrap; }
.expand-alert { margin-top: 12px; }
.audit-note-card, .audit-conclusion-card { margin-top: 16px; }
.guidance-details { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); background: #f9fafb; border: 1px solid #ebeef5; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 600; color: #374151; }
.guidance-details .guidance-content { margin-top: 8px; line-height: 1.7; }
.guidance-details .guidance-content p { margin: 0 0 4px; }
</style>
