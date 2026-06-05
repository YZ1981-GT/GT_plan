<template>
  <div class="gt-multi-year-compare">
    <!-- 控制栏 -->
    <div class="gt-myc-controls">
      <div class="gt-myc-controls__left">
        <span class="gt-myc-label">年度选择</span>
        <el-select
          v-model="selectedYears"
          multiple
          :multiple-limit="5"
          placeholder="选择年度（最多5年）"
          size="small"
          style="width: 320px"
          @change="onYearsChange"
        >
          <el-option
            v-for="yr in availableYears"
            :key="yr"
            :label="`${yr}年`"
            :value="yr"
          />
        </el-select>
      </div>
      <div class="gt-myc-controls__center">
        <el-select v-model="rowFilter" size="small" style="width: 160px" @change="onFilterChange">
          <el-option label="显示全部行" value="all" />
          <el-option label="仅有数据行" value="nonzero" />
          <el-option label="仅合计行" value="total" />
          <el-option label="仅变动行" value="changed" />
        </el-select>
      </div>
      <div class="gt-myc-controls__right">
        <el-radio-group v-model="reportType" size="small" @change="fetchData">
          <el-radio-button value="balance_sheet">资产负债表</el-radio-button>
          <el-radio-button value="income_statement">利润表</el-radio-button>
          <el-radio-button value="cash_flow_statement">现金流量表</el-radio-button>
        </el-radio-group>
        <el-button size="small" @click="onExport" :loading="exporting" style="margin-left: 12px">
          📥 导出Excel
        </el-button>
      </div>
    </div>

    <!-- 数据表格 -->
    <el-table
      v-loading="loading"
      ref="mycTableRef"
      :data="filteredTableData"
      border
      size="small"
      style="width: 100%"
      :max-height="600"
      :header-cell-style="{ background: '#f8f6fb', color: '#333', whiteSpace: 'nowrap', fontSize: '12px' }"
      :row-class-name="rowClassName"
      :cell-class-name="cellClassName"
      @cell-click="onCellClick"
      @cell-dblclick="onCellDblClick"
      @cell-contextmenu="onCellContextMenu"
    >
      <!-- 项目名称列 (fixed) -->
      <el-table-column prop="item_name" label="项目" fixed min-width="260" :resizable="true">
        <template #default="{ row }">
          <span style="font-size: 13px">{{ row.item_name }}</span>
        </template>
      </el-table-column>

      <!-- 动态年度列 -->
      <template v-for="(yr, idx) in sortedYears" :key="yr">
        <!-- 金额列 -->
        <el-table-column :label="`${yr}年`" align="right" min-width="140" :resizable="true">
          <template #default="{ row }">
            <span class="gt-amt">{{ formatAmount(row.values[String(yr)]) }}</span>
          </template>
        </el-table-column>
        <!-- YoY 变动列（第一年无变动率） -->
        <el-table-column
          v-if="idx > 0"
          :label="`${yr}年同比`"
          align="right"
          width="200"
          :resizable="true"
        >
          <template #default="{ row }">
            <span :class="getChangeClass(row.yoy_changes[String(yr)])">
              {{ formatChange(row.yoy_changes[String(yr)]) }}
              <span v-if="row.yoy_changes[String(yr)] != null" class="gt-myc-arrow">
                {{ getArrow(row.yoy_changes[String(yr)]) }}
              </span>
            </span>
          </template>
        </el-table-column>
      </template>
    </el-table>

    <!-- 空状态 -->
    <div v-if="!loading && filteredTableData.length === 0 && selectedYears.length > 0" class="gt-myc-empty">
      <span>暂无数据，请确认已生成对应年度的报表</span>
    </div>

    <!-- 右键菜单 -->
    <teleport to="body">
      <div
        v-if="ctxMenu.visible"
        class="gt-myc-ctx-menu"
        :style="{ left: ctxMenu.x + 'px', top: ctxMenu.y + 'px' }"
        @click.stop
      >
        <div class="gt-myc-ctx-item" @click="onCtxCopy">📋 复制</div>
        <div class="gt-myc-ctx-item" @click="onCtxSum">∑ 求和</div>
        <div class="gt-myc-ctx-item" @click="onCtxCompare">📊 对比差异</div>
        <div class="gt-myc-ctx-divider" />
        <div class="gt-myc-ctx-item" @click="onCtxDrill">🔍 查看穿透</div>
        <div class="gt-myc-ctx-item" @click="onCtxGoReport">📈 跳转报表</div>
        <div class="gt-myc-ctx-item" @click="onCtxViewFormula">ƒx 查看公式</div>
        <div class="gt-myc-ctx-divider" />
        <div class="gt-myc-ctx-item" @click="onCtxExportSelection">📥 导出选区</div>
      </div>
    </teleport>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { reports as reportsApi, reportConfig as rcApi } from '@/services/apiPaths'
import { handleApiError } from '@/utils/errorHandler'
import { exportData, type ExcelColumn } from '@/composables/useExcelIO'
import { useCellSelection } from '@/composables/useCellSelection'

/* ── Props ── */
const props = defineProps<{
  projectId: string
  currentYear: number
}>()

const emit = defineEmits<{
  drill: [payload: { reportType: string; rowCode: string }]
}>()

/* ── State ── */
const loading = ref(false)
const exporting = ref(false)
const reportType = ref<string>('balance_sheet')
const selectedYears = ref<number[]>([])
const tableData = ref<any[]>([])
const rowFilter = ref<string>('all')
const mycTableRef = ref<any>(null)

// 单元格选中支持
const cellSel = useCellSelection()

function cellClassName({ rowIndex, columnIndex }: any) {
  return cellSel.cellClassName({ rowIndex, columnIndex })
}

function onCellClick(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  ctxMenu.value.visible = false
  const rowIdx = filteredTableData.value.indexOf(row)
  const colIdx = column.index ?? 0
  if (rowIdx < 0) return
  const value = row.values?.[String(sortedYears.value[colIdx - 1])] ?? row.item_name ?? ''
  cellSel.selectCell(rowIdx, colIdx, value, event.ctrlKey || event.metaKey, event.shiftKey)
}

// 右键菜单
const ctxMenu = ref({ visible: false, x: 0, y: 0 })

function onCellContextMenu(row: any, column: any, _cell: HTMLElement, event: MouseEvent) {
  event.preventDefault()
  const rowIdx = filteredTableData.value.indexOf(row)
  const colIdx = column.index ?? 0
  if (rowIdx >= 0 && !cellSel.isCellSelected(rowIdx, colIdx)) {
    const value = row.values?.[String(sortedYears.value[colIdx - 1])] ?? row.item_name ?? ''
    cellSel.selectCell(rowIdx, colIdx, value, false)
  }
  ctxMenu.value = { visible: true, x: event.clientX, y: event.clientY }
}

function onCellDblClick(row: any, column: any) {
  // 双击金额列 → emit 穿透事件让父组件跳转到对应报表
  if (column.index > 0 && row.row_code) {
    emit('drill', { reportType: reportType.value, rowCode: row.row_code })
  }
}

function onCtxCopy() {
  const cells = cellSel.selectedCells.value
  if (!cells.length) return
  const text = cells.map(c => c.value ?? '-').join('\t')
  navigator.clipboard.writeText(text)
  ElMessage.success('已复制')
  ctxMenu.value.visible = false
}

function onCtxSum() {
  const cells = cellSel.selectedCells.value
  const nums = cells.map(c => Number(c.value)).filter(n => !isNaN(n) && n !== 0)
  const sum = nums.reduce((s, n) => s + n, 0)
  ElMessage.info(`选中 ${cells.length} 格，合计：${sum.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}`)
  ctxMenu.value.visible = false
}

function onCtxCompare() {
  const cells = cellSel.selectedCells.value
  if (cells.length < 2) { ElMessage.warning('请选中至少 2 个单元格'); ctxMenu.value.visible = false; return }
  const vals = cells.map(c => Number(c.value) || 0)
  const diff = vals[0] - vals[1]
  const pct = vals[1] !== 0 ? ((diff / Math.abs(vals[1])) * 100).toFixed(2) + '%' : '-'
  ElMessage.info(`差异：${diff.toLocaleString('zh-CN', { maximumFractionDigits: 2 })}，变动率：${pct}`)
  ctxMenu.value.visible = false
}

function onCtxDrill() {
  const cells = cellSel.selectedCells.value
  if (!cells.length) { ctxMenu.value.visible = false; return }
  const row = filteredTableData.value[cells[0].row]
  if (row?.row_code) {
    emit('drill', { reportType: reportType.value, rowCode: row.row_code })
  }
  ctxMenu.value.visible = false
}

function onCtxGoReport() {
  emit('drill', { reportType: reportType.value, rowCode: '' })
  ctxMenu.value.visible = false
}

function onCtxViewFormula() {
  const cells = cellSel.selectedCells.value
  if (!cells.length) { ctxMenu.value.visible = false; return }
  const row = filteredTableData.value[cells[0].row]
  ElMessage.info(`行次 ${row?.row_code || '-'}，公式需在公式管理器中查看`)
  ctxMenu.value.visible = false
}

function onCtxExportSelection() {
  const cells = cellSel.selectedCells.value
  if (!cells.length) { ElMessage.warning('请先选中单元格'); ctxMenu.value.visible = false; return }
  const text = cells.map(c => c.value ?? '-').join('\n')
  navigator.clipboard.writeText(text)
  ElMessage.success(`已导出 ${cells.length} 个单元格到剪贴板`)
  ctxMenu.value.visible = false
}

// 拖选绑定
cellSel.setupTableDrag(mycTableRef, (rowIdx: number, colIdx: number) => {
  const row = filteredTableData.value[rowIdx]
  if (!row) return null
  if (colIdx === 0) return row.item_name
  return row.values?.[String(sortedYears.value[colIdx - 1])] ?? null
})
/* ── Computed ── */
const availableYears = computed(() => {
  const current = props.currentYear || new Date().getFullYear()
  const years: number[] = []
  for (let i = current; i >= current - 9; i--) {
    years.push(i)
  }
  return years
})

const sortedYears = computed(() => [...selectedYears.value].sort((a, b) => a - b))

// 筛选后的表格数据
const filteredTableData = computed(() => {
  if (rowFilter.value === 'all') return tableData.value
  return tableData.value.filter((row: any) => {
    if (rowFilter.value === 'nonzero') {
      // 任一年度有非零值
      if (!row.values) return false
      return Object.values(row.values).some((v: any) => v != null && v !== 0)
    }
    if (rowFilter.value === 'total') {
      return row.is_total_row
    }
    if (rowFilter.value === 'changed') {
      // 有同比变动数据
      if (!row.yoy_changes) return false
      return Object.values(row.yoy_changes).some((v: any) => v != null && v !== 0)
    }
    return true
  })
})

function onFilterChange() { /* reactive, no action needed */ }

/* ── Methods ── */
function onYearsChange() {
  if (selectedYears.value.length >= 2) {
    fetchData()
  } else {
    tableData.value = []
  }
}

async function fetchData() {
  if (selectedYears.value.length < 2) {
    tableData.value = []
    return
  }

  loading.value = true
  try {
    const url = reportsApi.multiYear(props.projectId, sortedYears.value, reportType.value)
    const resp = await http.get(url)
    const rows = resp.data?.rows || resp.data?.data?.rows || resp.data || []
    if (Array.isArray(rows) && rows.length > 0) {
      tableData.value = rows
    } else {
      // Fallback：从 report_config 加载行结构（始终有行次定义）
      try {
        const configResp = await http.get(rcApi.list, {
          params: { report_type: reportType.value, applicable_standard: 'soe_standalone' },
        })
        const configs = configResp.data?.data || configResp.data || []
        tableData.value = (Array.isArray(configs) ? configs : []).map((r: any) => ({
          item_name: r.row_name || '',
          row_code: r.row_code || '',
          indent_level: r.indent_level || 0,
          is_total_row: r.is_total_row || false,
          values: sortedYears.value.map(() => null),
          yoy: sortedYears.value.slice(1).map(() => null),
        }))
      } catch {
        tableData.value = []
      }
    }
  } catch (err: any) {
    handleApiError(err, '查询')
    tableData.value = []
  } finally {
    loading.value = false
  }
}

function formatAmount(val: number | null | undefined): string {
  if (val == null || val === 0) return '-'
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function formatChange(val: number | null | undefined): string {
  if (val == null) return '-'
  return `${val >= 0 ? '+' : ''}${val.toFixed(2)}%`
}

function getArrow(val: number | null | undefined): string {
  if (val == null) return ''
  if (val > 0) return '↑'
  if (val < 0) return '↓'
  return '→'
}

function getChangeClass(val: number | null | undefined): string {
  if (val == null) return 'gt-myc-change'
  const abs = Math.abs(val)
  if (abs >= 20) return 'gt-myc-change gt-myc-change--alert'
  if (val > 0) return 'gt-myc-change gt-myc-change--up'
  if (val < 0) return 'gt-myc-change gt-myc-change--down'
  return 'gt-myc-change'
}

function rowClassName({ row }: { row: any }): string {
  // 检查是否有任何 YoY 变动 >= 20%
  if (row.yoy_changes) {
    for (const key of Object.keys(row.yoy_changes)) {
      const val = row.yoy_changes[key]
      if (val != null && Math.abs(val) >= 20) {
        return 'gt-myc-row--highlight'
      }
    }
  }
  return ''
}

async function onExport() {
  if (tableData.value.length === 0) {
    ElMessage.warning('暂无数据可导出')
    return
  }

  exporting.value = true
  try {
    const reportTypeLabel: Record<string, string> = {
      balance_sheet: '资产负债表',
      income_statement: '利润表',
      cash_flow_statement: '现金流量表',
    }

    // 构建列定义
    const columns: ExcelColumn[] = [
      { key: 'item_name', header: '项目', width: 30 },
    ]

    for (let i = 0; i < sortedYears.value.length; i++) {
      const yr = sortedYears.value[i]
      columns.push({ key: `val_${yr}`, header: `${yr}年金额`, width: 18 })
      if (i > 0) {
        columns.push({ key: `yoy_${yr}`, header: `${yr}年同比变动率(%)`, width: 18 })
      }
    }

    // 构建数据
    const data = tableData.value.map(row => {
      const obj: Record<string, any> = { item_name: row.item_name }
      for (let i = 0; i < sortedYears.value.length; i++) {
        const yr = sortedYears.value[i]
        obj[`val_${yr}`] = row.values[String(yr)] ?? ''
        if (i > 0) {
          const yoy = row.yoy_changes[String(yr)]
          obj[`yoy_${yr}`] = yoy != null ? `${yoy.toFixed(2)}%` : '-'
        }
      }
      return obj
    })

    const label = reportTypeLabel[reportType.value] || '报表'
    const yearsStr = sortedYears.value.join('-')
    await exportData({
      data,
      columns,
      sheetName: '多年度对比',
      fileName: `${label}_多年度对比_${yearsStr}.xlsx`,
    })
  } catch (err: any) {
    handleApiError(err, '导出')
  } finally {
    exporting.value = false
  }
}

/* ── Lifecycle ── */
onMounted(() => {
  const current = props.currentYear || new Date().getFullYear()
  selectedYears.value = [current - 1, current]
  fetchData()
  document.addEventListener('click', () => { ctxMenu.value.visible = false })
})
onUnmounted(() => {
  document.removeEventListener('click', () => { ctxMenu.value.visible = false })
})

/* ── Expose for parent ── */
defineExpose({ fetchData, onExport })
</script>

<style scoped>
.gt-multi-year-compare {
  padding: 0;
}

.gt-myc-controls {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 12px;
  flex-wrap: wrap;
  gap: 8px;
}

.gt-myc-controls__left {
  display: flex;
  align-items: center;
  gap: 8px;
}

.gt-myc-controls__right {
  display: flex;
  align-items: center;
}

.gt-myc-controls__center {
  display: flex;
  align-items: center;
}

.gt-myc-label {
  font-size: 13px;
  color: var(--gt-color-text-secondary, #666);
  white-space: nowrap;
}

.gt-myc-change {
  font-size: 12px;
  white-space: nowrap;
}

.gt-myc-change--up {
  color: var(--gt-color-coral, #e74c3c);
}

.gt-myc-change--down {
  color: var(--gt-color-success, #27ae60);
}

.gt-myc-change--alert {
  color: var(--gt-color-coral, #e74c3c);
  font-weight: 700;
}

.gt-myc-arrow {
  margin-left: 2px;
}

.gt-myc-empty {
  text-align: center;
  padding: 40px 0;
  color: var(--gt-color-text-tertiary, #999);
  font-size: 14px;
}

:deep(.gt-myc-row--highlight) {
  background-color: rgba(231, 76, 60, 0.06) !important;
}

:deep(.gt-myc-row--highlight td) {
  background-color: rgba(231, 76, 60, 0.06) !important;
}
</style>

<style>
/* 右键菜单（teleport to body，非 scoped） */
.gt-myc-ctx-menu {
  position: fixed;
  z-index: 10001;
  background: #fff;
  border-radius: 8px;
  box-shadow: 0 8px 24px rgba(75, 45, 119, 0.175);
  padding: 6px 0;
  min-width: 140px;
  border: 1px solid #f0f0f5;
}
.gt-myc-ctx-item {
  padding: 8px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: background 0.15s;
}
.gt-myc-ctx-item:hover {
  background: #f4f0fa;
  color: #4b2d77;
}
.gt-myc-ctx-divider {
  height: 1px;
  background: #f0f0f5;
  margin: 4px 8px;
}
</style>
