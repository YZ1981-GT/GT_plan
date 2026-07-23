<template>
  <div class="i2-cutoff-backward">
    <div class="section-header">
      <span class="section-title">I2-14 截止性测试（单据→账簿）</span>
      <div class="section-actions">
        <el-button size="small" type="default" text @click="handleReview">复核</el-button>
      </div>
    </div>

    <el-alert
      type="info"
      :closable="false"
      class="objective-alert"
      title="一、审计目标：确认开发支出已记录于正确的会计期间（从支出凭单追查至记账凭证，关注漏记/跨期）。"
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
            @update:model-value="(v: string) => updateBackwardCriteria({ cutoffDate: v || '' })"
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
            @change="(v: number | undefined) => updateBackwardCriteria({ daysBefore: Number(v) || 5 })"
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
            @change="(v: number | undefined) => updateBackwardCriteria({ daysAfter: Number(v) || 5 })"
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
            @change="(v: number | undefined) => updateBackwardCriteria({ amountThreshold: Number(v) || 0 })"
          />
          <span>元的支出凭单，与开发支出记账凭证核对。</span>
          <el-button v-if="suggestedThreshold" size="small" type="primary" link :disabled="isReadonly" @click="applyMaterialityThreshold">
            采用建议门槛 {{ fmtAmount(suggestedThreshold) }}（约 PM×5%）
          </el-button>
        </div>
        <div class="sample-row first-year">
          <el-checkbox
            :model-value="criteria.firstYearClient"
            :disabled="isReadonly"
            @change="(v: boolean | string | number) => updateBackwardCriteria({ firstYearClient: Boolean(v) })"
          >
            对首次接受委托的客户，对上期期末执行截止性测试（适用于首次接受委托）
          </el-checkbox>
        </div>
        <div v-if="criteria.firstYearClient && priorPeriodCutoffDate" class="sample-row first-year">
          <el-alert type="error" :closable="false" show-icon
            :title="`首年承接：请对上期期末（${priorPeriodCutoffDate}）执行本表截止测试，建议扩大窗口至±30天。`" />
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
        <span class="flow-hint">编制流程：①设截止日 → ②抽期末支出凭单 → ③追查记账凭证 → ④判断跨期 → ⑤填说明结论</span>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:I2-14" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ backwardRows.length }} 行</el-tag>
        <GtIndexChip value="I6-6" @click="emit('navigate-sheet', 'I6-6')" />
      </div>
    </div>

    <CutoffCrossCheck
      title="双表交叉核对（I2-13 ↔ I2-14）"
      forward-label="I2-13"
      backward-label="I2-14"
      :summary="crossCheckSummary"
    />

    <div class="stats-card">
      <div class="stat-item">
        <span class="stat-label">样本总数</span>
        <span class="stat-value">{{ backwardRows.length }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">跨期笔数</span>
        <span class="stat-value" :class="{ 'stat-danger': backwardCrossPeriodCount > 0 }">{{ backwardCrossPeriodCount }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">跨期金额</span>
        <span class="stat-value" :class="{ 'stat-danger': backwardCrossPeriodAmount > 0 }">{{ fmtAmount(backwardCrossPeriodAmount) }}</span>
      </div>
      <div class="stat-item">
        <span class="stat-label">跨期比例</span>
        <span class="stat-value" :class="{ 'stat-danger': backwardCrossPeriodCount > 0 }">
          {{ backwardRows.length > 0 ? ((backwardCrossPeriodCount / backwardRows.length) * 100).toFixed(1) + '%' : '—' }}
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

    <div class="test-block">
      <div class="block-header">
        <span class="block-title">三、测试 — 截止日期前样本</span>
        <span class="block-hint">支出凭单日期 ≤ 截止日，追查是否已在本期入账</span>
      </div>
      <I2CutoffSampleTable
        direction="backward"
        :rows="backwardBeforeRows"
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
        <span class="block-hint">支出凭单日期 &gt; 截止日，核查是否被提前计入本期</span>
      </div>
      <I2CutoffSampleTable
        direction="backward"
        :rows="backwardAfterRows"
        :is-readonly="isReadonly"
        show-extended
        @update="onUpdate"
        @remove="onRemove"
      />
    </div>

    <div v-if="backwardUnsortedRows.length > 0" class="test-block">
      <div class="block-header">
        <span class="block-title">待归类样本</span>
        <span class="block-hint">请填写支出凭单日期与截止日后自动归入截止日前/后</span>
      </div>
      <I2CutoffSampleTable
        direction="backward"
        :rows="backwardUnsortedRows"
        :is-readonly="isReadonly"
        show-extended
        @update="onUpdate"
        @remove="onRemove"
      />
    </div>

    <div class="table-actions">
      <el-button size="small" type="primary" plain :disabled="isReadonly" @click="addBackwardRow()">+ 新增行</el-button>
      <el-button size="small" type="warning" plain :disabled="isReadonly" @click="handleAutoSampling">序时账自动提取</el-button>
      <el-button size="small" type="success" plain :disabled="isReadonly" @click="showCutoffPanel = !showCutoffPanel">截止模块取数</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="showSamplingDialog = true">抽凭引擎</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="syncCriteriaToPeer('backward')">同步标准→I2-13</el-button>
      <el-button size="small" plain :disabled="isReadonly || isExporting" @click="exportData('I2-14')">导出</el-button>
      <el-button size="small" plain :disabled="isReadonly" @click="triggerImport">导入</el-button>
      <el-button size="small" :disabled="isReadonly" @click="syncCutoffDateFromProject()">同步截止日</el-button>
      <el-button size="small" type="danger" plain :disabled="isReadonly || backwardCrossPeriodCount === 0" @click="expandTestWindow('backward', 30)">扩大窗口至±30天</el-button>
      <el-button size="small" type="danger" plain :disabled="isReadonly || backwardCrossPeriodCount === 0" @click="handleDraftAje">跨期→I2-3草稿</el-button>
      <el-button size="small" @click="emit('navigate-sheet', 'I2-13')">对照 I2-13 →</el-button>
      <el-button size="small" type="success" :disabled="isReadonly" @click="handleSave">保存</el-button>
    </div>

    <GtCutoffAutoSampling
      v-if="showCutoffPanel"
      account-code="1717"
      cutoff-direction="pre_cutoff"
      :default-conditions="cutoffPanelDefaults"
      :workpaper-id="wpId"
      :project-id="projectId"
      :year="currentYear"
      :readonly="isReadonly"
      @filled="handleCutoffFilled"
      @applied="saveAuditNote"
    />

    <el-dialog v-model="showSamplingDialog" title="抽凭引擎（1717 开发支出 · I2-14）" width="720px" destroy-on-close>
      <GtVoucherSamplingEngine
        v-if="showSamplingDialog"
        :project-id="projectId"
        :workpaper-id="wpId"
        account-code="1717"
        phase="final"
        :year="currentYear"
        @filled="handleVoucherFilled"
      />
    </el-dialog>

    <input ref="importInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onImportFile" />

    <el-alert
      v-if="backwardCrossPeriodCount > 0"
      type="error"
      :closable="false"
      show-icon
      class="expand-alert"
      title="已发现跨期样本：请扩大测试期间与样本量（可扩至审计报告日），并与 I2-13（账→单据）交叉评价；必要时生成 I2-3 调整草稿。"
    />

    <el-card shadow="never" class="audit-note-card">
      <template #header><span>四、审计说明</span></template>
      <el-input type="textarea" :model-value="auditNote" :disabled="isReadonly" :autosize="{ minRows: 5 }" placeholder="记录样本选取依据、检查范围、发现的跨期事项及处理..." @change="saveAuditNote" />
    </el-card>
    <el-card shadow="never" class="audit-conclusion-card">
      <template #header><span>五、审计结论</span></template>
      <el-input type="textarea" :model-value="auditConclusion" :disabled="isReadonly" :autosize="{ minRows: 3 }" placeholder="基于测试结果，判断开发支出截止认定是否恰当..." @change="saveAuditConclusion" />
    </el-card>

    <details class="guidance-details">
      <summary>编制提示</summary>
      <div class="guidance-content">
        <p>1. 本表为「单据→账簿」方向：从期末前后支出凭单出发，追查是否已记入开发支出。</p>
        <p>2. 跨期判定：支出凭单日期与记账日期分处截止日两侧即为跨期；跨期金额取支出凭单金额。</p>
        <p>3. 自动取数后须查原件补填单据日期；金额不一致行需追查原因。</p>
        <p>4. 发现跨期时应与 I2-13 交叉评价，并与 I6-6 研发费用截止底稿联动。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { inject, toRef, ref, watch, computed, defineAsyncComponent, onMounted, onBeforeUnmount } from 'vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'
import I2CutoffSampleTable from './I2CutoffSampleTable.vue'
import CutoffCrossCheck from '../../shared/CutoffCrossCheck.vue'
import { useI2Cutoff } from '../../composables/useI2Cutoff'
import type { CutoffRow } from '../../composables/useCycleCutoff'
import type { ExtractedVoucher, FillMode } from '../../composables/useCutoffAutoSampling'
import { useCutoffMaterialityHint } from '../../composables/useCutoffMaterialityHint'
import { useI2ImportExport } from '../../composables/useI2ImportExport'

const GtCutoffAutoSampling = defineAsyncComponent(() => import('../../cutoff/GtCutoffAutoSampling.vue'))
const GtVoucherSamplingEngine = defineAsyncComponent(() => import('../../voucher-sampling/GtVoucherSamplingEngine.vue'))

const props = defineProps<{
  sheetName: string
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
  backwardRows,
  backwardCriteria,
  backwardBeforeRows,
  backwardAfterRows,
  backwardUnsortedRows,
  backwardCrossPeriodCount,
  backwardCrossPeriodAmount,
  amountMismatchCount,
  lagAnomalyCount,
  crossCheckSummary,
  priorPeriodCutoffDate,
  updateBackwardCriteria,
  addBackwardRow,
  removeBackwardRow,
  updateBackwardRow,
  loadFromAutoSampling,
  importExtractedVouchers,
  save: saveCutoff,
  syncCutoffDateFromProject,
  expandTestWindow,
  draftAjeFromCrossPeriod,
  persistCompletion,
  syncCriteriaToPeer,
  flushAutoSave,
} = useI2Cutoff({
  allResponses: toRef(props, 'allResponses'),
  saveResponses: props.saveResponse,
  projectId: toRef(props, 'projectId'),
  year: toRef(props, 'year'),
})

const criteria = computed(() => backwardCriteria.value)
const showCutoffPanel = ref(false)
const showSamplingDialog = ref(false)
const importInputRef = ref<HTMLInputElement | null>(null)
const currentYear = computed(() => props.year ?? new Date().getFullYear())
const { suggestedThreshold, fetchHint } = useCutoffMaterialityHint(toRef(props, 'projectId'))
const { exportData, importData, isExporting } = useI2ImportExport({
  wpId: toRef(props, 'wpId'),
  onImported: () => emit('save'),
})
const cutoffPanelDefaults = computed(() => ({
  cutoffDate: criteria.value.cutoffDate,
  daysBefore: criteria.value.daysBefore,
  daysAfter: criteria.value.daysAfter,
  amountThreshold: criteria.value.amountThreshold,
}))

const AUDIT_NOTE_KEY = 'I2-14-audit-note'
const AUDIT_CONCLUSION_KEY = 'I2-14-audit-conclusion'
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
  void props.saveResponse('I2-14', { [AUDIT_NOTE_KEY]: val })
}
function saveAuditConclusion(val: string) {
  auditConclusion.value = val
  void props.saveResponse('I2-14', { [AUDIT_CONCLUSION_KEY]: val })
}
watch(() => props.allResponses, () => hydrateAudit(), { immediate: true })
onMounted(() => {
  hydrateAudit()
  void fetchHint()
})
onBeforeUnmount(() => { void flushAutoSave() })

function applyMaterialityThreshold() {
  if (suggestedThreshold.value == null) return
  updateBackwardCriteria({ amountThreshold: suggestedThreshold.value })
  ElMessage.success(`已采用建议金额门槛 ${suggestedThreshold.value}`)
}

function triggerImport() {
  importInputRef.value?.click()
}
async function onImportFile(e: Event) {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (!file) return
  await importData(file, 'I2-14')
  ;(e.target as HTMLInputElement).value = ''
}

function rowIndex(row: CutoffRow): number {
  return backwardRows.value.indexOf(row)
}
function onUpdate(row: CutoffRow, field: string, value: any) {
  const idx = rowIndex(row)
  if (idx < 0) return
  updateBackwardRow(idx, field, value)
}
function onRemove(row: CutoffRow) {
  const idx = rowIndex(row)
  if (idx < 0) return
  removeBackwardRow(idx)
}
async function handleAutoSampling() {
  await loadFromAutoSampling('backward')
}
function handleCutoffFilled(payload: { samples: ExtractedVoucher[]; fillMode: FillMode }) {
  importExtractedVouchers('backward', payload.samples.map((v) => ({
    voucher_date: v.voucherDate,
    voucher_no: v.voucherNo,
    summary: v.summary,
    amount: v.debitAmount ? parseFloat(v.debitAmount) : (v.creditAmount ? parseFloat(v.creditAmount) : 0),
  })), { fillDocumentDate: false })
  showCutoffPanel.value = false
  ElMessage.success(`截止模块已填入 ${payload.samples.length} 笔（单据日期请查原件后补填）`)
}
function handleVoucherFilled(payload: any) {
  const vouchers = payload?.samples ?? []
  importExtractedVouchers('backward', vouchers.map((v: any) => ({
    voucher_date: v.voucherDate ?? v.voucher_date,
    voucher_no: v.voucherNo ?? v.voucher_no,
    summary: v.summary,
    amount: Number(v.debitAmount ?? v.debit_amount ?? 0),
  })), { fillDocumentDate: false })
  showSamplingDialog.value = false
  if (vouchers.length) ElMessage.success(`抽凭已填入 ${vouchers.length} 笔`)
}
async function handleDraftAje() {
  await draftAjeFromCrossPeriod('backward')
  emit('navigate-sheet', 'I2-3')
}
async function handleSave() {
  await saveCutoff('backward')
  await persistCompletion('backward')
  emit('save')
  ElMessage.success('单据→账簿截止性测试已保存')
}
function handleReview() {
  openReviewDialog('I2-14-截止性测试-单据到账')
}
function fmtAmount(v: number | null | undefined): string {
  if (v == null || Math.abs(v) < 0.005) return '—'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i2-cutoff-backward { font-size: var(--wp-font-size, 13px); padding: 16px; }
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
