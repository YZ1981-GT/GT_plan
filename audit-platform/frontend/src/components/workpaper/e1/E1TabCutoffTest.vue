<script setup lang="ts">
/**
 * E1TabCutoffTest.vue — E1-21/22 截止测试 (variant: bank/other)
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 18.15
 *
 * - Uses useE1CutoffTest composable
 * - Props: variant detected from sheetName (E1-21→'bank', E1-22→'other')
 * - el-table: 凭证号 | 日期 | 金额 | 对方账户 | 是否跨期(readonly, computed, red highlight)
 * - Dynamic rows
 *
 * Requirements: 10.4-10.5
 */
import { ref, computed, inject, toRef, onMounted, watch, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  useE1CutoffTest,
  type CutoffVariant,
  type CutoffTestRow,
  determineCutoff,
} from '../composables/useE1CutoffTest'
import { useE1ImportExport } from '../composables/useE1ImportExport'
import type { UseE1BaseOptions } from '../composables/useE1Adjudication'
import GtIndexChip from '../GtIndexChip.vue'
import GtCutoffAutoSampling from '../cutoff/GtCutoffAutoSampling.vue'
import { DisplayPrefs_Key } from '../composables/displayPrefsKey'
import { useDisplayPrefsStore } from '@/stores/displayPrefs'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  saveImmediate: (items: any[]) => Promise<void>
  debouncedSave: (items: any[]) => Promise<void>
  isReadonly: boolean
  sheetName?: string
  bsDate?: string
}>()

// ─── Inject ──────────────────────────────────────────────────────────────────

const displayPrefs = inject(DisplayPrefs_Key, null) ?? useDisplayPrefsStore()

const reloadWorkpaperData = inject<(() => Promise<void>) | null>('reloadWorkpaperData', null)

// ─── Variant Detection ───────────────────────────────────────────────────────

const variant = computed<CutoffVariant>(() => {
  const name = props.sheetName || ''
  if (name.includes('E1-22') || name.includes('其他货币资金')) return 'other'
  return 'bank'
})

// ─── Composable ──────────────────────────────────────────────────────────────

const options: UseE1BaseOptions & { variant: CutoffVariant } = {
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  projectId: toRef(props, 'projectId') as unknown as Ref<string>,
  allResponses: toRef(props, 'allResponses') as unknown as Ref<Map<string, any>>,
  saveImmediate: props.saveImmediate,
  debouncedSave: props.debouncedSave,
  isReadonly: toRef(props, 'isReadonly') as unknown as Ref<boolean>,
  bsDate: toRef(props, 'bsDate') as unknown as Ref<string>,
  variant: variant.value,
}

const {
  rows,
  balanceSheetDate,
  isLoading,
  addRow,
  removeRow,
  updateCell,
} = useE1CutoffTest(options)

// ─── 导入导出（E1-21 bank / E1-22 other） ─────────────────────────────────────

const sheetCode = computed(() => (variant.value === 'other' ? 'E1-22' : 'E1-21'))
const { exportTemplate, exportData, importData, isImporting } = useE1ImportExport({
  wpId: toRef(props, 'wpId') as unknown as Ref<string>,
  sheet: sheetCode as unknown as Ref<string>,
})

async function handleImport(file: File): Promise<boolean> {
  const res = await importData(file)
  if (res.success) {
    ElMessage.success(res.message || '导入成功')
    await reloadWorkpaperData?.()
  } else {
    ElMessage.warning(res.message || '导入失败')
  }
  return false
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClass({ row }: { row: CutoffTestRow }): string {
  if (row.isCrossover) return 'e1-cutoff-red-row'
  return ''
}

// ─── 截止自动取数 (GtCutoffAutoSampling) ─────────────────────────────────────

const cutoffSamplingVisible = ref(false)
const cutoffAccountCode = computed(() => variant.value === 'other' ? '1012' : '1002')
const samplingYear = computed(() => {
  const bs = props.bsDate || ''
  const match = bs.match(/^(\d{4})/)
  return match ? Number(match[1]) : new Date().getFullYear() - 1
})

function onCutoffFilled(payload: any): void {
  const samples = payload?.samples || payload
  if (!Array.isArray(samples) || samples.length === 0) return
  const bsVal = balanceSheetDate.value || props.bsDate || ''
  for (const s of samples) {
    const date = s.voucherDate || s.date || ''
    const isCross = determineCutoff(date, bsVal)
    const newRow: Partial<CutoffTestRow> = {
      voucherNo: s.voucherNo || '',
      date,
      amount: s.debitAmount || s.creditAmount || s.amount || 0,
      counterparty: s.counterpartAccount || s.counterparty || s.summary || '',
      isCrossover: isCross,
      note: isCross ? '跨期(自动标记)' : '',
    }
    // Avoid duplicates by voucherNo
    if (newRow.voucherNo && rows.value.some(r => r.voucherNo === newRow.voucherNo)) continue
    addRow()
    const lastRow = rows.value[rows.value.length - 1]
    if (lastRow) {
      updateCell(lastRow.id, 'voucherNo', newRow.voucherNo || '')
      updateCell(lastRow.id, 'date', newRow.date || '')
      updateCell(lastRow.id, 'amount', String(newRow.amount || 0))
      updateCell(lastRow.id, 'counterparty', newRow.counterparty || '')
      if (newRow.note) updateCell(lastRow.id, 'note', newRow.note)
    }
  }
  cutoffSamplingVisible.value = false
  ElMessage.success(`已导入 ${samples.length} 笔截止凭证`)
}

/** AI 复核意见经用户确认后追加到审计说明（GtCutoffAutoSampling @applied） */
function onCutoffApplied(text: string): void {
  if (!text || props.isReadonly) return
  const merged = auditNote.value ? `${auditNote.value}\n${text}` : text
  saveAuditNote(merged)
}

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────

const NOTE_KEY = computed(() => `E1-cutoff-audit-note-${variant.value}`)
const CONCLUSION_KEY = computed(() => `E1-cutoff-audit-conclusion-${variant.value}`)
const auditNote = ref('')
const auditConclusion = ref('')

function loadAuditText(): void {
  const noteResp = props.allResponses.get(NOTE_KEY.value)
  auditNote.value = noteResp?.remark || ''
  const concResp = props.allResponses.get(CONCLUSION_KEY.value)
  auditConclusion.value = concResp?.remark || ''
}

onMounted(loadAuditText)
watch(variant, loadAuditText)

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY.value, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY.value, item)
  void props.saveImmediate([item])
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  const item = { item_id: CONCLUSION_KEY.value, conclusion: null, remark: val }
  props.allResponses.set(CONCLUSION_KEY.value, item)
  void props.saveImmediate([item])
}

// ─── OCR 链路（凭证影像 → E1CutoffOcrConfirmDialog → 确认写行）──────────────
// @spec e1-orphan-components-wiring — Task 7

import E1CutoffOcrConfirmDialog from './E1CutoffOcrConfirmDialog.vue'
import type { CutoffOcrFields } from './E1CutoffOcrConfirmDialog.vue'
import http from '@/utils/http'

const ocrVisible = ref(false)
const ocrFields = ref<Partial<CutoffOcrFields>>({})
const ocrConfidence = ref<number | undefined>()
const ocrPreview = ref('')
const ocrFileName = ref('')

async function onOcrUpload(file: File): Promise<boolean> {
  const form = new FormData()
  form.append('file', file)
  try {
    const res = await http.post(`/api/workpapers/${props.wpId}/e1/cutoff-ocr`, form)
    const data = res?.data ?? res
    ocrFields.value = data?.fields ?? {}
    ocrConfidence.value = data?.confidence
    ocrPreview.value = data?.preview ?? ''
    ocrFileName.value = data?.file_name ?? file.name ?? ''
    ocrVisible.value = true
  } catch (e) {
    console.warn('[E1TabCutoffTest] OCR failed:', e)
    ElMessage.warning('OCR 识别失败，请手工录入')
  }
  return false // prevent el-upload default behavior
}

function onOcrConfirm(fields: CutoffOcrFields): void {
  ocrVisible.value = false
  // Write confirmed fields into a new row
  addRow()
  const lastRow = rows.value[rows.value.length - 1]
  if (!lastRow) return
  if (fields.voucherNo) updateCell(lastRow.id, 'voucherNo', fields.voucherNo)
  if (fields.date) updateCell(lastRow.id, 'date', fields.date)
  if (fields.businessContent) updateCell(lastRow.id, 'businessContent', fields.businessContent)
  if (fields.counterparty) updateCell(lastRow.id, 'counterparty', fields.counterparty)
  if (fields.debitAmount) updateCell(lastRow.id, 'debitAmount', Number(fields.debitAmount) || 0)
  if (fields.creditAmount) updateCell(lastRow.id, 'creditAmount', Number(fields.creditAmount) || 0)
  if (fields.receiptDate) updateCell(lastRow.id, 'receiptDate', fields.receiptDate)
  if (fields.otherDocDate) updateCell(lastRow.id, 'otherDocDate', fields.otherDocDate)
  if (fields.note) updateCell(lastRow.id, 'note', fields.note)
}

// ─── AI 辅助（spec: e1-orphan-components-wiring Task 9）─────────────────────
import { useE1AiGenerate } from '../composables/useE1AiGenerate'

const { generateText, isGenerating } = useE1AiGenerate(toRef(props, 'wpId') as Ref<string>)

async function generateAuditNote(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-21-audit-note',
    prompt: '你是注册会计师助理。请撰写 E1-21/22 截止测试 的审计说明，概述审计程序执行情况与主要发现。不得虚构。约 100～200 字。',
    context: { 底稿: 'E1-21/22 截止测试', 说明: auditNote.value },
    existingContent: auditNote.value,
    confirmTitle: 'AI 生成 · 审计说明',
  })
  if (text) saveAuditNote(text)
}

async function generateAuditConclusion(): Promise<void> {
  if (props.isReadonly) return
  const text = await generateText({
    section: 'e1-21-audit-conclusion',
    prompt: '你是注册会计师助理。请撰写 E1-21/22 截止测试 的审计结论，对审计程序结果给出结论性评价。不得虚构。约 60～150 字。',
    context: { 底稿: 'E1-21/22 截止测试', 结论: auditConclusion.value },
    existingContent: auditConclusion.value,
    confirmTitle: 'AI 生成 · 审计结论',
  })
  if (text) saveAuditConclusion(text)
}
</script>

<template>
  <div class="e1-tab-cutoff-test">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 抽取资产负债表日前后各若干天（通常±3~5天）的银行收付款凭证进行截止测试。</p>
        <p>2. 检查款项是否记入正确会计期间，"是否跨期"列由系统根据凭证日期与资产负债表日自动判定（跨期红色高亮）。</p>
        <p>3. 跨期项目应评估对货币资金及往来科目（应收/应付）的影响，必要时提请调整。</p>
        <p>4. 结合银行对账单、余额调节表（E1-6）核查未达账项的真实性与合理性。</p>
      </div>
    </details>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：通过截止测试确认货币资金收支已记入正确会计期间，防止跨期错报。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" :type="variant === 'other' ? 'warning' : 'success'">
          {{ variant === 'other' ? '其他货币资金 (E1-22)' : '银行存款 (E1-21)' }}
        </el-tag>
        <el-tag v-if="balanceSheetDate" size="small" type="info">资产负债表日：{{ balanceSheetDate }}</el-tag>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加行</el-button>
        <el-button size="small" type="warning" :disabled="isReadonly" @click="cutoffSamplingVisible = true">🎲 截止取数</el-button>
        <el-upload :show-file-list="false" accept=".pdf,.png,.jpg,.jpeg,.tif,.tiff,.bmp,.webp" :before-upload="onOcrUpload" :disabled="isReadonly" style="display:inline-block;margin-left:4px">
          <el-button size="small" :disabled="isReadonly">📎 凭证OCR</el-button>
        </el-upload>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click" :disabled="isReadonly">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="exportTemplate()">导出模板</el-dropdown-item>
              <el-dropdown-item @click="exportData()">导出数据</el-dropdown-item>
              <el-dropdown-item>
                <el-upload
                  :show-file-list="false"
                  accept=".xlsx,.xls"
                  :before-upload="handleImport"
                  :disabled="isImporting"
                >
                  <span>导入数据</span>
                </el-upload>
              </el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:E1-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <el-skeleton :loading="isLoading" :rows="8" animated>
      <template #default>
        <el-table
          :data="rows"
          border
          stripe
          size="small"
          max-height="500"
          style="width: 100%"
          :row-class-name="getRowClass"
        >
          <el-table-column label="凭证号" width="130">
            <template #default="{ row }">
              <el-input :model-value="row.voucherNo" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'voucherNo', val)" />
            </template>
          </el-table-column>
          <el-table-column label="日期" width="140">
            <template #default="{ row }">
              <el-date-picker :model-value="row.date" :disabled="isReadonly" type="date"
                value-format="YYYY-MM-DD" size="small" style="width: 100%"
                @update:model-value="(val: string) => updateCell(row.id, 'date', val || '')" />
            </template>
          </el-table-column>
          <el-table-column label="金额" width="150" align="right">
            <template #default="{ row }">
              <el-input-number :model-value="row.amount" :disabled="isReadonly"
                :controls="false" :precision="2" size="small"
                @change="(val: number) => updateCell(row.id, 'amount', val ?? 0)" />
            </template>
          </el-table-column>
          <el-table-column label="对方账户" min-width="150">
            <template #default="{ row }">
              <el-input :model-value="row.counterparty" :disabled="isReadonly" size="small"
                @change="(val: string) => updateCell(row.id, 'counterparty', val)" />
            </template>
          </el-table-column>
          <el-table-column label="是否跨期" width="100" align="center" class-name="auto-calc-col">
            <template #default="{ row }">
              <el-tag v-if="row.isCrossover" type="danger" size="small">跨期</el-tag>
              <span v-else class="auto-calc-value">否</span>
            </template>
          </el-table-column>
          <el-table-column label="操作" width="70" align="center" fixed="right">
            <template #default="{ row }">
              <el-button v-if="!isReadonly" type="danger" text size="small"
                @click="removeRow(row.id)">删除</el-button>
            </template>
          </el-table-column>
        </el-table>

        <!-- 审计说明 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header"><span>审计说明</span></div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditNote"
            :disabled="isReadonly"
            :autosize="{ minRows: 5 }"
            :placeholder="variant === 'other'
              ? '填写审计说明：可概述（1）其他货币资金截止测试抽取的期间（资产负债表日前后±3~5天）与样本；（2）跨期收支事项的判定及对往来科目的影响；（3）如发现跨期是否已扩大测试范围。'
              : '填写审计说明：可概述（1）银行存款截止测试抽取的期间（资产负债表日前后±3~5天）与样本；（2）跨期收支事项的判定及对货币资金/往来科目的影响；（3）结合银行对账单与余额调节表（E1-6）核查未达账项。'"
            @change="(val: string) => saveAuditNote(val)"
          />
        </el-card>

        <!-- 审计结论 -->
        <el-card shadow="never" class="audit-note-card">
          <template #header>
            <div class="card-header"><span>审计结论</span></div>
          </template>
          <el-input
            type="textarea"
            :model-value="auditConclusion"
            :disabled="isReadonly"
            :autosize="{ minRows: 3 }"
            placeholder="填写审计结论：A、货币资金收支已记入正确会计期间，未见跨期错报。B、除上述跨期事项应提请调整外，其余未见异常。C、由于发现跨期舞弊迹象（或样本受限），已扩大测试期间并作进一步核查。"
            @change="(val: string) => saveAuditConclusion(val)"
          />
        </el-card>
      </template>
    </el-skeleton>

    <!-- 截止自动取数弹窗 -->
    <el-dialog
      v-model="cutoffSamplingVisible"
      title="截止自动取数"
      width="880px"
      append-to-body
      destroy-on-close
    >
      <GtCutoffAutoSampling
        :account-code="cutoffAccountCode"
        :workpaper-id="wpId"
        :project-id="projectId"
        :year="samplingYear"
        cutoff-direction="window"
        :default-conditions="{ cutoffDate: balanceSheetDate || bsDate || '' }"
        :readonly="isReadonly"
        @filled="onCutoffFilled"
        @applied="onCutoffApplied"
      />
    </el-dialog>

    <!-- OCR 确认弹窗 -->
    <E1CutoffOcrConfirmDialog
      v-model="ocrVisible"
      :fields="ocrFields"
      :confidence="ocrConfidence"
      :ocr-preview="ocrPreview"
      :file-name="ocrFileName"
      @confirm="onOcrConfirm"
      @cancel="ocrVisible = false"
    />
  </div>
</template>

<style scoped>
.e1-tab-cutoff-test {
  padding: 12px 0;
}
.e1-tab-cutoff-test :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.e1-tab-cutoff-test :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}

/* 编制提示 */
.guidance-details {
  margin-bottom: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.objective-alert {
  margin-bottom: 12px;
}

/* 工具栏 */
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  flex-wrap: wrap;
  gap: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
  flex-wrap: wrap;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }

/* 自动计算列灰底 */
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
.auto-calc-value {
  color: #909399;
}
:deep(.e1-cutoff-red-row) {
  background-color: #fef0f0 !important;
}
:deep(.e1-cutoff-red-row td) {
  color: #f56c6c;
}
.audit-note-card {
  margin-top: 16px;
}
.audit-note-card .card-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  font-weight: 500;
}
</style>
