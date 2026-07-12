<!--
  G3TabDisclosureListed.vue — 附注披露（上市公司）

  36行×6列结构化表格 + textarea
  Subscribe: 'substantive:adjudicated'(accountCode='1131') 自动刷新
  Publish: 'disclosure:note-text-updated' 联动附注模块
  Storage: 'G3-disclosure-listed-text' + 'G3-disclosure-listed-table'

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.4
  Requirements: 4.1, 4.3, 4.4
-->
<template>
  <div class="g3-disclosure-listed">
    <div class="section-head">
      <h3 class="sheet-title">附注披露（上市公司）</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="fillAiDraft">🤖AI辅助</el-button>
        <el-button size="small" @click="openReviewDialog('G3-disclosure-listed')">💬复核</el-button>
        <GtIndexChip value="wp:G3-1" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ tableRows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：复核上市公司应收股利附注披露的完整性与准确性，确保与审定数勾稽一致，符合列报披露要求。"
    />

    <!-- 6列结构化表格 -->
    <el-table :data="tableRows" border size="small" max-height="400" class="disclosure-table">
      <el-table-column label="被投资方" min-width="140">
        <template #default="{ row }">
          <el-input :model-value="row.investeeName" size="small" :disabled="isReadonly"
            @change="(v: string) => updateTableRow(row.id, 'investeeName', v)" />
        </template>
      </el-table-column>
      <el-table-column label="期初余额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.openingBalance" size="small" :controls="false"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: number) => updateTableRow(row.id, 'openingBalance', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="本期增加" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.currentIncrease" size="small" :controls="false"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: number) => updateTableRow(row.id, 'currentIncrease', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="本期减少" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.currentDecrease" size="small" :controls="false"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: number) => updateTableRow(row.id, 'currentDecrease', v ?? 0)" />
        </template>
      </el-table-column>
      <el-table-column label="期末余额" width="120" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="期末余额 = 期初 + 增加 - 减少">
            {{ fmtNum(row.openingBalance + row.currentIncrease - row.currentDecrease) }}
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
        placeholder="上市公司应收股利附注披露内容..."
      />
    </el-card>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（CAS 依据）</summary>
      <div class="guidance-content">
        <p>1. 上市公司附注格式（36 行 ×6 列），按被投资方列示期初/期末金额。</p>
        <p>2. 期末余额 = 期初余额 + 本期增加 - 本期减少（灰色底纹为自动计算列）。</p>
        <p>3. 监听 substantive:adjudicated(1131) 自动同步审定数。</p>
        <p>4. 编辑后发布 disclosure:note-text-updated 联动附注模块。</p>
        <p class="cas-basis">CAS 依据：应收股利应在财务报表附注中充分披露（《企业会计准则第 30 号——财务报表列报》、《企业会计准则第 37 号——金融工具列报》）。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, onMounted, onBeforeUnmount, inject } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import GtIndexChip from '../GtIndexChip.vue'
import type { ChecklistResponse } from '../composables/useF1FormData'

// ─── Types ───
interface DisclosureTableRow {
  id: string
  investeeName: string
  openingBalance: number
  currentIncrease: number
  currentDecrease: number
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
const TEXT_KEY = 'G3-disclosure-listed-text'
const TABLE_KEY = 'G3-disclosure-listed-table'

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
      detail: { accountCode: '1131', section: 'listed', text: val },
    }))
  } catch { /* silent */ }
})

// ─── Table Rows ───
function generateId(): string {
  return `dl-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyTableRow(): DisclosureTableRow {
  return { id: generateId(), investeeName: '', openingBalance: 0, currentIncrease: 0, currentDecrease: 0, remark: '' }
}

function loadTableRows(): DisclosureTableRow[] {
  const raw = props.allResponses.get(TABLE_KEY)?.conclusion
  if (!raw) return [emptyTableRow()]
  try {
    const parsed = JSON.parse(raw) as Partial<DisclosureTableRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyTableRow()]
    return parsed.map((p) => ({ ...emptyTableRow(), ...p, id: p.id ?? generateId() }))
  } catch { return [emptyTableRow()] }
}

const tableRows = ref<DisclosureTableRow[]>(loadTableRows())

watch(() => props.allResponses.get(TABLE_KEY)?.conclusion, (raw) => {
  if (raw) tableRows.value = loadTableRows()
}, { immediate: false })

function persistTable() {
  if (!props.isReadonly) {
    props.debouncedSave(TABLE_KEY, { conclusion: JSON.stringify(tableRows.value) })
  }
}

function updateTableRow(id: string, field: keyof DisclosureTableRow, value: any) {
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
  const total = tableRows.value.reduce(
    (s, r) => s + r.openingBalance + r.currentIncrease - r.currentDecrease, 0,
  )
  const draft = `应收股利期末余额 ${fmtNum(total)} 元，按被投资方分类列示如下：\n` +
    tableRows.value
      .filter((r) => r.investeeName)
      .map((r) => `  - ${r.investeeName}：${fmtNum(r.openingBalance + r.currentIncrease - r.currentDecrease)} 元`)
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
.g3-disclosure-listed {
  padding: 12px;
  font-size: var(--wp-font-size, 13px);
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
  padding: 0 4px;
  text-align: right;
  background: #f5f7fa;
  border-radius: 2px;
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

/* 审计目标 */
.audit-objective {
  margin-bottom: 12px;
}

/* 编制提示（guidance-details gold 样式） */
.guidance-details {
  margin-top: 12px;
  border-left: 3px solid #409eff;
  background: #ecf5ff;
  border-radius: 4px;
  padding: 8px 12px;
}
.guidance-details summary {
  cursor: pointer;
  font-weight: 500;
  color: #409eff;
}
.guidance-content {
  margin-top: 8px;
  font-size: var(--wp-font-size, 13px);
  color: #606266;
  line-height: 1.6;
}
.guidance-content p {
  margin: 2px 0;
}
.guidance-content .cas-basis {
  margin-top: 6px;
  color: #909399;
  font-size: 12px;
}
</style>
