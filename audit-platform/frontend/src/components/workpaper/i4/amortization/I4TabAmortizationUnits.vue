<template>
  <div class="i4-tab-amortization-units">
    <!-- 蓝色渐变引导区 -->
    <div class="guide-area">
      <div class="guide-grid">
        <div class="guide-step"><span class="step-num">①</span> 录入项目基础数据（名称/原始金额/总预计工作量）</div>
        <div class="guide-step"><span class="step-num">②</span> 逐月填入实际工作量，系统自动计算月摊销</div>
        <div class="guide-step"><span class="step-num">③</span> 月摊销 = 原始金额 × (当月工作量 ÷ 总预计工作量)</div>
        <div class="guide-step"><span class="step-num">④</span> 底部合计汇总 + 摊销进度跟踪</div>
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

    <!-- 横向12月矩阵表 (28列): 项目|原始金额|总工作量|M1量|M1摊|...M12量|M12摊|年合计|累计|进度 -->
    <div class="matrix-wrapper">
      <el-table
        :data="rows"
        border
        stripe
        size="small"
        class="amort-table"
        :max-height="560"
        show-summary
        :summary-method="getSummary"
      >
        <!-- 固定列 -->
        <el-table-column prop="itemName" label="项目名称" min-width="140" fixed>
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input v-model="row.itemName" size="small" @blur="onCellBlur($index)" />
            </template>
            <span v-else>{{ row.itemName }}</span>
          </template>
        </el-table-column>

        <el-table-column prop="originalAmount" label="原始金额" width="120" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
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

        <el-table-column prop="totalUnits" label="总工作量" width="100" align="right">
          <template #default="{ row, $index }">
            <template v-if="!isReadonly">
              <el-input-number
                v-model="row.totalUnits"
                :controls="false"
                :min="0"
                size="small"
                @change="recalcRow($index)"
              />
            </template>
            <span v-else>{{ row.totalUnits }}</span>
          </template>
        </el-table-column>

        <!-- M1~M12: 每月一对列(工作量 + 摊销额) -->
        <el-table-column
          v-for="m in 12"
          :key="`m${m}`"
          :label="`${m}月`"
        >
          <el-table-column :label="`量`" width="70" align="right">
            <template #default="{ row, $index }">
              <template v-if="!isReadonly">
                <el-input-number
                  :model-value="row.monthlyUnits[m - 1]"
                  :controls="false"
                  size="small"
                  :min="0"
                  @change="(v: number) => onUnitsChange($index, m - 1, v)"
                />
              </template>
              <span v-else>{{ row.monthlyUnits[m - 1] || '-' }}</span>
            </template>
          </el-table-column>
          <el-table-column :label="`摊`" width="90" align="right">
            <template #default="{ row }">
              <span class="formula-cell" title="= 原始金额 × (当月量 ÷ 总量)">
                {{ fmtAmt(row.monthlyAmort[m - 1]) }}
              </span>
            </template>
          </el-table-column>
        </el-table-column>

        <!-- 汇总列 -->
        <el-table-column label="年合计" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= Σ(M1摊~M12摊)">{{ fmtAmt(row.yearTotal) }}</span>
          </template>
        </el-table-column>

        <el-table-column label="累计摊销" width="110" align="right">
          <template #default="{ row }">
            <span class="formula-cell" title="= 期初累计 + 年合计">{{ fmtAmt(row.accumulatedAmort) }}</span>
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
            <template v-if="!isReadonly">
              <el-input v-model="row.remark" size="small" @blur="onCellBlur($index)" />
            </template>
            <span v-else>{{ row.remark }}</span>
          </template>
        </el-table-column>

        <!-- 操作列 -->
        <el-table-column v-if="!isReadonly" label="操作" width="60" align="center" fixed="right">
          <template #default="{ $index }">
            <el-button type="danger" link size="small" @click="handleDeleteRow($index)">删除</el-button>
          </template>
        </el-table-column>
      </el-table>
    </div>

    <!-- 编制提示 -->
    <details class="compile-hint">
      <summary>编制提示</summary>
      <ul>
        <li>工作量法公式：月摊销 = 原始金额 × (当月工作量 ÷ 总预计工作量)</li>
        <li>总工作量不能为0（系统自动拦截）</li>
        <li>适用场景：模具费按产量分摊、矿区权益按采矿量分摊等</li>
        <li>各月实际工作量需手工填入或从生产数据导入</li>
        <li>年合计 = Σ各月摊销额，底部合计行自动汇总</li>
      </ul>
    </details>

    <!-- 隐藏的文件上传input -->
    <input ref="fileInputRef" type="file" accept=".xlsx,.xls" style="display:none" @change="onFileSelected" />
  </div>
</template>

<script setup lang="ts">
/**
 * I4TabAmortizationUnits.vue — I4-7 工作量法摊销测算表（21公式）
 *
 * 横向12月矩阵: 项目|原始金额|总工作量|M1量|M1摊|...M12量|M12摊|年合计|累计|进度
 * Formula: 月摊销 = 原始金额 × (当月量 ÷ 总量) (calcUnitsOfProductionAmort)
 * Dynamic rows + import/export
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 4.8
 * Requirements: 6.1-6.6
 */
import { ref, computed, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import { ArrowDown } from '@element-plus/icons-vue'
import { calcUnitsOfProductionAmort, calcAmortizationRate } from '../../composables/useI4AmortizationEngine'
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

interface UnitsAmortRow {
  rowId: string
  itemName: string
  originalAmount: number
  totalUnits: number
  monthlyUnits: number[]      // M1~M12 每月实际工作量
  monthlyAmort: number[]      // M1~M12 对应摊销额
  yearTotal: number           // = Σ monthlyAmort
  priorAccumulated: number    // 期初累计摊销
  accumulatedAmort: number    // = priorAccumulated + yearTotal
  amortRate: number           // = accumulatedAmort / originalAmount
  remark: string
}

// ─── State ───────────────────────────────────────────────────────────────────

const PREFIX = 'I4-7'
const rows = ref<UnitsAmortRow[]>([])
const fileInputRef = ref<HTMLInputElement | null>(null)

// ─── Import/Export ───────────────────────────────────────────────────────────

const importExport = useI4ImportExport({
  wpId: computed(() => props.wpId),
  projectId: computed(() => props.projectId),
  onImported: () => _load(),
})

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

function _ensureRow(r: any): UnitsAmortRow {
  const monthlyUnits = Array.isArray(r.monthlyUnits) ? r.monthlyUnits.slice(0, 12) : new Array(12).fill(0)
  while (monthlyUnits.length < 12) monthlyUnits.push(0)
  const originalAmount = r.originalAmount ?? 0
  const totalUnits = r.totalUnits ?? 0
  const monthlyAmort = monthlyUnits.map((u: number) =>
    calcUnitsOfProductionAmort(originalAmount, u, totalUnits),
  )
  const yearTotal = calcSubtotal(monthlyAmort)
  const priorAccumulated = r.priorAccumulated ?? 0
  const accumulatedAmort = priorAccumulated + yearTotal
  const amortRate = originalAmount > 0 ? calcAmortizationRate(accumulatedAmort, originalAmount) : 0

  return {
    rowId: r.rowId || `i4u-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    itemName: r.itemName ?? '',
    originalAmount,
    totalUnits,
    monthlyUnits,
    monthlyAmort,
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
  _recalcAll(row)
  _persist()
}

function _recalcAll(row: UnitsAmortRow): void {
  row.monthlyAmort = row.monthlyUnits.map((u) =>
    calcUnitsOfProductionAmort(row.originalAmount, u, row.totalUnits),
  )
  row.yearTotal = calcSubtotal(row.monthlyAmort)
  row.accumulatedAmort = row.priorAccumulated + row.yearTotal
  row.amortRate = row.originalAmount > 0
    ? calcAmortizationRate(row.accumulatedAmort, row.originalAmount)
    : 0
}

function onUnitsChange(idx: number, monthIdx: number, val: number): void {
  const row = rows.value[idx]
  if (!row) return
  row.monthlyUnits[monthIdx] = val ?? 0
  _recalcAll(row)
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
    const newRow: UnitsAmortRow = {
      rowId: `i4u-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
      itemName: name,
      originalAmount: 0,
      totalUnits: 0,
      monthlyUnits: new Array(12).fill(0),
      monthlyAmort: new Array(12).fill(0),
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

function getSummary({ columns, data }: { columns: any[]; data: UnitsAmortRow[] }): string[] {
  const sums: string[] = []
  columns.forEach((col: any, colIdx: number) => {
    if (colIdx === 0) { sums[colIdx] = '合计'; return }
    const prop = col.property
    if (prop === 'originalAmount') {
      sums[colIdx] = fmtAmt(calcSubtotal(data.map((r) => r.originalAmount)))
    } else {
      sums[colIdx] = ''
    }
  })
  return sums
}

// ─── Import/Export Actions ───────────────────────────────────────────────────

function handleExportTemplate(): void { importExport.exportTemplate('I4-7') }
function handleExportData(): void { importExport.exportData('I4-7') }
function triggerImport(): void { fileInputRef.value?.click() }
function onFileSelected(e: Event): void {
  const file = (e.target as HTMLInputElement).files?.[0]
  if (file) importExport.importData('I4-7', file)
  if (fileInputRef.value) fileInputRef.value.value = ''
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

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
.i4-tab-amortization-units { padding: 16px; font-size: var(--wp-font-size, 13px); }

/* 蓝色渐变引导区 */
.guide-area {
  background: linear-gradient(135deg, #e8f4fd 0%, #d4ecfb 100%);
  border-radius: 8px; padding: 16px; margin-bottom: 16px;
}
.guide-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 8px; }
.guide-step { display: flex; align-items: flex-start; gap: 6px; font-size: var(--wp-font-size, 13px); }
.step-num { font-weight: 700; color: var(--el-color-primary); min-width: 20px; }

/* 工具栏 */
.toolbar-row {
  display: flex; align-items: center; gap: 12px; margin-bottom: 12px;
}
.row-count { font-size: 12px; color: var(--el-text-color-secondary); margin-left: auto; }

/* 矩阵表容器 */
.matrix-wrapper { overflow-x: auto; margin-bottom: 16px; }
.amort-table { font-size: 12px; }

/* 公式列 */
.formula-cell {
  border-bottom: 1px dashed var(--el-border-color);
  cursor: help;
  font-variant-numeric: tabular-nums;
}
.amount-cell { font-variant-numeric: tabular-nums; }

/* 编制提示 */
.compile-hint { margin-top: 12px; font-size: 12px; color: var(--el-text-color-secondary); }
.compile-hint summary { cursor: pointer; font-weight: 500; }
.compile-hint ul { padding-left: 20px; margin-top: 8px; }
.compile-hint li { margin-bottom: 4px; }
</style>
