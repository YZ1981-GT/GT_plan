<script setup lang="ts">
/**
 * F4TabAdjustment — F4-3 调整分录
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.6
 * 借贷平衡校验 + 动态行 + 导入导出
 * Requirements: 4.1~4.5, 6.1~6.4
 */
import { inject, toRef, ref, computed, watch, onMounted, onBeforeUnmount, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import axios from 'axios'
import { parseNum, calcSubtotal } from '../composables/useF4AccPayFormulaEngine'
import type { ChecklistResponse } from '../composables/useF4FormData'
import GtIndexChip from '../GtIndexChip.vue'

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const openReviewDialog = inject<((sectionId: string) => void) | null>('openReviewDialog', null)

// ─── 类型 ────────────────────────────────────────────────────────────────────

interface AdjustmentRow {
  rowId: string
  seq: number
  entryNo: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  summary: string
  remark: string
}

const STORAGE_KEY = 'F4-3-rows'

function generateRowId(): string {
  return `f4adj-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number): AdjustmentRow {
  return {
    rowId: generateRowId(), seq, entryNo: '', accountCode: '',
    accountName: '', debitAmount: 0, creditAmount: 0, summary: '', remark: '',
  }
}

// ─── 数据 ────────────────────────────────────────────────────────────────────

let debounceTimer: ReturnType<typeof setTimeout> | null = null
const rows = ref<AdjustmentRow[]>([emptyRow(1)])

function loadRows(): void {
  const raw = (props.allResponses as Map<string, any>).get(STORAGE_KEY)?.remark
  if (!raw) return
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed) && parsed.length) {
      rows.value = parsed.map((r: any, i: number) => ({
        ...emptyRow(i + 1),
        rowId: r.rowId || generateRowId(),
        seq: r.seq ?? i + 1,
        entryNo: r.entryNo || '',
        accountCode: r.accountCode || '',
        accountName: r.accountName || '',
        debitAmount: parseNum(r.debitAmount),
        creditAmount: parseNum(r.creditAmount),
        summary: r.summary || '',
        remark: r.remark || '',
      }))
    }
  } catch { /* ignore */ }
}

watch(() => (props.allResponses as Map<string, any>).get(STORAGE_KEY)?.remark, () => {
  if (rows.value.length <= 1 && !rows.value[0]?.accountCode) loadRows()
}, { immediate: true })

// ─── 计算 ────────────────────────────────────────────────────────────────────

const totalDebit = computed(() => calcSubtotal(rows.value.map((r) => r.debitAmount)))
const totalCredit = computed(() => calcSubtotal(rows.value.map((r) => r.creditAmount)))
const isBalanced = computed(() => Math.abs(totalDebit.value - totalCredit.value) < 0.01)

// ─── 操作 ────────────────────────────────────────────────────────────────────

function addRow() {
  if (props.isReadonly) return
  rows.value.push(emptyRow(rows.value.length + 1))
  persist()
}

function removeRow(rowId: string) {
  if (props.isReadonly || rows.value.length <= 1) return
  const idx = rows.value.findIndex((r) => r.rowId === rowId)
  if (idx === -1) return
  rows.value.splice(idx, 1)
  rows.value.forEach((r, i) => { r.seq = i + 1 })
  persist()
}

function updateCell(rowId: string, field: string, value: any) {
  if (props.isReadonly) return
  const row = rows.value.find((r) => r.rowId === rowId)
  if (!row) return
  if (field === 'debitAmount' || field === 'creditAmount') (row as any)[field] = parseNum(value)
  else (row as any)[field] = String(value ?? '')
  persist()
}

function persist() {
  const map = props.allResponses as Map<string, ChecklistResponse>
  map.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(rows.value) })
  if (debounceTimer) clearTimeout(debounceTimer)
  debounceTimer = setTimeout(() => {
    debounceTimer = null
    const item = map.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
  }, 2000)
}

onBeforeUnmount(() => { if (debounceTimer) { clearTimeout(debounceTimer); persist() } })

// ─── 导入导出 ────────────────────────────────────────────────────────────────
async function handleExportTemplate() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-template?sheet=F4-3`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-3调整分录模板.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出模板失败') }
}

async function handleExportData() {
  try {
    const resp = await axios.post(`/api/workpapers/${props.wpId}/f4/export-data?sheet=F4-3`, null, { responseType: 'blob' })
    const url = URL.createObjectURL(resp.data)
    const a = document.createElement('a'); a.href = url; a.download = 'F4-3调整分录数据.xlsx'; a.click()
    URL.revokeObjectURL(url)
  } catch { ElMessage.error('导出数据失败') }
}

function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async () => {
    const file = input.files?.[0]
    if (!file) return
    const fd = new FormData(); fd.append('file', file)
    try {
      await axios.post(`/api/workpapers/${props.wpId}/f4/import-data?sheet=F4-3`, fd)
      ElMessage.success('导入成功')
      window.location.reload()
    } catch { ElMessage.error('导入失败') }
  }
  input.click()
}

function fmtAmount(v: number): string {
  if (v === 0) return '-'
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── 审计说明 / 审计结论 ─────────────────────────────────────────────────────
const NOTE_KEY = 'F4-3-audit-note'
const CONCLUSION_KEY = 'F4-3-audit-conclusion'
const auditNote = ref('')
const auditConclusion = ref('')

function persistF4(key: string, val: string): void {
  const item = { item_id: key, conclusion: null, remark: val }
  ;(props.allResponses as Map<string, any>).set(key, item)
  window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
}

function saveAuditNote(val: string): void {
  if (props.isReadonly) return
  auditNote.value = val
  persistF4(NOTE_KEY, val)
}

function saveAuditConclusion(val: string): void {
  if (props.isReadonly) return
  auditConclusion.value = val
  persistF4(CONCLUSION_KEY, val)
}

onMounted(() => {
  const map = props.allResponses as Map<string, any>
  const n = map.get(NOTE_KEY)
  if (n?.remark) auditNote.value = n.remark
  const c = map.get(CONCLUSION_KEY)
  if (c?.remark) auditConclusion.value = c.remark
})
</script>

<template>
  <div class="f4-tab-adjustment">
    <details class="guidance-details">
      <summary>📋 编制提示</summary>
      <div class="guidance-content">
        <p>1. 调整分录用于记录审计发现的重大错报，借贷必须平衡。</p>
        <p>2. 借贷不平衡时底部红色警告，保存前必须修正。</p>
        <p>3. 调整分录确认后将自动回写试算表的AJE调整列。</p>
      </div>
    </details>

    <el-alert
      class="audit-objective"
      type="info"
      :closable="false"
      show-icon
      title="审计目标：将应付账款(2202)审计发现的错报以调整分录如实记录，确保借贷平衡，经确认后回写试算表 AJE 调整列。"
    />

    <el-alert v-if="!isBalanced" type="error" :closable="false" style="margin-bottom:8px">
      ⚠️ 借贷不平衡：借方合计 {{ fmtAmount(totalDebit) }} ≠ 贷方合计 {{ fmtAmount(totalCredit) }}，差额 {{ fmtAmount(Math.abs(totalDebit - totalCredit)) }}
    </el-alert>

    <div class="section-toolbar">
      <div class="toolbar-left">
        <el-button size="small" :disabled="isReadonly" @click="addRow">+ 新增行</el-button>
      </div>
      <div class="toolbar-right">
        <el-dropdown size="small" trigger="click">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <span class="chip-wrap"><GtIndexChip value="wp:F4-1" :context-project-id="projectId" /></span>
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
        <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-3-adjustment')">复核</el-button>
      </div>
    </div>

    <el-table :data="rows" border size="small" style="width:100%;font-size:13px">
      <el-table-column prop="seq" label="序号" width="60" />
      <el-table-column label="分录号" min-width="90">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.entryNo" size="small" @change="(v: string) => updateCell(row.rowId, 'entryNo', v)" />
          <span v-else>{{ row.entryNo }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目代码" min-width="100">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountCode" size="small" @change="(v: string) => updateCell(row.rowId, 'accountCode', v)" />
          <span v-else>{{ row.accountCode }}</span>
        </template>
      </el-table-column>
      <el-table-column label="科目名称" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.accountName" size="small" @change="(v: string) => updateCell(row.rowId, 'accountName', v)" />
          <span v-else>{{ row.accountName }}</span>
        </template>
      </el-table-column>
      <el-table-column label="借方金额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.debitAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'debitAmount', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.debitAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="贷方金额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.creditAmount" :controls="false" size="small" style="width:100%" @change="(v: number) => updateCell(row.rowId, 'creditAmount', v ?? 0)" />
          <span v-else>{{ fmtAmount(row.creditAmount) }}</span>
        </template>
      </el-table-column>
      <el-table-column label="摘要" min-width="150">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.summary" size="small" @change="(v: string) => updateCell(row.rowId, 'summary', v)" />
          <span v-else>{{ row.summary }}</span>
        </template>
      </el-table-column>
      <el-table-column label="操作" width="60">
        <template #default="{ row }">
          <el-button v-if="!isReadonly" link size="small" type="danger" @click="removeRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <div class="subtotal-bar" :class="{ 'balance-fail': !isBalanced }">
      借方合计：{{ fmtAmount(totalDebit) }} ｜贷方合计：{{ fmtAmount(totalCredit) }}
      <span v-if="isBalanced" class="balance-ok">✓ 平衡</span>
      <span v-else class="balance-err">✗ 不平衡</span>
    </div>

    <!-- ─── 审计说明 ──────────────────────────────────────────────────── -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计说明</span>
          <el-button v-if="openReviewDialog" size="small" @click="openReviewDialog('f4-3-note')">💬</el-button>
        </div>
      </template>
      <el-input
        :model-value="auditNote"
        type="textarea"
        :autosize="{ minRows: 5 }"
        :disabled="isReadonly"
        placeholder="填写审计说明：说明各笔调整分录的错报来源、性质及依据。"
        @change="saveAuditNote"
      />
    </el-card>

    <!-- ─── 审计结论 ──────────────────────────────────────────────────── -->
    <el-card class="opinion-card" shadow="never">
      <template #header>
        <div class="opinion-header">
          <span class="opinion-title">审计结论</span>
        </div>
      </template>
      <el-input
        :model-value="auditConclusion"
        type="textarea"
        :autosize="{ minRows: 3 }"
        :disabled="isReadonly"
        placeholder="填写审计结论：调整分录已与被审计单位沟通并取得认可情况。"
        @change="saveAuditConclusion"
      />
    </el-card>
  </div>
</template>

<style scoped>
.f4-tab-adjustment { font-size: var(--wp-font-size, 13px); }
.guidance-details { margin-bottom: 12px; border-left: 3px solid #409eff; background: #ecf5ff; border-radius: 4px; padding: 8px 12px; }
.guidance-details summary { cursor: pointer; font-weight: 500; color: #409eff; font-size: var(--wp-font-size, 13px); }
.guidance-details .guidance-content { margin-top: 8px; font-size: var(--wp-font-size, 13px); color: #606266; line-height: 1.6; }
.guidance-details .guidance-content p { margin: 2px 0; }
.section-toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px; }
.toolbar-left { display: flex; gap: 8px; align-items: center; }
.toolbar-right { display: flex; gap: 8px; align-items: center; }
.chip-wrap { display: inline-flex; align-items: center; }
.subtotal-bar { margin-top: 8px; padding: 8px 12px; background: #f0f9eb; border-radius: 4px; font-weight: 600; font-size: var(--wp-font-size, 13px); }
.subtotal-bar.balance-fail { background: #fef0f0; }
.balance-ok { color: #67c23a; margin-left: 12px; }
.balance-err { color: #f56c6c; margin-left: 12px; }
.audit-objective { margin-bottom: 12px; }
.opinion-card { margin-top: 16px; border-radius: 8px; }
.opinion-card :deep(.el-card__header) { padding: 12px 16px; background: #fafafa; border-bottom: 1px solid #ebeef5; }
.opinion-header { display: flex; align-items: center; justify-content: space-between; }
.opinion-title { font-size: 14px; font-weight: 600; color: #303133; }
</style>
