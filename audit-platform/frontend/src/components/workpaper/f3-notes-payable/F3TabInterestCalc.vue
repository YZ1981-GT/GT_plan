<script setup lang="ts">
/** F3TabInterestCalc — F3-4 应付票据（带息）利息测算表（对齐源表结构） */
import { ref, watch, toRef, inject, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  useF3InterestCalc, F3_INTEREST_NOTE_TYPES,
  type F3NoteOcrFields, type F3InterestCalcRow,
} from '../composables/useF3InterestCalc'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import F3SheetAttachments from './F3SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)
function onImported() { reloadWorkpaperData?.() }

function fmt(v: number): string {
  return v === 0 ? '-' : v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

const {
  rows, totals, filledCount, abnormalCount, auditConclusion,
  addRow, removeRow, updateCell, rowClassName, mergeOcrFields,
  pendingAccrualRows, pushInterestAccrualToAdjustment,
} = useF3InterestCalc({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

// ─── 审计说明（AI section: interest-note） ───
const NOTE_KEY = 'F3-4-note'
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
    rowCount: filledCount.value,
    abnormalCount: abnormalCount.value,
    totalFaceValue: totals.value.faceValue,
    totalPayableInterest: totals.value.payableInterest,
    totalBookInterest: totals.value.bookInterest,
    totalVariance: totals.value.variance,
    varianceRows: rows.value
      .filter((r) => Math.abs(r.variance) > 100)
      .map((r) => ({ noteType: r.noteType, ticketNo: r.ticketNo, faceValue: r.faceValue, variance: r.variance })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('interest-note', auditNote.value, aiContext(), 'AI 生成 · 利息测算审计说明')
  if (text) saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm('interest-conclusion', auditConclusion.value, aiContext(), 'AI 生成 · 利息测算审计结论')
  if (text) auditConclusion.value = text
}

async function handleGenerateAccrual() {
  if (props.isReadonly) return
  const targets = pendingAccrualRows.value
  if (targets.length === 0) {
    ElMessage.info('无差异超阈值的带息票据，无需补提/冲回')
    return
  }
  const preview = targets
    .map((r) => `· ${r.noteType || '带息票据'}${r.ticketNo ? `(${r.ticketNo})` : ''} 差异 ${fmt(r.variance)}（${r.variance > 0 ? '补提' : '冲回'}）`)
    .join('\n')
  try {
    await ElMessageBox.confirm(
      `将对差异超阈值的带息应付票据生成补提/冲回利息分录（AJE，幂等替换本表历史生成项）：\n补提 借 财务费用(6603) / 贷 应付利息(2231)；冲回反向。\n\n${preview}\n\n是否写入 F3-3 调整分录汇总？`,
      '生成补提利息分录',
      { confirmButtonText: '生成并写入 F3-3', cancelButtonText: '取消', type: 'warning' },
    )
    const { count, total } = pushInterestAccrualToAdjustment()
    ElMessage.success(`已生成 ${count} 笔利息调整（差异合计 ${fmt(total)}）并写入 F3-3`)
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('生成失败')
  }
}

const ocrLoadingId = ref<string | null>(null)

async function handleNoteOcr(rowId: string, file: File) {
  if (props.isReadonly) return
  ocrLoadingId.value = rowId
  const formData = new FormData()
  formData.append('file', file)

  try {
    const res = await http.post(
      `/api/workpapers/${props.wpId}/f3/contract-ocr`,
      formData,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = res.data?.data ?? res.data
    const { extracted_fields: fields, confidence } = data

    const fieldSummary = Object.entries(fields || {})
      .filter(([, v]) => v != null && v !== '' && v !== 0)
      .map(([k, v]) => `${k}: ${v}`)
      .join('\n')

    await ElMessageBox.confirm(
      `OCR识别完成（置信度: ${((confidence || 0) * 100).toFixed(0)}%）\n\n提取字段：\n${fieldSummary || '（未提取到有效信息）'}\n\n是否将提取结果填入当前行？`,
      '票据OCR提取结果',
      { confirmButtonText: '填入（覆盖空字段）', cancelButtonText: '取消', type: 'info' },
    )
    mergeOcrFields(rowId, fields as F3NoteOcrFields, false)
    ElMessage.success('OCR结果已填入')
  } catch (err: any) {
    if (err !== 'cancel' && err?.message !== 'cancel') {
      ElMessage.warning('OCR识别失败，请手动填写')
    }
  } finally {
    ocrLoadingId.value = null
  }
}

/** 表内合计行（对齐源表"合 计"行：票面金额/应计利息/账面已计利息/差异） */
function summaryMethod({ columns }: { columns: any[]; data: F3InterestCalcRow[] }) {
  const sums: string[] = []
  columns.forEach((col, idx) => {
    if (idx === 0) { sums[idx] = '合 计'; return }
    if (col.property === 'faceValue') { sums[idx] = fmt(totals.value.faceValue); return }
    if (col.property === 'payableInterest') { sums[idx] = fmt(totals.value.payableInterest); return }
    if (col.property === 'bookInterest') { sums[idx] = fmt(totals.value.bookInterest); return }
    if (col.property === 'variance') { sums[idx] = fmt(totals.value.variance); return }
    sums[idx] = ''
  })
  return sums
}
</script>

<template>
  <div class="f3-tab-interest">
    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 从带息应付票据台账逐笔登记票据类别、票据号、出票日、到期日、票面金额与票面利率；期限（天）自动按 到期日−出票日 计算。</p>
        <p>2. 灰底虚线列为公式列：应计利息 = 票面金额 × 票面利率% × 期限 / 360（未填日期时按 票面金额 × 票面利率% 直接测算）；差异 = 应计利息 − 账面已计利息。</p>
        <p>3. 差异绝对值 &gt; 100 元橙色高亮，重大差异应提请调整（补提或冲回应付利息），并在"说明"列记录原因。</p>
        <p>4. 📎 列可上传票据影像 OCR 识别，自动填充票据号、面值、利率、出票日/到期日等字段。</p>
        <p>5. 票面金额合计应与 F3-2 明细表中带息票据合计核对一致。</p>
      </div>
    </details>

    <!-- 审计目标 / 审计过程（对齐源表） -->
    <el-alert
      type="info"
      :closable="false"
      title="审计目标：应付票据以恰当的金额包括在财务报表中，与之相关的计价或分摊调整已恰当记录，相关披露已得到恰当计量和描述。"
      description="审计过程：复核带息应付票据利息是否足额计提，其会计处理是否正确。"
      class="objective-alert"
    />

    <!-- 工具栏 -->
    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加票据</el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || pendingAccrualRows.length === 0"
          @click="handleGenerateAccrual"
        >⇄ 生成补提利息分录（{{ pendingAccrualRows.length }}）</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-4" :disabled="isReadonly" @imported="onImported" />
        <span class="chip-wrap"><GtIndexChip value="wp:F3-4" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F3-3" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">已填 {{ filledCount }} 笔</el-tag>
        <el-tag v-if="abnormalCount > 0" size="small" type="warning">差异 {{ abnormalCount }} 笔</el-tag>
      </div>
    </div>

    <F3SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F3-4" label="利息测算附件" />

    <el-table
      :data="rows" border size="small" :row-class-name="rowClassName"
      show-summary :summary-method="summaryMethod" style="width: 100%"
    >
      <el-table-column prop="seq" label="序号" width="50" align="center" />
      <el-table-column prop="noteType" label="票据类别" min-width="130">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.noteType" size="small" clearable placeholder="选择" style="width:100%"
            @change="(v: string) => updateCell(row.rowId, 'noteType', v ?? '')">
            <el-option v-for="t in F3_INTEREST_NOTE_TYPES" :key="t" :label="t" :value="t" />
          </el-select>
          <span v-else>{{ row.noteType }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="ticketNo" label="票据号" min-width="130">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.ticketNo" size="small" @change="(v: string) => updateCell(row.rowId, 'ticketNo', v)" /><span v-else>{{ row.ticketNo }}</span></template>
      </el-table-column>
      <el-table-column prop="issueDate" label="出票日" width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.issueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%"
            @update:model-value="(v: string | null) => updateCell(row.rowId, 'issueDate', v ?? '')" />
          <span v-else>{{ row.issueDate }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="dueDate" label="到期日" width="130">
        <template #default="{ row }">
          <el-date-picker v-if="!isReadonly" :model-value="row.dueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%"
            @update:model-value="(v: string | null) => updateCell(row.rowId, 'dueDate', v ?? '')" />
          <span v-else>{{ row.dueDate }}</span>
        </template>
      </el-table-column>
      <el-table-column prop="termDays" label="期限(天)" width="80" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula-cell" title="期限 = 到期日 − 出票日">{{ row.termDays || '-' }}</span></template>
      </el-table-column>
      <el-table-column prop="faceValue" label="票面金额" width="120" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'faceValue', v ?? 0)" /><span v-else>{{ fmt(row.faceValue) }}</span></template>
      </el-table-column>
      <el-table-column prop="interestRate" label="票面利率%" width="90" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.interestRate" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'interestRate', v ?? 0)" /><span v-else>{{ row.interestRate }}</span></template>
      </el-table-column>
      <el-table-column prop="payableInterest" label="应计利息" width="110" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula-cell" title="应计利息 = 票面金额 × 票面利率% × 期限 / 360">{{ fmt(row.payableInterest) }}</span></template>
      </el-table-column>
      <el-table-column prop="bookInterest" label="账面已计利息" width="120" align="right">
        <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.bookInterest" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'bookInterest', v ?? 0)" /><span v-else>{{ fmt(row.bookInterest) }}</span></template>
      </el-table-column>
      <el-table-column prop="variance" label="差异" width="100" align="right" class-name="auto-calc-col">
        <template #default="{ row }"><span class="formula-cell" title="差异 = 应计利息 − 账面已计利息">{{ fmt(row.variance) }}</span></template>
      </el-table-column>
      <el-table-column prop="note" label="说明" min-width="150">
        <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.note" size="small" @change="(v: string) => updateCell(row.rowId, 'note', v)" /><span v-else>{{ row.note }}</span></template>
      </el-table-column>
      <el-table-column label="📎" width="45" align="center">
        <template #default="{ row }">
          <el-upload :show-file-list="false" :auto-upload="false" :disabled="isReadonly || ocrLoadingId === row.rowId"
            @change="(f: any) => handleNoteOcr(row.rowId, f.raw || f)">
            <el-button link size="small" :loading="ocrLoadingId === row.rowId">📎</el-button>
          </el-upload>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="55"><template #default="{ row }"><el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删</el-button></template></el-table-column>
    </el-table>

    <!-- 三、审计说明 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">三、审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiNote">🤖 AI 生成说明</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-4-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        v-model="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：利息测算方法与依据、测算数与账面已计利息差异及原因、拟调整事项。"
        @change="(v: string) => saveAuditNote(v)"
      />
    </el-card>

    <!-- 四、审计结论 -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">四、审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion">🤖 AI 生成结论</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-4-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 3, maxRows: 8 }" :disabled="isReadonly" placeholder="请输入利息测算审计结论（如：带息应付票据利息已足额计提，会计处理正确）..." />
    </el-card>
  </div>
</template>

<style scoped>
.f3-tab-interest {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-interest :deep(.el-table) {
  --el-table-font-size: var(--wp-font-size, 13px);
  font-size: var(--wp-font-size, 13px);
}
.f3-tab-interest :deep(.el-table .cell) {
  font-size: var(--wp-font-size, 13px) !important;
}
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
.tab-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
}
.toolbar-left {
  display: flex;
  gap: 8px;
  align-items: center;
}
.toolbar-right {
  display: flex;
  gap: 6px;
  align-items: center;
}
.chip-wrap { display: inline-flex; align-items: center; }
.formula-cell {
  background: #f5f7fa;
  border-bottom: 1px dashed #c0c4cc;
  cursor: help;
}
:deep(.auto-calc-col) {
  background-color: #f5f7fa !important;
}
:deep(.variance-warn td) {
  background: #fdf6ec !important;
}
:deep(.el-table__footer .cell) {
  font-weight: 600;
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
.opinion-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
}
.opinion-title {
  font-size: 14px;
  font-weight: 600;
  color: #303133;
}
.opinion-actions {
  display: flex;
  gap: 6px;
}
</style>
