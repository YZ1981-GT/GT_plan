<script setup lang="ts">
/**
 * E1CommitOcrConfirmDialog — 承诺函 OCR/AI 识别结果确认后回填
 */
import { reactive, watch } from 'vue'

export interface CommitAccountRow {
  bank: string
  accountNo: string
  accountType: string
  openDate: string
  closeDate: string
  accountStatus: string
  restrictionStatus: string
}

export interface CommitOcrFields {
  unit: string
  legalRep: string
  finance: string
  date: string
  signConfirm: string
  checkSummary: string
  accounts: CommitAccountRow[]
}

const props = defineProps<{
  modelValue: boolean
  fields: Partial<CommitOcrFields>
  confidence?: number
  ocrPreview?: string
  fileName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [CommitOcrFields]
  cancel: []
}>()

function emptyAccount(): CommitAccountRow {
  return {
    bank: '',
    accountNo: '',
    accountType: '',
    openDate: '',
    closeDate: '',
    accountStatus: '正常',
    restrictionStatus: '无',
  }
}

const draft = reactive<CommitOcrFields>({
  unit: '',
  legalRep: '',
  finance: '',
  date: '',
  signConfirm: '',
  checkSummary: '',
  accounts: [],
})

watch(
  () => [props.modelValue, props.fields] as const,
  ([visible, fields]) => {
    if (!visible) return
    draft.unit = fields.unit || ''
    draft.legalRep = fields.legalRep || ''
    draft.finance = fields.finance || ''
    draft.date = fields.date || ''
    draft.signConfirm = fields.signConfirm || ''
    draft.checkSummary = fields.checkSummary || ''
    draft.accounts = Array.isArray(fields.accounts) && fields.accounts.length
      ? fields.accounts.map(r => ({ ...emptyAccount(), ...r }))
      : []
  },
  { immediate: true, deep: true },
)

function addRow(): void {
  draft.accounts.push(emptyAccount())
}

function removeRow(index: number): void {
  draft.accounts.splice(index, 1)
}

function onConfirm(): void {
  emit('confirm', {
    unit: draft.unit,
    legalRep: draft.legalRep,
    finance: draft.finance,
    date: draft.date,
    signConfirm: draft.signConfirm,
    checkSummary: draft.checkSummary,
    accounts: draft.accounts
      .map(r => ({ ...r }))
      .filter(r => r.bank.trim() || r.accountNo.trim()),
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
    title="承诺函 OCR/AI 识别确认"
    width="860px"
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
      <span class="hint">请核对下方字段与账户清单，确认后回填到 E1-11（标准承诺正文不会被改写）</span>
    </div>

    <el-form label-width="110px" size="small" class="ocr-form">
      <el-form-item label="被审计单位">
        <el-input v-model="draft.unit" />
      </el-form-item>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="法定代表人">
            <el-input v-model="draft.legalRep" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="财务负责人">
            <el-input v-model="draft.finance" />
          </el-form-item>
        </el-col>
      </el-row>
      <el-row :gutter="12">
        <el-col :span="12">
          <el-form-item label="声明日期">
            <el-input v-model="draft.date" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
        <el-col :span="12">
          <el-form-item label="签署盖章">
            <el-radio-group v-model="draft.signConfirm">
              <el-radio value="Y">已签字盖章</el-radio>
              <el-radio value="N">未签署</el-radio>
              <el-radio value="">不确定</el-radio>
            </el-radio-group>
          </el-form-item>
        </el-col>
      </el-row>
      <el-form-item label="核对摘要">
        <el-input v-model="draft.checkSummary" type="textarea" :autosize="{ minRows: 2, maxRows: 4 }" />
      </el-form-item>
    </el-form>

    <div class="accounts-header">
      <span>识别到的账户清单（{{ draft.accounts.length }}）</span>
      <el-button size="small" @click="addRow">添加行</el-button>
    </div>
    <el-table :data="draft.accounts" border size="small" max-height="280">
      <el-table-column label="开户银行" min-width="120">
        <template #default="{ row }">
          <el-input v-model="row.bank" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="账号" min-width="130">
        <template #default="{ row }">
          <el-input v-model="row.accountNo" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="性质" width="90">
        <template #default="{ row }">
          <el-input v-model="row.accountType" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="开户日" width="110">
        <template #default="{ row }">
          <el-input v-model="row.openDate" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="销户日" width="110">
        <template #default="{ row }">
          <el-input v-model="row.closeDate" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="状态" width="80">
        <template #default="{ row }">
          <el-input v-model="row.accountStatus" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="冻结/抵押/质押" min-width="110">
        <template #default="{ row }">
          <el-input v-model="row.restrictionStatus" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="" width="60" align="center">
        <template #default="{ $index }">
          <el-button type="danger" text size="small" @click="removeRow($index)">删</el-button>
        </template>
      </el-table-column>
    </el-table>

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
.accounts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 12px 0 8px;
  font-weight: 500;
  font-size: 13px;
}
.ocr-preview {
  margin-top: 12px;
  font-size: 12px;
  color: #606266;
}
.ocr-preview pre {
  max-height: 160px;
  overflow: auto;
  background: #f5f7fa;
  padding: 8px;
  border-radius: 4px;
  white-space: pre-wrap;
  word-break: break-all;
}
</style>
