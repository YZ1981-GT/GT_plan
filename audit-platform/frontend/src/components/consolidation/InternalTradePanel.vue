<template>
  <div class="internal-trade-panel">
    <!-- Toolbar -->
    <div class="panel-toolbar">
      <div class="toolbar-left">
        <!-- View Toggle -->
        <el-radio-group v-model="viewMode" size="small" class="view-toggle">
          <el-radio-button value="table">
            <el-icon><Grid /></el-icon> 表格视图
          </el-radio-button>
          <el-radio-button value="matrix">
            <el-icon><Menu /></el-icon> 交易矩阵
          </el-radio-button>
        </el-radio-group>

        <!-- Filters -->
        <el-select
          v-model="filterSeller"
          placeholder="卖方公司"
          clearable
          size="small"
          style="width: 140px"
          :disabled="viewMode === 'matrix'"
        >
          <el-option
            v-for="c in companies"
            :key="c.code"
            :label="c.name"
            :value="c.code"
          />
        </el-select>

        <el-select
          v-model="filterBuyer"
          placeholder="买方公司"
          clearable
          size="small"
          style="width: 140px"
          :disabled="viewMode === 'matrix'"
        >
          <el-option
            v-for="c in companies"
            :key="c.code"
            :label="c.name"
            :value="c.code"
          />
        </el-select>

        <el-select
          v-model="filterTradeType"
          placeholder="交易类型"
          clearable
          size="small"
          style="width: 120px"
          :disabled="viewMode === 'matrix'"
        >
          <el-option label="商品交易" value="goods" />
          <el-option label="劳务服务" value="services" />
          <el-option label="资产交易" value="assets" />
          <el-option label="其他" value="other" />
        </el-select>
      </div>

      <div class="toolbar-right">
        <el-button
          size="small"
          type="primary"
          :disabled="!selectedRows.length"
          :loading="generatingElimination"
          @click="handleBatchGenerate"
        >
          批量生成抵消分录
          <span v-if="selectedRows.length" class="batch-count">({{ selectedRows.length }})</span>
        </el-button>
        <el-button size="small" @click="refresh" :loading="loading" plain>
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <!-- ─── Table View ─────────────────────────────────────────────── -->
    <div v-show="viewMode === 'table'" class="view-container">
      <el-table
        ref="tableRef"
        :data="filteredTrades"
        v-loading="loading"
        border
        stripe
        size="small"
        row-key="id"
        @selection-change="handleSelectionChange"
        class="gt-trade-table"
      >
        <el-table-column type="selection" width="40" />

        <el-table-column prop="trade_no" label="交易编号" width="130" />

        <el-table-column prop="trade_date" label="日期" width="100">
          <template #default="{ row }">{{ row.trade_date || '—' }}</template>
        </el-table-column>

        <el-table-column prop="seller_company_name" label="卖方公司" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.seller_company_name || row.seller_company_code }}</template>
        </el-table-column>

        <el-table-column prop="buyer_company_name" label="买方公司" min-width="140" show-overflow-tooltip>
          <template #default="{ row }">{{ row.buyer_company_name || row.buyer_company_code }}</template>
        </el-table-column>

        <el-table-column prop="trade_type" label="交易类型" width="110">
          <template #default="{ row }">
            <el-tag size="small">{{ tradeTypeLabel(row.trade_type) }}</el-tag>
          </template>
        </el-table-column>

        <el-table-column prop="trade_amount" label="金额" width="140" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ formatAmount(row.trade_amount) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="currency" label="币种" width="70" />

        <el-table-column prop="elimination_status" label="抵消状态" width="110" align="center">
          <template #default="{ row }">
            <el-tag :type="eliminationStatusTagType(row.elimination_status)" size="small">
              {{ eliminationStatusLabel(row.elimination_status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="160" fixed="right">
          <template #default="{ row }">
            <el-button size="small" text @click="handleViewDetail(row)">查看详情</el-button>
            <el-button
              size="small"
              text
              type="primary"
              :disabled="row.elimination_status === 'completed'"
              @click="handleGenerateSingle(row)"
            >
              生成抵消
            </el-button>
          </template>
        </el-table-column>
      </el-table>

      <!-- Summary Footer -->
      <div class="table-footer">
        <span>共 {{ filteredTrades.length }} 条记录</span>
        <span class="amount-summary">
          合计金额：
          <strong>{{ formatAmount(totalTradeAmount) }}</strong>
        </span>
      </div>
    </div>

    <!-- ─── Matrix View ─────────────────────────────────────────────── -->
    <div v-show="viewMode === 'matrix'" class="view-container matrix-container">
      <el-table
        :data="matrixData"
        border
        stripe
        size="small"
        class="gt-matrix-table"
        :span-method="matrixSpanMethod"
      >
        <el-table-column prop="seller" label="卖方 \ 买方" width="160" fixed>
          <template #default>
            <span class="matrix-header-label">卖方 \ 买方</span>
          </template>
        </el-table-column>

        <el-table-column
          v-for="buyer in matrixColumns"
          :key="buyer.code"
          :prop="buyer.code"
          :label="buyer.name"
          width="140"
          align="right"
        >
          <template #default="{ row }">
            <template v-if="row.seller && buyer.code && row[row.seller + '_' + buyer.code] !== undefined">
              <div
                class="matrix-cell"
                :style="{ backgroundColor: getHeatColor(row[row.seller + '_' + buyer.code]) }"
                @click="handleMatrixCellClick(row.seller, buyer.code, row[row.seller + '_' + buyer.code])"
              >
                <span class="matrix-amount">{{ formatAmount(row[row.seller + '_' + buyer.code]) }}</span>
                <span class="matrix-detail-hint">点击查看明细</span>
              </div>
            </template>
            <template v-else-if="row.seller && buyer.code && row.seller === buyer.code">
              <span class="matrix-diagonal">—</span>
            </template>
          </template>
        </el-table-column>
      </el-table>

      <div class="matrix-legend">
        <span class="legend-label">金额热力：</span>
        <div class="legend-gradient">
          <div class="legend-bar" />
          <div class="legend-labels">
            <span>低</span>
            <span>高</span>
          </div>
        </div>
      </div>
    </div>

    <!-- ─── Detail Dialog ───────────────────────────────────────────── -->
    <el-dialog v-model="detailVisible" title="内部交易详情" width="640px">
      <el-descriptions v-if="detailRow" :column="2" border size="small">
        <el-descriptions-item label="交易编号">{{ detailRow.trade_no || '—' }}</el-descriptions-item>
        <el-descriptions-item label="日期">{{ detailRow.trade_date || '—' }}</el-descriptions-item>
        <el-descriptions-item label="卖方公司">
          {{ detailRow.seller_company_name || detailRow.seller_company_code }}
        </el-descriptions-item>
        <el-descriptions-item label="买方公司">
          {{ detailRow.buyer_company_name || detailRow.buyer_company_code }}
        </el-descriptions-item>
        <el-descriptions-item label="交易类型">
          {{ tradeTypeLabel(detailRow.trade_type) }}
        </el-descriptions-item>
        <el-descriptions-item label="抵消状态">
          <el-tag :type="eliminationStatusTagType(detailRow.elimination_status)" size="small">
            {{ eliminationStatusLabel(detailRow.elimination_status) }}
          </el-tag>
        </el-descriptions-item>
        <el-descriptions-item label="交易金额" align="right">
          {{ formatAmount(detailRow.trade_amount) }} {{ detailRow.currency }}
        </el-descriptions-item>
        <el-descriptions-item label="成本金额" align="right">
          {{ formatAmount(detailRow.cost_amount) }}
        </el-descriptions-item>
        <el-descriptions-item label="未实现利润" align="right">
          {{ formatAmount(detailRow.unrealized_profit) }}
        </el-descriptions-item>
        <el-descriptions-item label="描述" :span="2">{{ detailRow.description || '—' }}</el-descriptions-item>
      </el-descriptions>
      <template #footer>
        <el-button @click="detailVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :disabled="!detailRow || detailRow.elimination_status === 'completed'"
          @click="handleGenerateSingle(detailRow!)"
        >
          生成抵消分录
        </el-button>
      </template>
    </el-dialog>

    <!-- ─── Matrix Detail Dialog ────────────────────────────────────── -->
    <el-dialog v-model="matrixDetailVisible" title="交易明细" width="700px">
      <div class="matrix-detail-header">
        <span>卖方：<strong>{{ matrixDetailSeller }}</strong></span>
        <span class="arrow">→</span>
        <span>买方：<strong>{{ matrixDetailBuyer }}</strong></span>
        <span class="total">合计：<strong>{{ formatAmount(matrixDetailTotal) }}</strong></span>
      </div>
      <el-table :data="matrixDetailRows" border stripe size="small" class="gt-trade-table">
        <el-table-column prop="trade_no" label="交易编号" width="130" />
        <el-table-column prop="trade_date" label="日期" width="100" />
        <el-table-column prop="trade_type" label="类型" width="100">
          <template #default="{ row }">{{ tradeTypeLabel(row.trade_type) }}</template>
        </el-table-column>
        <el-table-column prop="trade_amount" label="金额" width="140" align="right">
          <template #default="{ row }">{{ formatAmount(row.trade_amount) }}</template>
        </el-table-column>
        <el-table-column prop="elimination_status" label="状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="eliminationStatusTagType(row.elimination_status)" size="small">
              {{ eliminationStatusLabel(row.elimination_status) }}
            </el-tag>
          </template>
        </el-table-column>
        <el-table-column label="操作" width="120">
          <template #default="{ row }">
            <el-button size="small" text @click="handleGenerateSingle(row)">生成抵消</el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-dialog>
  </div>
</template>

<script setup lang="ts">
import { ref, reactive, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Grid, Menu, Refresh } from '@element-plus/icons-vue'
import type { ElTable } from 'element-plus'
import {
  getInternalTradeList,
  getTransactionMatrix,
  generateAutoElimination,
  type InternalTradeDetail,
  type TransactionMatrix,
  type TradeEliminationStatus,
} from '@/services/consolidationApi'

// ─── Types ─────────────────────────────────────────────────────────────────────
interface Company {
  code: string
  name: string
}

interface MatrixRow {
  seller?: string
  sellerName?: string
  [key: string]: string | undefined
}

// ─── Props & Emits ─────────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
  period: number
}>()

const emit = defineEmits<{
  eliminationGenerated: [entryIds: string[]]
}>()

// ─── State ─────────────────────────────────────────────────────────────────────
const tableRef = ref<InstanceType<typeof ElTable>>()
const trades = ref<InternalTradeDetail[]>([])
const matrixData = ref<TransactionMatrix | null>(null)
const loading = ref(false)
const generatingElimination = ref(false)
const viewMode = ref<'table' | 'matrix'>('table')
const selectedRows = ref<InternalTradeDetail[]>([])

// Filters
const filterSeller = ref<string | undefined>()
const filterBuyer = ref<string | undefined>()
const filterTradeType = ref<string | undefined>()

// Detail dialog
const detailVisible = ref(false)
const detailRow = ref<InternalTradeDetail | null>(null)

// Matrix detail dialog
const matrixDetailVisible = ref(false)
const matrixDetailSeller = ref('')
const matrixDetailBuyer = ref('')
const matrixDetailTotal = ref('')
const matrixDetailRows = ref<InternalTradeDetail[]>([])

// Companies list (derived from data)
const companies = computed<Company[]>(() => {
  const codes = new Set<string>()
  const names: Record<string, string> = {}
  for (const t of trades.value) {
    if (t.seller_company_code && !codes.has(t.seller_company_code)) {
      codes.add(t.seller_company_code)
      names[t.seller_company_code] = t.seller_company_name || t.seller_company_code
    }
    if (t.buyer_company_code && !codes.has(t.buyer_company_code)) {
      codes.add(t.buyer_company_code)
      names[t.buyer_company_code] = t.buyer_company_name || t.buyer_company_code
    }
  }
  return Array.from(codes).map(code => ({ code, name: names[code] || code }))
})

// ─── Computed ──────────────────────────────────────────────────────────────────
const filteredTrades = computed(() => {
  return trades.value.filter(t => {
    if (filterSeller.value && t.seller_company_code !== filterSeller.value) return false
    if (filterBuyer.value && t.buyer_company_code !== filterBuyer.value) return false
    if (filterTradeType.value && t.trade_type !== filterTradeType.value) return false
    return true
  })
})

const totalTradeAmount = computed(() => {
  return filteredTrades.value.reduce((sum, t) => {
    return sum + (parseFloat(t.trade_amount) || 0)
  }, 0)
})

const matrixColumns = computed(() => {
  if (!matrixData.value) return []
  return matrixData.value.company_codes.map(code => ({
    code,
    name: matrixData.value!.company_names?.[code] || code,
  }))
})

// Max amount for heat color calculation
const matrixMaxAmount = computed(() => {
  if (!matrixData.value) return 0
  let max = 0
  for (const seller of matrixData.value.company_codes) {
    for (const buyer of matrixData.value.company_codes) {
      const val = matrixData.value.matrix[seller]?.[buyer]
      if (val) {
        const n = typeof val === 'string' ? parseFloat(val) : val
        if (n > max) max = n
      }
    }
  }
  return max || 1
})

// ─── Helpers ───────────────────────────────────────────────────────────────────
function tradeTypeLabel(type: string | undefined): string {
  if (!type) return '—'
  const map: Record<string, string> = {
    goods: '商品交易',
    services: '劳务服务',
    assets: '资产交易',
    other: '其他',
  }
  return map[type] || type
}

function eliminationStatusLabel(status: TradeEliminationStatus | string | undefined): string {
  if (!status) return '—'
  const map: Record<string, string> = {
    pending: '待抵消',
    partial: '部分抵消',
    completed: '已完成',
  }
  return map[status] || status
}

function eliminationStatusTagType(
  status: TradeEliminationStatus | string | undefined
): '' | 'success' | 'warning' | 'info' | 'danger' | 'primary' {
  if (!status) return ''
  const map: Record<string, '' | 'success' | 'warning' | 'info' | 'danger' | 'primary'> = {
    pending: 'warning',
    partial: 'primary',
    completed: 'success',
  }
  return map[status] || ''
}

function formatAmount(value: string | undefined | null): string {
  if (!value) return '—'
  const n = parseFloat(value)
  if (isNaN(n)) return value
  return n.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getHeatColor(value: string | undefined): string {
  if (!value) return 'transparent'
  const n = parseFloat(value)
  if (isNaN(n) || matrixMaxAmount.value === 0) return 'var(--gt-color-primary-light)'
  const ratio = Math.min(n / matrixMaxAmount.value, 1)
  // Light purple → deep purple gradient
  const r = Math.round(160 + (75 - 160) * ratio)
  const g = Math.round(109 + (45 - 109) * ratio)
  const b = Math.round(255 + (119 - 255) * ratio)
  return `rgba(${r}, ${g}, ${b}, ${0.15 + ratio * 0.6})`
}

function matrixSpanMethod({ row, columnIndex }: { row: MatrixRow; columnIndex: number }) {
  // First column (seller label)
  if (columnIndex === 0) {
    return { rowspan: 1, colspan: 1 }
  }
  return { rowspan: 1, colspan: 1 }
}

// ─── Data Loading ──────────────────────────────────────────────────────────────
async function refresh() {
  loading.value = true
  try {
    if (viewMode.value === 'table') {
      trades.value = await getInternalTradeList(props.projectId, props.period)
    } else {
      matrixData.value = await getTransactionMatrix(props.projectId, props.period)
    }
  } catch (e) {
    ElMessage.error('加载内部交易数据失败')
  } finally {
    loading.value = false
  }
}

async function loadMatrixData() {
  loading.value = true
  try {
    matrixData.value = await getTransactionMatrix(props.projectId, props.period)
  } catch (e) {
    ElMessage.error('加载交易矩阵失败')
  } finally {
    loading.value = false
  }
}

// ─── Handlers ──────────────────────────────────────────────────────────────────
function handleSelectionChange(selection: InternalTradeDetail[]) {
  selectedRows.value = selection
}

function handleViewDetail(row: InternalTradeDetail) {
  detailRow.value = row
  detailVisible.value = true
}

async function handleGenerateSingle(row: InternalTradeDetail) {
  generatingElimination.value = true
  try {
    const result = await generateAutoElimination(props.projectId, [row.id])
    ElMessage.success(result.message || `已生成 ${result.generated_count} 条抵消分录`)
    emit('eliminationGenerated', result.entry_ids)
    await refresh()
    detailVisible.value = false
  } catch (e) {
    ElMessage.error('生成抵消分录失败')
  } finally {
    generatingElimination.value = false
  }
}

async function handleBatchGenerate() {
  if (!selectedRows.value.length) return
  generatingElimination.value = true
  try {
    const ids = selectedRows.value.map(r => r.id)
    const result = await generateAutoElimination(props.projectId, ids)
    ElMessage.success(`批量生成完成：${result.generated_count} 条抵消分录`)
    emit('eliminationGenerated', result.entry_ids)
    selectedRows.value = []
    tableRef.value?.clearSelection()
    await refresh()
  } catch (e) {
    ElMessage.error('批量生成抵消分录失败')
  } finally {
    generatingElimination.value = false
  }
}

function handleMatrixCellClick(seller: string, buyer: string, amount: string) {
  matrixDetailSeller.value = seller
  matrixDetailBuyer.value = buyer
  matrixDetailTotal.value = amount
  // Filter trades for this seller→buyer pair
  matrixDetailRows.value = trades.value.filter(
    t => t.seller_company_code === seller && t.buyer_company_code === buyer
  )
  matrixDetailVisible.value = true
}

// Watch view mode
async function onViewModeChange(mode: 'table' | 'matrix') {
  if (mode === 'matrix') {
    await loadMatrixData()
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  refresh()
})
</script>

<script lang="ts">
export default { name: 'InternalTradePanel' }
</script>

<style scoped>
.internal-trade-panel {
  display: flex;
  flex-direction: column;
  gap: var(--gt-space-3);
}

.panel-toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  flex-wrap: wrap;
  gap: var(--gt-space-2);
}

.toolbar-left {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  flex-wrap: wrap;
}

.toolbar-right {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
}

.view-container {
  min-height: 300px;
}

.amount-cell {
  font-family: var(--gt-font-family-en);
  font-size: 13px;
}

.batch-count {
  margin-left: 2px;
  opacity: 0.85;
}

.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--gt-space-2) var(--gt-space-1);
  font-size: 13px;
  color: var(--gt-color-primary-dark);
  border-top: 1px solid var(--el-border-color-lighter);
}

.amount-summary {
  font-size: 13px;
  color: var(--gt-color-primary);
}

/* Matrix View */
.matrix-container {
  overflow-x: auto;
}

.matrix-header-label {
  font-weight: 600;
  color: var(--gt-color-primary-dark);
}

.matrix-cell {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 6px 4px;
  border-radius: var(--gt-radius-sm);
  cursor: pointer;
  transition: all 0.2s;
  min-width: 60px;
}

.matrix-cell:hover {
  outline: 2px solid var(--gt-color-primary);
  outline-offset: -2px;
}

.matrix-amount {
  font-size: 13px;
  font-weight: 600;
  font-family: var(--gt-font-family-en);
  color: var(--gt-color-primary-dark);
  white-space: nowrap;
}

.matrix-detail-hint {
  font-size: 10px;
  color: var(--gt-color-primary);
  opacity: 0;
  transition: opacity 0.2s;
}

.matrix-cell:hover .matrix-detail-hint {
  opacity: 1;
}

.matrix-diagonal {
  color: var(--el-text-color-placeholder);
}

.matrix-legend {
  display: flex;
  align-items: center;
  gap: var(--gt-space-2);
  margin-top: var(--gt-space-2);
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

.legend-gradient {
  display: flex;
  flex-direction: column;
  gap: 2px;
}

.legend-bar {
  width: 120px;
  height: 10px;
  border-radius: 3px;
  background: linear-gradient(to right, rgba(160, 109, 255, 0.15), rgba(75, 45, 119, 0.9));
}

.legend-labels {
  display: flex;
  justify-content: space-between;
  width: 120px;
  font-size: 10px;
  color: var(--el-text-color-placeholder);
}

/* Detail Dialog */
.matrix-detail-header {
  display: flex;
  align-items: center;
  gap: var(--gt-space-3);
  margin-bottom: var(--gt-space-3);
  padding: var(--gt-space-2) var(--gt-space-3);
  background: var(--el-fill-color-light);
  border-radius: var(--gt-radius-sm);
  font-size: 14px;
}

.matrix-detail-header .arrow {
  color: var(--gt-color-primary);
  font-size: 16px;
}

.matrix-detail-header .total {
  margin-left: auto;
  color: var(--gt-color-primary);
}

.gt-trade-table :deep(.el-table__row:hover) {
  background-color: var(--el-fill-color-lighter);
}
</style>
