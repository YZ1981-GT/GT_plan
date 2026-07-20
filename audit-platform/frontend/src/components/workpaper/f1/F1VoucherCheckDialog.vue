<template>
  <el-dialog
    :model-value="modelValue"
    :title="dialogTitle"
    width="76%"
    top="4vh"
    destroy-on-close
    append-to-body
    @update:model-value="(value: boolean) => emit('update:modelValue', value)"
  >
    <div v-if="form" class="check-dialog-body">
      <main class="document-groups">
        <el-card shadow="never" class="document-card">
          <template #header>
            <span>① 记账凭证</span>
            <el-upload
              v-if="canOcr"
              :show-file-list="false"
              :auto-upload="false"
              accept=".pdf,.png,.jpg,.jpeg"
              :disabled="isOcrLoading('voucher')"
              @change="(file: any) => runOcr(file?.raw, 'voucher')"
            >
              <el-button link type="primary" size="small" :loading="isOcrLoading('voucher')">
                📎 上传凭证并识别
              </el-button>
            </el-upload>
          </template>
          <div class="field-grid">
            <label>供应商名称<el-input v-model="form.supplierName" size="small" :disabled="readonly" /></label>
            <label>日期<el-input v-model="form.date" size="small" placeholder="YYYY-MM-DD" :disabled="readonly" /></label>
            <label>凭证编号<el-input v-model="form.voucherNo" size="small" :disabled="readonly" /></label>
            <label>业务内容<el-input v-model="form.businessContent" size="small" :disabled="readonly" /></label>
            <label>对方科目<el-input v-model="form.counterAccount" size="small" :disabled="readonly" /></label>
            <label>明细科目<el-input v-model="form.counterDetailAccount" size="small" :disabled="readonly" /></label>
            <label v-if="section === 'debit'">借方金额
              <el-input-number v-model="(form as F1DebitCheckRow).debitAmount" :controls="false" size="small" :disabled="readonly" />
            </label>
            <label v-else>贷方金额
              <el-input-number v-model="(form as F1CreditCheckRow).creditAmount" :controls="false" size="small" :disabled="readonly" />
            </label>
          </div>
        </el-card>

        <template v-if="section === 'debit'">
          <el-card shadow="never" class="document-card">
            <template #header>
              <span>② 付款审批单</span>
              <el-upload
                v-if="canOcr"
                :show-file-list="false"
                :auto-upload="false"
                accept=".pdf,.png,.jpg,.jpeg"
                :disabled="isOcrLoading('approval')"
                @change="(file: any) => runOcr(file?.raw, 'approval')"
              >
                <el-button link type="primary" size="small" :loading="isOcrLoading('approval')">
                  📎 上传审批单并识别
                </el-button>
              </el-upload>
            </template>
            <div class="field-grid">
              <label>日期/编号
                <el-input v-model="(form as F1DebitCheckRow).approvalDateNo" size="small" :disabled="readonly" />
              </label>
              <label>是否经过恰当审批
                <el-select v-model="(form as F1DebitCheckRow).approvalOk" size="small" clearable :disabled="readonly">
                  <el-option v-for="opt in F1_YES_NO_OPTIONS" :key="opt.value" :label="opt.label" :value="opt.value" />
                </el-select>
              </label>
            </div>
          </el-card>

          <el-card shadow="never" class="document-card">
            <template #header>
              <span>③ 银行回单</span>
              <el-upload
                v-if="canOcr"
                :show-file-list="false"
                :auto-upload="false"
                accept=".pdf,.png,.jpg,.jpeg"
                :disabled="isOcrLoading('bank-receipt')"
                @change="(file: any) => runOcr(file?.raw, 'bank-receipt')"
              >
                <el-button link type="primary" size="small" :loading="isOcrLoading('bank-receipt')">
                  📎 上传回单并识别
                </el-button>
              </el-upload>
            </template>
            <div class="field-grid">
              <label>付款信息
                <el-input v-model="(form as F1DebitCheckRow).bankPayment" size="small" :disabled="readonly" />
              </label>
              <label>收款方
                <el-input v-model="(form as F1DebitCheckRow).bankPayee" size="small" :disabled="readonly" />
              </label>
              <label>金额
                <el-input-number v-model="(form as F1DebitCheckRow).bankAmount" :controls="false" size="small" :disabled="readonly" />
              </label>
            </div>
          </el-card>

          <el-card shadow="never" class="document-card">
            <template #header><span>④ 合同 / 订单 / 其他</span></template>
            <div class="field-grid">
              <label>合同名称
                <el-input v-model="(form as F1DebitCheckRow).contractName" size="small" :disabled="readonly" />
              </label>
              <label>合同金额
                <el-input-number v-model="(form as F1DebitCheckRow).contractAmount" :controls="false" size="small" :disabled="readonly" />
              </label>
              <label class="full">其他证据说明
                <el-input v-model="(form as F1DebitCheckRow).receiptDoc" type="textarea" :rows="2" :disabled="readonly" />
              </label>
            </div>
          </el-card>
        </template>

        <template v-else>
          <el-card shadow="never" class="document-card">
            <template #header>
              <span>② 入库单 / 验收单</span>
              <el-upload
                v-if="canOcr"
                :show-file-list="false"
                :auto-upload="false"
                accept=".pdf,.png,.jpg,.jpeg"
                :disabled="isOcrLoading('goods-receipt')"
                @change="(file: any) => runOcr(file?.raw, 'goods-receipt')"
              >
                <el-button link type="primary" size="small" :loading="isOcrLoading('goods-receipt')">
                  📎 上传入库单并识别
                </el-button>
              </el-upload>
            </template>
            <div class="field-grid">
              <label>日期/编号
                <el-input v-model="(form as F1CreditCheckRow).recvDateNo" size="small" :disabled="readonly" />
              </label>
              <label>品名
                <el-input v-model="(form as F1CreditCheckRow).recvItemName" size="small" :disabled="readonly" />
              </label>
              <label>单位
                <el-input v-model="(form as F1CreditCheckRow).recvUnit" size="small" :disabled="readonly" />
              </label>
              <label>数量
                <el-input v-model="(form as F1CreditCheckRow).recvQty" size="small" :disabled="readonly" />
              </label>
            </div>
          </el-card>

          <el-card shadow="never" class="document-card">
            <template #header>
              <span>③ 采购发票</span>
              <el-upload
                v-if="canOcr"
                :show-file-list="false"
                :auto-upload="false"
                accept=".pdf,.png,.jpg,.jpeg"
                :disabled="isOcrLoading('invoice')"
                @change="(file: any) => runOcr(file?.raw, 'invoice')"
              >
                <el-button link type="primary" size="small" :loading="isOcrLoading('invoice')">
                  📎 上传发票并识别
                </el-button>
              </el-upload>
            </template>
            <div class="field-grid">
              <label>日期/编号
                <el-input v-model="(form as F1CreditCheckRow).invoiceDateNo" size="small" :disabled="readonly" />
              </label>
              <label>对手方名称
                <el-input v-model="(form as F1CreditCheckRow).invoiceCounterparty" size="small" :disabled="readonly" />
              </label>
              <label>金额
                <el-input-number v-model="(form as F1CreditCheckRow).invoiceAmount" :controls="false" size="small" :disabled="readonly" />
              </label>
            </div>
          </el-card>
        </template>

        <el-card v-if="projectId && wpId" shadow="never" class="document-card">
          <template #header><span>⑤ 本笔附件（单据影像归档）</span></template>
          <ItemAttachment
            :project-id="projectId"
            :wp-id="wpId"
            :sheet-key="`F1-7-${section}`"
            :item-index="attSlot"
            accept=".pdf,.png,.jpg,.jpeg,.doc,.docx,.xls,.xlsx"
          />
        </el-card>
      </main>

      <aside class="check-side">
        <el-card shadow="never">
          <template #header>
            <div class="side-header">
              <span>实时单据勾稽</span>
              <el-tag size="small" :type="statusMeta.type">{{ statusMeta.label }}</el-tag>
            </div>
          </template>
          <ul class="check-list">
            <li v-for="item in checks" :key="item.key" :class="`status-${item.status}`">
              <span class="check-icon">{{ statusIcon[item.status] }}</span>
              <div>
                <strong>{{ item.label }}</strong>
                <small>{{ item.detail }}</small>
              </div>
            </li>
          </ul>
        </el-card>

        <el-card shadow="never">
          <template #header><span>本笔结论</span></template>
          <label>索引号<el-input v-model="form.indexRef" size="small" :disabled="readonly" /></label>
          <label>是否异常
            <el-select v-model="form.isAbnormal" size="small" clearable :disabled="readonly">
              <el-option
                v-for="opt in F1_ABNORMAL_OPTIONS"
                :key="opt.value || '_empty'"
                :label="opt.label"
                :value="opt.value"
              />
            </el-select>
          </label>
          <label>
            <span class="issue-label">
              异常/检查说明
              <el-button
                link
                type="primary"
                size="small"
                :disabled="readonly || !aiAvailable"
                :loading="aiLoading"
                @click="runIssueAi"
              >AI 生成</el-button>
            </span>
            <el-input v-model="form.remark" type="textarea" :rows="3" :disabled="readonly" />
          </label>
          <el-button type="primary" class="side-save" :disabled="readonly" @click="save">保存本笔</el-button>
        </el-card>
      </aside>
    </div>

    <template #footer>
      <el-button @click="emit('update:modelValue', false)">取消</el-button>
      <el-button type="primary" :disabled="readonly" @click="save">保存本笔</el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
/** F1VoucherCheckDialog — F1-7 逐笔单据核对弹窗（对齐 F4-8） */
import { computed, ref, watch, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'
import {
  evaluateF1Evidence,
  f1EvidenceStatusLabel,
  F1_VOUCHER_SECTION_LABELS,
  F1_YES_NO_OPTIONS,
  F1_ABNORMAL_OPTIONS,
  type F1DebitCheckRow,
  type F1CreditCheckRow,
  type F1VoucherSection,
} from '../composables/useF1ComprehensiveCheck'
import { useF1AiGenerate } from '../composables/useF1AiGenerate'
import ItemAttachment from '../ItemAttachment.vue'

type F1OcrDocumentType = 'voucher' | 'approval' | 'bank-receipt' | 'goods-receipt' | 'invoice'

const props = defineProps<{
  modelValue: boolean
  row: F1DebitCheckRow | F1CreditCheckRow | null
  section: F1VoucherSection
  wpId?: string
  projectId?: string
  readonly?: boolean
}>()

const emit = defineEmits<{
  (event: 'update:modelValue', value: boolean): void
  (event: 'save', section: F1VoucherSection, patch: F1DebitCheckRow | F1CreditCheckRow): void
}>()

const form = ref<F1DebitCheckRow | F1CreditCheckRow | null>(null)
watch(
  () => [props.modelValue, props.row] as const,
  ([visible, row]) => {
    if (visible && row) form.value = { ...row }
  },
  { immediate: true },
)

const dialogTitle = computed(() =>
  `逐笔单据核对 · ${F1_VOUCHER_SECTION_LABELS[props.section]} · ${form.value?.voucherNo || form.value?.supplierName || '未命名凭证'}`,
)
const checks = computed(() => (form.value ? evaluateF1Evidence(props.section, form.value) : []))
const statusMeta = computed(() => f1EvidenceStatusLabel(checks.value))
const statusIcon: Record<'ok' | 'missing' | 'mismatch', string> = {
  ok: '✓',
  missing: '!',
  mismatch: '✕',
}

const canOcr = computed(() => !!props.wpId && !props.readonly)
const ocrLoadingType = ref<F1OcrDocumentType | null>(null)
const { aiAvailable, loading: aiLoading, generateAndConfirm } = useF1AiGenerate(
  computed(() => props.wpId || '') as Ref<string>,
)

const attSlot = computed(() => {
  const id = form.value?.rowId || '0'
  let h = 0
  for (let i = 0; i < id.length; i++) h = (h * 31 + id.charCodeAt(i)) | 0
  return (Math.abs(h) % 9000) + 100
})

function isOcrLoading(documentType: F1OcrDocumentType): boolean {
  return ocrLoadingType.value === documentType
}

async function runOcr(file: File | undefined, documentType: F1OcrDocumentType): Promise<void> {
  if (!file || !form.value || !props.wpId) return
  ocrLoadingType.value = documentType
  try {
    const formData = new FormData()
    formData.append('file', file)
    formData.append('document_type', documentType)
    const res = await http.post(`/api/workpapers/${props.wpId}/f4/contract-ocr`, formData, {
      headers: { 'Content-Type': 'multipart/form-data' },
      _silent: true,
    } as any)
    const data = res.data?.data ?? res.data
    const fields = (data?.extracted_fields ?? {}) as Record<string, unknown>
    const confidence = Number(data?.confidence ?? 0)
    const summary = Object.entries(fields)
      .filter(([, value]) => value != null && value !== '' && value !== 0)
      .map(([key, value]) => `${key}: ${value}`)
      .join('\n')

    await ElMessageBox.confirm(
      `OCR 置信度 ${(confidence * 100).toFixed(0)}%${confidence < 0.8 ? '（建议人工核对）' : ''}\n\n${summary || '未提取到有效字段'}`,
      'OCR 提取结果 · 确认后填入本单据区域',
      {
        confirmButtonText: '确认回填本单据',
        cancelButtonText: '取消',
        type: confidence < 0.8 ? 'warning' : 'info',
      },
    )
    applyOcrFields(documentType, fields)
    ElMessage.success('OCR 结果已填入对应单据区域，可继续二次编辑')
  } catch (error: any) {
    if (error !== 'cancel' && error?.message !== 'cancel') {
      ElMessage.warning('OCR 识别失败，请手动填写')
    }
  } finally {
    ocrLoadingType.value = null
  }
}

function text(value: unknown): string {
  return value == null ? '' : String(value)
}

function numeric(value: unknown): number {
  const result = typeof value === 'number' ? value : Number.parseFloat(String(value ?? '0'))
  return Number.isFinite(result) ? result : 0
}

function applyOcrFields(documentType: F1OcrDocumentType, fields: Record<string, unknown>): void {
  const row = form.value
  if (!row) return
  if (documentType === 'voucher') {
    if (fields.supplierName) row.supplierName = text(fields.supplierName)
    if (fields.voucherDate || fields.date) row.date = text(fields.voucherDate || fields.date)
    if (fields.voucherNo) row.voucherNo = text(fields.voucherNo)
    if (fields.businessContent) row.businessContent = text(fields.businessContent)
    if (fields.counterAccount) row.counterAccount = text(fields.counterAccount)
    if (fields.detailAccount) row.counterDetailAccount = text(fields.detailAccount)
    const amt = numeric(fields.amount)
    if (amt) {
      if (props.section === 'debit') (row as F1DebitCheckRow).debitAmount = amt
      else (row as F1CreditCheckRow).creditAmount = amt
    }
  } else if (documentType === 'approval' && props.section === 'debit') {
    const d = row as F1DebitCheckRow
    if (fields.approvalDateNo) d.approvalDateNo = text(fields.approvalDateNo)
    if (fields.approvalProper) {
      const v = text(fields.approvalProper)
      d.approvalOk = v === '是' || v === 'Y' ? 'Y' : v === '否' || v === 'N' ? 'N' : v
    }
  } else if (documentType === 'bank-receipt' && props.section === 'debit') {
    const d = row as F1DebitCheckRow
    if (fields.bankReceiptDate) d.bankPayment = text(fields.bankReceiptDate)
    if (fields.bankPayee) d.bankPayee = text(fields.bankPayee)
    if (numeric(fields.bankAmount)) d.bankAmount = numeric(fields.bankAmount)
  } else if (documentType === 'goods-receipt' && props.section !== 'debit') {
    const c = row as F1CreditCheckRow
    if (fields.receiptDateNo) c.recvDateNo = text(fields.receiptDateNo)
    if (fields.receiptProduct) c.recvItemName = text(fields.receiptProduct)
    if (fields.receiptUnit) c.recvUnit = text(fields.receiptUnit)
    if (fields.receiptQty != null) c.recvQty = text(fields.receiptQty)
  } else if (documentType === 'invoice' && props.section !== 'debit') {
    const c = row as F1CreditCheckRow
    if (fields.invoiceDateNo) c.invoiceDateNo = text(fields.invoiceDateNo)
    if (fields.invoiceCounterparty) c.invoiceCounterparty = text(fields.invoiceCounterparty)
    if (numeric(fields.invoiceAmount)) c.invoiceAmount = numeric(fields.invoiceAmount)
  }
}

async function runIssueAi(): Promise<void> {
  if (!form.value) return
  const row = form.value
  const generated = await generateAndConfirm(
    'voucher-check-issue',
    row.remark || '',
    {
      sheet: 'F1-7',
      section: F1_VOUCHER_SECTION_LABELS[props.section],
      supplierName: row.supplierName,
      date: row.date,
      voucherNo: row.voucherNo,
      businessContent: row.businessContent,
      isAbnormal: row.isAbnormal,
      evidenceChecks: checks.value.map(item => ({
        document: item.label,
        status: item.status,
        detail: item.detail,
      })),
    },
    'AI 生成 · 本笔异常/检查说明',
  )
  if (generated && form.value) form.value.remark = generated
}

function save(): void {
  if (!form.value) return
  emit('save', props.section, { ...form.value })
  emit('update:modelValue', false)
}
</script>

<style scoped>
.check-dialog-body {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 310px;
  gap: 14px;
  height: 66vh;
  overflow: hidden;
}
.document-groups {
  overflow-y: auto;
  padding-right: 4px;
  display: flex;
  flex-direction: column;
  gap: 10px;
}
.check-side {
  display: flex;
  flex-direction: column;
  gap: 10px;
  overflow-y: auto;
  padding-right: 2px;
}
.document-groups > .el-card,
.check-side > .el-card { flex-shrink: 0; }
.issue-label { display: flex; align-items: center; justify-content: space-between; }
.side-save { width: 100%; margin-top: 4px; }
.document-card :deep(.el-card__header) {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 9px 12px;
  font-weight: 600;
}
.document-card :deep(.el-card__body) { padding: 10px 12px; }
.field-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 9px 12px; }
label {
  display: flex;
  flex-direction: column;
  gap: 4px;
  margin-bottom: 9px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
}
.field-grid label { margin-bottom: 0; }
.field-grid .full { grid-column: 1 / -1; }
.field-grid :deep(.el-input-number),
.field-grid :deep(.el-select),
.check-side :deep(.el-select) { width: 100%; }
.side-header { display: flex; align-items: center; justify-content: space-between; }
.check-list {
  list-style: none;
  margin: 0;
  padding: 0;
  display: flex;
  flex-direction: column;
  gap: 8px;
}
.check-list li {
  display: flex;
  gap: 8px;
  padding: 8px;
  border-radius: 4px;
  background: #f5f7fa;
}
.check-list strong,
.check-list small { display: block; }
.check-list small { margin-top: 2px; color: #909399; line-height: 1.35; }
.check-icon { width: 18px; font-weight: 700; text-align: center; }
.status-ok .check-icon { color: #67c23a; }
.status-missing .check-icon { color: #e6a23c; }
.status-mismatch .check-icon { color: #f56c6c; }
@media (max-width: 1000px) {
  .check-dialog-body {
    grid-template-columns: 1fr;
    height: auto;
    max-height: 66vh;
    overflow-y: auto;
  }
  .document-groups, .check-side { overflow: visible; }
}
</style>
