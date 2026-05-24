<!--
  SheetCellRangePicker — Sheet 单元格区域选择器弹窗

  用户在左树点击具体 sheet 叶子时弹出，提供网格界面供用户框选要查询的单元格区域。

  Phase 1（当前）：空白 grid（60 行 × 27 列 A~AA）+ 鼠标拖选记录起止 cell + 确认 range
  Phase 2（后续）：接入真实 Univer 模板 cellData，展示底稿真实内容

  Emits:
    confirm: { wp_code, sheet_name, range }  → 父组件用 range 作为查询过滤条件
    update:visible: 关闭弹窗
-->
<template>
  <el-dialog
    v-model="visible"
    :title="dialogTitle"
    width="80%"
    top="5vh"
    append-to-body
    destroy-on-close
    class="gt-sheet-picker-dialog"
  >
    <div class="gt-sheet-picker-toolbar">
      <span class="gt-sheet-picker-tab">📄 {{ isModuleMode ? moduleLabel : (sheetName || wpCode) }}</span>
      <el-tag v-if="dataSource === 'jsonb_direct'" size="small" effect="dark" type="success" round
        title="数据来自 JSONB 直接读取">📥 JSONB</el-tag>
      <el-tag v-else-if="dataSource === 'univer_snapshot'" size="small" effect="dark" type="success" round
        title="数据来自用户最近一次保存的 Univer snapshot（公式已计算）">📥 实时</el-tag>
      <el-tag v-else-if="dataSource === 'xlsx_recomputed'" size="small" effect="plain" type="warning" round
        title="模板首次查询，已通过 LibreOffice 重算公式">⚙ 重算</el-tag>
      <el-tag v-else-if="dataSource === 'xlsx_cache'" size="small" effect="plain" type="info" round
        title="数据来自模板默认值（无用户编辑）">📋 模板</el-tag>
      <el-select v-if="allSheets.length > 1" v-model="activeSheet" size="small" style="width:240px"
        @change="loadSheetData">
        <el-option v-for="s in allSheets" :key="s" :label="s" :value="s" />
      </el-select>
      <span style="flex:1" />
      <span v-if="loadStatus === 'loaded'" class="gt-sheet-picker-meta">
        {{ realRows }} 行 × {{ realCols }} 列 · {{ Object.keys(cellData).length }} 个单元格
      </span>
      <span v-if="selectedRange" class="gt-sheet-picker-range">
        已选区域：<strong>{{ selectedRange }}</strong>
      </span>
      <el-button size="small" @click="resetSelection" :disabled="!selectedRange">↺ 清除</el-button>
      <el-button size="small" type="info" plain @click="onClearMemory" title="清除当前 sheet 的选区记忆">🗑 清除记忆</el-button>
    </div>

    <div class="gt-sheet-picker-hint">
      <span v-if="loadStatus === 'loading'">⏳ 加载真实模板内容...</span>
      <span v-else-if="loadStatus === 'unavailable'" style="color:var(--gt-color-warning)">
        ⚠ {{ unavailableReason || '该底稿在当前项目不可用' }}（仍可在空白网格上选区作占位）
      </span>
      <span v-else-if="loadStatus === 'loaded'">💡 鼠标拖动框选要查询的单元格区域，灰显单元格无内容</span>
      <span v-else>💡 鼠标拖动框选要查询的单元格区域</span>
    </div>

    <div class="gt-sheet-picker-grid-wrap" @mouseup="onMouseUp" @mouseleave="onMouseUp" v-loading="loadStatus === 'loading'">
      <table class="gt-sheet-picker-grid" @selectstart.prevent>
        <thead>
          <tr>
            <th class="gt-corner"></th>
            <th v-for="(col, ci) in COLS" :key="ci" class="gt-col-header">{{ col }}</th>
          </tr>
        </thead>
        <tbody>
          <tr v-for="row in ROWS" :key="row">
            <th class="gt-row-header">{{ row }}</th>
            <td
              v-for="(col, ci) in COLS"
              :key="ci"
              :class="['gt-cell', {
                'gt-cell-selected': isCellSelected(row, ci),
                'gt-cell-empty': loadStatus === 'loaded' && !getCell(row - 1, ci),
                'gt-cell-numeric': isNumericCell(row - 1, ci),
                'gt-cell-formula': isFormulaCell(row - 1, ci),
              }]"
              :title="cellTooltip(row - 1, ci)"
              @mousedown="onMouseDown(row, ci)"
              @mouseenter="onMouseEnter(row, ci)"
            >{{ formatCell(getCell(row - 1, ci)) }}</td>
          </tr>
        </tbody>
      </table>
    </div>

    <template #footer>
      <el-button @click="visible = false">取消</el-button>
      <el-button type="primary" :disabled="!selectedRange" @click="onConfirm">
        ✓ 确认选区{{ selectedRange ? `（${selectedRange}）` : '' }}
      </el-button>
    </template>
  </el-dialog>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue'
import { api } from '@/services/apiProxy'
import { useRangeMemory, clampRange } from '@/composables/useRangeMemory'
import { ElMessage } from 'element-plus'

const props = defineProps<{
  modelValue: boolean
  wpCode: string
  sheetName?: string
  projectId?: string
  /** 跨模块 source（report:type / note:section / adj:type / tb:dim），传入时走模块 cell 路由 */
  moduleSource?: string
  year?: number
}>()
const emit = defineEmits<{
  'update:modelValue': [v: boolean]
  confirm: [payload: { wp_code: string; sheet_name?: string; range: string; module_source?: string }]
}>()

const visible = computed({
  get: () => props.modelValue,
  set: (v) => emit('update:modelValue', v),
})

// 选区记忆
const rangeMemory = useRangeMemory('current-user') // userId 由实际登录态提供

const dialogTitle = computed(() => {
  if (isModuleMode.value) return `📐 选择单元格区域 — ${moduleLabel.value}`
  return `📐 选择单元格区域 — ${props.wpCode}${props.sheetName ? ' / ' + props.sheetName : ''}`
})

// 网格规模：A~AA 27 列 × 60 行（覆盖大多数底稿首屏）
const ROW_COUNT = 60
const COL_COUNT = 27
const ROWS = Array.from({ length: ROW_COUNT }, (_, i) => i + 1)
const COLS = Array.from({ length: COL_COUNT }, (_, i) => _colLabel(i))

function _colLabel(i: number): string {
  if (i < 26) return String.fromCharCode(65 + i)
  return 'A' + String.fromCharCode(65 + (i - 26))
}

// 拖选状态
const dragging = ref(false)
const startCell = ref<{ row: number; col: number } | null>(null)
const endCell = ref<{ row: number; col: number } | null>(null)

// 真实模板数据
type LoadStatus = 'idle' | 'loading' | 'loaded' | 'unavailable'
const loadStatus = ref<LoadStatus>('idle')
const unavailableReason = ref<string>('')
const cellData = ref<Record<string, { v: any }>>({})  // key 'r,c' (0-indexed)
const realRows = ref(0)
const realCols = ref(0)
const allSheets = ref<string[]>([])
const activeSheet = ref<string>('')
const dataSource = ref<string>('')  // univer_snapshot / xlsx_cache / xlsx_recomputed

function getCell(r: number, c: number): { v: any } | null {
  return cellData.value[`${r},${c}`] || null
}
function isNumericCell(r: number, c: number): boolean {
  const cell = getCell(r, c)
  return !!cell && typeof cell.v === 'number'
}
function isFormulaCell(r: number, c: number): boolean {
  const cell = getCell(r, c) as any
  return !!cell && cell.f != null && cell.f !== ''
}
function formatCell(cell: { v: any } | null): string {
  if (!cell) return ''
  const v = cell.v
  // 公式 cell 但 cache 为空 → 显示公式 string 截断
  if ((v === '' || v == null) && (cell as any).f) {
    const f = String((cell as any).f).slice(0, 14)
    return f
  }
  if (typeof v === 'number') {
    return Number.isInteger(v) ? String(v) : v.toFixed(2)
  }
  const s = String(v ?? '')
  return s.length > 14 ? s.slice(0, 13) + '…' : s
}
function cellTooltip(r: number, c: number): string {
  const cell = getCell(r, c) as any
  if (!cell) return ''
  if (cell.f) return `公式: ${cell.f}\n值: ${cell.v ?? '(待求值, 查询时自动重算)'}`
  return String(cell.v ?? '')
}

/** 判断当前是否为跨模块 cell 查询模式 */
const isModuleMode = computed(() => {
  if (!props.moduleSource) return false
  return /^(report|note|adj|tb):/.test(props.moduleSource)
})

/** 模块模式下的显示标签 */
const moduleLabel = computed(() => {
  if (!props.moduleSource) return ''
  const m = props.moduleSource.match(/^(report|note|adj|tb):(.+)/)
  if (!m) return props.moduleSource
  const labels: Record<string, string> = { report: '📊 报表', note: '📝 附注', adj: '📐 调整分录', tb: '📋 试算表' }
  return `${labels[m[1]] || m[1]} / ${m[2]}`
})

async function loadSheetData() {
  // 跨模块 cell 查询模式：通过 execute 端点加载虚拟 sheet 数据
  if (isModuleMode.value && props.moduleSource && props.projectId) {
    loadStatus.value = 'loading'
    unavailableReason.value = ''
    cellData.value = {}
    try {
      // 用全范围 A1:G100 预加载虚拟 sheet 数据
      const fullSource = `${props.moduleSource}|A1:G100`
      const data = await api.post('/api/custom-query/execute', {
        project_id: props.projectId,
        year: props.year || new Date().getFullYear(),
        source: fullSource,
        filters: {},
      }) as any
      if (data?.error) {
        loadStatus.value = 'unavailable'
        unavailableReason.value = data.error
        return
      }
      // 将 rows 转换为 cellData 格式（0-indexed key 'r,c'）
      const cells: Record<string, { v: any; f?: string }> = {}
      let maxR = 0, maxC = 0
      for (const row of (data?.rows || [])) {
        const ref = row.cell_ref as string
        if (!ref) continue
        const m = ref.match(/^([A-Z]+)(\d+)$/)
        if (!m) continue
        const colStr = m[1]
        const rowNum = parseInt(m[2], 10)
        let colNum = 0
        for (const ch of colStr) colNum = colNum * 26 + (ch.charCodeAt(0) - 64)
        const r = rowNum - 1  // 0-indexed
        const c = colNum - 1  // 0-indexed
        const entry: any = { v: row.value }
        if (row.formula) entry.f = row.formula
        cells[`${r},${c}`] = entry
        if (r > maxR) maxR = r
        if (c > maxC) maxC = c
      }
      cellData.value = cells
      realRows.value = maxR + 1
      realCols.value = maxC + 1
      allSheets.value = []
      activeSheet.value = data?.rows?.[0]?.sheet_name || ''
      dataSource.value = data?.source || 'jsonb_direct'
      loadStatus.value = Object.keys(cells).length > 0 ? 'loaded' : 'unavailable'
      if (loadStatus.value === 'unavailable') unavailableReason.value = '无数据'
    } catch (e) {
      loadStatus.value = 'unavailable'
      unavailableReason.value = '加载失败'
    }
    return
  }

  // 原有底稿模式
  if (!props.projectId || !props.wpCode) {
    loadStatus.value = 'idle'
    return
  }
  loadStatus.value = 'loading'
  unavailableReason.value = ''
  cellData.value = {}
  try {
    const data = await api.get('/api/custom-query/wp-sheet-preview', {
      params: {
        project_id: props.projectId,
        wp_code: props.wpCode,
        sheet_name: activeSheet.value || props.sheetName || undefined,
      },
    }) as any
    if (!data?.available) {
      loadStatus.value = 'unavailable'
      unavailableReason.value = data?.reason || '该底稿不可用'
      allSheets.value = []
      return
    }
    cellData.value = data.cells || {}
    realRows.value = data.rows || 0
    realCols.value = data.cols || 0
    allSheets.value = data.all_sheets || []
    activeSheet.value = data.sheet_name || ''
    dataSource.value = data.source || ''
    loadStatus.value = 'loaded'
  } catch (e) {
    loadStatus.value = 'unavailable'
    unavailableReason.value = '加载失败'
  }
}

const selectedRange = computed(() => {
  if (!startCell.value || !endCell.value) return ''
  const r1 = Math.min(startCell.value.row, endCell.value.row)
  const r2 = Math.max(startCell.value.row, endCell.value.row)
  const c1 = Math.min(startCell.value.col, endCell.value.col)
  const c2 = Math.max(startCell.value.col, endCell.value.col)
  const a1 = `${COLS[c1]}${r1}`
  const a2 = `${COLS[c2]}${r2}`
  return r1 === r2 && c1 === c2 ? a1 : `${a1}:${a2}`
})

function isCellSelected(row: number, col: number): boolean {
  if (!startCell.value || !endCell.value) return false
  const r1 = Math.min(startCell.value.row, endCell.value.row)
  const r2 = Math.max(startCell.value.row, endCell.value.row)
  const c1 = Math.min(startCell.value.col, endCell.value.col)
  const c2 = Math.max(startCell.value.col, endCell.value.col)
  return row >= r1 && row <= r2 && col >= c1 && col <= c2
}

function onMouseDown(row: number, col: number) {
  dragging.value = true
  startCell.value = { row, col }
  endCell.value = { row, col }
}

function onMouseEnter(row: number, col: number) {
  if (dragging.value) endCell.value = { row, col }
}

function onMouseUp() {
  dragging.value = false
}

function resetSelection() {
  startCell.value = null
  endCell.value = null
}

function onConfirm() {
  if (!selectedRange.value) return
  // 保存选区记忆
  const sheet = activeSheet.value || props.sheetName || ''
  if (props.wpCode && sheet) {
    rangeMemory.save(props.wpCode, sheet, selectedRange.value)
  }
  emit('confirm', {
    wp_code: props.wpCode,
    sheet_name: activeSheet.value || props.sheetName,
    range: selectedRange.value,
    ...(isModuleMode.value && props.moduleSource ? { module_source: props.moduleSource } : {}),
  })
  visible.value = false
}

function onClearMemory() {
  const sheet = activeSheet.value || props.sheetName || ''
  if (props.wpCode && sheet) {
    rangeMemory.clear(props.wpCode, sheet)
    ElMessage.success('已清除当前 sheet 的选区记忆')
  }
}

// 弹窗打开时自动加载真实数据 + 回填选区记忆，关闭时清空
watch(visible, (v) => {
  if (v) {
    activeSheet.value = props.sheetName || ''
    loadSheetData().then(() => {
      // 加载完成后尝试回填选区记忆
      const sheet = activeSheet.value || props.sheetName || ''
      if (props.wpCode && sheet) {
        const savedRange = rangeMemory.load(props.wpCode, sheet)
        if (savedRange) {
          // 越界 clamp
          const maxRow = realRows.value || ROW_COUNT
          const maxCol = realCols.value || COL_COUNT
          const { clampedExpr, wasClamped } = clampRange(savedRange, maxRow, maxCol)
          if (wasClamped) {
            ElMessage.info('上次选区已部分调整（sheet 结构变化）')
          }
          // 解析 clamped range 并设置选区
          applyRangeExpr(clampedExpr)
        }
      }
    })
  } else {
    resetSelection()
    loadStatus.value = 'idle'
    cellData.value = {}
  }
})

/**
 * 从 range 表达式（如 A1:B10）设置选区状态
 */
function applyRangeExpr(expr: string) {
  // 取第一个区域（多区域时取首个）
  const firstRange = expr.split(',')[0]?.trim()
  if (!firstRange) return
  const parts = firstRange.split(':')
  const start = parseCellRef(parts[0])
  const end = parts[1] ? parseCellRef(parts[1]) : start
  if (start && end) {
    startCell.value = start
    endCell.value = end
  }
}

function parseCellRef(ref: string): { row: number; col: number } | null {
  const m = ref.match(/^([A-Z]{1,3})(\d+)$/)
  if (!m) return null
  const colStr = m[1]
  const row = parseInt(m[2], 10)
  // 将列字母转为 0-indexed col
  let col = 0
  for (const ch of colStr) col = col * 26 + (ch.charCodeAt(0) - 64)
  col -= 1 // 0-indexed
  return { row, col }
}
</script>

<style scoped>
.gt-sheet-picker-toolbar {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 8px 0;
  border-bottom: 1px solid var(--gt-color-border-purple);
  margin-bottom: 8px;
}
.gt-sheet-picker-tab {
  font-size: var(--gt-font-size-md);
  font-weight: 600;
  color: var(--gt-color-primary);
  background: var(--gt-color-bg-purple-light, #f5f0ff);
  padding: 4px 12px;
  border-radius: 4px 4px 0 0;
  border-bottom: 2px solid var(--gt-color-primary);
}
.gt-sheet-picker-range {
  font-size: var(--gt-font-size-sm);
  color: var(--gt-color-text-regular);
}
.gt-sheet-picker-range strong {
  color: var(--gt-color-primary);
  font-family: 'Consolas', 'Monaco', monospace;
}
.gt-sheet-picker-hint {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
  margin-bottom: 6px;
}
.gt-sheet-picker-grid-wrap {
  max-height: calc(100vh - 280px);
  overflow: auto;
  border: 1px solid var(--gt-color-border);
  user-select: none;
}
.gt-sheet-picker-grid {
  border-collapse: collapse;
  font-size: 12px;
  table-layout: fixed;
}
.gt-sheet-picker-grid th,
.gt-sheet-picker-grid td {
  border: 1px solid #e0e0e0;
  width: 80px;
  height: 22px;
  padding: 0;
  text-align: center;
  background: #fff;
}
.gt-corner {
  width: 40px !important;
  background: #f5f5f5 !important;
  position: sticky;
  left: 0;
  top: 0;
  z-index: 3;
}
.gt-col-header {
  background: #f5f5f5 !important;
  position: sticky;
  top: 0;
  z-index: 2;
  font-weight: 600;
  color: var(--gt-color-text-secondary);
}
.gt-row-header {
  width: 40px !important;
  background: #f5f5f5 !important;
  position: sticky;
  left: 0;
  z-index: 1;
  font-weight: 600;
  color: var(--gt-color-text-secondary);
}
.gt-cell {
  cursor: cell;
  font-size: 11px;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
  max-width: 80px;
  padding: 0 3px !important;
}
.gt-cell:hover {
  background: rgba(124, 58, 237, 0.06) !important;
}
.gt-cell-selected {
  background: rgba(124, 58, 237, 0.18) !important;
  border-color: var(--gt-color-primary) !important;
}
.gt-cell-empty {
  background: #fafafa !important;
  color: #ccc;
}
.gt-cell-numeric {
  text-align: right !important;
  font-family: 'Consolas', 'Monaco', monospace;
  color: var(--gt-color-text-primary, #303133);
}
.gt-cell-formula {
  color: var(--gt-color-warning, #e6a23c) !important;
  font-style: italic;
  background: rgba(230, 162, 60, 0.05);
}
.gt-cell-formula::before { content: "ƒ "; color: var(--gt-color-warning, #e6a23c); }
.gt-sheet-picker-meta {
  font-size: var(--gt-font-size-xs);
  color: var(--gt-color-text-tertiary);
}
</style>
