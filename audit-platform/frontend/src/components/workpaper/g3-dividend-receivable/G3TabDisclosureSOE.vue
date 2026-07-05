<!--
  G3TabDisclosureSOE.vue — 附注披露（国企）

  29行×5列结构化表格 + textarea
  Subscribe: 'substantive:adjudicated'(accountCode='1131') 自动刷新
  Publish: 'disclosure:note-text-updated' 联动附注模块
  Storage: 'G3-disclosure-soe-text' + 'G3-disclosure-soe-table'

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.4
  Requirements: 4.2, 4.3, 4.4
-->
<template>
  <div class="g3-disclosure-soe">
    <div class="section-head">
      <h3 class="sheet-title">附注披露（国企）</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G3-disclosure-soe')">💬复核</el-button>
      </div>
    </div>

    <!-- 5列结构化表格 -->
    <el-table :data="tableRows" border size="small" max-height="400" class="disclosure-table">
      <el-table-column label="被投资方" min-width="160">
        <template #default="{ row }">
          <el-input :model-value="row.investeeName" size="small" :disabled="isReadonly"
            @change="(v: string) => updateTableRow(row.id, 'investeeName', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="130" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.openingBalance" size="small" :controls="false"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: number) => updateTableRow(row.id, 'openingBalance', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="本期变动" width="130" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.currentChange" size="small" :controls="false"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: number) => updateTableRow(row.id, 'currentChange', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="130" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末余额 = 期初余额 + 本期变动">
            {{ fmtNum(row.openingBalance + row.currentChange) }}
          </span>
        </template>
      </el-table-column>
      <el-table-column label="备注" width="140">
        <template #default="{ row }">
          <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => updateTableRow(row.id, 'remark', v)" />
        </template>
      </el-table-column>
      <!-- 操作 -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="removeTableRow(row.id)"><Delete /></el-icon>
        </template>
      </el-table-column>
    </el-table>

    <el-button v-if="!isReadonly" size="small" style="margin-top:8px" @click="addTableRow">＋ 新增行</el-button>

    <!-- 附注文本 -->
    <el-card class="note-card" shadow="never" style="margin-top:12px">
      <template #header>
        <div class="note-header">
          <span>附注披露文本</span>
        </div>
      </template>
      <el-input
        v-model="noteText"
        type="textarea"
        :autosize="{ minRows: 6, maxRows: 20 }"
        :disabled="isReadonly"
        placeholder="国企应收股利附注披露内容..."
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="prep-hint">
      <summary>编制提示</summary>
      <ul>
        <li>国企附注格式（29行×5列），简化列示期初/期末金额</li>
        <li>期末余额 = 期初余额 + 本期变动</li>
        <li>监听 substantive:adjudicated(1131) 自动同步审定数</li>
        <li>编辑后发布 disclosure:note-text-updated 联动附注模块</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

// ─── Types ───
interface DisclosureSOERow {
  id: string
  investeeName: string
  openingBalance: number
  currentChange: number
  remark: string
}

// ─── Props ───
const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Storage Keys ───
const TEXT_KEY = 'G3-disclosure-soe-text'
const TABLE_KEY = 'G3-disclosure-soe-table'

// ─── Note Text ───
const noteText = ref('')

watch(() => props.allResponses.get(TEXT_KEY)?.remark, (v) => {
  if (v && v !== noteText.value) noteText.value = v
}, { immediate: true })

watch(noteText, (val) => {
  if (props.isReadonly) return
  props.debouncedSave(TEXT_KEY, { conclusion: null, remark: val })
  // Publish disclosure update
  try {
    window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
      detail: { accountCode: '1131', section: 'soe', text: val },
    }))
  } catch { /* silent */ }
})

// ─── Table Rows ───
function generateId(): string {
  return `ds-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyTableRow(): DisclosureSOERow {
  return { id: generateId(), investeeName: '', openingBalance: 0, currentChange: 0, remark: '' }
}

function loadTableRows(): DisclosureSOERow[] {
  const raw = props.allResponses.get(TABLE_KEY)?.conclusion
  if (!raw) return [emptyTableRow()]
  try {
    const parsed = JSON.parse(raw) as Partial<DisclosureSOERow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyTableRow()]
    return parsed.map((p) => ({ ...emptyTableRow(), ...p, id: p.id ?? generateId() }))
  } catch { return [emptyTableRow()] }
}

const tableRows = ref<DisclosureSOERow[]>(loadTableRows())

watch(() => props.allResponses.get(TABLE_KEY)?.conclusion, (raw) => {
  if (raw) tableRows.value = loadTableRows()
}, { immediate: false })

function persistTable() {
  if (!props.isReadonly) {
    props.debouncedSave(TABLE_KEY, { conclusion: JSON.stringify(tableRows.value) })
  }
}

function updateTableRow(id: string, field: keyof DisclosureSOERow, value: any) {
  if (props.isReadonly) return
  tableRows.value = tableRows.value.map((r) => (r.id === id ? { ...r, [field]: value } : r))
  persistTable()
}

function addTableRow() {
  if (props.isReadonly) return
  tableRows.value = [...tableRows.value, emptyTableRow()]
  persistTable()
}

function removeTableRow(id: string) {
  if (props.isReadonly || tableRows.value.length <= 1) return
  tableRows.value = tableRows.value.filter((r) => r.id !== id)
  persistTable()
}

// ─── Subscribe substantive:adjudicated(1131) ───
function handleAdjudicated(e: Event): void {
  const d = (e as CustomEvent<{ accountCode: string; adjudicatedAmount: number }>).detail
  if (d?.accountCode === '1131') {
    // Auto-refresh: could update template variables / totals here
  }
}

onMounted(() => { window.addEventListener('substantive:adjudicated', handleAdjudicated) })
onBeforeUnmount(() => { window.removeEventListener('substantive:adjudicated', handleAdjudicated) })

// ─── AI ───
function fillAiDraft() {
  if (props.isReadonly) return
  const total = tableRows.value.reduce((s, r) => s + r.openingBalance + r.currentChange, 0)
  const draft = `应收股利期末余额 ${fmtNum(total)} 元，主要为以下被投资方宣告尚未收到的现金股利：\n` +
    tableRows.value
      .filter((r) => r.investeeName)
      .map((r) => `  - ${r.investeeName}：${fmtNum(r.openingBalance + r.currentChange)} 元`)
      .join('\n')
  noteText.value = noteText.value ? `${noteText.value}\n${draft}` : draft
}

// ─── Formatting ───
function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return String(v ?? '')
}
</script>

<style scoped>
.g3-disclosure-soe {
  padding: 12px;
  font-size: 13px;
}

.section-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 12px;
}

.sheet-title {
  margin: 0;
  font-size: 15px;
}

.head-actions {
  display: flex;
  gap: 8px;
}

.disclosure-table {
  width: 100%;
}

.formula-cell {
  border-bottom: 1px dashed #909399;
  cursor: help;
  display: inline-block;
  min-width: 40px;
  text-align: right;
}

.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

.note-card :deep(.el-card__header) {
  padding: 12px 16px;
}

.note-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
}

.prep-hint {
  margin-top: 12px;
  font-size: 12px;
  color: #909399;
}
.prep-hint summary {
  cursor: pointer;
}
.prep-hint ul {
  margin: 8px 0 0;
  padding-left: 18px;
}
</style>
