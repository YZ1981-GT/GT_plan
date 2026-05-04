/**
 * 通用单元格选中 composable
 * 支持单击选中、Ctrl+多选、右键菜单定位
 */
import { ref, reactive, onMounted, onUnmounted } from 'vue'

export interface SelectedCell {
  row: number
  col: number
  value: any
}

export interface CellContextMenuState {
  visible: boolean
  x: number
  y: number
  itemName: string
  rowData: any
}

export function useCellSelection() {
  const selectedCells = ref<SelectedCell[]>([])
  const contextMenu = reactive<CellContextMenuState>({
    visible: false, x: 0, y: 0, itemName: '', rowData: null,
  })

  function cellClassName({ rowIndex, columnIndex }: { rowIndex: number; columnIndex: number }): string {
    return selectedCells.value.some(c => c.row === rowIndex && c.col === columnIndex)
      ? 'gt-ucell--selected' : ''
  }

  function selectCell(rowIdx: number, colIdx: number, value: any, multi: boolean) {
    if (multi) {
      const idx = selectedCells.value.findIndex(c => c.row === rowIdx && c.col === colIdx)
      if (idx >= 0) selectedCells.value.splice(idx, 1)
      else selectedCells.value.push({ row: rowIdx, col: colIdx, value })
    } else {
      selectedCells.value = [{ row: rowIdx, col: colIdx, value }]
    }
  }

  function openContextMenu(e: MouseEvent, itemName: string, rowData?: any) {
    e.preventDefault()
    e.stopPropagation()
    setTimeout(() => {
      contextMenu.x = e.clientX
      contextMenu.y = e.clientY
      contextMenu.itemName = itemName
      contextMenu.rowData = rowData || null
      contextMenu.visible = true
    }, 0)
  }

  function closeContextMenu() {
    contextMenu.visible = false
  }

  function copySelectedValues() {
    const values = selectedCells.value.map(c => c.value ?? '-').join('\t')
    navigator.clipboard?.writeText(values)
  }

  function sumSelectedValues(): number {
    return selectedCells.value.reduce((s, c) => s + (Number(c.value) || 0), 0)
  }

  // 点击其他地方关闭菜单
  function onDocClick(e: MouseEvent) {
    if (!(e.target as HTMLElement)?.closest('.gt-ucell-context-menu')) {
      closeContextMenu()
    }
  }

  onMounted(() => document.addEventListener('click', onDocClick))
  onUnmounted(() => document.removeEventListener('click', onDocClick))

  return {
    selectedCells,
    contextMenu,
    cellClassName,
    selectCell,
    openContextMenu,
    closeContextMenu,
    copySelectedValues,
    sumSelectedValues,
  }
}
