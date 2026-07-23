<script setup lang="ts">
/** F3TabOverdueCheck — F3-5 逾期未付票据检查表 */
import { computed, inject, ref, toRef, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import {
  F3_OVERDUE_NOTE_TYPES,
  F3_YES_NO_OPTIONS,
  useF3OverdueCheck,
  type F3OverdueNoteRow,
  type F3OverdueOcrFields,
} from '../composables/useF3OverdueCheck'
import { useF3AiGenerate } from '../composables/useF3AiGenerate'
import F3ImportExportToolbar from './F3ImportExportToolbar.vue'
import F3SheetAttachments from './F3SheetAttachments.vue'
import GtIndexChip from '../GtIndexChip.vue'
import ItemAttachment from '../ItemAttachment.vue'

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
  rows, summary, filledCount, auditConclusion, addRow, removeRow, updateCell,
  mergeOcrFields, rowClassName,
  pendingReclassRows, reclassPreview, pushReclassToAdjustment,
} = useF3OverdueCheck({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF3AiGenerate(toRef(props, 'wpId') as Ref<string>)

const NOTE_KEY = 'F3-5-note'
const auditNote = ref('')
function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  const item = { item_id: NOTE_KEY, conclusion: null, remark: val }
  props.allResponses.set(NOTE_KEY, item)
  window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
}
watch(() => props.allResponses.get(NOTE_KEY)?.remark, (v) => {
  if (typeof v === 'string') auditNote.value = v
}, { immediate: true })

function aiContext() {
  return {
    ticketCount: summary.value.count,
    totalFaceValue: summary.value.totalAmount,
    postPaymentAmount: summary.value.postPaymentAmount,
    unpaidAmount: summary.value.unpaidAmount,
    collateralAmount: summary.value.collateralAmount,
    highRiskCount: summary.value.highRisk,
    adjustedCount: summary.value.adjusted,
    riskTickets: rows.value.filter((row) => row.riskFlags.length).map((row) => ({
      ticketNo: row.ticketNo,
      noteType: row.noteType,
      dueDate: row.dueDate,
      overdueDays: row.overdueDays,
      unpaidAmount: row.unpaidAmount,
      isAdjusted: row.isAdjusted,
      riskFlags: row.riskFlags,
    })),
  }
}

async function generateAiNote() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'overdue-note', auditNote.value, aiContext(), 'AI 生成 · 逾期票据审计说明',
  )
  if (text) saveAuditNote(text)
}

async function generateAiConclusion() {
  if (props.isReadonly) return
  const text = await generateAndConfirm(
    'overdue-evaluation', auditConclusion.value, aiContext(), 'AI 生成 · 逾期票据审计结论',
  )
  if (text) auditConclusion.value = text
}

const evidenceDialogVisible = ref(false)
const activeRowId = ref('')
const evidenceUploading = ref(false)
const attachmentRefresh = ref(0)
const activeRow = computed(() => rows.value.find((row) => row.rowId === activeRowId.value) || null)

function openEvidenceDialog(row: F3OverdueNoteRow) {
  activeRowId.value = row.rowId
  evidenceDialogVisible.value = true
}

async function uploadAndRecognize(file: File) {
  const row = activeRow.value
  if (!row || props.isReadonly) return
  evidenceUploading.value = true
  try {
    // 同一文件先保存为逐票关联附件，再送OCR识别，避免附件与识别结果脱节。
    const attachmentForm = new FormData()
    attachmentForm.append('file', file)
    attachmentForm.append('attachment_type', 'workpaper_item')
    attachmentForm.append('reference_type', 'workpaper_item')
    const objectId = `${props.wpId}:F3-5:${row.attSlot}`
    attachmentForm.append('title', objectId)
    attachmentForm.append('document_type', objectId)
    await api.post(`/api/projects/${props.projectId}/attachments/upload`, attachmentForm, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    attachmentRefresh.value += 1

    const ocrForm = new FormData()
    ocrForm.append('file', file)
    ocrForm.append('document_type', 'overdue-note')
    const res = await http.post(`/api/workpapers/${props.wpId}/f3/contract-ocr`, ocrForm, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    const data = res.data?.data ?? res.data
    const fields = (data?.extracted_fields || {}) as F3OverdueOcrFields
    const summaryText = Object.entries(fields)
      .filter(([, value]) => value !== '' && value !== 0 && value != null)
      .map(([key, value]) => `${key}: ${value}`)
      .join('\n')
    await ElMessageBox.confirm(
      `附件已关联。OCR置信度：${Math.round(Number(data?.confidence || 0) * 100)}%\n\n${summaryText || '未识别到可回填字段'}\n\n是否将识别结果回填到当前票据的空字段？`,
      '逾期票据附件识别',
      { confirmButtonText: '确认回填', cancelButtonText: '仅保留附件', type: 'info' },
    )
    mergeOcrFields(row.rowId, fields, false)
    ElMessage.success('附件已关联，识别结果已回填')
  } catch (error: any) {
    if (error === 'cancel' || error?.message === 'cancel') {
      ElMessage.success('附件已关联，未执行字段回填')
    } else {
      ElMessage.warning('附件已尝试保存，但识别失败，请检查附件列表并手工填写')
    }
  } finally {
    evidenceUploading.value = false
  }
}

async function handleGenerateReclass() {
  if (props.isReadonly) return
  const targets = reclassPreview.value
  if (targets.length === 0) {
    ElMessage.info('无逾期未调整票据，或金额为0，无需生成重分类分录')
    return
  }
  const preview = targets
    .map((t) => `· ${t.noteType || '票据'}${t.ticketNo ? `(${t.ticketNo})` : ''} ${fmt(t.amount)} → ${t.targetName}(${t.targetCode})`)
    .join('\n')
  try {
    await ElMessageBox.confirm(
      `将按源模板规则生成重分类分录（RJE，幂等替换本表历史生成项）：\n逾期银行承兑汇票→短期借款(2001)，逾期商业承兑汇票→应付账款(2202)。\n\n${preview}\n\n借：应付票据(2201) / 贷：目标科目。是否写入 F3-3 调整分录汇总？`,
      '生成逾期重分类分录',
      { confirmButtonText: '生成并写入 F3-3', cancelButtonText: '取消', type: 'warning' },
    )
    const { count, total } = pushReclassToAdjustment()
    ElMessage.success(`已生成 ${count} 笔重分类（合计 ${fmt(total)}）并写入 F3-3`)
  } catch (e: any) {
    if (e !== 'cancel' && e?.message !== 'cancel') ElMessage.warning('生成失败')
  }
}

function summaryMethod({ columns }: { columns: any[] }) {
  return columns.map((column, index) => {
    if (index === 0) return '合计'
    if (column.property === 'faceValue') return fmt(summary.value.totalAmount)
    if (column.property === 'postPaymentAmount') return fmt(summary.value.postPaymentAmount)
    if (column.property === 'collateralAmount') return fmt(summary.value.collateralAmount)
    return ''
  })
}
</script>

<template>
  <div class="f3-tab-overdue">
    <details class="guidance-details">
      <summary>📋 编制提示与核查逻辑</summary>
      <div class="guidance-content">
        <p>1. 从F3-2明细表、应付票据备查簿及征信资料筛出截止日已到期但尚未兑付的票据，逐笔登记票据类别、号码及出票人/承兑人/收款人。</p>
        <p>2. 期限自动按“到期日－出票日”计算；系统同时提示当前逾期天数和期后尚未支付金额。期后支付应取得银行回单、兑付凭证并与本表逐笔关联。</p>
        <p>3. 检查合同或票据条款中的追索权、罚息、加速到期及交叉违约条件，判断是否需要转入应付账款/短期借款、补提利息或确认预计负债。</p>
        <p>4. 对抵押担保逐项登记物品和金额，核对权属及披露；逾期是否引发诉讼，应取得诉状、律师函或和解协议。</p>
        <p>5. 综合未付规模、逾期时长、诉讼及抵押情况，评价逾期未付票据对信用风险和持续经营能力的影响。</p>
      </div>
    </details>

    <el-alert
      type="warning"
      :closable="false"
      title="编制主线：逾期票据识别 → 期后支付核验 → 借款/违约条件分析 → 会计调整判断 → 抵押与诉讼证据 → 持续经营评价"
      class="objective-alert"
    />

    <div class="tab-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addRow">+ 添加逾期票据</el-button>
        <el-button
          size="small"
          type="warning"
          plain
          :disabled="isReadonly || pendingReclassRows.length === 0"
          @click="handleGenerateReclass"
        >⇄ 生成逾期重分类分录（{{ pendingReclassRows.length }}）</el-button>
      </div>
      <div class="toolbar-right">
        <F3ImportExportToolbar :wp-id="wpId" :project-id="projectId" sheet="F3-5" :disabled="isReadonly" @imported="onImported" />
        <span class="chip-wrap"><GtIndexChip value="wp:F3-5" :context-project-id="projectId" /></span>
        <span class="chip-wrap"><GtIndexChip value="wp:F3-3" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">已填 {{ filledCount }} 笔</el-tag>
        <el-tag v-if="summary.highRisk" size="small" type="danger">高风险 {{ summary.highRisk }} 笔</el-tag>
      </div>
    </div>

    <F3SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F3-5" label="逾期检查附件" />

    <div class="table-scroll-wrap">
      <el-table
        :data="rows" border size="small" :row-class-name="rowClassName"
        show-summary :summary-method="summaryMethod" class="overdue-table"
      >
        <el-table-column prop="seq" label="序号" width="50" fixed="left" align="center" />
        <el-table-column prop="noteType" label="票据类别" width="135" fixed="left">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.noteType" size="small" clearable @change="(v: string) => updateCell(row.rowId, 'noteType', v)">
              <el-option v-for="item in F3_OVERDUE_NOTE_TYPES" :key="item" :label="item" :value="item" />
            </el-select>
            <span v-else>{{ row.noteType }}</span>
          </template>
        </el-table-column>
        <el-table-column prop="ticketNo" label="票据号" width="145" fixed="left">
          <template #default="{ row }">
            <el-input v-if="!isReadonly" :model-value="row.ticketNo" size="small" @change="(v: string) => updateCell(row.rowId, 'ticketNo', v)" />
            <span v-else>{{ row.ticketNo }}</span>
            <div v-if="row.overdueDays" class="cell-hint danger">逾期 {{ row.overdueDays }} 天</div>
          </template>
        </el-table-column>
        <el-table-column label="票据关系人" align="center">
          <el-table-column prop="drawer" label="出票人" width="140">
            <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.drawer" size="small" @change="(v: string) => updateCell(row.rowId, 'drawer', v)" /><span v-else>{{ row.drawer }}</span></template>
          </el-table-column>
          <el-table-column prop="acceptor" label="承兑人" width="140">
            <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.acceptor" size="small" @change="(v: string) => updateCell(row.rowId, 'acceptor', v)" /><span v-else>{{ row.acceptor }}</span></template>
          </el-table-column>
          <el-table-column prop="payee" label="收款人" width="140">
            <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.payee" size="small" @change="(v: string) => updateCell(row.rowId, 'payee', v)" /><span v-else>{{ row.payee }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="票据期限" align="center">
          <el-table-column prop="issueDate" label="出票日" width="130">
            <template #default="{ row }"><el-date-picker v-if="!isReadonly" :model-value="row.issueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" @update:model-value="(v: string | null) => updateCell(row.rowId, 'issueDate', v ?? '')" /><span v-else>{{ row.issueDate }}</span></template>
          </el-table-column>
          <el-table-column prop="dueDate" label="到期日" width="130">
            <template #default="{ row }"><el-date-picker v-if="!isReadonly" :model-value="row.dueDate" type="date" value-format="YYYY-MM-DD" size="small" style="width:100%" @update:model-value="(v: string | null) => updateCell(row.rowId, 'dueDate', v ?? '')" /><span v-else>{{ row.dueDate }}</span></template>
          </el-table-column>
          <el-table-column prop="termDays" label="期限(天)" width="80" align="right" class-name="auto-calc-col">
            <template #default="{ row }"><span class="formula-cell">{{ row.termDays || '-' }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column prop="interestRate" label="票面利率%" width="100" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.interestRate" :controls="false" size="small" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowId, 'interestRate', v ?? 0)" /><span v-else>{{ row.interestRate || '-' }}</span></template>
        </el-table-column>
        <el-table-column prop="faceValue" label="票面金额" width="120" align="right">
          <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.faceValue" :controls="false" size="small" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowId, 'faceValue', v ?? 0)" /><span v-else>{{ fmt(row.faceValue) }}</span></template>
        </el-table-column>
        <el-table-column prop="postPaymentAmount" label="期后支付金额" width="130" align="right">
          <template #default="{ row }">
            <el-input-number v-if="!isReadonly" :model-value="row.postPaymentAmount" :controls="false" size="small" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowId, 'postPaymentAmount', v ?? 0)" />
            <span v-else>{{ fmt(row.postPaymentAmount) }}</span>
            <div v-if="row.unpaidAmount" class="cell-hint">尚未支付 {{ fmt(row.unpaidAmount) }}</div>
          </template>
        </el-table-column>
        <el-table-column prop="loanConditions" label="借款条件" width="190">
          <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.loanConditions" type="textarea" :autosize="{ minRows: 1, maxRows: 3 }" @change="(v: string) => updateCell(row.rowId, 'loanConditions', v)" /><span v-else>{{ row.loanConditions }}</span></template>
        </el-table-column>
        <el-table-column prop="isAdjusted" label="是否调整" width="105">
          <template #default="{ row }">
            <el-select v-if="!isReadonly" :model-value="row.isAdjusted" size="small" clearable @change="(v: string) => updateCell(row.rowId, 'isAdjusted', v)">
              <el-option v-for="item in F3_YES_NO_OPTIONS" :key="item" :label="item" :value="item" />
            </el-select>
            <span v-else>{{ row.isAdjusted }}</span>
          </template>
        </el-table-column>
        <el-table-column label="抵押情况" align="center">
          <el-table-column prop="collateralName" label="物品名称" width="140">
            <template #default="{ row }"><el-input v-if="!isReadonly" :model-value="row.collateralName" size="small" @change="(v: string) => updateCell(row.rowId, 'collateralName', v)" /><span v-else>{{ row.collateralName }}</span></template>
          </el-table-column>
          <el-table-column prop="collateralAmount" label="金额" width="120" align="right">
            <template #default="{ row }"><el-input-number v-if="!isReadonly" :model-value="row.collateralAmount" :controls="false" size="small" style="width:100%" @change="(v: number | undefined) => updateCell(row.rowId, 'collateralAmount', v ?? 0)" /><span v-else>{{ fmt(row.collateralAmount) }}</span></template>
          </el-table-column>
        </el-table-column>
        <el-table-column label="风险提示" width="170">
          <template #default="{ row }">
            <div class="risk-flags"><el-tag v-for="flag in row.riskFlags" :key="flag" size="small" type="warning">{{ flag }}</el-tag><span v-if="!row.riskFlags.length">—</span></div>
          </template>
        </el-table-column>
        <el-table-column label="附件/操作" width="135" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEvidenceDialog(row)">附件识别</el-button>
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="summary-strip">
      <span>逾期票据 {{ summary.count }} 笔</span>
      <span>票面金额 {{ fmt(summary.totalAmount) }}</span>
      <span>期后已付 {{ fmt(summary.postPaymentAmount) }}</span>
      <span class="danger">尚未支付 {{ fmt(summary.unpaidAmount) }}</span>
      <span>抵押金额 {{ fmt(summary.collateralAmount) }}</span>
      <span>已调整 {{ summary.adjusted }} 笔</span>
    </div>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">1、审计说明</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiNote">🤖 AI 生成说明</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-5-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-alert type="info" :closable="false" class="note-prompt">
        <template #default>
          <div>• 逾期票据是否引发诉讼事项？如已引发，取得诉状、律师函或和解协议并在逐票附件中关联。</div>
          <div>• 分析逾期未付票据对公司持续经营的影响程度。</div>
        </template>
      </el-alert>
      <el-input v-model="auditNote" type="textarea" :autosize="{ minRows: 5, maxRows: 12 }" :disabled="isReadonly"
        placeholder="说明诉讼、期后兑付、违约条款、调整处理、抵押担保及持续经营影响..." @change="saveAuditNote" />
    </el-card>

    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">2、审计结论</span>
          <div class="opinion-actions">
            <el-button size="small" type="primary" plain :disabled="isReadonly || !aiAvailable" :loading="aiLoading" @click="generateAiConclusion">🤖 AI 生成结论</el-button>
            <el-button size="small" @click="openReviewDialog?.('F3-5-conclusion')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input v-model="auditConclusion" type="textarea" :autosize="{ minRows: 4, maxRows: 10 }" :disabled="isReadonly" placeholder="评价逾期票据会计处理、披露、诉讼与持续经营影响..." />
    </el-card>

    <el-dialog v-model="evidenceDialogVisible" width="760px" title="逾期票据附件关联与识别" destroy-on-close>
      <template v-if="activeRow">
        <el-descriptions :column="3" border size="small" class="evidence-summary">
          <el-descriptions-item label="票据号">{{ activeRow.ticketNo || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="到期日">{{ activeRow.dueDate || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="票面金额">{{ fmt(activeRow.faceValue) }}</el-descriptions-item>
        </el-descriptions>
        <el-alert type="info" :closable="false" title="建议上传：票据影像、期后银行回单/兑付凭证、借款或票据合同、诉讼文书、律师函、抵押担保文件。" />
        <section class="evidence-section">
          <h4>上传并识别回填</h4>
          <el-upload :show-file-list="false" :auto-upload="false" accept=".pdf,.png,.jpg,.jpeg" :disabled="isReadonly || evidenceUploading"
            @change="(upload: any) => uploadAndRecognize(upload.raw || upload)">
            <el-button type="primary" :loading="evidenceUploading" :disabled="isReadonly">上传附件并OCR识别</el-button>
          </el-upload>
          <span class="upload-hint">同一文件会自动保存到本票据附件，并在确认后仅回填空字段。</span>
        </section>
        <section class="evidence-section">
          <h4>已关联附件 / 补充上传</h4>
          <ItemAttachment
            :key="`${activeRow.attSlot}-${attachmentRefresh}`"
            :project-id="projectId" :wp-id="wpId" sheet-key="F3-5"
            :item-index="activeRow.attSlot" accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
          />
        </section>
      </template>
      <template #footer><el-button @click="evidenceDialogVisible = false">关闭</el-button></template>
    </el-dialog>
  </div>
</template>

<style scoped>
.f3-tab-overdue { padding: 12px; font-size: var(--wp-font-size, 13px); min-width: 0; }
.f3-tab-overdue :deep(.el-table), .f3-tab-overdue :deep(.el-table .cell) { font-size: var(--wp-font-size, 13px) !important; }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #4b2d77; background: #f5f1fa; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 600; color: #4b2d77; }
.guidance-content { margin-top: 8px; color: #606266; line-height: 1.65; }
.guidance-content p { margin: 3px 0; }
.objective-alert { margin-bottom: 12px; }
.tab-toolbar, .toolbar-left, .toolbar-right, .opinion-header, .opinion-actions { display: flex; align-items: center; }
.tab-toolbar { justify-content: space-between; margin-bottom: 8px; }
.toolbar-left, .toolbar-right, .opinion-actions { gap: 7px; }
.chip-wrap { display: inline-flex; align-items: center; }
.table-scroll-wrap { width: 100%; overflow-x: auto; border-radius: 4px; }
.overdue-table { width: 2320px; }
.formula-cell { display: block; background: #f5f7fa; border-bottom: 1px dashed #c0c4cc; text-align: right; }
:deep(.auto-calc-col) { background: #f5f7fa !important; }
:deep(.risk-high td) { background: #fef0f0 !important; }
:deep(.risk-medium td) { background: #fdf6ec !important; }
:deep(.el-table__footer .cell) { font-weight: 700; }
.cell-hint { margin-top: 3px; font-size: 11px; color: #909399; white-space: nowrap; }
.danger { color: #d03050 !important; }
.risk-flags { display: flex; flex-wrap: wrap; gap: 3px; }
.summary-strip { display: flex; justify-content: flex-end; flex-wrap: wrap; gap: 8px 18px; padding: 9px 12px; background: #f5f1fa; border-radius: 0 0 4px 4px; font-weight: 600; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; }
.opinion-header { justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; }
.note-prompt { margin-bottom: 10px; line-height: 1.7; }
.evidence-summary, .evidence-section { margin-bottom: 16px; }
.evidence-section { padding: 14px; border: 1px solid #e4e7ed; border-radius: 6px; }
.evidence-section h4 { margin: 0 0 10px; color: #4b2d77; }
.upload-hint { margin-left: 10px; color: #909399; font-size: 12px; }
</style>
