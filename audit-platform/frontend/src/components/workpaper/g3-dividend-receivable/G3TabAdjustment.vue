<!--
  G3TabAdjustment.vue — G3-3 调整分录（10列）

  列：序号|分录类型(AJE/RJE)|日期|摘要|科目代码|科目名称|借方金额|贷方金额|编制人|备注
  借贷平衡校验：isDebitCreditBalanced — |SUM(借方)-SUM(贷方)| < 0.01
  不平衡时底部红色警告 + 差额显示
  动态行增删 + 导入导出

  Spec: .kiro/specs/g3-dividend-receivable/ Task 6.4
  Requirements: 6.1~6.4
-->
<template>
  <div class="g3-adjustment">
    <div class="section-head">
      <h3 class="sheet-title">G3-3 调整分录</h3>
      <div class="head-actions">
        <el-button size="small" :disabled="isReadonly" @click="addRow">＋ 新增分录</el-button>
        <el-dropdown trigger="click" size="small">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
              <el-dropdown-item @click="handleImportData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
        <el-button size="small" @click="openReviewDialog('G3-3-adjustment')">💬复核</el-button>
        <GtIndexChip value="wp:G3-3" :context-project-id="projectId" />
        <el-tag size="small" type="info">共 {{ rows.length }} 行</el-tag>
      </div>
    </div>

    <!-- 审计目标 -->
    <el-alert
      type="info"
      :closable="false"
      show-icon
      class="audit-objective"
      title="审计目标：记录并复核应收股利相关的审计调整(AJE)与重分类调整(RJE)，确保每笔分录借贷平衡且调整依据充分。"
    />

    <el-table :data="rows" border size="small" max-height="500" class="adjustment-table">
      <!-- 序号 -->
      <el-table-column label="序号" width="55" align="center" fixed>
        <template #default="{ $index }">{{ $index + 1 }}</template>
      </el-table-column>

      <!-- 分录类型 AJE/RJE -->
      <el-table-column label="类型" width="90">
        <template #default="{ row }">
          <el-select :model-value="row.entryType" size="small" :disabled="isReadonly"
            @change="(v: string) => updateRow(row.id, { entryType: v })">
            <el-option value="AJE" label="AJE" />
            <el-option value="RJE" label="RJE" />
          </el-select>
        </template>
      </el-table-column>

      <!-- 日期 -->
      <el-table-column label="日期" width="130">
        <template #default="{ row }">
          <el-date-picker :model-value="row.entryDate" type="date" size="small"
            value-format="YYYY-MM-DD" :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: string) => updateRow(row.id, { entryDate: v ?? '' })" />
        </template>
      </el-table-column>

      <!-- 摘要 -->
      <el-table-column label="摘要" min-width="150">
        <template #default="{ row }">
          <el-input :model-value="row.summary" size="small" :disabled="isReadonly"
            @change="(v: string) => updateRow(row.id, { summary: v })" />
        </template>
      </el-table-column>

      <!-- 科目代码 -->
      <el-table-column label="科目代码" width="110">
        <template #default="{ row }">
          <el-input :model-value="row.accountCode" size="small" :disabled="isReadonly"
            @change="(v: string) => updateRow(row.id, { accountCode: v })" />
        </template>
      </el-table-column>

      <!-- 科目名称 -->
      <el-table-column label="科目名称" width="130">
        <template #default="{ row }">
          <el-input :model-value="row.accountName" size="small" :disabled="isReadonly"
            @change="(v: string) => updateRow(row.id, { accountName: v })" />
        </template>
      </el-table-column>

      <!-- 借方金额 -->
      <el-table-column label="借方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.debitAmount" size="small" :controls="false"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: number) => updateRow(row.id, { debitAmount: v ?? 0 })" />
        </template>
      </el-table-column>

      <!-- 贷方金额 -->
      <el-table-column label="贷方金额" width="120" align="right">
        <template #default="{ row }">
          <el-input-number :model-value="row.creditAmount" size="small" :controls="false"
            :disabled="isReadonly" style="width:100%"
            @update:model-value="(v: number) => updateRow(row.id, { creditAmount: v ?? 0 })" />
        </template>
      </el-table-column>

      <!-- 编制人 -->
      <el-table-column label="编制人" width="100">
        <template #default="{ row }">
          <el-input :model-value="row.preparedBy" size="small" :disabled="isReadonly"
            @change="(v: string) => updateRow(row.id, { preparedBy: v })" />
        </template>
      </el-table-column>

      <!-- 备注 -->
      <el-table-column label="备注" width="120">
        <template #default="{ row }">
          <el-input :model-value="row.remark" size="small" :disabled="isReadonly"
            @change="(v: string) => updateRow(row.id, { remark: v })" />
        </template>
      </el-table-column>

      <!-- 操作列(删除) -->
      <el-table-column v-if="!isReadonly" label="" width="50" align="center" fixed="right">
        <template #default="{ row }">
          <el-icon class="delete-icon" @click="removeRow(row.id)"><Delete /></el-icon>
        </template>
      </el-table-column>
    </el-table>

    <!-- 借贷平衡校验 -->
    <div :class="['balance-bar', { 'balance-error': !balanced }]">
      <span class="balance-label">借方合计：{{ fmtNum(debitTotal) }}</span>
      <span class="balance-label">贷方合计：{{ fmtNum(creditTotal) }}</span>
      <span v-if="balanced" class="balance-ok">✓ 借贷平衡</span>
      <span v-else class="balance-warn">✗ 借贷不平衡，差额：{{ fmtNum(Math.abs(debitTotal - creditTotal)) }}</span>
    </div>

    <!-- 编制提示 -->
    <details class="guidance-details">
      <summary>📋 编制提示（CAS 依据）</summary>
      <div class="guidance-content">
        <p>1. AJE = 审计调整分录，RJE = 重分类调整分录。</p>
        <p>2. 每笔分录的借方合计与贷方合计应相等（借贷平衡），不平衡时底部红色告警并显示差额。</p>
        <p>3. 调整分录将自动反映到 G3-1 审定表的 AJE/RJE 列。</p>
        <p>4. 科目代码 1131 为应收股利，其他科目按实际情况填列。</p>
        <p class="cas-basis">CAS 依据：调整分录应有充分、适当的审计证据支持（《中国注册会计师审计准则第 1301 号——审计证据》）。</p>
      </div>
    </details>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, inject } from 'vue'
import { Delete } from '@element-plus/icons-vue'
import { ElMessage } from 'element-plus'
import GtIndexChip from '../GtIndexChip.vue'
import { isDebitCreditBalanced, parseNum } from '../composables/useG3DivRecFormulaEngine'
import type { ChecklistResponse } from '../composables/useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

interface AdjustmentRow {
  id: string
  entryType: 'AJE' | 'RJE'
  entryDate: string
  summary: string
  accountCode: string
  accountName: string
  debitAmount: number
  creditAmount: number
  preparedBy: string
  remark: string
}

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, ChecklistResponse>
  isReadonly: boolean
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
}>()

const openReviewDialog = inject<(sectionId: string) => void>('openReviewDialog', () => {})

// ─── Storage ─────────────────────────────────────────────────────────────────

const DATA_KEY = 'G3-3-adjustment-rows'

function generateId(): string {
  return `adj-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function emptyRow(): AdjustmentRow {
  return {
    id: generateId(),
    entryType: 'AJE',
    entryDate: '',
    summary: '',
    accountCode: '',
    accountName: '',
    debitAmount: 0,
    creditAmount: 0,
    preparedBy: '',
    remark: '',
  }
}

function loadRows(map: Map<string, ChecklistResponse>): AdjustmentRow[] {
  const raw = map.get(DATA_KEY)?.conclusion
  if (!raw) return [emptyRow()]
  try {
    const parsed = JSON.parse(raw) as Partial<AdjustmentRow>[]
    if (!Array.isArray(parsed) || parsed.length === 0) return [emptyRow()]
    return parsed.map((p) => ({ ...emptyRow(), ...p, id: p.id ?? generateId() }))
  } catch {
    return [emptyRow()]
  }
}

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<AdjustmentRow[]>(loadRows(props.allResponses))

// Reload when allResponses updates async
watch(() => props.allResponses.get(DATA_KEY)?.conclusion, (raw) => {
  if (raw) rows.value = loadRows(props.allResponses)
}, { immediate: false })

// ─── Computed ────────────────────────────────────────────────────────────────

const debitTotal = computed(() => rows.value.reduce((s, r) => s + parseNum(r.debitAmount), 0))
const creditTotal = computed(() => rows.value.reduce((s, r) => s + parseNum(r.creditAmount), 0))
const balanced = computed(() => isDebitCreditBalanced(
  rows.value.map((r) => r.debitAmount),
  rows.value.map((r) => r.creditAmount),
))

// ─── Actions ─────────────────────────────────────────────────────────────────

function persistAll() {
  if (!props.isReadonly) {
    props.debouncedSave(DATA_KEY, { conclusion: JSON.stringify(rows.value) })
  }
}

function updateRow(id: string, patch: Partial<AdjustmentRow>) {
  if (props.isReadonly) return
  rows.value = rows.value.map((r) => (r.id === id ? { ...r, ...patch } : r))
  persistAll()
}

function addRow() {
  if (props.isReadonly) return
  rows.value = [...rows.value, emptyRow()]
  persistAll()
}

function removeRow(id: string) {
  if (props.isReadonly || rows.value.length <= 1) return
  rows.value = rows.value.filter((r) => r.id !== id)
  persistAll()
}

// ─── Formatting ──────────────────────────────────────────────────────────────

function fmtNum(v: unknown): string {
  if (v === 0) return '0.00'
  if (typeof v === 'number') return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
  return String(v ?? '')
}

// ─── 导入导出（占位，useG3ImportExport Task 8.2 实现） ───
function handleExportTemplate() { ElMessage.info('导出模板功能将在导入导出模块完成后启用') }
function handleExportData() { ElMessage.info('导出数据功能将在导入导出模块完成后启用') }
function handleImportData() { ElMessage.info('导入数据功能将在导入导出模块完成后启用') }
</script>

<style scoped>
.g3-adjustment {
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
  align-items: center;
}

.adjustment-table {
  width: 100%;
}

/* 删除图标 */
.delete-icon {
  cursor: pointer;
  color: #909399;
  transition: color 0.2s;
}
.delete-icon:hover {
  color: #f56c6c;
}

/* 借贷平衡栏 */
.balance-bar {
  display: flex;
  gap: 16px;
  margin-top: 12px;
  padding: 8px 12px;
  background: #f5f7fa;
  border-radius: 4px;
  font-size: var(--wp-font-size, 13px);
  font-weight: 600;
  align-items: center;
  flex-wrap: wrap;
}

.balance-bar.balance-error {
  background: #fef0f0;
  border: 1px solid #f56c6c;
}

.balance-label {
  color: #606266;
}

.balance-ok {
  color: #67c23a;
}

.balance-warn {
  color: #f56c6c;
  font-weight: 700;
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
