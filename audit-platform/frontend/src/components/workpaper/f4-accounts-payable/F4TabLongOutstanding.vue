<script setup lang="ts">
/**
 * F4TabLongOutstanding — F4-5 账龄1年以上应付账款检查表
 * 支持F4-2同步、逐行附件、OCR识别确认回填、导入导出及AI说明/结论。
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import {
  F4_YES_NO_OPTIONS,
  useF4LongOutstanding,
  type F4LongOutstandingOcrFields,
  type LongOutstandingRow,
} from '../composables/useF4LongOutstanding'
import { useF4AiGenerate } from '../composables/useF4AiGenerate'
import F4ImportExportToolbar from './F4ImportExportToolbar.vue'
import F4SheetAttachments from './F4SheetAttachments.vue'
import ItemAttachment from '../ItemAttachment.vue'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const reloadWorkpaperData = inject<(() => void) | null>('reloadWorkpaperData', null)
const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

const {
  rows,
  summary,
  filledCount,
  pendingSyncCount,
  agingOptions,
  auditNote,
  auditConclusion,
  loadRows,
  syncFromDetail,
  addRow,
  removeRow,
  updateCell,
  mergeOcrFields,
  saveAuditNote,
  saveAuditConclusion,
  rowClassName,
} = useF4LongOutstanding({
  wpId: toRef(props, 'wpId') as Ref<string>,
  projectId: toRef(props, 'projectId') as Ref<string>,
  allResponses: toRef(props, 'allResponses') as Ref<Map<string, any>>,
  isReadonly: toRef(props, 'isReadonly') as Ref<boolean>,
})

const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF4AiGenerate(
  toRef(props, 'wpId') as Ref<string>,
)

async function onImported(): Promise<void> {
  if (reloadWorkpaperData) await reloadWorkpaperData()
  loadRows()
}

function fmtAmount(value: number): string {
  if (Math.abs(value) < 0.005) return '-'
  const formatted = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${formatted})` : formatted
}

function handleSync(): void {
  const added = syncFromDetail()
  if (added > 0) ElMessage.success(`已从F4-2同步 ${added} 个账龄1年以上的债权人`)
  else ElMessage.info('F4-2中符合条件的债权人均已同步')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F4-5',
    count: summary.value.count,
    totals: {
      closingBalance: summary.value.closingTotal,
      auditedAmount: summary.value.auditedTotal,
      adjustmentAmount: summary.value.adjustmentTotal,
      unableToPayAmount: summary.value.unableToPayAmount,
      litigationAmount: summary.value.litigationAmount,
    },
    missingEvidenceCount: summary.value.missingEvidenceCount,
    highRiskCount: summary.value.highRiskCount,
    rows: rows.value
      .filter((row) => row.creditor || row.closingBalance)
      .map((row) => ({
        creditor: row.creditor,
        closingBalance: row.closingBalance,
        aging: row.aging,
        businessDescription: row.businessDescription,
        unsettledReason: row.unsettledReason,
        unableToPay: row.unableToPay,
        litigation: row.litigation,
        paymentPlan: row.paymentPlan,
        auditedAmount: row.auditedAmount,
        supportingEvidence: row.supportingEvidence,
        riskFlags: row.riskFlags,
      })),
  }
}

async function generateAuditNote(): Promise<void> {
  const generated = await generateAndConfirm(
    'long-outstanding-note',
    auditNote.value,
    aiContext(),
    'AI 生成 · F4-5审计说明',
  )
  if (generated) saveAuditNote(generated)
}

async function generateAuditConclusion(): Promise<void> {
  const generated = await generateAndConfirm(
    'long-outstanding-conclusion',
    auditConclusion.value,
    aiContext(),
    'AI 生成 · F4-5审计结论',
  )
  if (generated) saveAuditConclusion(generated)
}

// ─── 逐行附件 + OCR确认回填 ─────────────────────────────────────────────────
const evidenceDialogVisible = ref(false)
const activeRowId = ref('')
const evidenceUploading = ref(false)
const attachmentRefresh = ref(0)
const activeRow = computed(() =>
  rows.value.find((row) => row.rowId === activeRowId.value) || null,
)

function openEvidenceDialog(row: LongOutstandingRow): void {
  activeRowId.value = row.rowId
  evidenceDialogVisible.value = true
}

const OCR_FIELD_LABELS: Record<keyof F4LongOutstandingOcrFields, string> = {
  creditor: '债权人名称',
  closingBalance: '期末余额',
  aging: '账龄',
  businessDescription: '经济业务说明',
  unsettledReason: '未偿还/未结转原因',
  unableToPay: '是否无法支付',
  litigation: '是否诉讼',
  paymentPlan: '支付计划',
  auditedAmount: '审定金额',
  supportingEvidence: '支持性证据',
  remark: '备注',
}

async function uploadAndRecognize(file: File): Promise<void> {
  const row = activeRow.value
  if (!row || props.isReadonly) return
  evidenceUploading.value = true
  let attachmentSaved = false
  try {
    // 先保存关联附件；即使OCR失败，审计证据仍保留在当前债权人名下。
    const attachmentForm = new FormData()
    attachmentForm.append('file', file)
    attachmentForm.append('attachment_type', 'workpaper_item')
    attachmentForm.append('reference_type', 'workpaper_item')
    const objectId = `${props.wpId}:F4-5:${row.attSlot}`
    attachmentForm.append('title', objectId)
    attachmentForm.append('document_type', objectId)
    await api.post(`/api/projects/${props.projectId}/attachments/upload`, attachmentForm, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    attachmentSaved = true
    attachmentRefresh.value += 1

    const ocrForm = new FormData()
    ocrForm.append('file', file)
    ocrForm.append('document_type', 'long-outstanding')
    const response = await http.post(
      `/api/workpapers/${props.wpId}/f4/contract-ocr`,
      ocrForm,
      {
        headers: { 'Content-Type': 'multipart/form-data' },
        _silent: true,
      } as any,
    )
    const data = response.data?.data ?? response.data
    const fields = (data?.extracted_fields || {}) as F4LongOutstandingOcrFields
    const recognized = Object.entries(fields)
      .filter(([, value]) => value !== '' && value !== 0 && value != null)
      .map(([key, value]) =>
        `${OCR_FIELD_LABELS[key as keyof F4LongOutstandingOcrFields] || key}：${value}`,
      )
      .join('\n')

    await ElMessageBox.confirm(
      `附件已关联到“${row.creditor || '当前行'}”。\n`
      + `OCR置信度：${Math.round(Number(data?.confidence || 0) * 100)}%\n\n`
      + `${recognized || '未识别到可回填字段'}\n\n`
      + '是否将识别结果回填到当前行的空字段？',
      '长期挂账支持性证据识别',
      {
        confirmButtonText: '确认回填',
        cancelButtonText: '仅保留附件',
        type: 'info',
      },
    )
    mergeOcrFields(row.rowId, fields, false)
    ElMessage.success('附件已关联，识别结果已回填')
  } catch (error: any) {
    if (error === 'cancel' || error?.message === 'cancel') {
      ElMessage.success('附件已关联，未执行字段回填')
    } else if (attachmentSaved) {
      ElMessage.warning('附件已保存，但OCR识别失败，请手工填写或重新识别')
    } else {
      ElMessage.error('附件上传失败')
    }
  } finally {
    evidenceUploading.value = false
  }
}
</script>

<template>
  <div class="f4-tab-long-outstanding">
    <details class="guidance-details">
      <summary>📋 编制思路、证据要求与联动逻辑</summary>
      <div class="guidance-content">
        <p>1. 本表检查账龄1年以上的应付账款，逐项核实债权人、余额、经济业务实质、长期未偿还或未结转原因，以及是否存在无法支付或诉讼情形。</p>
        <p>2. 点击“从F4-2同步”自动提取审定账龄中1～2年、2～3年及3年以上的实际债权人；余额、账龄和款项性质持续联动F4-2，检查结论字段在本表补充。</p>
        <p>3. 支持性证据应包括合同、对账单、付款计划、银行回单、管理层说明、诉讼文书或律师函等；每行附件独立关联。</p>
        <p>4. 上传PDF或图片后先保存附件，再进行OCR；识别结果必须经用户确认，只回填当前行的空字段，不覆盖已复核内容。</p>
        <p>5. 对无法支付、涉及诉讼、3年以上、缺少原因/支付计划/支持性证据或存在审计调整的项目进行风险提示。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：验证账龄1年以上应付账款真实存在、余额准确，长期未偿还原因及支付安排合理，诉讼或无法支付事项已获得充分证据并作出恰当审计处理。"
    />

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button size="small" type="primary" plain :disabled="isReadonly" @click="handleSync">
          ⇄ 从F4-2同步
          <el-badge v-if="pendingSyncCount" :value="pendingSyncCount" class="sync-badge" />
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 手工添加</el-button>
      </div>
      <div class="toolbar-right">
        <F4ImportExportToolbar
          :wp-id="wpId"
          :project-id="projectId"
          sheet="F4-5"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <GtIndexChip value="wp:F4-2" :context-project-id="projectId" />
        <el-tag size="small" type="info">已填 {{ filledCount }} 项</el-tag>
        <el-tag v-if="summary.highRiskCount" size="small" type="danger">
          高风险 {{ summary.highRiskCount }} 项
        </el-tag>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-5-long-outstanding')">复核</el-button>
      </div>
    </div>

    <F4SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F4-5" label="长期挂账附件" />

    <div class="table-scroll-wrap">
      <el-table
        :data="rows"
        border
        size="small"
        class="long-table"
        :row-class-name="rowClassName"
        max-height="600"
      >
        <el-table-column type="index" label="序号" width="58" fixed="left" />
        <el-table-column label="债权人名称" width="170" fixed="left">
          <template #default="{ row }">
            <el-tooltip v-if="row.linked" content="联动F4-2债权人">
              <span class="linked-value">🔗 {{ row.creditor }}</span>
            </el-tooltip>
            <el-input
              v-else-if="!isReadonly"
              :model-value="row.creditor"
              size="small"
              @change="(value: string) => updateCell(row.rowId, 'creditor', value)"
            />
            <span v-else>{{ row.creditor }}</span>
          </template>
        </el-table-column>
        <el-table-column label="期末余额" width="135" align="right">
          <template #default="{ row }">
            <span v-if="row.linked" class="linked-value">{{ fmtAmount(row.closingBalance) }}</span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.closingBalance"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'closingBalance', value ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.closingBalance) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="账龄" width="145">
          <template #default="{ row }">
            <span v-if="row.linked" class="linked-value">{{ row.aging }}</span>
            <el-select
              v-else-if="!isReadonly"
              :model-value="row.aging"
              size="small"
              filterable
              allow-create
              clearable
              @change="(value: string) => updateCell(row.rowId, 'aging', value)"
            >
              <el-option v-for="option in agingOptions" :key="option" :label="option" :value="option" />
            </el-select>
            <span v-else>{{ row.aging }}</span>
          </template>
        </el-table-column>
        <el-table-column label="经济业务说明" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.businessDescription"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              :placeholder="row.linked ? '默认取F4-2款项性质，可补充业务背景' : '款项性质及经济业务内容'"
              @change="(value: string) => updateCell(row.rowId, 'businessDescription', value)"
            />
            <span v-else>{{ row.businessDescription }}</span>
          </template>
        </el-table-column>
        <el-table-column label="未偿还或未结转的原因" min-width="210">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.unsettledReason"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 4 }"
              placeholder="据实说明长期挂账原因"
              @change="(value: string) => updateCell(row.rowId, 'unsettledReason', value)"
            />
            <span v-else>{{ row.unsettledReason }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否无法支付" width="115" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.unableToPay"
              size="small"
              @change="(value: string) => updateCell(row.rowId, 'unableToPay', value)"
            >
              <el-option v-for="option in F4_YES_NO_OPTIONS" :key="option" :label="option" :value="option" />
            </el-select>
            <span v-else>{{ row.unableToPay }}</span>
          </template>
        </el-table-column>
        <el-table-column label="是否诉讼" width="100" align="center">
          <template #default="{ row }">
            <el-select
              v-if="!isReadonly"
              :model-value="row.litigation"
              size="small"
              @change="(value: string) => updateCell(row.rowId, 'litigation', value)"
            >
              <el-option v-for="option in F4_YES_NO_OPTIONS" :key="option" :label="option" :value="option" />
            </el-select>
            <span v-else>{{ row.litigation }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支付计划" min-width="180">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.paymentPlan"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="预计支付日期、金额或分期安排"
              @change="(value: string) => updateCell(row.rowId, 'paymentPlan', value)"
            />
            <span v-else>{{ row.paymentPlan }}</span>
          </template>
        </el-table-column>
        <el-table-column label="审定金额" width="135" align="right">
          <template #default="{ row }">
            <span v-if="row.linked" class="linked-value">{{ fmtAmount(row.auditedAmount) }}</span>
            <el-input-number
              v-else-if="!isReadonly"
              :model-value="row.auditedAmount"
              :controls="false"
              size="small"
              style="width:100%"
              @change="(value: number | undefined) => updateCell(row.rowId, 'auditedAmount', value ?? 0)"
            />
            <span v-else>{{ fmtAmount(row.auditedAmount) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="支持性证据" min-width="190">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.supportingEvidence"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              placeholder="证据名称、编号及关键结论"
              @change="(value: string) => updateCell(row.rowId, 'supportingEvidence', value)"
            />
            <span v-else>{{ row.supportingEvidence }}</span>
          </template>
        </el-table-column>
        <el-table-column label="备注" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="!isReadonly"
              :model-value="row.remark"
              type="textarea"
              :autosize="{ minRows: 1, maxRows: 3 }"
              @change="(value: string) => updateCell(row.rowId, 'remark', value)"
            />
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>
        <el-table-column label="风险提示" width="170">
          <template #default="{ row }">
            <div class="risk-flags">
              <el-tag
                v-for="flag in row.riskFlags"
                :key="flag"
                size="small"
                :type="row.highlightLevel === 'danger' ? 'danger' : 'warning'"
              >{{ flag }}</el-tag>
              <span v-if="!row.riskFlags.length">—</span>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="附件/操作" width="145" fixed="right">
          <template #default="{ row }">
            <el-button link type="primary" size="small" @click="openEvidenceDialog(row)">附件识别</el-button>
            <el-button link type="danger" size="small" :disabled="isReadonly" @click="removeRow(row.rowId)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <div class="summary-strip">
      <span>期末余额 {{ fmtAmount(summary.closingTotal) }}</span>
      <span>审定金额 {{ fmtAmount(summary.auditedTotal) }}</span>
      <span>调整 {{ fmtAmount(summary.adjustmentTotal) }}</span>
      <span>无法支付 {{ fmtAmount(summary.unableToPayAmount) }}</span>
      <span>涉及诉讼 {{ fmtAmount(summary.litigationAmount) }}</span>
      <span :class="{ danger: summary.missingEvidenceCount }">
        证据待补 {{ summary.missingEvidenceCount }} 项
      </span>
    </div>

    <el-card shadow="never" class="text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">三、审计说明</div>
            <div class="card-hint">说明长期挂账原因、支付计划、诉讼/无法支付判断、证据获取及调整情况。</div>
          </div>
          <div class="card-actions">
            <el-button
              size="small"
              type="primary"
              plain
              :disabled="isReadonly || !aiAvailable"
              :loading="aiLoading"
              @click="generateAuditNote"
            >🤖 AI生成说明</el-button>
            <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-5-note')">💬</el-button>
          </div>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5, maxRows: 12 }"
        :disabled="isReadonly"
        placeholder="概述1年以上款项构成、主要挂账原因、支付安排、诉讼或无法支付事项、支持性证据及审计调整。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="text-card">
      <template #header>
        <div class="card-header">
          <div>
            <div class="card-title">四、审计结论</div>
            <div class="card-hint">评价长期挂账应付款真实性、计价、负债终止确认和列报是否恰当。</div>
          </div>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateAuditConclusion"
          >🤖 AI生成结论</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3, maxRows: 8 }"
        :disabled="isReadonly"
        placeholder="综合证据评价长期挂账余额是否真实准确，无法支付、诉讼及调整事项是否处理恰当。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <el-dialog v-model="evidenceDialogVisible" title="F4-5 支持性证据附件与OCR识别" width="760px">
      <template v-if="activeRow">
        <el-descriptions :column="2" border size="small" class="evidence-summary">
          <el-descriptions-item label="债权人">{{ activeRow.creditor || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="账龄">{{ activeRow.aging || '未填写' }}</el-descriptions-item>
          <el-descriptions-item label="期末余额">{{ fmtAmount(activeRow.closingBalance) }}</el-descriptions-item>
          <el-descriptions-item label="审定金额">{{ fmtAmount(activeRow.auditedAmount) }}</el-descriptions-item>
        </el-descriptions>
        <el-alert
          type="info"
          :closable="false"
          title="建议上传：采购/工程合同、往来对账单、付款计划、银行回单、管理层说明、诉讼文书、律师函等。"
        />
        <section class="evidence-section">
          <h4>上传并识别回填</h4>
          <el-upload
            :show-file-list="false"
            :auto-upload="false"
            accept=".pdf,.png,.jpg,.jpeg"
            :disabled="isReadonly || evidenceUploading"
            @change="(upload: any) => uploadAndRecognize(upload.raw || upload)"
          >
            <el-button type="primary" :loading="evidenceUploading" :disabled="isReadonly">
              上传附件并OCR识别
            </el-button>
          </el-upload>
          <span class="upload-hint">附件先关联到当前行；确认后只回填空字段，不覆盖已复核信息。</span>
        </section>
        <section class="evidence-section">
          <h4>已关联附件 / 补充上传</h4>
          <ItemAttachment
            :key="`${activeRow.attSlot}-${attachmentRefresh}`"
            :project-id="projectId"
            :wp-id="wpId"
            sheet-key="F4-5"
            :item-index="activeRow.attSlot"
            accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
          />
        </section>
      </template>
      <template #footer>
        <el-button @click="evidenceDialogVisible = false">关闭</el-button>
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.f4-tab-long-outstanding { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 8px;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sync-badge { margin-left: 4px; }
.table-scroll-wrap { width: 100%; overflow-x: auto; }
.long-table { min-width: 1900px; }
.long-table :deep(.el-input-number), .long-table :deep(.el-select) { width: 100%; }
.linked-value { color: #7b4ba3; font-weight: 600; }
.risk-flags { display: flex; flex-wrap: wrap; gap: 3px; }
:deep(.long-outstanding-warning td) { background: #fdf6ec !important; }
:deep(.long-outstanding-danger td) { background: #fef0f0 !important; }
.summary-strip {
  display: flex;
  justify-content: flex-end;
  flex-wrap: wrap;
  gap: 10px 24px;
  padding: 9px 12px;
  border: 1px solid #dcdfe6;
  border-top: none;
  background: #f3f5f8;
  font-weight: 700;
}
.summary-strip .danger { color: #d03050; }
.text-card { margin-top: 16px; border-radius: 8px; }
.text-card :deep(.el-card__header) { padding: 11px 14px; background: #fafafa; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 16px; }
.card-title { color: #303133; font-weight: 600; }
.card-hint { margin-top: 3px; color: #909399; font-size: 12px; }
.card-actions { display: flex; gap: 6px; }
.evidence-summary { margin-bottom: 12px; }
.evidence-section { margin-top: 16px; }
.evidence-section h4 { margin: 0 0 8px; color: #303133; }
.upload-hint { display: inline-block; margin-left: 10px; color: #909399; font-size: 12px; }
</style>
