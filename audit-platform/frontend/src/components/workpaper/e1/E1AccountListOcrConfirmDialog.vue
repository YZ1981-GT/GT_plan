<script setup lang="ts">
/**
 * E1AccountListOcrConfirmDialog — 《已开立银行结算账户清单》OCR 确认回填
 */
import { reactive, watch } from 'vue'

export interface AccountListOcrRow {
  bank: string
  accountNo: string
  accountType: string
  accountStatus: string
  openDate: string
  closeDate: string
}

export interface AccountListOcrFields {
  entityName: string
  printDate: string
  accounts: AccountListOcrRow[]
}

const props = defineProps<{
  modelValue: boolean
  fields: Partial<AccountListOcrFields>
  confidence?: number
  ocrPreview?: string
  fileName?: string
}>()

const emit = defineEmits<{
  'update:modelValue': [boolean]
  confirm: [AccountListOcrFields]
  cancel: []
}>()

function emptyAccount(): AccountListOcrRow {
  return {
    bank: '',
    accountNo: '',
    accountType: '',
    accountStatus: '正常',
    openDate: '',
    closeDate: '',
  }
}

const draft = reactive<AccountListOcrFields>({
  entityName: '',
  printDate: '',
  accounts: [],
})

watch(
  () => [props.modelValue, props.fields] as const,
  ([visible, fields]) => {
    if (!visible) return
    draft.entityName = fields.entityName || ''
    draft.printDate = fields.printDate || ''
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
    entityName: draft.entityName,
    printDate: draft.printDate,
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
    title="已开立银行结算账户清单 OCR/AI 识别确认"
    width="920px"
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
      <span class="hint">请核对清单字段后确认回填；开户/销户原因与企业信息核对需人工完成</span>
    </div>

    <el-form label-width="100px" size="small" class="ocr-form">
      <el-row :gutter="12">
        <el-col :span="14">
          <el-form-item label="单位名称">
            <el-input v-model="draft.entityName" placeholder="清单上的企业名称" />
          </el-form-item>
        </el-col>
        <el-col :span="10">
          <el-form-item label="打印日期">
            <el-input v-model="draft.printDate" placeholder="YYYY-MM-DD" />
          </el-form-item>
        </el-col>
      </el-row>
    </el-form>

    <div class="accounts-header">
      <span>识别账户（{{ draft.accounts.length }}）</span>
      <el-button size="small" @click="addRow">添加行</el-button>
    </div>
    <el-table :data="draft.accounts" border size="small" max-height="320">
      <el-table-column type="index" label="序号" width="50" align="center" />
      <el-table-column label="开户银行名称" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.bank" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="账号" min-width="140">
        <template #default="{ row }">
          <el-input v-model="row.accountNo" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="账户性质" width="120">
        <template #default="{ row }">
          <el-input v-model="row.accountType" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="账户状态" width="90">
        <template #default="{ row }">
          <el-input v-model="row.accountStatus" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="开户日期" width="110">
        <template #default="{ row }">
          <el-input v-model="row.openDate" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="销户日期" width="110">
        <template #default="{ row }">
          <el-input v-model="row.closeDate" size="small" />
        </template>
      </el-table-column>
      <el-table-column label="" width="56" align="center">
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
.hint { font-size: 12px; color: #909399; }
.ocr-form { margin-top: 4px; }
.accounts-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin: 10px 0 8px;
  font-weight: 500;
  font-size: 13px;
}
.ocr-preview { margin-top: 12px; font-size: 12px; color: #606266; }
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
