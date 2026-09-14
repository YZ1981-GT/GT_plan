<script setup lang="ts">
/**
 * E1CreditOcrConfirmDialog — 征信 OCR/AI 识别结果确认后回填
 */
import { reactive, watch } from 'vue'

export interface CreditOcrFields {
  borrowerName: string
  creditCode: string
  loanCardCode: string
  reportDate: string
  inquireDate: string
  hasOverview: string
  hasFinance: string
  hasCreditInfo: string
  outstandingNote: string
  queryResult: string
  attachmentIndex: string
}

const props = defineProps<{
  modelValue: boolean
  fields: Partial<CreditOcrFields>
  confidence?: number
  ocrPreview?: string
  fileName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [CreditOcrFields]
  cancel: []
}>()

const draft = reactive<CreditOcrFields>({
  borrowerName: '',
  creditCode: '',
  loanCardCode: '',
  reportDate: '',
  inquireDate: '',
  hasOverview: '',
  hasFinance: '',
  hasCreditInfo: '',
  outstandingNote: '',
  queryResult: '',
  attachmentIndex: '',
})

watch(
  () => [props.modelValue, props.fields] as const,
  ([visible, fields]) => {
    if (!visible) return
    Object.assign(draft, {
      borrowerName: '',
      creditCode: '',
      loanCardCode: '',
      reportDate: '',
      inquireDate: '',
      hasOverview: '',
      hasFinance: '',
      hasCreditInfo: '',
      outstandingNote: '',
      queryResult: '',
      attachmentIndex: '',
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
    title="征信报告 OCR/AI 识别确认"
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
      <span class="hint">请核对下方字段，确认后回填到 E1-18 查询记录</span>
    </div>

    <el-form label-width="120px" size="small" class="ocr-form">
      <el-form-item label="借款人名称">
        <el-input v-model="draft.borrowerName" />
      </el-form-item>
      <el-form-item label="征信人代码">
        <el-input v-model="draft.creditCode" />
      </el-form-item>
      <el-form-item label="贷款卡编码">
        <el-input v-model="draft.loanCardCode" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="报告日期">
            <el-input v-model="draft.reportDate" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="查询日期">
            <el-input v-model="draft.inquireDate" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="打印件范围">
        <el-checkbox v-model="draft.hasOverview" true-value="Y" false-value="">征信人概况</el-checkbox>
        <el-checkbox v-model="draft.hasFinance" true-value="Y" false-value="">财务信息</el-checkbox>
        <el-checkbox v-model="draft.hasCreditInfo" true-value="Y" false-value="">信贷信息</el-checkbox>
      </el-form-item>
      <el-form-item label="未结清勾稽说明">
        <el-input v-model="draft.outstandingNote" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
      </el-form-item>
      <el-form-item label="查询结果">
        <el-input v-model="draft.queryResult" type="textarea" :autosize="{ minRows: 2, maxRows: 5 }" />
      </el-form-item>
      <el-form-item label="附件索引号">
        <el-input v-model="draft.attachmentIndex" placeholder="如 E1-18-1" />
      </el-form-item>
    </el-form>

    <details v-if="ocrPreview" class="ocr-preview">
      <summary>OCR 原文预览</summary>
      <pre>{{ ocrPreview.length > 2000 ? `${ocrPreview.slice(0, 2000)}…` : ocrPreview }}</pre>
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
  font-size: 12px;
  color: #909399;
}
.ocr-form {
  margin-top: 4px;
}
.ocr-preview {
  margin-top: 8px;
  font-size: 12px;
  color: #606266;
}
.ocr-preview pre {
  max-height: 180px;
  overflow: auto;
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
