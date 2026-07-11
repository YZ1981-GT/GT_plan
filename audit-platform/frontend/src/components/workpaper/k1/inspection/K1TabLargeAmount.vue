<!-- K1TabLargeAmount.vue — K1-5 大额其他应收款情况分析表 | Task 4.6 | Req 7.1-7.4 -->
<template>
  <div class="k1-tab-large-amount">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K1-5大额其他应收款情况分析表用于识别金额重大的其他应收款项目，重点关注占比超过10%的款项。
        核查要素包括：款项性质、形成原因、预计收回时间及可能性。大额款项需逐项分析，确保充分审计关注。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K1-5 大额其他应收款情况分析表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('K1-5-large')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
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
        <el-button size="small" @click="handleReview('K1-5-large')">💬 复核</el-button>
      </div>
    </div>

    <!-- 合计统计 -->
    <div class="summary-bar">
      <span>合计余额：<b>{{ fmtAmt(totalAmount) }}</b></span>
      <span>笔数：<b>{{ rows.length }}</b></span>
      <span>高亮阈值：<b>{{ (highlightThreshold * 100).toFixed(0) }}%</b></span>
    </div>

    <!-- 主表格 -->
    <el-table
      :data="rows"
      border
      size="small"
      :max-height="520"
      class="large-amount-table"
      :row-style="tableRowStyle"
    >
      <el-table-column label="往来对象" min-width="140" fixed>
        <template #default="{ row }">
          <span class="counterparty-link" @click="navigateToDetail(row)">
            {{ row.counterparty }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="期末余额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" :model-value="row.endBalance" size="small"
            :controls="false" class="amount-input"
            @change="(v: number) => handleUpdate(row.id, 'endBalance', v ?? 0)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="占比" min-width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="占比=单项余额/其他应收款合计">
            {{ row.proportion != null ? (row.proportion * 100).toFixed(2) + '%' : '-' }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="性质" min-width="110">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.nature" size="small" clearable
            placeholder="请选择" @change="(v: string) => handleUpdate(row.id, 'nature', v)">
            <el-option label="经营性往来" value="经营性往来" />
            <el-option label="非经营性往来" value="非经营性往来" />
            <el-option label="保证金/押金" value="保证金/押金" />
            <el-option label="备用金" value="备用金" />
            <el-option label="代垫款项" value="代垫款项" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.nature || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="形成原因" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.formReason" size="small"
            placeholder="形成原因"
            @change="(v: string) => handleUpdate(row.id, 'formReason', v)" />
          <span v-else>{{ row.formReason || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="预计收回时间" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.expectedRecovery" size="small"
            placeholder="如：2026年6月"
            @change="(v: string) => handleUpdate(row.id, 'expectedRecovery', v)" />
          <span v-else>{{ row.expectedRecovery || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="收回可能性" min-width="110" align="center">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" :model-value="row.recoverability" size="small"
            placeholder="请选择" @change="(v: string) => handleUpdate(row.id, 'recoverability', v)">
            <el-option label="很可能" value="很可能" />
            <el-option label="可能" value="可能" />
            <el-option label="极小可能" value="极小可能" />
          </el-select>
          <el-tag v-else :type="recoveryTagType(row.recoverability)" size="small">
            {{ row.recoverability || '-' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="后续核查" min-width="130">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" :model-value="row.followUp" size="small"
            placeholder="核查措施"
            @change="(v: string) => handleUpdate(row.id, 'followUp', v)" />
          <span v-else>{{ row.followUp || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.id)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>按期末余额降序排列，占比>10%黄色高亮；点击往来对象跳转K1-2</li>
        <li>收回可能性：很可能(>50%)/可能(≈50%)/极小可能(&lt;5%)</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K1TabLargeAmount.vue — K1-5 大额其他应收款情况分析表
 * Spec: .kiro/specs/k1-other-receivables/ | Task: 4.6
 * Requirements: 7.1-7.4
 */
import { computed, inject, toRef, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK1LargeAmount, type K1LargeAmountRow } from '../../composables/useK1LargeAmount'
import { useK1ImportExport } from '../../composables/useK1ImportExport'

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

const emit = defineEmits<{
  (e: 'save', itemId: string, value: any): void
  (e: 'navigate-sheet', sheetName: string): void
}>()

// ─── Injections ──────────────────────────────────────────────────────────────

const openReviewDialog = inject<(id: string) => void>('openReviewDialog', () => {})

// ─── Composables ─────────────────────────────────────────────────────────────

const allResponsesRef = computed(() => props.allResponses)

const {
  rows,
  totalAmount,
  highlightThreshold,
  loadRows,
  addRow,
  updateRow,
  removeRow,
  isAboveThreshold,
  serializeRows,
} = useK1LargeAmount({
  wpId: toRef(props, 'wpId'),
  projectId: toRef(props, 'projectId'),
  allResponses: allResponsesRef as any,
})

const { exportTemplate, exportData, importData } = useK1ImportExport({ wpId: toRef(props, 'wpId') })

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => { loadRows() })

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入往来对象名称',
      '新增大额分析行',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '往来对象名称' }
    )
    if (!value?.trim()) { ElMessage.warning('名称不能为空'); return }
    addRow(value.trim(), 0)
    persistRows()
    ElMessage.success(`已新增：${value.trim()}`)
  } catch { /* cancelled */ }
}

function handleRemoveRow(id: string) { removeRow(id); persistRows() }

function handleUpdate(id: string, field: keyof K1LargeAmountRow, value: any) {
  updateRow(id, field, value)
  persistRows()
}

function persistRows() {
  const itemId = 'K1-5-large-rows'
  const payload = { item_id: itemId, conclusion: null, remark: serializeRows() }
  props.allResponses.set(itemId, payload)
  emit('save', itemId, { remark: serializeRows() })
}

function navigateToDetail(row: K1LargeAmountRow) {
  emit('navigate-sheet', 'K1-2 明细表')
}

// ─── 导入导出 ─────────────────────────────────────────────────────────────────

function handleExportTemplate() { exportTemplate('K1-5') }
function handleExportData() { exportData('K1-5') }
function handleImportData() {
  const input = document.createElement('input')
  input.type = 'file'; input.accept = '.xlsx,.xls'
  input.onchange = async (e) => {
    const file = (e.target as HTMLInputElement).files?.[0]
    if (!file) return
    const result = await importData('K1-5', file)
    if (result) { loadRows() }
  }
  input.click()
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function tableRowStyle({ row }: { row: K1LargeAmountRow }): Record<string, string> {
  if (isAboveThreshold(row)) return { 'background-color': '#fef9c3' }
  return {}
}

function recoveryTagType(val: string): 'success' | 'warning' | 'danger' | 'info' {
  if (val === '很可能') return 'success'
  if (val === '可能') return 'warning'
  if (val === '极小可能') return 'danger'
  return 'info'
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function handleAiGenerate(section: string) { console.log('[K1-5] AI generate:', section) }
function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k1-tab-large-amount { padding: 16px; font-size: 13px; }
.methodology-context { border-left: 4px solid var(--el-color-warning); background: #fffbeb; padding: 10px 14px; margin-bottom: 16px; font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.summary-bar { display: flex; gap: 20px; margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-regular); }
.large-amount-table { font-size: 13px; }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.counterparty-link { color: var(--el-color-primary); cursor: pointer; }
.counterparty-link:hover { text-decoration: underline; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
