<script setup lang="ts">
/** F3TabVoucherCheck — F3-7 应付票据检查表（三检查区 + 弹窗逐单据核对，参照 F2-56 模式） */
import { ref, computed, watch, toRef, inject, type Ref } from 'vue'
import {
  useF3VoucherCheck,
  F3_VOUCHER_SECTION_LABELS,
  type F3VoucherCheckRow,
  type F3VoucherSection,
} from '../composables/useF3VoucherCheck'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import { useStickySectionNav } from '../composables/useStickySectionNav'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { SampledVoucher, FillMode, Phase } from '../composables/useSamplingAlgorithms'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import F3SheetAttachments from './F3SheetAttachments.vue'
import type { F3ImportableSheet } from '../composables/useF3ImportExport'
import F3VoucherCheckTable from './F3VoucherCheckTable.vue'
import F3VoucherCheckDialog from './F3VoucherCheckDialog.vue'
import GtIndexChip from '../GtIndexChip.vue'

const f3VoucherNav = [
  { id: 'f3-7-sampling', label: '抽凭' },
  { id: 'f3-7-debit', label: '借方' },
  { id: 'f3-7-credit', label: '贷方' },
  { id: 'f3-7-subsequent', label: '日后' },
  { id: 'f3-7-note', label: '说明' },
  { id: 'f3-7-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(f3VoucherNav)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
function onImported() { reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  debitRows, creditRows, subsequentRows,
  debitTotal, creditTotal, subsequentTotal,
  debitAbnormal, creditAbnormal, subsequentAbnormal,
  checkRatios, auditConclusion,
  addRow, removeRow, updateCell, saveRow, applySamplingResults,
} = useF3VoucherCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

const sections: Array<{
  key: F3VoucherSection
  rows: typeof debitRows
  total: typeof debitTotal
  abnormal: typeof debitAbnormal
  sheet: F3ImportableSheet
}> = [
  { key: 'debit', rows: debitRows, total: debitTotal, abnormal: debitAbnormal, sheet: 'F3-7-debit' },
  { key: 'credit', rows: creditRows, total: creditTotal, abnormal: creditAbnormal, sheet: 'F3-7-credit' },
  { key: 'subsequent', rows: subsequentRows, total: subsequentTotal, abnormal: subsequentAbnormal, sheet: 'F3-7-subsequent' },
]

const auditYear = computed(() => props.year ?? new Date().getFullYear() - 1)
const currentPhase = computed<Phase>(() => 'final')
const totalRowCount = computed(() => debitRows.value.length + creditRows.value.length + subsequentRows.value.length)
const totalAbnormal = computed(() => debitAbnormal.value + creditAbnormal.value + subsequentAbnormal.value)

// ─── 弹窗逐单据核对（参照 F2-56） ───
const checkDialogVisible = ref(false)
const activeSection = ref<F3VoucherSection>('debit')
const activeRow = ref<F3VoucherCheckRow | null>(null)

function openCheckDialog(section: F3VoucherSection, rowId: string): void {
  const rows = section === 'debit' ? debitRows.value : section === 'credit' ? creditRows.value : subsequentRows.value
  const row = rows.find((item) => item.rowId === rowId)
  if (!row) return
  activeSection.value = section
  activeRow.value = row
  checkDialogVisible.value = true
}

function onDialogSave(section: F3VoucherSection, patch: F3VoucherCheckRow): void {
  saveRow(section, patch)
}

// ─── 审计说明 / 审计结论（含 AI） ───
const NOTE_KEY = 'F3-7-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
}
watch(() => props.allResponses.get(NOTE_KEY)?.remark, (v) => { if (typeof v === 'string') auditNote.value = v }, { immediate: true })

function aiContext() {
  return {
    checkRatios: checkRatios.value,
    sections: sections.map((section) => ({
      section: F3_VOUCHER_SECTION_LABELS[section.key],
      sampleCount: section.rows.value.filter((row) => row.voucherNo || row.amount).length,
      totalAmount: section.total.value,
      abnormalCount: section.abnormal.value,
      abnormalRows: section.rows.value
        .filter((row) => row.isAbnormal === '是')
        .map((row) => ({ voucherNo: row.voucherNo, amount: row.amount, issueDesc: row.issueDesc })),
    })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'voucher-check-note', auditNote.value, aiContext(), 'AI 生成 · 应付票据检查审计说明',
  )
  if (text) saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'voucher-check-conclusion', auditConclusion.value, aiContext(), 'AI 生成 · 应付票据检查审计结论',
  )
  if (text) auditConclusion.value = text
}

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  applySamplingResults(payload.samples, payload.fillMode)
}

function ratioClass(ratio: number): string {
  return ratio > 0 && ratio < 50 ? 'ratio-low' : ''
}
</script>

<template>
  <div class="f3-tab-voucher">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示与核对逻辑</summary>
      <div class="guidance-content">
        <p>1. 测试内容：原始凭证是否齐全；记账凭证与原始凭证是否相符；账务处理是否正确；是否记录于恰当的会计期间。</p>
        <p>2. 三个检查区对应源表结构：借方区（兑付）核对付款审批单和银行回单；贷方区（开票）核对入库单/验收单和采购发票；日后借方区关注应计未计票据。</p>
        <p>3. 每行点击"单据核对"打开弹窗，逐单据上传影像并OCR识别回填，右侧实时勾稽提示金额不符或单据缺失。</p>
        <p>4. 特定样本（大额、关联方、异常款项）全部测试；抽样样本可用下方抽凭引擎自动填入借贷两区。</p>
        <p>5. 检查比例自动与F3-2明细表账面数比对，比例较低时应扩大样本量或说明原因。</p>
      </div>
    </details>

    <!-- 审计目标（对齐源表） -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：1.应付票据是存在的且记录于恰当账户；2.由被审计单位拥有或控制；3.以恰当金额包括在财务报表中，计价分摊调整已恰当记录，披露恰当。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left"></div>
      <div class="toolbar-right">
        <span class="chip-wrap"><GtIndexChip value="wp:F3-7" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ totalRowCount }} 行</el-tag>
        <el-tag v-if="totalAbnormal" size="small" type="danger">异常 {{ totalAbnormal }} 笔</el-tag>
      </div>
    </div>

    <F3SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F3-7" label="检查表附件" />

    <nav class="st-sec-nav" aria-label="F3-7 分区导航">
      <button
        v-for="item in f3VoucherNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <el-collapse id="f3-7-sampling" class="sampling-engine-collapse">
      <el-collapse-item title="自动抽凭（科目 2201 应付票据 · 样本按借贷方向自动分配）" name="auto-sampling">
        <GtVoucherSamplingEngine
          account-code="2201"
          :phase="currentPhase"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="auditYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <template v-for="section in sections" :key="section.key">
      <div :id="`f3-7-${section.key}`" class="voucher-section">
        <h4 class="block-title">{{ F3_VOUCHER_SECTION_LABELS[section.key] }}</h4>
        <div class="block-toolbar">
          <div class="toolbar-left">
            <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow(section.key)">+ 添加凭证</el-button>
          </div>
          <div class="toolbar-right">
            <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" :sheet="section.sheet" :disabled="isReadonly" @imported="onImported" />
            <el-tag size="small" type="info">共 {{ section.rows.value.length }} 行</el-tag>
          </div>
        </div>
        <F3VoucherCheckTable
          :section="section.key"
          :rows="section.rows.value"
          :is-readonly="isReadonly"
          :wp-id="wpId"
          :project-id="projectId"
          :all-responses="allResponses"
          @update-cell="(id, f, v) => updateCell(section.key, id, f, v)"
          @remove-row="(id) => removeRow(section.key, id)"
          @open-check="(id) => openCheckDialog(section.key, id)"
        />
        <div class="subtotal">
          小计 {{ fmt(section.total.value) }} |
          <el-tag v-if="section.abnormal.value > 0" type="danger" size="small">异常 {{ section.abnormal.value }} 笔</el-tag>
          <el-tag v-else type="success" size="small">无异常</el-tag>
        </div>
      </div>
    </template>

    <!-- 四、审计说明：检查比例（对齐源表） -->
    <el-card id="f3-7-note" class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">四、审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiNote">🤖 AI 生成说明</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-7-note')">💬</el-button>
          </div>
        </div>
      </template>
      <table class="ratio-table">
        <thead>
          <tr><th>方向</th><th>账面金额（F3-2）</th><th>检查金额</th><th>检查比例</th></tr>
        </thead>
        <tbody>
          <tr v-for="item in checkRatios" :key="item.label">
            <td>{{ item.label }}</td>
            <td class="num">{{ fmt(item.bookAmount) }}</td>
            <td class="num">{{ fmt(item.checkedAmount) }}</td>
            <td class="num" :class="ratioClass(item.ratio)">{{ item.bookAmount > 0 ? `${item.ratio.toFixed(2)}%` : '—' }}</td>
          </tr>
        </tbody>
      </table>
      <p class="ratio-hint">如果检查比例较低应扩大检查样本量或说明原因。</p>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：样本选取标准与规模、检查比例分析、异常凭证及追加程序。"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>

    <!-- 五、审计结论 -->
    <el-card id="f3-7-conclusion" class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">五、审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion">🤖 AI 生成结论</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-7-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly" placeholder="评价应付票据存在性、完整性、准确性及会计期间恰当性，说明异常事项处理..." />
    </el-card>

    <!-- 逐笔单据核对弹窗 -->
    <F3VoucherCheckDialog
      v-model="checkDialogVisible"
      :row="activeRow"
      :section="activeSection"
      :wp-id="wpId"
      :project-id="projectId"
      :readonly="isReadonly"
      @save="onDialogSave"
    />
  </div>
</template>

<style scoped>
.f3-tab-voucher {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-voucher :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-voucher :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #4b2d77;
  background: #f5f1fa;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 600;
  color: #4b2d77;
}
.guidance-content {
  margin-top: 8px;
  color: #606266;
  line-height: 1.65;
}
.guidance-content p {
  margin: 3px 0;
}
.objective-alert {
  margin-bottom: 12px;
}
.sampling-engine-collapse {
  margin-bottom: 12px;
}
.tab-toolbar, .block-toolbar, .toolbar-left, .toolbar-right, .opinion-header, .opinion-actions {
  display: flex;
  align-items: center;
}
.tab-toolbar, .block-toolbar, .opinion-header {
  justify-content: space-between;
}
.tab-toolbar { margin-bottom: 8px; }
.block-toolbar { margin-bottom: 8px; }
.toolbar-left, .toolbar-right, .opinion-actions { gap: 7px; }
.chip-wrap { display: inline-flex; align-items: center; }
.block-title {
  margin: 14px 0 8px;
  font-size: 14px;
  color: #303133;
}
.subtotal {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 8px;
  font-weight: 600;
  margin: 4px 0 12px;
}
.opinion-card {
  margin-top: 16px;
  border-radius: 8px;
}
.opinion-card :deep(.el-card__header) {
  padding: 12px 16px;
  background: #fafafa;
  border-bottom: 1px solid #ebeef5;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.ratio-table {
  width: 100%;
  max-width: 640px;
  border-collapse: collapse;
  margin-bottom: 6px;
}
.ratio-table th, .ratio-table td {
  border: 1px solid #e4e7ed;
  padding: 6px 10px;
  text-align: left;
}
.ratio-table th {
  background: #f5f1fa;
  color: #4b2d77;
}
.ratio-table td.num {
  text-align: right;
}
.ratio-table td.ratio-low {
  color: #d03050;
  font-weight: 700;
}
.ratio-hint {
  margin: 0 0 10px;
  color: #909399;
  font-size: 12px;
}
.voucher-section {
  margin-bottom: 8px;
}
</style>

<style src="../f2/stocktake/f2StocktakeSoftNav.css"></style>
