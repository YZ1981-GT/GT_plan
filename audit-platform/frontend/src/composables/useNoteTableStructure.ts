/**
 * useNoteTableStructure - 附注表格结构手动编辑
 *
 * 支持：新增行/删除行/新增列/删除列/修改列名/调整列顺序
 * 结构编辑后按合计构成重算合计 / 小计行（`noteTotalTerms`，与后端同一判定；判不准的不动、手工格不动）
 * 支持撤销/重做（Ctrl+Z / Ctrl+Y）
 * 支持"恢复模板结构"操作
 *
 * Validates: Requirements 38.1, 38.2, 38.3, 38.4, 38.5, 38.6
 */
import { ref, computed, onMounted, onBeforeUnmount } from 'vue'
import { isTextEntryTarget } from '@/utils/shortcuts'
import { isTotalRow, recalcNoteTableTotals, rowKind } from '@/views/composables/noteTotalTerms'

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

/**
 * 集团下推的固定行（合并附注「📤 下推模板」打的行身份）：子企业不可删除、不可改名（后端保存时同口径拒绝，
 * `note_pushed_row_guard`：有行身份、类别缺省按固定行算）。
 */
export function isPushedFixedRow(row: unknown): boolean {
  const r = row as { _pushed_row_id?: unknown; _pushed_category?: unknown } | null
  return !!r && !!r._pushed_row_id && (r._pushed_category ?? 'required') === 'required'
}

/** 下推行身份字段：恢复模板结构时按行名带回，合并拉数仍按它精确对应。 */
const PUSHED_KEYS = ['_pushed_row_id', '_pushed_category', '_pushed_optional_active'] as const
/** 按数值列序号存的逐格元数据（取数 / 手工模式）：恢复模板结构时按列映射搬 */
const CELL_KEYS = ['_cell_meta', '_cell_modes'] as const
/** 随表头一起恢复的表结构键（多级表头与列身份）；`_row_types` 只在表里原本有时按新行重算 */
const STRUCTURE_KEYS = ['columns', '_column_groups'] as const
const RESTORE_KEYS = [...STRUCTURE_KEYS, '_row_types'] as const

const clone = <T>(v: T): T => (v === undefined ? v : JSON.parse(JSON.stringify(v)))
const squash = (s: unknown): string => String(s ?? '').replace(/\s+/g, '')

/** 逐数值列身份：列定义的 key（end_amount / prior_amount）、「分组/列名#同名第几列」、列名 */
function valueColumnIds(table: Record<string, any>): { key: string | null; text: string; leaf: string }[] {
  const headers: unknown[] = Array.isArray(table.headers) ? table.headers : []
  const cols: any[] | null = Array.isArray(table.columns) && table.columns.length === headers.length ? table.columns : null
  const groups: any[] = Array.isArray(table._column_groups) ? table._column_groups : []
  const seen = new Map<string, number>()
  const out: { key: string | null; text: string; leaf: string }[] = []
  for (let c = 1; c < headers.length; c++) {
    const g = groups.find(x => Number(x?.start) <= c && c < Number(x?.start) + Number(x?.span || 1))
    const leaf = squash(headers[c])
    const base = `${squash(g?.group ?? cols?.[c]?.group ?? '')}/${leaf}`
    const n = seen.get(base) ?? 0
    seen.set(base, n + 1)
    out.push({ key: cols?.[c]?.key ? String(cols[c].key) : null, text: `${base}#${n}`, leaf })
  }
  return out
}

type ColumnId = ReturnType<typeof valueColumnIds>[number]
/** 对应规则由强到弱，逐轮做完一轮再下一轮（弱规则不抢强规则能对上的列） */
const COLUMN_TIERS: ((s: ColumnId, d: ColumnId) => boolean)[] = [
  (s, d) => !!d.key && s.key === d.key,
  (s, d) => s.text === d.text,
  (s, d) => s.leaf === d.leaf, // 兜底：旧表没有分组信息 / 分组改过名 ⇒ 同名列按出现顺序取还没用过的
]

/** 模板数值列 → 当前表数值列（每列只用一次）：列定义 key 相同优先，其次分组 / 列名 / 第几次出现相同，最后同列名。
 * 原先只按列名找第一列：期末、上年年末下的同名列都取第一列 */
export function mapValueColumns(current: Record<string, any>, template: Record<string, any>): (number | null)[] {
  const src = valueColumnIds(current)
  const dst = valueColumnIds(template)
  const out: (number | null)[] = dst.map(() => null)
  const used = new Set<number>()
  for (const same of COLUMN_TIERS) {
    dst.forEach((d, j) => {
      if (out[j] != null) return
      const i = src.findIndex((s, k) => !used.has(k) && same(s, d))
      if (i >= 0) { out[j] = i; used.add(i) }
    })
  }
  return out
}

/**
 * 「➕ 行 / ➖ 行」的位置：新行插在第一个上方有明细的合计 / 小计行之前（标题式小计表插进第一组，没有合计行放末尾）；
 * 删最后一个可删的明细行（合计 / 小计、「其中：」标记、减项 / 加项、占位行、集团下推的固定行都不删），
 * 明细行不足两行时不删（`deleteAt = -1`）。
 */
export function structureRowTargets(rows: readonly unknown[]): { insertAt: number; deleteAt: number } {
  let firstTotal = -1
  let insertAt = -1
  let seenDetail = false
  rows.forEach((row, i) => {
    const kind = rowKind(row)
    if (kind === 'total' || kind === 'subtotal') {
      if (firstTotal < 0) firstTotal = i
      if (seenDetail && insertAt < 0) insertAt = i
    } else if (kind === 'data' || kind === 'marker' || kind === 'sub') {
      seenDetail = true
    }
  })
  const details = rows.flatMap((row, i) => (rowKind(row) === 'data' ? [i] : []))
  const deletable = details.filter(i => !isPushedFixedRow(rows[i]))
  return {
    insertAt: insertAt >= 0 ? insertAt : firstTotal >= 0 ? firstTotal : rows.length,
    deleteAt: details.length > 1 && deletable.length ? deletable[deletable.length - 1] : -1,
  }
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
    if (isTotalRow(row) || isPushedFixedRow(row)) return // 合计 / 小计行、集团下推的固定行不删
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

  /** 按合计构成重算合计 / 小计行（多段小计各算各的、「其中」不重复加、「小计 / 减：X / 合计」= 小计 − X） */
  function recalcTotals() {
    const table = getActiveTable()
    if (table) recalcNoteTableTotals(table)
  }

  // ─── Restore Template Structure ──────────────────────────────────────────

  /**
   * 恢复为模板结构（`templateTable` = 后端按当前表的表名 / 序号取的同一张模板表）：
   * 表头与逐列定义（`columns` / `_column_groups`，多级表头）一起换；金额按列身份搬（列定义 key 优先，其次「分组/列名」，
   * 同名列按第几次出现 —— 期末、上年年末下各有一列「应收账款」，只按列名会把期末数搬进上年年末）；行按行名对应
   * （同名多行依次对应），带回行类型、集团下推行身份与单元格模式（按列映射搬）。
   */
  function restoreTemplateStructure(templateTable: TableData) {
    const table = getActiveTable() as (TableData & Record<string, any>) | null
    if (!table) return
    const template = templateTable as TableData & Record<string, any>

    // Snapshot current state for undo
    const oldHeaders = [...table.headers]
    const oldRows = table.rows.map(r => ({ ...r, values: [...r.values] }))
    const oldStructure = Object.fromEntries(RESTORE_KEYS.map(k => [k, clone(table[k])]))

    const cmd: StructureCommand = {
      type: 'restoreTemplate',
      description: '恢复模板结构',
      redo: () => {
        const colMap = mapValueColumns(table, template) // 模板数值列 → 当前数值列
        const taken = new Set<number>()
        const findRow = (label: string): TableRow | null => {
          let i = oldRows.findIndex((r, k) => !taken.has(k) && r.label === label)
          if (i < 0) i = oldRows.findIndex((r, k) => !taken.has(k) && squash(r.label) === squash(label))
          if (i < 0) return null
          taken.add(i)
          return oldRows[i]
        }
        const newRows: TableRow[] = template.rows.map(templateRow => {
          const existing = findRow(templateRow.label)
          const restored: TableRow = {
            label: templateRow.label,
            values: colMap.map(src => (src == null || !existing ? null : existing.values[src] ?? null)),
            is_total: templateRow.is_total || false,
          }
          if (templateRow.row_type) restored.row_type = templateRow.row_type
          if (!existing) return restored
          for (const key of PUSHED_KEYS) {
            if (existing[key] !== undefined) restored[key] = existing[key]
          }
          for (const key of CELL_KEYS) {
            const meta = existing[key]
            if (!meta || typeof meta !== 'object') continue
            const moved: Record<string, unknown> = {}
            colMap.forEach((src, j) => { if (src != null && meta[String(src)] !== undefined) moved[String(j)] = clone(meta[String(src)]) })
            restored[key] = moved
          }
          return restored
        })

        table.headers.splice(0, table.headers.length, ...template.headers)
        table.rows.splice(0, table.rows.length, ...newRows)
        for (const key of STRUCTURE_KEYS) {
          if (template[key] !== undefined) table[key] = clone(template[key])
          else delete table[key]
        }
        if (Array.isArray(oldStructure._row_types)) {
          table._row_types = newRows.map(r => r.row_type || (r.is_total ? 'total' : 'data'))
        }
      },
      undo: () => {
        table.headers.splice(0, table.headers.length, ...oldHeaders)
        table.rows.splice(0, table.rows.length, ...oldRows)
        for (const key of RESTORE_KEYS) {
          if (oldStructure[key] !== undefined) table[key] = clone(oldStructure[key])
          else delete table[key]
        }
      },
    }
    pushCommand(cmd)
    recalcTotals()
  }

  // ─── Keyboard Shortcuts ──────────────────────────────────────────────────

  function handleKeydown(e: KeyboardEvent) {
    // Only handle when not in an input/textarea（表格承接框不算输入框：选中单元格时 Ctrl+Z 照常撤销结构改动）
    if (isTextEntryTarget(e.target)) return

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
