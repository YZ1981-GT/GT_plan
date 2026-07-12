<!-- K3TabLargeAmount.vue — K3-4 大额其他应付款情况分析表（8公式） | Task 4.4 | Req 4.1-4.4 -->
<template>
  <div class="k3-tab-large-amount">
    <!-- 方法论上下文（琥珀色） -->
    <div class="methodology-context">
      <p>K3-4大额其他应付款情况分析表用于识别金额重大的其他应付款项目，按期末余额降序排列。
        重点核查：款项性质、形成原因、预计偿付时间及是否长期挂账。占比=单项余额÷其他应付款合计（公式列）。
        超过阈值的行橙色高亮，提示重点关注。</p>
    </div>

    <!-- 标题栏 + 操作 -->
    <div class="section-head">
      <h3 class="sheet-title">K3-4 大额其他应付款情况分析表</h3>
      <div class="head-actions">
        <el-button size="small" type="primary" link @click="handleAiGenerate('large-amount-eval')">
          <el-icon><MagicStick /></el-icon> AI辅助
        </el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleAddRow">＋ 新增</el-button>
        <el-button size="small" :disabled="isReadonly" @click="handleInitFromDetail">从明细同步</el-button>
        <el-button size="small" @click="handleReview('K3-4-large')">💬 复核</el-button>
      </div>
    </div>

    <!-- 阈值设置 + 合计统计 -->
    <div class="summary-bar">
      <span>大额阈值：
        <el-input-number
          v-model="threshold"
          :disabled="isReadonly"
          :min="0"
          :step="10000"
          :controls="true"
          size="small"
          style="width: 160px"
          @change="handleThresholdChange"
        />
        元
      </span>
      <span>合计余额：<b>{{ fmtAmt(largeTotal) }}</b></span>
      <span>总占比：<b class="formula-cell" title="合计占比=大额合计/其他应付款期末合计">{{ fmtPct(largeTotalProportion) }}</b></span>
      <span>笔数：<b>{{ largeRows.length }}</b></span>
    </div>

    <!-- 主表格 -->
    <el-table
      :data="largeRows"
      border
      size="small"
      :max-height="520"
      class="large-amount-table"
      :row-style="tableRowStyle"
    >
      <el-table-column type="index" label="序号" width="55" align="center" />

      <el-table-column label="往来对象" min-width="140" fixed>
        <template #default="{ row }">
          <span class="counterparty-link" @click="navigateToDetail(row)">
            {{ row.counterparty }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="期末余额" min-width="120" align="right">
        <template #default="{ row }">
          <el-input-number v-if="!isReadonly" v-model="row.endBalance" size="small"
            :controls="false" class="amount-input"
            @change="handleRowChange(row)" />
          <span v-else class="amount-cell">{{ fmtAmt(row.endBalance) }}</span>
        </template>
      </el-table-column>

      <el-table-column label="占比" min-width="90" align="right">
        <template #default="{ row }">
          <span class="formula-cell" title="占比=单项余额/其他应付款合计">
            {{ fmtPct(row.proportion) }}
          </span>
        </template>
      </el-table-column>

      <el-table-column label="性质" min-width="120">
        <template #default="{ row }">
          <el-select v-if="!isReadonly" v-model="row.nature" size="small" clearable placeholder="请选择"
            @change="handleRowChange(row)">
            <el-option label="保证金/押金" value="保证金/押金" />
            <el-option label="往来款" value="往来款" />
            <el-option label="代收代付" value="代收代付" />
            <el-option label="暂收款" value="暂收款" />
            <el-option label="其他" value="其他" />
          </el-select>
          <span v-else>{{ row.nature || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="形成原因" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.formationReason" size="small" placeholder="形成原因"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.formationReason || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="预计偿付时间" min-width="120">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.repaymentDate" size="small" placeholder="如：2026年6月"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.repaymentDate || '-' }}</span>
        </template>
      </el-table-column>

      <el-table-column label="是否长期挂账" min-width="110" align="center">
        <template #default="{ row }">
          <el-tag :type="row.isLongOutstanding ? 'danger' : 'success'" size="small">
            {{ row.isLongOutstanding ? '是' : '否' }}
          </el-tag>
        </template>
      </el-table-column>

      <el-table-column label="后续核查" min-width="140">
        <template #default="{ row }">
          <el-input v-if="!isReadonly" v-model="row.followUpAction" size="small" placeholder="核查措施"
            @change="handleRowChange(row)" />
          <span v-else>{{ row.followUpAction || '-' }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
        <template #default="{ row }">
          <el-button size="small" type="danger" link @click="handleRemoveRow(row.rowId)">删除</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>按金额降序排列，超过阈值行橙色高亮；点击往来对象GtIndexChip跳转K3-2对应行</li>
        <li>占比公式列（虚线）= 单项余额 ÷ 其他应付款期末合计</li>
        <li>长期挂账：3年以上账龄自动标记"是"</li>
        <li>后续核查：记录拟采取的进一步审计程序</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * K3TabLargeAmount.vue — K3-4 大额其他应付款情况分析表
 * Spec: .kiro/specs/k3-other-payables/ | Task: 4.4
 * Requirements: 4.1-4.4
 */
import { computed, inject, onMounted } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import { MagicStick } from '@element-plus/icons-vue'
import { useK3LargeAmount, type K3LargeAmountRow } from '../../composables/useK3LargeAmount'
import { calcSubtotal } from '../../composables/useK3FormulaEngine'

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

// detailTotal: get from K3-2 rows in allResponses
const detailTotal = computed(() => {
  const item = props.allResponses.get('K3-2-rows')
  const raw = item?.remark ?? item?.conclusion ?? null
  if (!raw) return 0
  try {
    const rows = JSON.parse(raw)
    if (Array.isArray(rows)) return calcSubtotal(rows.map((r: any) => Number(r.endBalance) || 0))
  } catch { /* ignore */ }
  return 0
})

const {
  largeRows,
  threshold,
  largeTotal,
  largeTotalProportion,
  initFromDetail,
  initFromResponses,
  sortByAmount,
} = useK3LargeAmount({ allResponses: allResponsesRef as any, detailTotal })

// ─── Lifecycle ───────────────────────────────────────────────────────────────

onMounted(() => { initFromResponses() })

// ─── 行操作 ──────────────────────────────────────────────────────────────────

async function handleAddRow() {
  try {
    const { value } = await ElMessageBox.prompt(
      '请输入往来对象名称',
      '新增大额分析行',
      { confirmButtonText: '确定', cancelButtonText: '取消', inputPlaceholder: '往来对象名称' }
    )
    if (!value?.trim()) { ElMessage.warning('名称不能为空'); return }
    largeRows.value.push({
      rowId: `lr-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`,
      seqNo: largeRows.value.length + 1,
      counterparty: value.trim(),
      endBalance: 0,
      proportion: null,
      nature: '',
      formationReason: '',
      repaymentDate: '',
      isLongOutstanding: false,
      followUpAction: '',
      sourceRowId: '',
    })
    persistRows()
    ElMessage.success(`已新增：${value.trim()}`)
  } catch { /* cancelled */ }
}

function handleRemoveRow(rowId: string) {
  largeRows.value = largeRows.value.filter(r => r.rowId !== rowId)
  largeRows.value.forEach((r, i) => { r.seqNo = i + 1 })
  persistRows()
}

function handleRowChange(_row: K3LargeAmountRow) {
  sortByAmount()
  persistRows()
}

function handleThresholdChange() {
  persistRows()
}

function handleInitFromDetail() {
  const item = props.allResponses.get('K3-2-rows')
  const raw = item?.remark ?? item?.conclusion ?? null
  if (!raw) { ElMessage.warning('K3-2明细数据为空，请先填写明细表'); return }
  try {
    const rows = JSON.parse(raw)
    if (Array.isArray(rows)) {
      initFromDetail(rows)
      persistRows()
      ElMessage.success(`已从K3-2明细同步${largeRows.value.length}笔大额数据`)
    }
  } catch { ElMessage.error('解析K3-2明细数据失败') }
}

function persistRows() {
  const rowsItemId = 'K3-4-rows'
  const thresholdItemId = 'K3-4-threshold'
  const rowData = JSON.stringify(largeRows.value)
  props.allResponses.set(rowsItemId, { item_id: rowsItemId, remark: rowData })
  props.allResponses.set(thresholdItemId, { item_id: thresholdItemId, remark: String(threshold.value) })
  emit('save', rowsItemId, { remark: rowData })
  emit('save', thresholdItemId, { remark: String(threshold.value) })
}

function navigateToDetail(row: K3LargeAmountRow) {
  emit('navigate-sheet', 'K3-2 明细表')
}

// ─── UI Helpers ──────────────────────────────────────────────────────────────

function tableRowStyle({ row }: { row: K3LargeAmountRow }): Record<string, string> {
  if (row.endBalance >= threshold.value) return { 'background-color': '#fff7ed' }
  return {}
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function fmtPct(val: number | null | undefined): string {
  if (val == null) return '-'
  return (val * 100).toFixed(2) + '%'
}

function handleAiGenerate(section: string) {
  console.log('[K3-4] AI generate:', section)
}

function handleReview(id: string) { openReviewDialog(id) }
</script>

<style scoped>
.k3-tab-large-amount { padding: 16px; font-size: var(--wp-font-size, 13px); }
.methodology-context { border-left: 4px solid var(--el-color-warning); background: #fffbeb; padding: 10px 14px; margin-bottom: 16px; font-size: 12px; color: var(--el-text-color-regular); line-height: 1.6; }
.section-head { display: flex; align-items: center; justify-content: space-between; margin-bottom: 12px; }
.sheet-title { font-size: 15px; font-weight: 600; margin: 0; }
.head-actions { display: flex; gap: 8px; align-items: center; }
.summary-bar { display: flex; gap: 20px; align-items: center; margin-bottom: 12px; font-size: 12px; color: var(--el-text-color-regular); flex-wrap: wrap; }
.large-amount-table { font-size: var(--wp-font-size, 13px); }
.amount-cell { font-variant-numeric: tabular-nums; }
.amount-input { width: 100%; }
.formula-cell { border-bottom: 1px dashed var(--el-border-color); cursor: help; }
.counterparty-link { color: var(--el-color-primary); cursor: pointer; }
.counterparty-link:hover { text-decoration: underline; }
.compile-hint { margin-top: 16px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; line-height: 1.8; }
</style>
