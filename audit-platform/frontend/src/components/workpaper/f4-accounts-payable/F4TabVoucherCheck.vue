<script setup lang="ts">
/** F4TabVoucherCheck — F4-8 应付账款检查表（借/贷两区 + 弹窗逐单据核对） */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import {
  useF4VoucherCheck,
  F4_VOUCHER_SECTION_LABELS,
  type F4VoucherCheckRow,
  type F4VoucherSection,
} from '../composables/useF4VoucherCheck'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import { useStickySectionNav } from '../composables/useStickySectionNav'
import GtVoucherSamplingEngine from '../voucher-sampling/GtVoucherSamplingEngine.vue'
import type { SampledVoucher, FillMode, Phase } from '../composables/useSamplingAlgorithms'
import F4VoucherCheckTable from './F4VoucherCheckTable.vue'
import F4VoucherCheckDialog from './F4VoucherCheckDialog.vue'
import F4SheetAttachments from './F4SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'
import WpSamplingMethodologyBar from '../shared/WpSamplingMethodologyBar.vue'
import { useSamplingMethodologyPersist } from '../composables/shared/useSamplingMethodologyPersist'
import type { SamplingMethodologySnapshot } from '../composables/shared/samplingFillTarget'

const f4VoucherNav = [
  { id: 'f4-8-sample', label: '样本' },
  { id: 'f4-8-sampling', label: '抽凭' },
  { id: 'f4-8-debit', label: '借方' },
  { id: 'f4-8-credit', label: '贷方' },
  { id: 'f4-8-note', label: '说明' },
  { id: 'f4-8-conclusion', label: '结论' },
]
const { activeId, scrollTo } = useStickySectionNav(f4VoucherNav)

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  year?: number
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  debitRows,
  creditRows,
  debitTotal,
  creditTotal,
  debitAbnormal,
  creditAbnormal,
  checkRatios,
  auditNote,
  auditConclusion,
  sampleBasis,
  loadSection,
  addRow,
  removeRow,
  updateCell,
  saveRow,
  applySamplingResults,
  saveAuditNote,
  saveAuditConclusion,
  saveSampleBasis,
} = useF4VoucherCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

const auditYear = computed(() => props.year ?? new Date().getFullYear() - 1)
const currentPhase = computed<Phase>(() => 'final')
const totalRowCount = computed(() => debitRows.value.length + creditRows.value.length)
const totalAbnormal = computed(() => debitAbnormal.value + creditAbnormal.value)

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function ratioClass(ratio: number): string {
  return ratio > 0 && ratio < 50 ? 'ratio-low' : ''
}

async function onImported(section: F4VoucherSection): Promise<void> {
  if (reloadWorkpaperData) await reloadWorkpaperData()
  loadSection(section)
}

// ─── 弹窗逐单据核对 ───
const checkDialogVisible = ref(false)
const activeSection = ref<F4VoucherSection>('debit')
const activeRow = ref<F4VoucherCheckRow | null>(null)

function openCheckDialog(section: F4VoucherSection, rowId: string): void {
  const rows = section === 'debit' ? debitRows.value : creditRows.value
  const row = rows.find((item) => item.rowId === rowId)
  if (!row) return
  activeSection.value = section
  activeRow.value = row
  checkDialogVisible.value = true
}

function onDialogSave(section: F4VoucherSection, patch: F4VoucherCheckRow): void {
  saveRow(section, patch)
}

/**
 * 抽样方法学留痕（R6.3/R6.4）：把 `filled` 载荷里的 methodology 落到固定 item key，
 * 并在抽凭区渲染到底稿正文 —— 复核与归档看的是底稿，不是后台抽凭日志。
 */
const { methodology, persistMethodology } = useSamplingMethodologyPersist({
  wpCode: 'F4',
  allResponses: toRef(props, 'allResponses') as never,
  persist: (itemId, remark) => {
    const item = { item_id: itemId, conclusion: null, remark }
    props.allResponses.set(itemId, item as never)
    window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
  },
  isReadonly: computed(() => props.isReadonly),
})

function handleSamplingFilled(payload: { samples: SampledVoucher[]; phase: Phase; fillMode: FillMode }): void {
  // 方法学先落库：即便回填 0 条，「抽过样且方法学如此」也是应留的痕
  void persistMethodology((payload as { methodology?: SamplingMethodologySnapshot })?.methodology)

  applySamplingResults(payload.samples, payload.fillMode)
}

function aiContext() {
  return {
    sheet: 'F4-8',
    sampleBasis: sampleBasis.value,
    checkRatios: checkRatios.value,
    sections: (['debit', 'credit'] as F4VoucherSection[]).map((section) => {
      const rows = section === 'debit' ? debitRows.value : creditRows.value
      return {
        section: F4_VOUCHER_SECTION_LABELS[section],
        sampleCount: rows.filter((row) => row.voucherNo || row.amount).length,
        totalAmount: section === 'debit' ? debitTotal.value : creditTotal.value,
        abnormalCount: section === 'debit' ? debitAbnormal.value : creditAbnormal.value,
        abnormalRows: rows
          .filter((row) => row.isAbnormal === '是')
          .map((row) => ({
            supplierName: row.supplierName,
            voucherNo: row.voucherNo,
            amount: row.amount,
            issueDesc: row.issueDesc,
          })),
      }
    }),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'voucher-check-note',
    auditNote.value,
    aiContext(),
    'AI 生成 · F4-8审计说明',
  )
  if (text) saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'voucher-check-conclusion',
    auditConclusion.value,
    aiContext(),
    'AI 生成 · F4-8审计结论',
  )
  if (text) saveAuditConclusion(text)
}
</script>

<template>
  <div class="f4-tab-voucher-check">
  <!-- 抽样方法学（来自抽凭引擎回填，底稿正文可见 → 归档与复核可追溯） -->
  <WpSamplingMethodologyBar :methodology="methodology" />

    <details class="guidance-details">
      <summary>📋 编制思路与单据核对逻辑</summary>
      <div class="guidance-content">
        <p>1. 审计目标：验证应付账款存在、权属、计价分摊及披露；本表通过借/贷发生额抽凭核对原始凭证完整性与账务处理正确性。</p>
        <p>2. 借方区核对「记账凭证 → 付款审批单 → 银行回单」；贷方区核对「记账凭证 → 入库单/验收单 → 采购发票」，贷方可结合存货采购入库检查 F2-33。</p>
        <p>3. 每行点击「单据核对」进入弹窗：分单据逐一上传影像、OCR识别、确认回填；回填后仍可二次编辑，右侧实时勾稽金额与对手方。</p>
        <p>4. 特定样本（大额、关联方、异常款项）全部测试；其余可用抽凭引擎按借贷方向自动分配样本。</p>
        <p>5. 检查比例自动与 F4-2 明细表账面借贷发生额比对；比例偏低时须扩大样本量或在审计说明中解释原因。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：1.资产负债表中记录的应付账款是存在的，且已经记录在恰当的账户中；2.记录的应付账款由被审计单位拥有或控制；3.应付账款以恰当的金额包括在财务报表中，相关计价分摊调整及披露恰当。"
    />

    <el-card id="f4-8-sample" shadow="never" class="sample-card">
      <template #header>
        <div class="card-header">
          <span>二、样本选取标准与规模</span>
          <GtIndexChip value="wp:F4-2" :context-project-id="projectId" />
        </div>
      </template>
      <el-input
        :model-value="sampleBasis"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="记录测试总体、特定样本、抽样总体、抽样方法、样本量及抽样工具过程索引……"
        @change="saveSampleBasis"
      />
    </el-card>

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="info">共 {{ totalRowCount }} 行</el-tag>
        <el-tag v-if="totalAbnormal" size="small" type="danger">异常 {{ totalAbnormal }} 笔</el-tag>
      </div>
      <div class="toolbar-right">
        <GtIndexChip value="wp:F2-33" :context-project-id="projectId" />
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="openReviewDialog('f4-8-voucher-check')"
        >复核</el-button>
      </div>
    </div>

    <F4SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F4-8" label="检查表附件" />

    <nav class="st-sec-nav" aria-label="F4-8 分区导航">
      <button
        v-for="item in f4VoucherNav"
        :key="item.id"
        type="button"
        class="st-sec-btn"
        :class="{ active: activeId === item.id }"
        @click="scrollTo(item.id)"
      >{{ item.label }}</button>
    </nav>

    <el-collapse id="f4-8-sampling" class="sampling-engine-collapse">
      <el-collapse-item title="自动抽凭（科目 2202 应付账款 · 样本按借贷方向自动分配）" name="auto-sampling">
        <GtVoucherSamplingEngine
          account-code="2202"
          :phase="currentPhase"
          default-method="random"
          :workpaper-id="wpId"
          :project-id="projectId"
          :year="auditYear"
          @filled="handleSamplingFilled"
        />
      </el-collapse-item>
    </el-collapse>

    <div id="f4-8-debit">
      <F4VoucherCheckTable
        section="debit"
        :rows="debitRows"
        :is-readonly="isReadonly"
        :wp-id="wpId"
        :project-id="projectId"
        :all-responses="allResponses"
        @add-row="addRow('debit')"
        @remove-row="(rowId) => removeRow('debit', rowId)"
        @update-cell="(rowId, field, value) => updateCell('debit', rowId, field, value)"
        @open-check="(rowId) => openCheckDialog('debit', rowId)"
        @imported="onImported('debit')"
      />
    </div>

    <div id="f4-8-credit">
      <F4VoucherCheckTable
        section="credit"
        :rows="creditRows"
        :is-readonly="isReadonly"
        :wp-id="wpId"
        :project-id="projectId"
        :all-responses="allResponses"
        @add-row="addRow('credit')"
        @remove-row="(rowId) => removeRow('credit', rowId)"
        @update-cell="(rowId, field, value) => updateCell('credit', rowId, field, value)"
        @open-check="(rowId) => openCheckDialog('credit', rowId)"
        @imported="onImported('credit')"
      />
    </div>

    <el-card id="f4-8-note" shadow="never" class="ratio-card">
      <template #header>
        <div class="card-header">
          <span>四、审计说明 · 本期发生额检查比例</span>
          <span class="ratio-hint">如果检查比例较低应扩大检查样本量或说明原因</span>
        </div>
      </template>
      <el-table :data="checkRatios" border size="small" style="max-width: 640px">
        <el-table-column prop="label" label="方向" width="120" />
        <el-table-column label="账面金额" align="right">
          <template #default="{ row }">{{ fmt(row.bookAmount) }}</template>
        </el-table-column>
        <el-table-column label="检查金额" align="right">
          <template #default="{ row }">{{ fmt(row.checkedAmount) }}</template>
        </el-table-column>
        <el-table-column label="检查比例" align="right">
          <template #default="{ row }">
            <span :class="ratioClass(row.ratio)">{{ row.ratio.toFixed(2) }}%</span>
          </template>
        </el-table-column>
      </el-table>

      <div class="overall-note">
        <div class="note-actions">
          <span>总体审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateAiNote"
          >🤖 AI生成说明</el-button>
        </div>
        <el-input
          :model-value="auditNote"
          type="textarea"
          :autosize="{ minRows: 4, maxRows: 10 }"
          :disabled="isReadonly"
          placeholder="综合说明样本选取、借/贷单据勾稽结果、检查比例偏低原因及扩大测试情况。"
          @change="saveAuditNote"
        />
      </div>
    </el-card>

    <el-card id="f4-8-conclusion" shadow="never" class="conclusion-card">
      <template #header>
        <div class="card-header">
          <span>五、审计结论</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateAiConclusion"
          >🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合评价应付账款借/贷发生额抽凭检查结果，评价存在、计价、截止及披露是否恰当。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <F4VoucherCheckDialog
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
.f4-tab-voucher-check { padding: 12px; font-size: var(--wp-font-size, 13px); }
.guidance-details {
  margin-bottom: 12px;
  padding: 8px 12px;
  border-left: 3px solid #315a8a;
  border-radius: 4px;
  background: #eef4fa;
}
.guidance-details summary { cursor: pointer; color: #315a8a; font-weight: 600; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.audit-objective { margin-bottom: 12px; }
.sample-card, .ratio-card, .conclusion-card {
  margin-bottom: 16px;
  border-radius: 8px;
}
.sample-card :deep(.el-card__header),
.ratio-card :deep(.el-card__header),
.conclusion-card :deep(.el-card__header) {
  padding: 11px 14px;
  background: #fafafa;
}
.card-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 12px;
}
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 10px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; }
.sampling-engine-collapse { margin-bottom: 16px; }
.ratio-hint { color: #d03050; font-size: 12px; }
.ratio-low { color: #d03050; font-weight: 700; }
.overall-note { margin-top: 14px; }
.note-actions {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 8px;
}
</style>

<style src="../f2/stocktake/f2StocktakeSoftNav.css"></style>
