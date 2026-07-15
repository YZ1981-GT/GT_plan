<script setup lang="ts">
/**
 * E1CutoffOcrConfirmDialog — 截止测试凭证附件 OCR/AI 识别结果确认后回填
 */
import { reactive, watch } from 'vue'

export interface CutoffOcrFields {
  voucherNo: string
  date: string
  businessContent: string
  debitAmount: number | string
  creditAmount: number | string
  counterparty: string
  receiptDate: string
  otherDocDate: string
  note: string
}

const props = defineProps<{
  modelValue: boolean
  fields: Partial<CutoffOcrFields>
  confidence?: number
  ocrPreview?: string
  fileName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [CutoffOcrFields]
  cancel: []
}>()

const draft = reactive<CutoffOcrFields>({
  voucherNo: '',
  date: '',
  businessContent: '',
  debitAmount: 0,
  creditAmount: 0,
  counterparty: '',
  receiptDate: '',
  otherDocDate: '',
  note: '',
})

watch(
  () => [props.modelValue, props.fields] as const,
  ([visible, fields]) => {
    if (!visible) return
    Object.assign(draft, {
      voucherNo: '',
      date: '',
      businessContent: '',
      debitAmount: 0,
      creditAmount: 0,
      counterparty: '',
      receiptDate: '',
      otherDocDate: '',
      note: '',
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
    title="截止凭证 OCR/AI 识别确认"
    width="680px"
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
      <span class="hint">请核对字段后回填；「收付款/其他原始凭单日期」影响跨期判定</span>
    </div>

    <el-form label-width="140px" size="small" class="ocr-form">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="凭证号">
            <el-input v-model="draft.voucherNo" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="入账日期">
            <el-input v-model="draft.date" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="业务内容">
        <el-input v-model="draft.businessContent" type="textarea" :autosize="{ minRows: 2 }" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="借方金额">
            <el-input v-model="draft.debitAmount" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="贷方金额">
            <el-input v-model="draft.creditAmount" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="对方账户">
        <el-input v-model="draft.counterparty" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="收付款凭单日期">
            <el-input v-model="draft.receiptDate" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="其他原始凭单日期">
            <el-input v-model="draft.otherDocDate" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="备注">
        <el-input v-model="draft.note" />
      </el-form-item>
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
.ocr-meta {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  align-items: center;
  margin-bottom: 12px;
}
.hint {
  color: #909399;
  font-size: 12px;
}
.ocr-form {
  margin-top: 4px;
}
.ocr-preview {
  margin-top: 12px;
  border-left: 3px solid #909399;
  background: #f5f7fa;
  padding: 8px 12px;
  border-radius: 4px;
}
.ocr-preview summary {
  cursor: pointer;
  color: #606266;
  font-size: 12px;
}
.ocr-preview pre {
  margin: 8px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 12px;
  max-height: 160px;
  overflow: auto;
}
</style>
