<script setup lang="ts">
/**
 * E1KeyPersonFlowOcrConfirmDialog — 个人流水 OCR 确认（复用 statement-ocr 结果）
 */
import { reactive, watch } from 'vue'

export interface KeyPersonOcrLine {
  date: string
  summary: string
  counterparty: string
  counterpartyAccount: string
  amount: number
  direction: '收入' | '支出' | ''
  cardNo: string
  cardType: string
}

export interface KeyPersonOcrFields {
  name: string
  position: string
  bank: string
  accountNo: string
  lines: KeyPersonOcrLine[]
}

const props = defineProps<{
  modelValue: boolean
  fields: Partial<KeyPersonOcrFields>
  confidence?: number
  ocrPreview?: string
  fileName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [KeyPersonOcrFields]
  cancel: []
}>()

function emptyLine(): KeyPersonOcrLine {
  return {
    date: '',
    summary: '',
    counterparty: '',
    counterpartyAccount: '',
    amount: 0,
    direction: '',
    cardNo: '',
    cardType: '',
  }
}

const draft = reactive<KeyPersonOcrFields>({
  name: '',
  position: '',
  bank: '',
  accountNo: '',
  lines: [],
})

watch(
  () => [props.modelValue, props.fields] as const,
  ([visible, fields]) => {
    if (!visible) return
    draft.name = fields.name || ''
    draft.position = fields.position || ''
    draft.bank = fields.bank || ''
    draft.accountNo = fields.accountNo || ''
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
    name: draft.name,
    position: draft.position,
    bank: draft.bank,
    accountNo: draft.accountNo,
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
    title="关键人员个人流水 OCR 识别确认"
    width="980px"
    :close-on-click-modal="false"
    destroy-on-close
    @update:model-value="emit('update:modelValue', $event)"
    @close="onCancel"
  >
    <div class="meta">
      <el-tag v-if="fileName" size="small">{{ fileName }}</el-tag>
      <el-tag v-if="confidence != null" size="small" type="success">置信度 {{ confidence }}</el-tag>
    </div>
    <el-form label-width="72px" size="small" class="meta-form">
      <el-row :gutter="12">
        <el-col :span="6">
          <el-form-item label="姓名"><el-input v-model="draft.name" /></el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="职位"><el-input v-model="draft.position" /></el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="开户行"><el-input v-model="draft.bank" /></el-form-item>
        </el-col>
        <el-col :span="6">
          <el-form-item label="账号"><el-input v-model="draft.accountNo" /></el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <div class="table-toolbar">
      <span>流水明细（{{ draft.lines.length }}）</span>
      <el-button size="small" @click="addRow">+ 行</el-button>
    </div>
    <el-table :data="draft.lines" border size="small" max-height="380">
      <el-table-column label="日期" width="120">
        <template #default="{ row }"><el-input v-model="row.date" size="small" /></template>
      </el-table-column>
      <el-table-column label="摘要" min-width="100">
        <template #default="{ row }"><el-input v-model="row.summary" size="small" /></template>
      </el-table-column>
      <el-table-column label="对方户名" min-width="100">
        <template #default="{ row }"><el-input v-model="row.counterparty" size="small" /></template>
      </el-table-column>
      <el-table-column label="对方账号" width="120">
        <template #default="{ row }"><el-input v-model="row.counterpartyAccount" size="small" /></template>
      </el-table-column>
      <el-table-column label="卡号" width="110">
        <template #default="{ row }"><el-input v-model="row.cardNo" size="small" /></template>
      </el-table-column>
      <el-table-column label="卡类型" width="90">
        <template #default="{ row }"><el-input v-model="row.cardType" size="small" /></template>
      </el-table-column>
      <el-table-column label="方向" width="90">
        <template #default="{ row }">
          <el-select v-model="row.direction" size="small" clearable>
            <el-option label="收入" value="收入" />
            <el-option label="支出" value="支出" />
          </el-select>
        </template>
      </el-table-column>
      <el-table-column label="金额" width="110">
        <template #default="{ row }">
          <el-input-number v-model="row.amount" :controls="false" size="small" style="width: 100%" />
        </template>
      </el-table-column>
      <el-table-column width="52">
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
  max-height: 120px; overflow: auto; white-space: pre-wrap;
  background: #f5f7fa; padding: 8px; border-radius: 4px;
}
</style>
