<template>
  <div class="i4-tab-amortization-straight">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 逐项录入长期待摊费用基础数据（项目/原始金额/总月数）</div>
        <div class="guide-step"><span class="step-num">②</span> 系统自动计算月摊销额 = 原始金额 ÷ 摊销总月数</div>
        <div class="guide-step"><span class="step-num">③</span> 横向12月矩阵展示逐月摊销情况，底部合计自动汇总</div>
        <div class="guide-step"><span class="step-num">④</span> 摊销进度条直观显示各项目摊销完成度</div>
      </div>
    </div>

    <!-- 导入导出 -->
    <div class="toolbar-row">
      <el-dropdown trigger="click" :disabled="isReadonly">
        <el-button size="small" type="default">
          导入导出 <el-icon class="el-icon--right"><ArrowDown /></el-icon>
        </el-button>
        <template #dropdown>
          <el-dropdown-menu>
            <el-dropdown-item @click="handleExportTemplate">导出模板</el-dropdown-item>
            <el-dropdown-item @click="handleExportData">导出数据</el-dropdown-item>
            <el-dropdown-item @click="triggerImport">导入数据</el-dropdown-item>
          </el-dropdown-menu>
        </template>
      </el-dropdown>
      <el-button size="small" type="primary" :disabled="isReadonly" @click="handleAddRow">
        + 新增项目
      </el-button>
      <span class="row-count">共 {{ rows.length }} 个项目</span>
    </div>

    <!-- 横向12月矩阵表 (28列) -->
    <div class="matrix-wrapper">
      <el-table
        :data="displayRows"
        border
        stripe
        size="small"
        class="amort-table"
        :max-height="560"
        show-summary
        :summary-method="getSummary"
      >
        <!-- 固定列：项目信息 -->
        <el-table-column prop="itemName" label="项目名称" min-width="140" fixed>
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <el-input v-model="row.itemName" size="small" @blur="onCellBlur($index)" />
            </template>
            <span v-else>{{ row.itemName }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="originalAmount" label="原始金额" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <el-input-number
                v-model="row.originalAmount"
                :controls="false"
                size="small"
                :precision="2"
                @change="recalcRow($index)"
              />
            </template>
            <span v-else class="amount-cell">{{ fmtAmt(row.originalAmount) }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="totalMonths" label="总月数" width="80" align="center">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <el-input-number
                v-model="row.totalMonths"
                :controls="false"
                :min="1"
                size="small"
                @change="recalcRow($index)"
              />
            </template>
            <span v-else>{{ row.totalMonths }}</span>
          </template>
        </el-table-column>

        <el-table-column label="月摊销额" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 原始金额 ÷ 摊销总月数">
              {{ fmtAmt(row.monthlyAmort) }}
            </span>
          </template>
        </el-table-column>

        <!-- M1 ~ M12 动态列 -->
        <el-table-column
          v-for="m in 12"
          :key="`m${m}`"
          :label="`${m}月`"
          width="90"
          align="right"
        >
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly && isMonthEditable(row, m)">
              <el-input-number
                :model-value="row.monthly[m - 1]"
                :controls="false"
                size="small"
                :precision="2"
                @change="(v: number) => onMonthChange($index, m - 1, v)"
              />
            </template>
            <span v-else :class="['amount-cell', { 'zero-cell': row.monthly[m - 1] === 0 }]">
              {{ row.monthly[m - 1] ? fmtAmt(row.monthly[m - 1]) : '-' }}
            </span>
          </template>
        </el-table-column>

        <!-- 汇总列 -->
        <el-table-column label="年合计" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= Σ(M1~M12)">{{ fmtAmt(row.yearTotal) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="累计摊销" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 历史累计 + 本年合计">{{ fmtAmt(row.accumulatedAmort) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="摊销进度" width="100" align="center">
          <template #default="{ row }">
            <el-progress
              :percentage="Math.min(100, Math.round((row.amortRate ?? 0) * 100))"
              :stroke-width="6"
              :color="getProgressColor(row.amortRate)"
              :show-text="true"
              :format="(p: number) => `${p}%`"
            />
          </template>
        </el-table-column>

        <el-table-column prop="remark" label="备注" width="120">
          <template #default="{ row, $index }">
            <template v-if="!row._isTotal && !isReadonly">
              <el-input v-model="row.remark" size="small" @blur="onCellBlur($index)" />
            </template>
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ $index, row }">
            <el-button
              v-if="!row._isTotal"
              type="danger"
              link
              size="small"
              @click="handleDeleteRow($index)"
            >删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>直线法公式：月摊销额 = 原始金额 ÷ 摊销总月数</li>
        <li>横向12月矩阵：默认按月摊销额均匀填充，可手动修改个别月份</li>
        <li>摊销进度 = 累计已摊月数 ÷ 总月数</li>
        <li>年合计自动汇总M1~M12，底部合计行汇总所有项目</li>
        <li>支持从I4-2明细表自动带入项目基础信息</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传input -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabAmortizationStraight.vue — I4-6 直线法摊销测算表（39公式）
 *
 * 横向12月矩阵 (28列): 项目|原始金额|月摊销额|M1~M12|年合计|累计摊销|摊销进度|备注
 * Formula: 月摊销额 = 原始金额 ÷ 摊销总月数 (calcStraightLineAmort)
 * Dynamic rows + import/export
 * Subtotals per month column
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 4.7
 * Requirements: 6.1-6.6
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox, ElMessage } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { calcStraightLineAmort, calcAmortizationRate } from '../../composables/useI4AmortizationEngine'
import { calcSubtotal } from '../../composables/useI4FormulaEngine'
import { useI4ImportExport } from '../../composables/useI4ImportExport'

// ─── Props ───────────────────────────────────────────────────────────────────

const props = defineProps<{
  wpId: string
  projectId: string
  allResponses: Map<string, any>
  isReadonly: boolean
}>()

// ─── Emits ───────────────────────────────────────────────────────────────────

const emit = defineEmits<{
  'navigate-sheet': [sheetName: string]
  'save': [itemId: string, value: any]
}>()

// ─── Types ───────────────────────────────────────────────────────────────────

interface AmortRow {
  rowId: string
  itemName: string
  originalAmount: number
  totalMonths: number
  monthlyAmort: number        // = originalAmount / totalMonths
  monthly: number[]           // M1~M12
  yearTotal: number           // = Σ monthly
  priorAccumulated: number    // 期初累计摊销
  accumulatedAmort: number    // = priorAccumulated + yearTotal
  amortRate: number           // = accumulatedAmort / originalAmount
  remark: string
  _isTotal?: boolean
}

// ─── State ───────────────────────────────────────────────────────────────────

const PREFIX = 'I4-6'
const rows = ref<AmortRow[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── Import/Export ───────────────────────────────────────────────────────────

const importExport = useI4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onImported: () => _load(),
})

// ─── Display rows (without _isTotal for the table's built-in summary) ────────

const displayRows = computed(() => rows.value)

// ─── Load ────────────────────────────────────────────────────────────────────

function _load(): void {
  const item = props.allResponses.get(`${PREFIX}-rows`)
  if (item?.remark) {
    try {
      const parsed = JSON.parse(item.remark)
      rows.value = Array.isArray(parsed) ? parsed.map(_ensureRow) : []
    } catch { rows.value = [] }
  } else {
    rows.value = []
  }
}

function _ensureRow(r: any): AmortRow {
  const monthly = Array.isArray(r.monthly) ? r.monthly.slice(0, 12) : new Array(12).fill(0)
  while (monthly.length < 12) monthly.push(0)
  const totalMonths = r.totalMonths > 0 ? r.totalMonths : 1
  const originalAmount = r.originalAmount ?? 0
  const monthlyAmort = calcStraightLineAmort(originalAmount, totalMonths)
  const yearTotal = calcSubtotal(monthly)
  const priorAccumulated = r.priorAccumulated ?? 0
  const accumulatedAmort = priorAccumulated + yearTotal
  const amortRate = originalAmount > 0 ? calcAmortizationRate(accumulatedAmort, originalAmount) : 0

  return {
    rowId: r.rowId || `i4s-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    itemName: r.itemName ?? '',
    originalAmount,
    totalMonths,
    monthlyAmort,
    monthly,
    yearTotal,
    priorAccumulated,
    accumulatedAmort,
    amortRate,
    remark: r.remark ?? '',
  }
}

watch(() => props.allResponses, () => _load(), { immediate: true })

// ─── Recalculate ─────────────────────────────────────────────────────────────

function recalcRow(idx: number): void {
  const row = rows.value[idx]
  if (!row) return
  row.monthlyAmort = calcStraightLineAmort(row.originalAmount, row.totalMonths)
  // 自动填充所有month为 monthlyAmort（如果当前都是0或全等于旧值）
  const allZeroOrSame = row.monthly.every((v) => v === 0)
  if (allZeroOrSame) {
    row.monthly = new Array(12).fill(row.monthlyAmort)
  }
  _recalcDerived(row)
  _persist()
}

function _recalcDerived(row: AmortRow): void {
  row.yearTotal = calcSubtotal(row.monthly)
  row.accumulatedAmort = row.priorAccumulated + row.yearTotal
  row.amortRate = row.originalAmount > 0
    ? calcAmortizationRate(row.accumulatedAmort, row.originalAmount)
    : 0
}

function onMonthChange(idx: number, monthIdx: number, val: number): void {
  const row = rows.value[idx]
  if (!row) return
  row.monthly[monthIdx] = val ?? 0
  _recalcDerived(row)
  _persist()
}

function onCellBlur(_idx: number): void {
  _persist()
}

// ─── CRUD ────────────────────────────────────────────────────────────────────

async function handleAddRow(): Promise<void> {
  try {
    const { value: name } = await ElMessageBox.prompt('请输入费用项目名称', '新增项目', {
      confirmButtonText: '确认',
      cancelButtonText: '取消',
      inputPattern: /\S+/,
      inputErrorMessage: '名称不能为空',
    })
    const newRow: AmortRow = {
      rowId: `i4s-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      itemName: name,
      originalAmount: 0,
      totalMonths: 12,
      monthlyAmort: 0,
      monthly: new Array(12).fill(0),
      yearTotal: 0,
      priorAccumulated: 0,
      accumulatedAmort: 0,
      amortRate: 0,
      remark: '',
    }
    rows.value.push(newRow)
    _persist()
  } catch { /* cancel */ }
}

function handleDeleteRow(idx: number): void {
  rows.value.splice(idx, 1)
  _persist()
}

// ─── Summary ─────────────────────────────────────────────────────────────────

function getSummary({ columns, data }: { columns: any[]; data: AmortRow[] }): string[] {
  const sums: string[] = []
  columns.forEach((col: any, colIdx: number) => {
    if (colIdx === 0) { sums[colIdx] = '合计'; return }
    const prop = col.property
    if (prop === 'originalAmount') {
      sums[colIdx] = fmtAmt(calcSubtotal(data.map((r) => r.originalAmount)))
    } else if (prop === 'remark' || prop === 'itemName') {
      sums[colIdx] = ''
    } else {
      sums[colIdx] = ''
    }
  })
  return sums
}

// ─── Import/Export Actions ───────────────────────────────────────────────────

function handleExportTemplate(): void { importExport.exportTemplate('I4-6') }
function handleExportData(): void { importExport.exportData('I4-6') }
function triggerImport(): void { fileInputRef.value?.click() }
function onFileSelected(e: Event): void {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) importExport.importData('I4-6', file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function isMonthEditable(row: AmortRow, _m: number): boolean {
  return row.originalAmount > 0 && row.totalMonths > 0
}

function fmtAmt(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function getProgressColor(rate: number | undefined): string {
  if (!rate) return '#909399'
  if (rate >= 1) return '#67c23a'
  if (rate >= 0.8) return '#e6a23c'
  return '#409eff'
}

// ─── Persistence ─────────────────────────────────────────────────────────────

function _persist(): void {
  emit('save', `${PREFIX}-rows`, JSON.stringify(rows.value))
}
</script>

<style scoped>
.i4-tab-amortization-straight { padding: 16px; font-size: 13px; }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: 13px; }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }

/* 工具栏 */
.toolbar-row {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px;
}
.row-count { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }

/* 矩阵表容器 */
.matrix-wrapper { overflow-x: auto; margin-bottom: 16px; }
.amort-table { font-size: 12px; }

/* 公式列（虚线下划线 + cursor:help） */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.amount-cell { font-variant-numeric: tabular-nums; }
.zero-cell { color: var(--el-text-color-placeholder); }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
