/**
 * cnoteHelpers.ts — GtCNoteTable 共享纯函数
 *
 * 从 GtCNoteTable.vue 原 733-776 行剪切，供 shell / CNoteCell / useCNoteFormula 共用。
 * spec: gt-c-note-table-shrink Task 1
 */
import type { SubClass, SubTableSchema, ColumnDefWithKey, RowData } from '../GtCNoteTable.types'

export function genRowId(): string {
  return `row-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

export function deriveSubClassFromStandard(std: string | undefined): SubClass {
  if (!std) return 'listed'
  return std.startsWith('soe') ? 'soe' : 'listed'
}

export function deriveStandardFromSubClass(
  sub: SubClass,
  prevStandard: string | undefined,
): string {
  // Preserve scope (standalone / consolidated)
  const scope = (prevStandard && prevStandard.includes('consolidated'))
    ? 'consolidated'
    : 'standalone'
  return `${sub}_${scope}`
}

export function isLabelField(field: string): boolean {
  return (
    field === 'category_label' ||
    field === 'aging_label' ||
    field === 'movement_label' ||
    field === 'maturity_label' ||
    field === 'guarantee_label' ||
    field === 'ecl_stage' ||
    field.endsWith('_label')
  )
}

export function escapeNumber(v: unknown): number | null {
  if (v === null || v === undefined || v === '') return null
  const n = typeof v === 'number' ? v : parseFloat(String(v))
  return isNaN(n) ? null : n
}

export function formatPercent(value: number | string | null | undefined): string {
  if (value == null || value === '') return ''
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (typeof num !== 'number' || isNaN(num)) return ''
  return `${num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

/** Get the label column field for a sub-table (first readonly/label column) */
export function labelColumnField(
  st: SubTableSchema,
  visibleCols: ColumnDefWithKey[],
): string | null {
  const first = visibleCols[0]
  if (first && (first.readonly || isLabelField(first.field))) return first.field
  return null
}

/** Build static rows view merged with stored data */
export function staticRowsView(
  st: SubTableSchema,
  storedRows: RowData[],
  visibleCols: ColumnDefWithKey[],
): RowData[] {
  const defs = st.static_rows ?? []
  const storedMap = new Map<string, RowData>()
  for (const r of storedRows) {
    if (r.id) storedMap.set(String(r.id), r)
  }
  const lf = labelColumnField(st, visibleCols)
  return defs.map(def => {
    const existing = storedMap.get(def.id)
    if (existing) {
      if (lf && !existing[lf]) existing[lf] = def.label
      existing._label = def.label
      existing._is_grand_total = def.is_grand_total
      existing._is_subtotal = def.is_subtotal
      existing._indent = def.indent ?? 0
      return existing
    }
    const fresh: RowData = {
      id: def.id,
      _label: def.label,
      _is_grand_total: def.is_grand_total,
      _is_subtotal: def.is_subtotal,
      _indent: def.indent ?? 0,
    }
    if (lf) fresh[lf] = def.label
    return fresh
  })
}

/** Build an empty row for dynamic sub-table */
export function buildEmptyRow(
  st: SubTableSchema,
  visibleCols: ColumnDefWithKey[],
  currentRowCount: number,
): RowData {
  const row: RowData = { _row_id: genRowId() }
  for (const col of visibleCols) {
    if (col.field === 'seq') {
      row[col.field] = currentRowCount + 1
      continue
    }
    if (col.type === 'multi_enum') row[col.field] = []
    else if (col.type === 'number') row[col.field] = null
    else if (col.type === 'boolean') row[col.field] = false
    else row[col.field] = col.default ?? ''
  }
  return row
}
