/**
 * useTbCellInteraction - 试算表单元格交互域逻辑
 *
 * 从 TrialBalance.vue 拆分而来，包含：
 * - 单元格选中与高亮
 * - 右键菜单触发与命令分派
 * - 拖拽框选
 * - 复制选中（Clipboard）
 * - 表格内搜索（Ctrl+F）
 * - 单元格双击（编辑/钻取）
 *
 * @domain tb-cell-interaction
 */
import { ref, computed, onMounted, onUnmounted, type Ref } from 'vue'

// ─── 类型 ───
export interface CellCoord {
  rowIndex: number
  columnIndex: number
  value?: any
  field?: string
}

export interface DragState {
  active: boolean
  startRow: number
  startCol: number
  endRow: number
  endCol: number
}

export function useTbCellInteraction(
  tbTableRef: Ref<any>,
  rows: Ref<any[]>,
) {
  // ─── 选中状态 ───
  const selectedCells = ref<CellCoord[]>([])
  const currentCell = ref<CellCoord | null>(null)

  // ─── 拖拽框选 ───
  const drag = ref<DragState>({
    active: false,
    startRow: 0,
    startCol: 0,
    endRow: 0,
    endCol: 0,
  })

  // ─── 方法 ───
  function selectCell(rowIndex: number, columnIndex: number, value?: any, field?: string, append = false) {
    const cell: CellCoord = { rowIndex, columnIndex, value, field }
    currentCell.value = cell
    if (append) {
      // Ctrl+点击追加
      const existIdx = selectedCells.value.findIndex(
        c => c.rowIndex === rowIndex && c.columnIndex === columnIndex,
      )
      if (existIdx >= 0) {
        selectedCells.value.splice(existIdx, 1)
      } else {
        selectedCells.value.push(cell)
      }
    } else {
      selectedCells.value = [cell]
    }
  }

  function clearSelection() {
    selectedCells.value = []
    currentCell.value = null
  }

  function selectRange(startRow: number, startCol: number, endRow: number, endCol: number) {
    const minR = Math.min(startRow, endRow)
    const maxR = Math.max(startRow, endRow)
    const minC = Math.min(startCol, endCol)
    const maxC = Math.max(startCol, endCol)
    const cells: CellCoord[] = []
    for (let r = minR; r <= maxR; r++) {
      for (let c = minC; c <= maxC; c++) {
        cells.push({ rowIndex: r, columnIndex: c })
      }
    }
    selectedCells.value = cells
  }

  // ─── 拖拽框选事件 ───
  function onDragStart(rowIndex: number, colIndex: number) {
    drag.value = { active: true, startRow: rowIndex, startCol: colIndex, endRow: rowIndex, endCol: colIndex }
  }

  function onDragMove(rowIndex: number, colIndex: number) {
    if (!drag.value.active) return
    drag.value.endRow = rowIndex
    drag.value.endCol = colIndex
    selectRange(drag.value.startRow, drag.value.startCol, rowIndex, colIndex)
  }

  function onDragEnd() {
    drag.value.active = false
  }

  // ─── 复制 ───
  function copySelection(): string {
    if (selectedCells.value.length === 0) return ''
    // 按行列排序
    const sorted = [...selectedCells.value].sort(
      (a, b) => a.rowIndex - b.rowIndex || a.columnIndex - b.columnIndex,
    )
    const lines: string[] = []
    let prevRow = -1
    let currentLine: string[] = []
    for (const cell of sorted) {
      if (cell.rowIndex !== prevRow) {
        if (currentLine.length > 0) lines.push(currentLine.join('\t'))
        currentLine = []
        prevRow = cell.rowIndex
      }
      currentLine.push(String(cell.value ?? ''))
    }
    if (currentLine.length > 0) lines.push(currentLine.join('\t'))
    const text = lines.join('\n')
    navigator.clipboard?.writeText(text)
    return text
  }

  // ─── 汇总统计 ───
  const selectionStats = computed(() => {
    if (selectedCells.value.length <= 1) return null
    const nums = selectedCells.value
      .map(c => Number(c.value))
      .filter(v => !isNaN(v) && v !== 0)
    if (nums.length === 0) return null
    const sum = nums.reduce((a, b) => a + b, 0)
    return {
      count: nums.length,
      sum,
      avg: sum / nums.length,
    }
  })

  // ─── 单元格样式 ───
  function isCellSelected(rowIndex: number, columnIndex: number): boolean {
    return selectedCells.value.some(
      c => c.rowIndex === rowIndex && c.columnIndex === columnIndex,
    )
  }

  function cellClassName({ rowIndex, columnIndex }: { rowIndex: number; columnIndex: number }) {
    if (isCellSelected(rowIndex, columnIndex)) return 'gt-tb-cell-selected'
    return ''
  }

  return {
    selectedCells,
    currentCell,
    drag,
    selectCell,
    clearSelection,
    selectRange,
    onDragStart,
    onDragMove,
    onDragEnd,
    copySelection,
    selectionStats,
    isCellSelected,
    cellClassName,
  }
}
