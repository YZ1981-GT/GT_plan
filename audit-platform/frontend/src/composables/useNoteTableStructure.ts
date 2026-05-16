/**
 * useNoteTableStructure - 附注表格结构手动编辑
 *
 * 支持：新增行/删除行/新增列/删除列/修改列名/调整列顺序
 * 结构编辑后自动重新计算合计行
 * 支持撤销/重做（Ctrl+Z / Ctrl+Y）
 * 支持"恢复模板结构"操作
 *
 * Validates: Requirements 38.1, 38.2, 38.3, 38.4, 38.5, 38.6
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface TableRow {
  label: string
  values: (number | null)[]
  is_total?: boolean
  [key: string]: any
}

export interface TableData {
  name?: string
  section_id?: string
  headers: string[]
  rows: TableRow[]
}

/** A command that can be undone/redone */
interface StructureCommand {
  type: string
  description: string
  undo: () => void
  redo: () => void
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useNoteTableStructure(options: {
  getActiveTable: () => TableData | null
  markDirty: () => void
}) {
  const { getActiveTable, markDirty } = options

  // ─── Undo/Redo Stack ─────────────────────────────────────────────────────
  const undoStack = ref<StructureCommand[]>([])
  const redoStack = ref<StructureCommand[]>([])

  const canUndo = computed(() => undoStack.value.length > 0)
  const canRedo = computed(() => redoStack.value.length > 0)

  function pushCommand(cmd: StructureCommand) {
    cmd.redo()
    undoStack.value.push(cmd)
    redoStack.value = [] // clear redo on new action
    markDirty()
  }

  function undo() {
    const cmd = undoStack.value.pop()
    if (!cmd) return
    cmd.undo()
    redoStack.value.push(cmd)
    markDirty()
  }

  function redo() {
    const cmd = redoStack.value.pop()
    if (!cmd) return
    cmd.redo()
    undoStack.value.push(cmd)
    markDirty()
  }

  // ─── Row Operations ──────────────────────────────────────────────────────

  /** Add a new empty row at the given index */
  function addRow(index: number) {
    const table = getActiveTable()
    if (!table) return
    const colCount = table.headers.length > 1 ? table.headers.length - 1 : 0
    const newRow: TableRow = {
      label: '',
      values: Array(colCount).fill(null),
      is_total: false,
    }
    const cmd: StructureCommand = {
      type: 'addRow',
      description: `新增行 (位置 ${index + 1})`,
      redo: () => { table.rows.splice(index, 0, { ...newRow, values: [...newRow.values] }) },
      undo: () => { table.rows.splice(index, 1) },
    }
    pushCommand(cmd)
    recalcTotals()
  }

  /** Delete the row at the given index */
  function deleteRow(index: number) {
    const table = getActiveTable()
    if (!table) return
    const row = table.rows[index]
    if (!row) return
    if (row.is_total) return // protect total rows from deletion
    const removedRow = { ...row, values: [...row.values] }
    const cmd: StructureCommand = {
      type: 'deleteRow',
      description: `删除行 "${row.label}"`,
      redo: () => { table.rows.splice(index, 1) },
      undo: () => { table.rows.splice(index, 0, removedRow) },
    }
    pushCommand(cmd)
    recalcTotals()
  }

  // ─── Column Operations ───────────────────────────────────────────────────

  /** Add a new column at the given index (0-based among value columns, not the label column) */
  function addColumn(index: number, name: string) {
    const table = getActiveTable()
    if (!table) return
    // headers[0] is the "项目" label column; value columns start at index 1
    const headerIdx = index + 1
    const cmd: StructureCommand = {
      type: 'addColumn',
      description: `新增列 "${name}"`,
      redo: () => {
        table.headers.splice(headerIdx, 0, name)
        for (const row of table.rows) {
          row.values.splice(index, 0, null)
        }
      },
      undo: () => {
        table.headers.splice(headerIdx, 1)
        for (const row of table.rows) {
          row.values.splice(index, 1)
        }
      },
    }
    pushCommand(cmd)
  }

  /** Delete the column at the given index (0-based among value columns) */
  function deleteColumn(index: number) {
    const table = getActiveTable()
    if (!table) return
    const headerIdx = index + 1
    if (headerIdx <= 0 || headerIdx >= table.headers.length) return // protect label column
    const removedName = table.headers[headerIdx]
    const removedValues = table.rows.map(r => r.values[index])
    const cmd: StructureCommand = {
      type: 'deleteColumn',
      description: `删除列 "${removedName}"`,
      redo: () => {
        table.headers.splice(headerIdx, 1)
        for (let i = 0; i < table.rows.length; i++) {
          table.rows[i].values.splice(index, 1)
        }
      },
      undo: () => {
        table.headers.splice(headerIdx, 0, removedName)
        for (let i = 0; i < table.rows.length; i++) {
          table.rows[i].values.splice(index, 0, removedValues[i])
        }
      },
    }
    pushCommand(cmd)
    recalcTotals()
  }

  /** Rename a column (0-based among value columns) */
  function renameColumn(index: number, newName: string) {
    const table = getActiveTable()
    if (!table) return
    const headerIdx = index + 1
    if (headerIdx >= table.headers.length) return
    const oldName = table.headers[headerIdx]
    if (oldName === newName) return
    const cmd: StructureCommand = {
      type: 'renameColumn',
      description: `重命名列 "${oldName}" → "${newName}"`,
      redo: () => { table.headers[headerIdx] = newName },
      undo: () => { table.headers[headerIdx] = oldName },
    }
    pushCommand(cmd)
  }

  /** Move a column left or right (0-based among value columns) */
  function moveColumn(index: number, direction: 'left' | 'right') {
    const table = getActiveTable()
    if (!table) return
    const headerIdx = index + 1
    const targetIdx = direction === 'left' ? headerIdx - 1 : headerIdx + 1
    // Cannot move past label column (index 0) or beyond last column
    if (targetIdx < 1 || targetIdx >= table.headers.length) return
    const targetValueIdx = direction === 'left' ? index - 1 : index + 1
    const cmd: StructureCommand = {
      type: 'moveColumn',
      description: `移动列 "${table.headers[headerIdx]}" ${direction === 'left' ? '左移' : '右移'}`,
      redo: () => {
        // Swap headers
        const tmp = table.headers[headerIdx]
        table.headers[headerIdx] = table.headers[targetIdx]
        table.headers[targetIdx] = tmp
        // Swap values in all rows
        for (const row of table.rows) {
          const tmpVal = row.values[index]
          row.values[index] = row.values[targetValueIdx]
          row.values[targetValueIdx] = tmpVal
        }
      },
      undo: () => {
        // Swap back
        const tmp = table.headers[headerIdx]
        table.headers[headerIdx] = table.headers[targetIdx]
        table.headers[targetIdx] = tmp
        for (const row of table.rows) {
          const tmpVal = row.values[index]
          row.values[index] = row.values[targetValueIdx]
          row.values[targetValueIdx] = tmpVal
        }
      },
    }
    pushCommand(cmd)
  }

  // ─── Auto-recalculate Totals ─────────────────────────────────────────────

  /** Recalculate all total rows (sum of non-total rows) */
  function recalcTotals() {
    const table = getActiveTable()
    if (!table) return
    for (const row of table.rows) {
      if (!row.is_total) continue
      const colCount = row.values.length
      for (let c = 0; c < colCount; c++) {
        let sum = 0
        let hasValue = false
        for (const r of table.rows) {
          if (r.is_total) continue
          const v = r.values[c]
          if (v != null && typeof v === 'number') {
            sum += v
            hasValue = true
          }
        }
        row.values[c] = hasValue ? sum : null
      }
    }
  }

  // ─── Restore Template Structure ──────────────────────────────────────────

  /**
   * Restore the table to its original template structure.
   * templateTable: the original template table data (headers + rows structure)
   * Preserves data in columns that match by name.
   */
  function restoreTemplateStructure(templateTable: TableData) {
    const table = getActiveTable()
    if (!table) return

    // Snapshot current state for undo
    const oldHeaders = [...table.headers]
    const oldRows = table.rows.map(r => ({ ...r, values: [...r.values] }))

    const cmd: StructureCommand = {
      type: 'restoreTemplate',
      description: '恢复模板结构',
      redo: () => {
        // Restore headers from template
        const newHeaders = [...templateTable.headers]
        // Build column mapping: for each template value column, find matching current column by name
        const colMapping: (number | null)[] = [] // template value col index → current value col index
        for (let ti = 1; ti < newHeaders.length; ti++) {
          const tName = newHeaders[ti]
          const currentIdx = table.headers.indexOf(tName)
          colMapping.push(currentIdx > 0 ? currentIdx - 1 : null)
        }

        // Build new rows from template structure, preserving data where columns match
        const newRows: TableRow[] = templateTable.rows.map(templateRow => {
          // Try to find matching row by label
          const existingRow = table.rows.find(r => r.label === templateRow.label)
          const newValues: (number | null)[] = colMapping.map((srcIdx) => {
            if (srcIdx == null || !existingRow) return null
            return existingRow.values[srcIdx] ?? null
          })
          return {
            label: templateRow.label,
            values: newValues,
            is_total: templateRow.is_total || false,
          }
        })

        table.headers.splice(0, table.headers.length, ...newHeaders)
        table.rows.splice(0, table.rows.length, ...newRows)
      },
      undo: () => {
        table.headers.splice(0, table.headers.length, ...oldHeaders)
        table.rows.splice(0, table.rows.length, ...oldRows)
      },
    }
    pushCommand(cmd)
    recalcTotals()
  }

  // ─── Keyboard Shortcuts ──────────────────────────────────────────────────

  function handleKeydown(e: KeyboardEvent) {
    // Only handle when not in an input/textarea
    const tag = (e.target as HTMLElement)?.tagName?.toLowerCase()
    if (tag === 'input' || tag === 'textarea') return

    if ((e.ctrlKey || e.metaKey) && e.key === 'z' && !e.shiftKey) {
      e.preventDefault()
      undo()
    } else if ((e.ctrlKey || e.metaKey) && (e.key === 'y' || (e.key === 'z' && e.shiftKey))) {
      e.preventDefault()
      redo()
    }
  }

  onMounted(() => {
    document.addEventListener('keydown', handleKeydown)
  })

  onBeforeUnmount(() => {
    document.removeEventListener('keydown', handleKeydown)
  })

  // ─── Clear history (when switching notes) ────────────────────────────────

  function clearHistory() {
    undoStack.value = []
    redoStack.value = []
  }

  return {
    // State
    canUndo,
    canRedo,
    // Row operations
    addRow,
    deleteRow,
    // Column operations
    addColumn,
    deleteColumn,
    renameColumn,
    moveColumn,
    // Totals
    recalcTotals,
    // Undo/Redo
    undo,
    redo,
    clearHistory,
    // Template restore
    restoreTemplateStructure,
  }
}
