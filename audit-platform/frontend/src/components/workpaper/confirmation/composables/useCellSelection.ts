/**
 * useCellSelection — 完整表格视图单元格选区 composable
 *
 * 支持：单击选中 / Ctrl 追加 / Shift 范围 / 拖拽框选
 * 输出：选中的 cell 坐标集 + 选区值（用于复制/求和）
 */
import { ref, computed, type Ref } from 'vue'
import type { ConfirmationRow } from '../confirmationTypes'

export interface CellCoord {
  rowIndex: number
  colField: string
}

export function useCellSelection(rows: Ref<ConfirmationRow[]>) {
  const selectedCells = ref<CellCoord[]>([])
  const anchorCell = ref<CellCoord | null>(null)

  function selectCell(coord: CellCoord, modifiers: { ctrl?: boolean; shift?: boolean } = {}) {
    if (modifiers.shift && anchorCell.value) {
      // Range select from anchor to coord
      const startRow = Math.min(anchorCell.value.rowIndex, coord.rowIndex)
      const endRow = Math.max(anchorCell.value.rowIndex, coord.rowIndex)
      selectedCells.value = []
      for (let r = startRow; r <= endRow; r++) {
        selectedCells.value.push({ rowIndex: r, colField: coord.colField })
      }
    } else if (modifiers.ctrl) {
      // Toggle selection
      const idx = selectedCells.value.findIndex(
        c => c.rowIndex === coord.rowIndex && c.colField === coord.colField
      )
      if (idx >= 0) {
        selectedCells.value.splice(idx, 1)
      } else {
        selectedCells.value.push(coord)
      }
      anchorCell.value = coord
    } else {
      // Single select
      selectedCells.value = [coord]
      anchorCell.value = coord
    }
  }

  function clearSelection() {
    selectedCells.value = []
    anchorCell.value = null
  }

  /** 获取选中单元格的数值用于求和 */
  const selectedValues = computed(() => {
    return selectedCells.value
      .map(cell => {
        const row = rows.value[cell.rowIndex]
        if (!row) return null
        const val = (row as any)[cell.colField]
        return typeof val === 'number' ? val : null
      })
      .filter((v): v is number => v !== null)
  })

  const selectionSum = computed(() => selectedValues.value.reduce((a, b) => a + b, 0))

  /** 复制选中内容为 TSV 格式 */
  function copyToClipboard() {
    const lines = selectedCells.value.map(cell => {
      const row = rows.value[cell.rowIndex]
      return row ? String((row as any)[cell.colField] ?? '') : ''
    })
    const text = lines.join('\n')
    navigator.clipboard?.writeText(text)
    return text
  }

  function isSelected(rowIndex: number, colField: string): boolean {
    return selectedCells.value.some(c => c.rowIndex === rowIndex && c.colField === colField)
  }

  return {
    selectedCells,
    selectCell,
    clearSelection,
    selectedValues,
    selectionSum,
    copyToClipboard,
    isSelected,
  }
}
