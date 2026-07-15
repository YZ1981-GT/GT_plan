<script setup lang="ts">
/**
 * E1StatementOcrConfirmDialog — 银行对账单/流水 OCR 确认回填
 */
import { reactive, watch } from 'vue'

export interface StatementOcrLine {
  date: string
  summary: string
  counterparty: string
  amount: number
  direction: '收入' | '支出' | ''
}

export interface StatementOcrFields {
  bank: string
  accountNo: string
  periodStart: string
  periodEnd: string
  lines: StatementOcrLine[]
}

const props = defineProps<{
  modelValue: boolean
  fields: Partial<StatementOcrFields>
  confidence?: number
  ocrPreview?: string
  fileName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [StatementOcrFields]
  cancel: []
}>()

function emptyLine(): StatementOcrLine {
  return { date: '', summary: '', counterparty: '', amount: 0, direction: '' }
}

const draft = reactive<StatementOcrFields>({
  bank: '',
  accountNo: '',
  periodStart: '',
  periodEnd: '',
  lines: [],
})

watch(
  () => [props.modelValue, props.fields] as const,
  ([visible, fields]) => {
    if (!visible) return
    draft.bank = fields.bank || ''
    draft.accountNo = fields.accountNo || ''
    draft.periodStart = fields.periodStart || ''
    draft.periodEnd = fields.periodEnd || ''
    draft.lines = Array.isArray(fields.lines) && fields.lines.length
      ? fields.lines.map(r => ({ ...emptyLine(), ...r }))
      : []
  },
  { immediate: true, deep: true },
)

function addRow(): void {
  draft.lines.push(emptyLine())
}

function removeRow(index: number): void {
  draft.lines.splice(index, 1)
}

function onConfirm(): void {
  emit('confirm', {
    bank: draft.bank,
    accountNo: draft.accountNo,
    periodStart: draft.periodStart,
    periodEnd: draft.periodEnd,
    lines: draft.lines
      .map(r => ({ ...r, amount: Number(r.amount) || 0 }))
      .filter(r => r.date || r.amount || r.counterparty),
  })
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
    title="银行对账单/流水 OCR 识别确认"
    width="960px"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
    @close="onCancel"
  >
    <div class="meta">
      <el-tag v-if="fileName" size="small">{{ fileName }}</el-tag>
      <el-tag v-if="confidence != null" size="small" type="success">置信度 {{ confidence }}</el-tag>
    </div>
    <el-form label-width="88px" size="small" class="meta-form">
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="开户银行">
            <el-input v-model="draft.bank" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="账号">
            <el-input v-model="draft.accountNo" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="期间起">
            <el-input v-model="draft.periodStart" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="期间止">
            <el-input v-model="draft.periodEnd" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <div class="table-toolbar">
      <span>流水明细（{{ draft.lines.length }}）</span>
      <el-button size="small" @click="addRow">+ 行</el-button>
    </div>
    <el-table :data="draft.lines" border size="small" max-height="360">
      <el-table-column label="日期" width="130">
        <template #default="{ row }">
          <el-input v-model="row.date" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.summary" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="对方" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.counterparty" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="方向" width="100">
        <template #default="{ row }">
          <el-select v-model="row.direction" size="small" clearable>
            <el-option label="收入" value="收入" />
            <el-option label="支出" value="支出" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="120">
        <template #default="{ row }">
          <el-input-number v-model="row.amount" :controls="false" size="small" style="width: 100%" />
        </template>
      </el-table-column>
      <el-table-column label="" width="56">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="removeRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <details v-if="ocrPreview" class="ocr-preview">
      <summary>OCR 原文预览</summary>
      <pre>{{ ocrPreview }}</pre>
    </details>

    <template #footer>
      <el-button @click="onCancel">取消</el-button>
      <el-button type="primary" @click="onConfirm">确认回填（{{ draft.lines.length }} 笔）</el-button>
    </template>
  </el-dialog>
</template>

<style scoped>
.meta { display: flex; gap: 8px; margin-bottom: 8px; flex-wrap: wrap; }
.meta-form { margin-bottom: 8px; }
.table-toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 6px; font-size: 13px;
}
.ocr-preview { margin-top: 10px; font-size: 12px; color: #606266; }
.ocr-preview pre {
  max-height: 140px; overflow: auto; white-space: pre-wrap;
  background: #f5f7fa; padding: 8px; border-radius: 4px;
}
</style>
