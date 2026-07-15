<script setup lang="ts">
/**
 * E1LargeCheckOcrConfirmDialog — 收支检查回单/审批 OCR 确认回填
 */
import { reactive, watch, computed } from 'vue'

export interface LargeCheckOcrFields {
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  amount: number | string
  receiptDate: string
  receiptParty: string
  receiptAmount: number | string
  approvalDateNo: string
  isProperlyApproved: string
  otherSupportDocs: string
  indexNo: string
}

const props = defineProps<{
  modelValue: boolean
  side: 'debit' | 'credit'
  fields: Partial<LargeCheckOcrFields>
  confidence?: number
  ocrPreview?: string
  fileName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [LargeCheckOcrFields]
  cancel: []
}>()

const draft = reactive<LargeCheckOcrFields>({
  date: '',
  voucherNo: '',
  businessContent: '',
  counterAccount: '',
  amount: 0,
  receiptDate: '',
  receiptParty: '',
  receiptAmount: 0,
  approvalDateNo: '',
  isProperlyApproved: '',
  otherSupportDocs: '',
  indexNo: '',
})

const partyLabel = computed(() => (props.side === 'debit' ? '付款方' : '收款方'))

watch(
  () => [props.modelValue, props.fields] as const,
  ([visible, fields]) => {
    if (!visible) return
    Object.assign(draft, {
      date: '',
      voucherNo: '',
      businessContent: '',
      counterAccount: '',
      amount: 0,
      receiptDate: '',
      receiptParty: '',
      receiptAmount: 0,
      approvalDateNo: '',
      isProperlyApproved: '',
      otherSupportDocs: '',
      indexNo: '',
      ...fields,
    })
  },
  { immediate: true, deep: true },
)

function onConfirm(): void {
  emit('confirm', { ...draft })
  emit('update:modelValue', false)
}
function onCancel(): void {
  emit('cancel')
  emit('update:modelValue', false)
}
</script>

<template>
  <el-dialog
    :model-value="modelValue"
    :title="side === 'debit' ? '借方样本 OCR/AI 识别确认' : '贷方样本 OCR/AI 识别确认'"
    width="720px"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
    @close="onCancel"
  >
    <div class="ocr-meta">
      <el-tag v-if="fileName" size="small" type="info">{{ fileName }}</el-tag>
      <el-tag v-if="confidence != null" size="small" :type="(confidence || 0) >= 0.5 ? 'success' : 'warning'">
        置信度 {{ Math.round((confidence || 0) * 100) }}%
      </el-tag>
      <span class="hint">请核对银行回单字段后回填；金额不符将建议标「异常」</span>
    </div>

    <el-form label-width="120px" size="small">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="凭证编号"><el-input v-model="draft.voucherNo" /></el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="入账日期"><el-input v-model="draft.date" placeholder="YYYY-MM-DD" /></el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="业务内容">
        <el-input v-model="draft.businessContent" type="textarea" :autosize="{ minRows: 2 }" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="对方科目"><el-input v-model="draft.counterAccount" /></el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item :label="side === 'debit' ? '借方金额' : '贷方金额'">
            <el-input v-model="draft.amount" />
          </el-form-item>
        </el-col>
      </el-row>

      <el-divider content-position="left">银行回单</el-divider>
      <el-row :gutter="12">
        <el-col :span="8">
          <el-form-item label="回单日期"><el-input v-model="draft.receiptDate" /></el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item :label="partyLabel"><el-input v-model="draft.receiptParty" /></el-form-item>
        </el-col>
        <el-col :span="8">
          <el-form-item label="回单金额"><el-input v-model="draft.receiptAmount" /></el-form-item>
        </el-col>
      </el-row>

      <template v-if="side === 'credit'">
        <el-divider content-position="left">付款审批单</el-divider>
        <el-row :gutter="12">
          <el-col :span="12">
            <el-form-item label="日期/编号"><el-input v-model="draft.approvalDateNo" /></el-form-item>
          </el-col>
          <el-col :span="12">
            <el-form-item label="恰当审批">
              <el-select v-model="draft.isProperlyApproved" clearable placeholder="请选择" style="width: 100%">
                <el-option label="是" value="是" />
                <el-option label="否" value="否" />
              </el-select>
            </el-form-item>
          </el-col>
        </el-row>
      </template>

      <el-form-item label="其他支持文件"><el-input v-model="draft.otherSupportDocs" /></el-form-item>
      <el-form-item label="索引号"><el-input v-model="draft.indexNo" /></el-form-item>
    </el-form>

    <details v-if="ocrPreview" class="ocr-preview">
      <summary>OCR 原文预览</summary>
      <pre>{{ ocrPreview }}</pre>
    </details>

    <template #footer>
      <el-button @click="onCancel">取消</el-button>
      <el-button type="primary" @click="onConfirm">确认回填</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.ocr-meta { display: flex; flex-wrap: wrap; gap: 8px; align-items: center; margin-bottom: 12px; }
.hint { color: #909399; font-size: 12px; }
.ocr-preview {
  margin-top: 12px; border-left: 3px solid #909399; background: #f5f7fa;
  padding: 8px 12px; border-radius: 4px;
}
.ocr-preview summary { cursor: pointer; font-size: 12px; color: #606266; }
.ocr-preview pre {
  margin: 8px 0 0; white-space: pre-wrap; word-break: break-word;
  font-size: 12px; max-height: 160px; overflow: auto;
}
</style>
