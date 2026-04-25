<template>
  <div class="internal-arap-panel">
    <!-- Toolbar -->
    <div class="panel-toolbar">
      <div class="toolbar-left">
        <el-select
          v-model="filterCompany"
          placeholder="公司"
          clearable
          size="small"
          style="width: 140px"
        >
          <el-option
            v-for="c in companies"
            :key="c.code"
            :label="c.name"
            :value="c.code"
          />
        </el-select>

        <el-select
          v-model="filterArApType"
          placeholder="往来类型"
          clearable
          size="small"
          style="width: 110px"
        >
          <el-option label="应收" value="ar" />
          <el-option label="应付" value="ap" />
        </el-select>

        <el-select
          v-model="filterStatus"
          placeholder="核对状态"
          clearable
          size="small"
          style="width: 110px"
        >
          <el-option label="已核对" value="matched" />
          <el-option label="未核对" value="unmatched" />
          <el-option label="容差" value="tolerance" />
        </el-select>

        <!-- Tolerance Input -->
        <div class="tolerance-config">
          <span class="tolerance-label">容忍额：</span>
          <el-input-number
            v-model="toleranceAmount"
            :min="0"
            :precision="2"
            :step="1000"
            size="small"
            style="width: 130px"
            placeholder="容忍额"
            controls-position="right"
          />
          <span class="tolerance-hint">差异 ≤ 此值时视为容差</span>
        </div>
      </div>

      <div class="toolbar-right">
        <el-button
          size="small"
          type="warning"
          :loading="reconciling"
          @click="handleReconcileAll"
        >
          一键核对全部
        </el-button>

        <el-button
          size="small"
          type="primary"
          :disabled="!hasUnadjustedRows"
          :loading="generating"
          @click="handleBatchGenerate"
        >
          生成全部未调差异抵消
          <span v-if="unadjustedRowsCount" class="batch-count">({{ unadjustedRowsCount }})</span>
        </el-button>

        <el-button size="small" @click="refresh" :loading="loading" plain>
          <el-icon><Refresh /></el-icon> 刷新
        </el-button>
      </div>
    </div>

    <!-- Table -->
    <div class="table-wrapper">
      <el-table
        ref="tableRef"
        :data="displayRows"
        v-loading="loading"
        border
        stripe
        size="small"
        row-key="id"
        class="gt-arap-table"
        :row-class-name="getRowClassName"
      >
        <el-table-column type="selection" width="40" />

        <el-table-column prop="arap_no" label="往来编号" width="130" />

        <el-table-column label="对方公司" min-width="140">
          <template #default="{ row }">
            {{ row.counterparty_name || row.counterparty_code }}
          </template>
        </el-table-column>

        <el-table-column label="我方科目" min-width="130">
          <template #default="{ row }">
            {{ row.my_account_name || row.my_account_code || '—' }}
          </template>
        </el-table-column>

        <el-table-column prop="arap_type" label="往来类型" width="90" align="center">
          <template #default="{ row }">
            <el-tag :type="row.arap_type === 'ar' ? 'success' : 'warning'" size="small">
              {{ row.arap_type === 'ar' ? '应收' : '应付' }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="我方账面数" width="140" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ formatAmount(row.my_book_amount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="对方账面数" width="140" align="right">
          <template #default="{ row }">
            <span class="amount-cell">{{ formatAmount(row.counterparty_book_amount) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="差异" width="140" align="right">
          <template #default="{ row }">
            <div class="diff-cell">
              <el-icon v-if="getDiffClass(row) === 'diff-zero'" color="var(--gt-color-success)"><SuccessFilled /></el-icon>
              <el-icon v-else-if="getDiffClass(row) === 'diff-warning'" color="var(--gt-color-wheat)"><WarningFilled /></el-icon>
              <el-icon v-else-if="getDiffClass(row) === 'diff-error'" color="var(--gt-color-coral)"><CircleCloseFilled /></el-icon>
              <span class="diff-amount" :class="getDiffClass(row)">
                {{ formatAmount(row.difference_amount) }}
              </span>
            </div>
          </template>
        </el-table-column>

        <el-table-column prop="reconciliation_status" label="核对状态" width="100" align="center">
          <template #default="{ row }">
            <el-tag :type="reconciliationStatusTagType(row.reconciliation_status)" size="small">
              {{ reconciliationStatusLabel(row.reconciliation_status) }}
            </el-tag>
          </template>
        </el-table-column>

        <el-table-column label="操作" width="120" fixed="right">
          <template #default="{ row }">
            <template v-if="getDiffValue(row) !== 0">
              <el-button size="small" text type="primary" @click="handleGenerateSingle(row)">
                生成抵消
              </el-button>
            </template>
            <template v-else>
              <el-button size="small" text disabled>—</el-button>
            </template>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- Summary Footer -->
    <div class="table-footer">
      <span>共 {{ displayRows.length }} 条记录</span>
      <div class="footer-summary">
        <span class="summary-item">
          <span class="dot matched"></span>
          已核对：{{ matchedCount }}
        </span>
        <span class="summary-item">
          <span class="dot unmatched"></span>
          未核对：{{ unmatchedCount }}
        </span>
        <span class="summary-item">
          <span class="dot tolerance"></span>
          容差：{{ toleranceCount }}
        </span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'
import { ElMessage } from 'element-plus'
import { Refresh, SuccessFilled, WarningFilled, CircleCloseFilled } from '@element-plus/icons-vue'
import type { ElTable } from 'element-plus'
import {
  getInternalArApList,
  reconcileAllInternalArAp,
  generateArApElimination,
  type InternalArApRow,
  type ArApReconciliationStatus,
} from '@/services/consolidationApi'

// ─── Types ─────────────────────────────────────────────────────────────────────
interface Company {
  code: string
  name: string
}

// ─── Props & Emits ─────────────────────────────────────────────────────────────
const props = defineProps<{
  projectId: string
  period: number
}>()

// ─── State ─────────────────────────────────────────────────────────────────────
const tableRef = ref<InstanceType<typeof ElTable>>()
const rows = ref<InternalArApRow[]>([])
const loading = ref(false)
const reconciling = ref(false)
const generating = ref(false)
const toleranceAmount = ref<number>(0)

// Filters
const filterCompany = ref<string | undefined>()
const filterArApType = ref<'ar' | 'ap' | undefined>()
const filterStatus = ref<ArApReconciliationStatus | undefined>()

// ─── Computed ──────────────────────────────────────────────────────────────────
const companies = computed<Company[]>(() => {
  const codes = new Set<string>()
  const names: Record<string, string> = {}
  for (const r of rows.value) {
    if (r.company_code && !codes.has(r.company_code)) {
      codes.add(r.company_code)
      names[r.company_code] = (r.company_name as string) || r.company_code
    }
    if (r.counterparty_code && !codes.has(r.counterparty_code)) {
      codes.add(r.counterparty_code)
      names[r.counterparty_code] = (r.counterparty_name as string) || r.counterparty_code
    }
  }
  return Array.from(codes).map(code => ({ code, name: names[code] || code }))
})

const displayRows = computed(() => {
  return rows.value.filter(r => {
    if (filterCompany.value && r.company_code !== filterCompany.value) return false
    if (filterArApType.value && r.arap_type !== filterArApType.value) return false
    if (filterStatus.value && r.reconciliation_status !== filterStatus.value) return false
    return true
  })
})

const matchedCount = computed(() => rows.value.filter(r => r.reconciliation_status === 'matched').length)
const unmatchedCount = computed(() => rows.value.filter(r => r.reconciliation_status === 'unmatched').length)
const toleranceCount = computed(() => rows.value.filter(r => r.reconciliation_status === 'tolerance').length)

const hasUnadjustedRows = computed(() => rows.value.some(r => getDiffValue(r) !== 0))
const unadjustedRowsCount = computed(() => rows.value.filter(r => getDiffValue(r) !== 0).length)

// ─── Helpers ──────────────────────────────────────────────────────────────────
function getDiffValue(row: InternalArApRow): number {
  const n = parseFloat(String(row.difference_amount) || '0')
  return isNaN(n) ? 0 : n
}

function getDiffClass(row: InternalArApRow): string {
  const diff = Math.abs(getDiffValue(row))
  if (diff === 0) return 'diff-zero'
  if (diff <= toleranceAmount.value) return 'diff-warning'
  return 'diff-error'
}

function getRowClassName({ row }: { row: InternalArApRow }): string {
  const cls = getDiffClass(row)
  if (cls === 'diff-zero') return 'row-matched'
  if (cls === 'diff-warning') return 'row-tolerance'
  if (cls === 'diff-error') return 'row-unmatched'
  return ''
}

function reconciliationStatusLabel(status: ArApReconciliationStatus | string | undefined): string {
  if (!status) return '—'
  const map: Record<string, string> = {
    matched: '已核对',
    unmatched: '未核对',
    tolerance: '容差',
  }
  return map[status] || status
}

function reconciliationStatusTagType(
  status: ArApReconciliationStatus | string | undefined
): '' | 'success' | 'warning' | 'danger' | 'info' | 'primary' {
  if (!status) return ''
  const map: Record<string, '' | 'success' | 'warning' | 'danger' | 'info' | 'primary'> = {
    matched: 'success',
    unmatched: 'danger',
    tolerance: 'warning',
  }
  return map[status] || ''
}

function formatAmount(value: string | undefined | null): string {
  if (!value) return '—'
  const n = parseFloat(value)
  if (isNaN(n)) return value
  const sign = n < 0 ? '-' : ''
  return sign + Math.abs(n).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

// ─── Data Loading ──────────────────────────────────────────────────────────────
async function refresh() {
  loading.value = true
  try {
    rows.value = await getInternalArApList(props.projectId, props.period)
  } catch (e) {
    ElMessage.error('加载内部往来数据失败')
  } finally {
    loading.value = false
  }
}

// ─── Handlers ──────────────────────────────────────────────────────────────────
async function handleReconcileAll() {
  reconciling.value = true
  try {
    const result = await reconcileAllInternalArAp(props.projectId, props.period)
    ElMessage.success(
      `核对完成：共 ${result.total_count} 条，已核对 ${result.matched_count}，未核对 ${result.unmatched_count}`
    )
    await refresh()
  } catch (e) {
    ElMessage.error('核对失败')
  } finally {
    reconciling.value = false
  }
}

async function handleGenerateSingle(_row: InternalArApRow) {
  generating.value = true
  try {
    const result = await generateArApElimination(props.projectId, props.period as any)
    ElMessage.success(result.message || `已生成 ${result.generated_count} 条抵消分录`)
    await refresh()
  } catch (e) {
    ElMessage.error('生成抵消分录失败')
  } finally {
    generating.value = false
  }
}

async function handleBatchGenerate() {
  const unadjustedRows = rows.value.filter(r => getDiffValue(r) !== 0)
  if (!unadjustedRows.length) {
    ElMessage.warning('没有需要调差异的往来记录')
    return
  }
  generating.value = true
  try {
    const result = await generateArApElimination(props.projectId, props.period as any)
    ElMessage.success(`批量生成完成：${result.generated_count} 条抵消分录`)
    await refresh()
  } catch (e) {
    ElMessage.error('批量生成抵消分录失败')
  } finally {
    generating.value = false
  }
}

// ─── Lifecycle ────────────────────────────────────────────────────────────────
onMounted(() => {
  refresh()
})
</script>

<script lang="ts">
export default { name: 'InternalArApPanel' }
</script>

<style scoped>
.internal-arap-panel {
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

.tolerance-config {
  display: flex;
  align-items: center;
  gap: var(--gt-space-1);
  font-size: 13px;
}

.tolerance-label {
  color: var(--el-text-color-regular);
  white-space: nowrap;
}

.tolerance-hint {
  color: var(--el-text-color-placeholder);
  font-size: 12px;
  white-space: nowrap;
}

.table-wrapper {
  overflow-x: auto;
}

.amount-cell {
  font-family: var(--gt-font-family-en);
  font-size: 13px;
}

.diff-cell {
  display: flex;
  align-items: center;
  justify-content: flex-end;
  gap: 4px;
}

.diff-amount {
  font-family: var(--gt-font-family-en);
  font-size: 13px;
  font-weight: 600;
}

.diff-zero {
  color: var(--gt-color-success);
}

.diff-warning {
  color: var(--gt-color-wheat);
}

.diff-error {
  color: var(--gt-color-coral);
}

.batch-count {
  margin-left: 2px;
  opacity: 0.85;
}

/* Row highlight colors */
.gt-arap-table :deep(.row-matched) {
  background-color: rgba(0, 148, 179, 0.06) !important;
}

.gt-arap-table :deep(.row-tolerance) {
  background-color: rgba(255, 194, 61, 0.06) !important;
}

.gt-arap-table :deep(.row-unmatched) {
  background-color: rgba(255, 81, 73, 0.06) !important;
}

/* Summary Footer */
.table-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: var(--gt-space-2) var(--gt-space-1);
  font-size: 13px;
  color: var(--gt-color-primary-dark);
  border-top: 1px solid var(--el-border-color-lighter);
}

.footer-summary {
  display: flex;
  gap: var(--gt-space-4);
}

.summary-item {
  display: flex;
  align-items: center;
  gap: 6px;
  font-size: 13px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
}

.dot.matched {
  background-color: var(--gt-color-success);
}

.dot.unmatched {
  background-color: var(--gt-color-coral);
}

.dot.tolerance {
  background-color: var(--gt-color-wheat);
}

.gt-arap-table :deep(.el-table__row:hover) {
  background-color: var(--el-fill-color-lighter) !important;
}
</style>
