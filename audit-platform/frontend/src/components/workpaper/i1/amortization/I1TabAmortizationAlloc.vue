<template>
  <div class="i1-tab-amort-alloc">
    <!-- 方法论上下文 -->
    <div class="methodology-context">
      <p><strong>摊销分配规则：</strong>将摊销测算表(I1-10/I1-11)计算的各资产本期摊销总额，按实际使用部门分配至对应费用科目。</p>
      <p>管理费用(K8)、销售费用(K9)、制造费用(D5)、研发费用(I6)、其他费用。各行分配合计必须等于该资产摊销总额，否则红色警示。</p>
      <p>底部合计行自动汇总各列，分配比例 = 各列合计 ÷ 摊销总额合计 × 100%。</p>
    </div>

    <!-- 操作栏 -->
    <div class="toolbar">
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
        + 新增资产行
      </el-button>
      <div class="toolbar-right">
        <el-dropdown trigger="click" @command="handleImportExport">
          <el-button size="small">导入导出 ▾</el-button>
          <template #dropdown>
            <el-dropdown-menu>
              <el-dropdown-item command="exportTemplate">导出模板</el-dropdown-item>
              <el-dropdown-item command="exportData">导出数据</el-dropdown-item>
              <el-dropdown-item command="importData">导入数据</el-dropdown-item>
            </el-dropdown-menu>
          </template>
        </el-dropdown>
      </div>
    </div>

    <!-- 主表 -->
    <el-table
      :data="displayRows"
      border
      stripe
      size="small"
      class="alloc-table"
      :row-class-name="getRowClassName"
    >
      <el-table-column type="index" width="40" label="#" />

      <!-- 资产名称 -->
      <el-table-column prop="name" label="资产名称" min-width="140">
        <template #default="{ row }">
          <span v-if="row._isSummary" class="summary-text">合计</span>
          <span v-else>{{ row.name || '—' }}</span>
        </template>
      </el-table-column>

      <!-- 摊销总额（来自I1-10/11，只读） -->
      <el-table-column label="摊销总额" min-width="110" align="right">
        <template #header>
          <el-tooltip content="来自摊销测算表(I1-10/I1-11) assetPeriodTotals" placement="top">
            <span class="formula-col-header">摊销总额</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtAmt(row.totalAmort) }}</span>
        </template>
      </el-table-column>

      <!-- 管理费用 -->
      <el-table-column label="管理费用" min-width="110" align="right">
        <template #header>
          <el-tooltip content="计入管理费用(K8)的摊销额" placement="top">
            <span class="formula-col-header">管理费用</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="!row._isSummary && !isReadonly"
            v-model="row.managementExpense"
            :controls="false"
            size="small"
            @change="onCellChange(row)"
          />
          <span v-else class="formula-value">{{ fmtAmt(row.managementExpense) }}</span>
        </template>
      </el-table-column>

      <!-- 销售费用 -->
      <el-table-column label="销售费用" min-width="110" align="right">
        <template #header>
          <el-tooltip content="计入销售费用(K9)的摊销额" placement="top">
            <span class="formula-col-header">销售费用</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="!row._isSummary && !isReadonly"
            v-model="row.sellingExpense"
            :controls="false"
            size="small"
            @change="onCellChange(row)"
          />
          <span v-else class="formula-value">{{ fmtAmt(row.sellingExpense) }}</span>
        </template>
      </el-table-column>

      <!-- 制造费用 -->
      <el-table-column label="制造费用" min-width="110" align="right">
        <template #header>
          <el-tooltip content="计入制造费用(D5)的摊销额" placement="top">
            <span class="formula-col-header">制造费用</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="!row._isSummary && !isReadonly"
            v-model="row.manufacturingCost"
            :controls="false"
            size="small"
            @change="onCellChange(row)"
          />
          <span v-else class="formula-value">{{ fmtAmt(row.manufacturingCost) }}</span>
        </template>
      </el-table-column>

      <!-- 研发费用 -->
      <el-table-column label="研发费用" min-width="110" align="right">
        <template #header>
          <el-tooltip content="计入研发费用(I6)的摊销额" placement="top">
            <span class="formula-col-header">研发费用</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-input-number
            v-if="!row._isSummary && !isReadonly"
            v-model="row.rdExpense"
            :controls="false"
            size="small"
            @change="onCellChange(row)"
          />
          <span v-else class="formula-value">{{ fmtAmt(row.rdExpense) }}</span>
        </template>
      </el-table-column>

      <!-- 其他 -->
      <el-table-column label="其他" min-width="100" align="right">
        <template #default="{ row }">
          <el-input-number
            v-if="!row._isSummary && !isReadonly"
            v-model="row.otherExpense"
            :controls="false"
            size="small"
            @change="onCellChange(row)"
          />
          <span v-else class="formula-value">{{ fmtAmt(row.otherExpense) }}</span>
        </template>
      </el-table-column>

      <!-- 合计（公式列） -->
      <el-table-column label="合计" min-width="110" align="right">
        <template #header>
          <el-tooltip content="合计 = 管理 + 销售 + 制造 + 研发 + 其他（必须 = 摊销总额）" placement="top">
            <span class="formula-col-header">合计</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <el-tooltip
            :content="getRowBalanceTooltip(row)"
            :disabled="row._isSummary || isRowBalanced(row)"
            placement="top"
          >
            <span :class="['formula-value', { 'alloc-error': !row._isSummary && !isRowBalanced(row) }]">
              {{ fmtAmt(calcRowSum(row)) }}
            </span>
          </el-tooltip>
        </template>
      </el-table-column>

      <!-- 分配比例 -->
      <el-table-column label="分配比例" min-width="90" align="right">
        <template #header>
          <el-tooltip content="分配比例 = 各列合计 ÷ 摊销总额合计 × 100%" placement="top">
            <span class="formula-col-header">分配比例</span>
          </el-tooltip>
        </template>
        <template #default="{ row }">
          <span class="formula-value">{{ fmtPercent(row) }}</span>
        </template>
      </el-table-column>

      <!-- 操作列 -->
      <el-table-column label="操作" width="50" v-if="!isReadonly">
        <template #default="{ row }">
          <el-button
            v-if="!row._isSummary"
            size="small"
            type="danger"
            link
            @click="handleRemoveRow(row.rowId)"
          >删</el-button>
        </template>
      </el-table-column>
    </el-table>

    <!-- 跳转目标 -->
    <div class="jump-targets">
      <span class="jump-label">跨底稿联动：</span>
      <GtIndexChip value="K8" @click="navigateTo('K8')" />
      <GtIndexChip value="K9" @click="navigateTo('K9')" />
      <GtIndexChip value="D5" @click="navigateTo('D5')" />
      <GtIndexChip value="I6" @click="navigateTo('I6')" />
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>摊销总额列来自摊销测算表(I1-10/I1-11)的本期摊销合计，不可编辑</li>
        <li>各行"合计"必须等于该行"摊销总额"，否则红色警示</li>
        <li>底部合计行自动SUM各列数据</li>
        <li>分配比例 = 该行合计 ÷ 总摊销额合计 × 100%</li>
        <li>GtIndexChip跳转：管理费用→K8、销售费用→K9、制造费用→D5、研发费用→I6</li>
        <li>新增行时需先在I1-10/I1-11摊销测算表中添加对应资产</li>
      </ul>
    </details>
  </div>
</template>

<script setup lang="ts">
/**
 * I1TabAmortizationAlloc.vue — I1-9 摊销分配分析表
 *
 * Columns: 资产名称|摊销总额|管理费用|销售费用|制造费用|研发费用|其他|合计|分配比例
 * Formula: 合计 = 管理+销售+制造+研发+其他 (must = 摊销总额, red warning if not)
 * Formula: 分配比例 = 该行合计 / 总合计 × 100%
 * Bottom 合计行 auto-SUM
 * GtIndexChip links: K8(管理费用)/K9(销售费用)/D5(制造费用)/I6(研发费用)
 * Storage: "I1-9-rows" item_id
 * Data source: amortizationByAsset prop (from useI1Amortization.assetPeriodTotals)
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Requirements: 10.1-10.4
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import GtIndexChip from '../../GtIndexChip.vue'

// ─── Types ───────────────────────────────────────────────────────────────────

interface I1AllocRow {
  rowId: string
  name: string
  totalAmort: number
  managementExpense: number
  sellingExpense: number
  manufacturingCost: number
  rdExpense: number
  otherExpense: number
  /** internal marker for summary row */
  _isSummary?: boolean
}

// ─── Props / Emits ───────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
  /** Record<assetName, periodAmortTotal> from useI1Amortization.assetPeriodTotals */
  amortizationByAsset: Record<string, number>
}>()

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID = 'I1-9-rows'

// ─── State ───────────────────────────────────────────────────────────────────

const rows = ref<I1AllocRow[]>([])

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _genRowId(): string {
  return `alloc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── Load from allResponses ──────────────────────────────────────────────────

function loadRows(): void {
  const item = props.allResponses.get(ITEM_ID)
  const raw = item?.remark ?? item?.conclusion
  if (!raw) {
    rows.value = []
    return
  }
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) { rows.value = []; return }
    rows.value = parsed.map((r: any) => ({
      rowId: r.rowId || _genRowId(),
      name: r.name || '',
      totalAmort: _getNum(r.totalAmort),
      managementExpense: _getNum(r.managementExpense),
      sellingExpense: _getNum(r.sellingExpense),
      manufacturingCost: _getNum(r.manufacturingCost),
      rdExpense: _getNum(r.rdExpense),
      otherExpense: _getNum(r.otherExpense),
    }))
  } catch {
    rows.value = []
  }
}

// ─── Watch allResponses to reload ────────────────────────────────────────────

watch(() => props.allResponses, () => { loadRows() }, { immediate: true })

// ─── Sync totalAmort from amortizationByAsset prop ───────────────────────────

watch(
  () => props.amortizationByAsset,
  (byAsset) => {
    if (!byAsset) return
    const assetNames = Object.keys(byAsset)

    // Update existing rows' totalAmort
    for (const row of rows.value) {
      if (row.name && byAsset[row.name] != null) {
        row.totalAmort = byAsset[row.name]
      }
    }

    // Add rows for new assets not yet in the alloc table
    const existingNames = new Set(rows.value.map(r => r.name))
    for (const name of assetNames) {
      if (!existingNames.has(name)) {
        rows.value.push({
          rowId: _genRowId(),
          name,
          totalAmort: byAsset[name],
          managementExpense: 0,
          sellingExpense: 0,
          manufacturingCost: 0,
          rdExpense: 0,
          otherExpense: 0,
        })
      }
    }
  },
  { immediate: true, deep: true },
)

// ─── Computed: Summary Row ───────────────────────────────────────────────────

const summaryRow = computed<I1AllocRow>(() => {
  let totalAmort = 0
  let mgmt = 0
  let sell = 0
  let mfg = 0
  let rd = 0
  let other = 0

  for (const row of rows.value) {
    totalAmort += row.totalAmort
    mgmt += row.managementExpense
    sell += row.sellingExpense
    mfg += row.manufacturingCost
    rd += row.rdExpense
    other += row.otherExpense
  }

  return {
    rowId: '__summary__',
    name: '合计',
    totalAmort,
    managementExpense: mgmt,
    sellingExpense: sell,
    manufacturingCost: mfg,
    rdExpense: rd,
    otherExpense: other,
    _isSummary: true,
  }
})

/** Display rows = detail rows + summary row at the bottom */
const displayRows = computed<I1AllocRow[]>(() => {
  return [...rows.value, summaryRow.value]
})

// ─── Formula Functions ───────────────────────────────────────────────────────

/** 合计 = 管理 + 销售 + 制造 + 研发 + 其他 */
function calcRowSum(row: I1AllocRow): number {
  return (
    _getNum(row.managementExpense) +
    _getNum(row.sellingExpense) +
    _getNum(row.manufacturingCost) +
    _getNum(row.rdExpense) +
    _getNum(row.otherExpense)
  )
}

/** 合计 must equal 摊销总额 (tolerance 0.01) */
function isRowBalanced(row: I1AllocRow): boolean {
  if (row._isSummary) return true
  const sum = calcRowSum(row)
  return Math.abs(sum - row.totalAmort) < 0.01
}

function getRowBalanceTooltip(row: I1AllocRow): string {
  if (row._isSummary || isRowBalanced(row)) return ''
  const sum = calcRowSum(row)
  const diff = sum - row.totalAmort
  return `分配合计(${fmtAmt(sum)}) ≠ 摊销总额(${fmtAmt(row.totalAmort)})，差额: ${fmtAmt(diff)}`
}

/** 分配比例 = 该行合计 / 总摊销合计 × 100% */
function fmtPercent(row: I1AllocRow): string {
  const totalAll = summaryRow.value.totalAmort
  if (!totalAll || totalAll === 0) return '—'
  const rowSum = row._isSummary
    ? calcRowSum(summaryRow.value)
    : calcRowSum(row)
  const pct = (rowSum / totalAll) * 100
  return `${pct.toFixed(2)}%`
}

// ─── Row Class ───────────────────────────────────────────────────────────────

function getRowClassName({ row }: { row: I1AllocRow }): string {
  if (row._isSummary) return 'summary-row'
  if (!isRowBalanced(row)) return 'error-row'
  return ''
}

// ─── Persist ─────────────────────────────────────────────────────────────────

function persist(): void {
  emit('save', ITEM_ID, rows.value)
}

// ─── Cell Change ─────────────────────────────────────────────────────────────

function onCellChange(_row: I1AllocRow): void {
  persist()
}

// ─── Row Management ──────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt(
      '请输入资产名称（建议与I1-10/I1-11摊销测算表资产名一致）',
      '新增资产行',
      {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '资产名称不能为空',
      },
    )
    if (!name) return

    // Check if the asset exists in amortizationByAsset for auto-fill totalAmort
    const totalAmort = props.amortizationByAsset?.[name] ?? 0

    rows.value.push({
      rowId: _genRowId(),
      name,
      totalAmort,
      managementExpense: 0,
      sellingExpense: 0,
      manufacturingCost: 0,
      rdExpense: 0,
      otherExpense: 0,
    })
    persist()
    ElMessage.success(`已新增资产行: ${name}`)
  } catch {
    // user cancelled
  }
}

function handleRemoveRow(rowId: string): void {
  const idx = rows.value.findIndex(r => r.rowId === rowId)
  if (idx >= 0) {
    rows.value.splice(idx, 1)
    persist()
  }
}

// ─── Import / Export ─────────────────────────────────────────────────────────

function handleImportExport(command: string): void {
  switch (command) {
    case 'exportTemplate':
      ElMessage.info('导出模板功能由 useI1ImportExport 处理，需在主入口集成')
      break
    case 'exportData':
      ElMessage.info('导出数据功能由 useI1ImportExport 处理，需在主入口集成')
      break
    case 'importData':
      ElMessage.info('导入数据功能由 useI1ImportExport 处理，需在主入口集成')
      break
  }
}

// ─── Navigation ──────────────────────────────────────────────────────────────

function navigateTo(wpCode: string): void {
  emit('navigate-sheet', wpCode)
}

// ─── Amount Formatter ────────────────────────────────────────────────────────

function fmtAmt(val: number | null | undefined): string {
  if (val == null) return '—'
  if (Math.abs(val) < 0.005) return '—'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
</script>

<style scoped>
.i1-tab-amort-alloc {
  padding: 16px;
  font-size: var(--wp-font-size, 13px);
}

/* 方法论上下文 — 琥珀色左边线 + 浅黄背景 */
.methodology-context {
  border-left: 4px solid #d97706;
  background: #fffbeb;
  padding: 12px 16px;
  margin-bottom: 16px;
  border-radius: 4px;
  font-size: 12px;
  color: #92400e;
  line-height: 1.8;
}
.methodology-context p {
  margin: 0;
}
.methodology-context strong {
  color: #78350f;
}

/* 工具栏 */
.toolbar {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
}
.toolbar-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

/* 表格 */
.alloc-table {
  font-size: var(--wp-font-size, 13px);
  margin-bottom: 16px;
}
.alloc-table :deep(.el-table__header th) {
  font-size: 12px;
  font-weight: 600;
  background: #f8fafc;
}
.alloc-table :deep(.el-input-number) {
  width: 100%;
}
.alloc-table :deep(.el-input-number .el-input__inner) {
  text-align: right;
}

/* 公式列头 — 虚线下划线 + cursor:help */
.formula-col-header {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  padding-bottom: 2px;
}

/* 公式值 */
.formula-value {
  font-variant-numeric: tabular-nums;
}

/* 合计行 */
.summary-text {
  font-weight: 700;
}
:deep(.summary-row) {
  background: #f0fdf4 !important;
  font-weight: 600;
}
:deep(.summary-row td) {
  background: #f0fdf4 !important;
}

/* 分配不平衡 — 红色警示 */
.alloc-error {
  color: var(--el-color-danger);
  font-weight: 700;
}
:deep(.error-row) {
  background: #fef2f2 !important;
}
:deep(.error-row td) {
  background: #fef2f2 !important;
}

/* 跳转目标 */
.jump-targets {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
}
.jump-label {
  font-size: 12px;
  color: var(--el-text-color-secondary);
}

/* 编制提示 */
.compile-hint {
  margin-top: 12px;
  font-size: 12px;
  color: var(--el-text-color-secondary);
  border-top: 1px solid var(--el-border-color-lighter);
  padding-top: 12px;
}
.compile-hint summary {
  cursor: pointer;
  font-weight: 500;
}
.compile-hint ul {
  padding-left: 20px;
  margin-top: 8px;
  line-height: 1.8;
}
</style>
