<script setup lang="ts">
import WpAmountInput from '../shared/WpAmountInput.vue'
/**
 * F4TabSupplierFinancing — F4-9 供应商融资检查表
 * 按供应商动态分组：插行/删行/从F4-2引用；附件+OCR确认回填；AI说明结论；导入导出。
 */
import { computed, inject, ref, toRef, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import { api } from '@/services/apiProxy'
import {
  F4_FINANCING_STATUS_OPTIONS,
  useF4SupplierFinancing,
  type F4FinancingOcrFields,
  type FinancingDisplayRow,
  type FinancingRow,
} from '../composables/useF4SupplierFinancing'
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
  displayRows,
  summary,
  pendingSyncCount,
  auditNote,
  auditConclusion,
  loadRows,
  addSupplierGroup,
  addRowInGroup,
  removeRow,
  removeSupplierGroup,
  updateCell,
  syncFromDetail,
  mergeOcrFields,
  saveAuditNote,
  saveAuditConclusion,
  rowClassName,
} = useF4SupplierFinancing({
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

function fmt(value: number): string {
  if (Math.abs(value) < 0.005) return '-'
  const formatted = Math.abs(value).toLocaleString('zh-CN', {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  })
  return value < 0 ? `(${formatted})` : formatted
}

function handleSync(): void {
  const added = syncFromDetail()
  if (added > 0) ElMessage.success(`已从F4-2引用 ${added} 个供应商并插入分组`)
  else ElMessage.info('F4-2中的供应商均已存在于本表')
}

function aiContext(): Record<string, unknown> {
  return {
    sheet: 'F4-9',
    summary: summary.value,
    overPurchaseHint: '如果供应商融资金额大于采购金额，重点关注供应商资金流向，是否存在体外资金循环，必要时执行供应商资金穿透检查程序',
    rows: displayRows.value
      .filter((row) => row.kind === 'detail' && row.detail)
      .map((row) => ({
        supplierName: row.detail!.supplierName,
        financingNo: row.detail!.financingNo,
        fundProvider: row.detail!.fundProvider,
        status: row.detail!.status,
        financingAmount: row.detail!.financingAmount,
        purchaseAmount: row.detail!.purchaseAmount,
        difference: row.detail!.difference,
        loanBalance: row.detail!.loanBalance,
        riskFlags: row.detail!.riskFlags,
      })),
  }
}

async function generateAuditNote(): Promise<void> {
  const text = await generateAndConfirm(
    'financing-note',
    auditNote.value,
    aiContext(),
    'AI 生成 · F4-9审计说明',
  )
  if (text) saveAuditNote(text)
}

async function generateAuditConclusion(): Promise<void> {
  const text = await generateAndConfirm(
    'financing-conclusion',
    auditConclusion.value,
    aiContext(),
    'AI 生成 · F4-9审计结论',
  )
  if (text) saveAuditConclusion(text)
}

// ─── 逐行附件 + OCR ───
const evidenceDialogVisible = ref(false)
const activeRowId = ref('')
const evidenceUploading = ref(false)
const attachmentRefresh = ref(0)
const activeDetail = computed(() => {
  const found = displayRows.value.find(
    (row) => row.kind === 'detail' && row.detail?.rowId === activeRowId.value,
  )
  return found?.detail || null
})

function openEvidenceDialog(row: FinancingRow): void {
  activeRowId.value = row.rowId
  evidenceDialogVisible.value = true
}

const OCR_FIELD_LABELS: Record<keyof F4FinancingOcrFields, string> = {
  supplierName: '供应商名称',
  promisedPayer: '承诺付款方',
  financingNo: '融资单号',
  fundProvider: '资金提供方（金融机构）',
  status: '状态',
  financingAmount: '融资金额',
  supplierSignDate: '供应商签收日期',
  disbursementDate: '放款日期',
  transferDate: '转让日期',
  promisedRepayDate: '承诺还款日期',
  actualRepayDate: '实际还款日期',
  purchaseAmount: '本期采购金额',
  loanBalance: '借款余额',
  remark: '备注',
}

async function uploadAndRecognize(file: File): Promise<void> {
  const row = activeDetail.value
  if (!row || props.isReadonly) return
  evidenceUploading.value = true
  let attachmentSaved = false
  try {
    const attachmentForm = new FormData()
    attachmentForm.append('file', file)
    attachmentForm.append('attachment_type', 'workpaper_item')
    attachmentForm.append('reference_type', 'working_paper')
    attachmentForm.append('reference_id', props.wpId)
    const objectId = `${props.wpId}:F4-9:${row.attSlot}`
    attachmentForm.append('title', objectId)
    attachmentForm.append('document_type', objectId)
    const uploadRes = await api.post(`/api/projects/${props.projectId}/attachments/upload`, attachmentForm, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    attachmentSaved = true
    attachmentRefresh.value += 1
    const uploaded = uploadRes?.data?.data ?? uploadRes?.data ?? uploadRes
    const attId = String(uploaded?.id || uploaded?.attachment_id || '')
    if (attId) {
      try {
        await api.post(`/api/attachments/${attId}/associate`, {
          wp_id: props.wpId,
          association_type: 'evidence',
        }, { _silent: true } as any)
      } catch { /* fail-open */ }
    }

    const ocrForm = new FormData()
    ocrForm.append('file', file)
    ocrForm.append('document_type', 'supplier-financing')
    if (attId) ocrForm.append('attachment_id', attId)
    const response = await http.post(
      `/api/workpapers/${props.wpId}/f4/contract-ocr`,
      ocrForm,
      { headers: { 'Content-Type': 'multipart/form-data' }, _silent: true } as any,
    )
    const data = response.data?.data ?? response.data
    const fields = (data?.extracted_fields || {}) as F4FinancingOcrFields
    const recognized = Object.entries(fields)
      .filter(([, value]) => value !== '' && value !== 0 && value != null)
      .map(([key, value]) =>
        `${OCR_FIELD_LABELS[key as keyof F4FinancingOcrFields] || key}：${value}`,
      )
      .join('\n')

    await ElMessageBox.confirm(
      `附件已关联到“${row.supplierName || row.financingNo || '当前融资行'}”。\n`
      + `OCR置信度：${Math.round(Number(data?.confidence || 0) * 100)}%\n\n`
      + `${recognized || '未识别到可回填字段'}\n\n`
      + '是否将识别结果回填到当前行的空字段？（已填字段不覆盖，可二次编辑）',
      '供应商融资单据识别',
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

function isDetail(row: FinancingDisplayRow): row is FinancingDisplayRow & { detail: FinancingRow } {
  return row.kind === 'detail' && !!row.detail
}

function confirmRemoveGroup(groupId: string, name: string): void {
  ElMessageBox.confirm(
    `确认删除供应商「${name || '未命名'}」及其全部融资明细？`,
    '删除供应商分组',
    { type: 'warning', confirmButtonText: '删除', cancelButtonText: '取消' },
  ).then(() => removeSupplierGroup(groupId)).catch(() => undefined)
}
</script>

<template>
  <div class="f4-tab-supplier-financing">
    <details class="guidance-details">
      <summary>📋 编制思路与动态行逻辑</summary>
      <div class="guidance-content">
        <p>1. 审计目标：确认所有应记录的应付账款及相关披露完整；供应商融资汇总/分解恰当，披露相关且可理解。</p>
        <p>2. 审计过程：将供应链融资平台明细与企业台账核对；检查融资金额与采购金额差异，关注虚假采购融资及对金融机构直付供应商款项的账务与披露。</p>
        <p>3. 「供应商1/2…」为动态分组：可新增供应商、在组内插行；也可从 F4-2 明细引用债权人并带入本期贷方作为采购金额参考。</p>
        <p>4. 差异 = 融资金额 − 本期采购金额；若融资金额大于采购金额须关注资金流向及体外循环，必要时穿透检查。</p>
        <p>5. 每笔融资可上传附件并 OCR；确认后仅回填空字段，主表可二次编辑。底部审计说明/结论支持 AI 生成。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：1.所有应记录的应付账款均已记录，相关披露均已包括；2.应付账款汇总/分解恰当，供应商融资相关披露在企业会计准则下相关且可理解。"
    />

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-tag size="small" type="info">供应商 {{ summary.supplierCount }}</el-tag>
        <el-tag size="small">明细 {{ summary.rowCount }} 笔</el-tag>
        <el-tag v-if="summary.overPurchaseCount" size="small" type="danger">
          融资&gt;采购 {{ summary.overPurchaseCount }} 笔
        </el-tag>
        <GtIndexChip value="wp:F4-2" :context-project-id="projectId" />
      </div>
      <div class="toolbar-right">
        <F4ImportExportToolbar
          :wp-id="wpId"
          :project-id="projectId"
          sheet="F4-9"
          :disabled="isReadonly"
          @imported="onImported"
        />
        <el-button size="small" :disabled="isReadonly" @click="handleSync">
          从F4-2引用供应商
          <el-badge v-if="pendingSyncCount" :value="pendingSyncCount" class="sync-badge" />
        </el-button>
        <el-button size="small" type="primary" :disabled="isReadonly" @click="addSupplierGroup()">
          + 新增供应商
        </el-button>
        <el-button
          v-if="openReviewDialog"
          size="small"
          @click="openReviewDialog('f4-9-supplier-financing')"
        >复核</el-button>
      </div>
    </div>

    <F4SheetAttachments :project-id="projectId" :wp-id="wpId" sheet-code="F4-9" label="供应商融资附件" />

    <el-alert
      v-if="summary.overPurchaseCount"
      class="risk-alert"
      type="warning"
      :closable="false"
      show-icon
      title="如果供应商融资金额大于采购金额，重点关注供应商资金流向，是否存在体外资金循环，必要时执行供应商资金穿透检查程序。"
    />

    <div class="table-scroll-wrap">
      <el-table
        :data="displayRows"
        border
        size="small"
        :row-class-name="rowClassName"
        class="financing-table"
      >
        <el-table-column label="供应商名称" min-width="140" fixed="left">
          <template #default="{ row }">
            <template v-if="row.kind === 'subtotal'">小计</template>
            <template v-else-if="row.kind === 'total'">合计</template>
            <el-input
              v-else-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.supplierName"
              size="small"
              placeholder="供应商名称"
              @change="(v: string) => updateCell(row.detail.rowId, 'supplierName', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.supplierName }}</span>
          </template>
        </el-table-column>

        <el-table-column label="承诺付款方" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.promisedPayer"
              size="small"
              @change="(v: string) => updateCell(row.detail.rowId, 'promisedPayer', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.promisedPayer || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="融资单号" min-width="120">
          <template #default="{ row }">
            <el-input
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.financingNo"
              size="small"
              @change="(v: string) => updateCell(row.detail.rowId, 'financingNo', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.financingNo || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="资金提供方（金融机构）" min-width="150">
          <template #default="{ row }">
            <el-input
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.fundProvider"
              size="small"
              @change="(v: string) => updateCell(row.detail.rowId, 'fundProvider', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.fundProvider || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="状态" width="110">
          <template #default="{ row }">
            <el-select
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.status"
              size="small"
              clearable
              filterable
              allow-create
              @change="(v: string) => updateCell(row.detail.rowId, 'status', v)"
            >
              <el-option v-for="opt in F4_FINANCING_STATUS_OPTIONS" :key="opt" :label="opt" :value="opt" />
            </el-select>
            <span v-else-if="isDetail(row)">{{ row.detail.status || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="融资金额" width="120" align="right">
          <template #default="{ row }">
            <WpAmountInput
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.financingAmount"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => updateCell(row.detail.rowId, 'financingAmount', v ?? 0)"
            />
            <span v-else :class="{ 'amt-warn': row.kind !== 'detail' && row.difference > 0 }">
              {{ fmt(row.financingAmount) }}
            </span>
          </template>
        </el-table-column>

        <el-table-column label="供应商签收日期" width="130">
          <template #default="{ row }">
            <el-input
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.supplierSignDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="(v: string) => updateCell(row.detail.rowId, 'supplierSignDate', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.supplierSignDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="放款日期" width="120">
          <template #default="{ row }">
            <el-input
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.disbursementDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="(v: string) => updateCell(row.detail.rowId, 'disbursementDate', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.disbursementDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="转让日期" width="120">
          <template #default="{ row }">
            <el-input
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.transferDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="(v: string) => updateCell(row.detail.rowId, 'transferDate', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.transferDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="承诺还款日期" width="130">
          <template #default="{ row }">
            <el-input
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.promisedRepayDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="(v: string) => updateCell(row.detail.rowId, 'promisedRepayDate', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.promisedRepayDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="实际还款日期" width="130">
          <template #default="{ row }">
            <el-input
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.actualRepayDate"
              size="small"
              placeholder="YYYY-MM-DD"
              @change="(v: string) => updateCell(row.detail.rowId, 'actualRepayDate', v)"
            />
            <span v-else-if="isDetail(row)">{{ row.detail.actualRepayDate || '—' }}</span>
          </template>
        </el-table-column>

        <el-table-column label="本期采购金额" width="120" align="right" class-name="col-formula">
          <template #default="{ row }">
            <WpAmountInput
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.purchaseAmount"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => updateCell(row.detail.rowId, 'purchaseAmount', v ?? 0)"
            />
            <span v-else>{{ fmt(row.purchaseAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="差异" width="110" align="right" class-name="col-formula">
          <template #default="{ row }">
            <span :class="{ 'amt-danger': row.difference > 0 }">{{ fmt(row.difference) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="借款余额" width="120" align="right" class-name="col-formula">
          <template #default="{ row }">
            <WpAmountInput
              v-if="isDetail(row) && !isReadonly"
              :model-value="row.detail.loanBalance"
              size="small"
              style="width:100%"
              @change="(v: number | undefined) => updateCell(row.detail.rowId, 'loanBalance', v ?? 0)"
            />
            <span v-else>{{ fmt(row.loanBalance) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="风险提示" min-width="160">
          <template #default="{ row }">
            <template v-if="isDetail(row) && row.detail.riskFlags.length">
              <el-tag
                v-for="flag in row.detail.riskFlags"
                :key="flag"
                size="small"
                :type="row.detail.highlightLevel === 'danger' ? 'danger' : 'warning'"
                class="risk-tag"
              >{{ flag }}</el-tag>
            </template>
            <span v-else-if="row.kind === 'subtotal' && row.difference > 0" class="amt-danger">
              本组融资大于采购
            </span>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="200" fixed="right">
          <template #default="{ row }">
            <template v-if="isDetail(row)">
              <el-button link type="primary" size="small" @click="openEvidenceDialog(row.detail)">
                附件/OCR
              </el-button>
              <el-button
                link
                type="primary"
                size="small"
                :disabled="isReadonly"
                @click="addRowInGroup(row.groupId)"
              >插行</el-button>
              <el-button
                link
                type="danger"
                size="small"
                :disabled="isReadonly"
                @click="removeRow(row.detail.rowId)"
              >删除</el-button>
            </template>
            <template v-else-if="row.kind === 'subtotal'">
              <el-button
                link
                type="primary"
                size="small"
                :disabled="isReadonly"
                @click="addRowInGroup(row.groupId)"
              >本组加行</el-button>
              <el-button
                link
                type="danger"
                size="small"
                :disabled="isReadonly"
                @click="confirmRemoveGroup(row.groupId, row.supplierName)"
              >删组</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="card-header">
          <span>三、审计说明</span>
          <el-button
            size="small"
            type="primary"
            plain
            :disabled="isReadonly || !aiAvailable"
            :loading="aiLoading"
            @click="generateAuditNote"
          >🤖 AI生成说明</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 4, maxRows: 10 }"
        :disabled="isReadonly"
        placeholder="说明平台明细与台账核对、融资金额与采购差异、虚假采购关注、直付供应商账务及披露检查结果。"
        @change="saveAuditNote"
      />
    </el-card>

    <el-card shadow="never" class="note-card">
      <template #header>
        <div class="card-header">
          <span>四、审计结论</span>
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
        placeholder="评价供应商融资完整性、列报与披露是否恰当，以及是否存在体外循环等重大异常。"
        @change="saveAuditConclusion"
      />
    </el-card>

    <el-dialog
      v-model="evidenceDialogVisible"
      :title="`融资证据 · ${activeDetail?.supplierName || activeDetail?.financingNo || '未命名'}`"
      width="640px"
      destroy-on-close
      append-to-body
    >
      <template v-if="activeDetail">
        <p class="evidence-hint">
          上传融资合同、平台导出明细、银行放款回单等。先关联附件，再 OCR 确认回填空字段。
        </p>
        <el-upload
          v-if="!isReadonly"
          :show-file-list="false"
          :auto-upload="false"
          accept=".pdf,.png,.jpg,.jpeg"
          :disabled="evidenceUploading"
          @change="(file: any) => file?.raw && uploadAndRecognize(file.raw)"
        >
          <el-button type="primary" :loading="evidenceUploading">📎 上传并识别</el-button>
        </el-upload>
        <ItemAttachment
          v-if="projectId && wpId"
          :key="`${activeDetail.attSlot}-${attachmentRefresh}`"
          :project-id="projectId"
          :wp-id="wpId"
          sheet-key="F4-9"
          :item-index="activeDetail.attSlot"
          accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
          class="evidence-attachments"
        />
      </template>
    </el-dialog>
  </div>
</template>

<style scoped>
.f4-tab-supplier-financing { padding: 12px; font-size: var(--wp-font-size, 13px); }
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
.audit-objective, .risk-alert { margin-bottom: 12px; }
.section-toolbar {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 12px;
  margin-bottom: 10px;
  flex-wrap: wrap;
}
.toolbar-left, .toolbar-right { display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
.sync-badge { margin-left: 4px; }
.table-scroll-wrap { width: 100%; overflow-x: auto; margin-bottom: 16px; }
.financing-table { min-width: 1680px; }
.financing-table :deep(.el-input-number) { width: 100%; }
.financing-table :deep(.row-subtotal) { background: #f0f2f5; font-weight: 600; }
.financing-table :deep(.row-total) { background: #e8eef5; font-weight: 700; }
.financing-table :deep(.row-warning) { background: #fdf6ec; }
.financing-table :deep(.row-danger) { background: #fef0f0; }
.financing-table :deep(.col-formula) { background: #f5f0fa; }
.amt-danger { color: #d03050; font-weight: 600; }
.amt-warn { color: #e6a23c; }
.risk-tag { margin: 2px 4px 2px 0; }
.note-card { margin-bottom: 14px; border-radius: 8px; }
.note-card :deep(.el-card__header) { padding: 11px 14px; background: #fafafa; }
.card-header { display: flex; align-items: center; justify-content: space-between; gap: 12px; }
.evidence-hint { margin: 0 0 12px; color: #606266; font-size: 13px; line-height: 1.5; }
.evidence-attachments { margin-top: 14px; }
</style>
