<!--
  DocumentRecognizeDialog.vue — 原始凭证 LLM 识别 + 逐份确认
  
  Spec: wp-evidence-collection Task 3.3
  复用 V3 Req6 AiContent 确认流（wrap_ai_output_with_log 门禁）
-->
<template>
  <el-dialog
    v-model="visible"
    title="原始凭证识别"
    width="800px"
    :close-on-click-modal="false"
    append-to-body
  >
    <!-- 步骤 1: 选择凭证类型 + 上传 -->
    <div v-if="step === 'upload'" class="doc-recognize-upload">
      <el-form label-width="100px">
        <el-form-item label="凭证类型">
          <el-select v-model="docType" placeholder="选择凭证类型">
            <el-option value="voucher" label="记账凭证" />
            <el-option value="invoice" label="发票" />
            <el-option value="warehouse" label="出入库单" />
            <el-option value="bank_receipt" label="银行回单" />
          </el-select>
        </el-form-item>
        <el-form-item label="附件">
          <div class="doc-recognize-files">
            已选择 {{ attachmentIds.length }} 个附件
          </div>
        </el-form-item>
      </el-form>
    </div>

    <!-- 步骤 2: 识别结果确认 -->
    <div v-else-if="step === 'confirm'" class="doc-recognize-confirm">
      <el-alert
        v-if="results.length > 0"
        :type="allConfirmed ? 'success' : 'info'"
        :closable="false"
        class="doc-recognize-status"
      >
        已确认 {{ confirmedCount }} / {{ results.length }}
      </el-alert>

      <div v-for="(item, idx) in results" :key="idx" class="doc-recognize-item">
        <div class="doc-recognize-item__header">
          <span>{{ item.filename || `附件 ${idx + 1}` }}</span>
          <el-tag :type="item.confirmed ? 'success' : 'warning'" size="small">
            {{ item.confirmed ? '已确认' : '待确认' }}
          </el-tag>
        </div>
        <el-descriptions :column="2" border size="small">
          <el-descriptions-item
            v-for="(value, key) in item.fields"
            :key="key"
            :label="fieldLabel(key as string)"
          >
            <el-input
              v-model="item.fields[key as string]"
              size="small"
              :placeholder="key as string"
              :disabled="item.confirmed"
            />
          </el-descriptions-item>
        </el-descriptions>
        <div class="doc-recognize-item__actions">
          <el-button
            v-if="!item.confirmed"
            type="primary"
            size="small"
            @click="confirmItem(idx)"
          >
            确认
          </el-button>
          <el-button
            v-if="!item.confirmed"
            size="small"
            @click="rejectItem(idx)"
          >
            驳回
          </el-button>
        </div>
      </div>
    </div>

    <template #footer>
      <div class="dialog-footer">
        <el-button @click="visible = false">取消</el-button>
        <el-button
          v-if="step === 'upload'"
          type="primary"
          :loading="recognizing"
          :disabled="attachmentIds.length === 0"
          @click="startRecognize"
        >
          开始识别
        </el-button>
        <el-button
          v-if="step === 'confirm' && allConfirmed"
          type="primary"
          @click="submitAll"
        >
          提交全部
        </el-button>
      </div>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { apiProxy } from '@/services/apiProxy'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  projectId: string
  wpId: string
  attachmentIds: string[]
}>()

const emit = defineEmits<{
  (e: 'confirmed', data: any): void
}>()

const visible = defineModel<boolean>('modelValue', { default: false })
const step = ref<'upload' | 'confirm'>('upload')
const docType = ref('voucher')
const recognizing = ref(false)
const results = ref<any[]>([])

const confirmedCount = computed(() => results.value.filter(r => r.confirmed).length)
const allConfirmed = computed(() =>
  results.value.length > 0 && results.value.every(r => r.confirmed || r.rejected)
)

const FIELD_LABELS: Record<string, string> = {
  voucher_no: '凭证号', voucher_date: '凭证日期',
  debit_amount: '借方金额', credit_amount: '贷方金额',
  summary: '摘要', account_name: '科目名称',
  preparer: '制单人', reviewer: '审核人',
  invoice_no: '发票号码', invoice_code: '发票代码',
  invoice_date: '开票日期', seller_name: '销方',
  buyer_name: '购方', amount: '金额',
  tax_amount: '税额', total_amount: '价税合计',
  tax_rate: '税率', invoice_type: '发票类型',
  doc_no: '单据编号', doc_date: '日期',
  direction: '方向', item_name: '物品名称',
  quantity: '数量', unit_price: '单价',
  warehouse_name: '仓库', handler: '经手人',
  receipt_no: '回单编号', transaction_date: '交易日期',
  payer_name: '付款方', payee_name: '收款方',
  payer_account: '付款账号', payee_account: '收款账号',
  bank_name: '开户行', purpose: '用途',
}

function fieldLabel(key: string) {
  return FIELD_LABELS[key] || key
}

async function startRecognize() {
  recognizing.value = true
  try {
    const data = await apiProxy.post(
      `/projects/${props.projectId}/document-recognize`,
      {
        attachments: props.attachmentIds.map(id => ({
          attachment_id: id,
          doc_type: docType.value,
        })),
      }
    )
    results.value = (data.results || []).map((r: any) => ({
      ...r,
      confirmed: false,
      rejected: false,
      filename: r.filename || r.attachment_id,
    }))
    step.value = 'confirm'
  } catch (e: any) {
    ElMessage.error(e?.message || '识别失败')
  } finally {
    recognizing.value = false
  }
}

function confirmItem(idx: number) {
  results.value[idx].confirmed = true
}

function rejectItem(idx: number) {
  results.value[idx].rejected = true
}

async function submitAll() {
  const confirmed = results.value.filter(r => r.confirmed)
  emit('confirmed', { doc_type: docType.value, items: confirmed })
  ElMessage.success(`已确认 ${confirmed.length} 份凭证`)
  visible.value = false
}
</script>

<style scoped>
.doc-recognize-upload {
  padding: 16px 0;
}
.doc-recognize-status {
  margin-bottom: 12px;
}
.doc-recognize-item {
  border: 1px solid var(--el-border-color-lighter);
  border-radius: 4px;
  padding: 12px;
  margin-bottom: 12px;
}
.doc-recognize-item__header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 8px;
  font-weight: 500;
}
.doc-recognize-item__actions {
  margin-top: 8px;
  text-align: right;
}
</style>
