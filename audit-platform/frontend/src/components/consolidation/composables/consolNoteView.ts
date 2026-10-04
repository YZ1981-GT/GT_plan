/**
 * 合并附注页的纯逻辑（spec consol-elimination-single-source-push 任务 12.2 / 需求 6）。
 *
 * - 编辑行 ⇄ 已保存数据（`consol_note_data.data`）：手工标记 `manual_cells` 随行对象移动，删行 / 插行后位置仍对；
 *   保存时按当前行号写回，并保留已保存数据里的其他键（整包替换不再丢 `manual_cells`）。
 * - 「按公式填入」结果的汇总与明细；「查看差额」的行与核对（线性公式各下级贡献之和 = 合并数）。
 * 金额只做 Decimal 比较，不在前端重算。
 */
import Decimal from 'decimal.js'
import type {
  ConsolNoteBreakdown,
  ConsolNoteBreakdownCell,
  ConsolNoteFillResult,
  ConsolNoteFormulaList,
} from '@/services/consolidationApi'

/** 编辑行：列号 → 文本；`__manual` = 本行手工填写的列号（按公式填入时保留） */
export interface NoteEditRow {
  [col: number]: string
  __manual?: number[]
}

export interface ManualCell {
  row: number
  col: number
}

/** 编辑区至少显示的行数（不足补空行，便于直接录入） */
export const MIN_EDIT_ROWS = 5

function cellText(v: unknown): string {
  return v === null || v === undefined ? '' : String(v)
}

/** 解析 `manual_cells`（与后端同口径：{row, col} / [row, col] / "row:col"），无效项跳过 */
export function parseManualCells(raw: unknown): Map<number, Set<number>> {
  const out = new Map<number, Set<number>>()
  if (!Array.isArray(raw)) return out
  const put = (r: unknown, c: unknown) => {
    const row = Number(r)
    const col = Number(c)
    if (!Number.isInteger(row) || !Number.isInteger(col) || row < 0 || col < 0) return
    if (!out.has(row)) out.set(row, new Set())
    out.get(row)!.add(col)
  }
  for (const item of raw) {
    if (Array.isArray(item) && item.length === 2) put(item[0], item[1])
    else if (item && typeof item === 'object') put((item as any).row, (item as any).col)
    else if (typeof item === 'string' && item.includes(':')) {
      const [r, c] = item.split(':', 2)
      put(r, c)
    }
  }
  return out
}

export function emptyEditRow(width: number): NoteEditRow {
  const row: NoteEditRow = {}
  for (let j = 0; j < width; j++) row[j] = ''
  return row
}

/** 已保存数据（或模板行）→ 编辑行；手工标记按已保存数据的实际行号挂到行对象上 */
export function toEditRows(headers: ReadonlyArray<unknown>, rows: ReadonlyArray<unknown>, manualCells?: unknown): NoteEditRow[] {
  const width = headers.length
  const manual = parseManualCells(manualCells)
  const out = rows.map((r, ri) => {
    const row = emptyEditRow(width)
    if (Array.isArray(r)) for (let j = 0; j < width; j++) row[j] = cellText(r[j])
    const cols = [...(manual.get(ri) || [])].filter((c) => c >= 1 && c < width).sort((a, b) => a - b)
    if (cols.length) row.__manual = cols
    return row
  })
  while (out.length < MIN_EDIT_ROWS) out.push(emptyEditRow(width))
  return out
}

/** 编辑行 → 行数据 + 手工标记（按当前行号） */
export function fromEditRows(
  headers: ReadonlyArray<unknown>, editRows: ReadonlyArray<NoteEditRow>,
): { rows: string[][]; manual_cells: ManualCell[] } {
  const width = headers.length
  const rows = editRows.map((r) => headers.map((_, j) => cellText(r[j])))
  const manual_cells: ManualCell[] = []
  editRows.forEach((r, ri) => {
    for (const col of r.__manual || []) if (col >= 1 && col < width) manual_cells.push({ row: ri, col })
  })
  return { rows, manual_cells }
}

/** 保存体：保留已保存数据里的其他键，只替换表头 / 行 / 手工标记 */
export function notePayload(
  saved: Record<string, unknown> | null | undefined, headers: ReadonlyArray<unknown>, editRows: ReadonlyArray<NoteEditRow>,
): Record<string, unknown> {
  const { rows, manual_cells } = fromEditRows(headers, editRows)
  return { ...(saved || {}), headers: [...headers], rows, manual_cells }
}

export function isManual(row: NoteEditRow | null | undefined, col: number): boolean {
  return !!row?.__manual?.includes(col)
}

/** 手工改了某格（第 0 列是项目名，不参与取数，不标） */
export function markManual(row: NoteEditRow, col: number): void {
  if (col < 1 || isManual(row, col)) return
  row.__manual = [...(row.__manual || []), col].sort((a, b) => a - b)
}

export function clearManual(row: NoteEditRow, col: number): void {
  if (!row.__manual) return
  const rest = row.__manual.filter((c) => c !== col)
  if (rest.length) row.__manual = rest
  else delete row.__manual
}

// ─── 按公式填入结果 ───────────────────────────────────────────────────────────

export function fillSummaryText(res: Pick<ConsolNoteFillResult, 'filled' | 'kept_manual' | 'blank'>): string {
  const parts = [`已按公式填入 ${res.filled?.length || 0} 格`]
  if (res.kept_manual?.length) parts.push(`${res.kept_manual.length} 格手工填写已保留`)
  if (res.blank?.length) parts.push(`${res.blank.length} 格取不到数未填`)
  return parts.join('；')
}

export interface FillDetailRow {
  kind: 'kept' | 'blank'
  position: string
  target_row: number | null
  col_index: number
  current: string | null
  formula_value: string | null
  reason: string | null
}

function positionOf(rows: ReadonlyArray<ReadonlyArray<unknown>>, headers: ReadonlyArray<unknown>,
  targetRow: number | null, rowIndex: number, col: number): string {
  const label = targetRow !== null ? cellText(rows[targetRow]?.[0]).trim() : ''
  const rowText = label || (targetRow !== null ? `第 ${targetRow + 1} 行` : `模板第 ${rowIndex + 1} 行`)
  const colText = cellText(headers[col]).replace(/\s+/g, '') || `第 ${col + 1} 列`
  return `${rowText} · ${colText}`
}

/** 保留的手工单元格（当前值 vs 公式值）与取不到数的单元格（原因） */
export function fillDetailRows(res: ConsolNoteFillResult): FillDetailRow[] {
  const rows = (res.data?.rows || []) as ReadonlyArray<ReadonlyArray<unknown>>
  const headers = (res.data?.headers || []) as ReadonlyArray<unknown>
  const kept: FillDetailRow[] = (res.kept_manual || []).map((k) => ({
    kind: 'kept', position: positionOf(rows, headers, k.target_row, k.row_index, k.col_index),
    target_row: k.target_row, col_index: k.col_index, current: k.current, formula_value: k.formula_value, reason: null,
  }))
  const blank: FillDetailRow[] = (res.blank || []).map((b) => ({
    kind: 'blank', position: positionOf(rows, headers, b.target_row, b.row_index, b.col_index),
    target_row: b.target_row, col_index: b.col_index, current: null, formula_value: null, reason: b.reason,
  }))
  return [...kept, ...blank]
}

/** 有公式的章节（「全部按公式填入」只跑这些） */
export function sectionIdsWithFormulas(list: Pick<ConsolNoteFormulaList, 'sections'> | null | undefined): string[] {
  return (list?.sections || []).filter((s) => s.formulas?.length).map((s) => s.section_id)
}

// ─── 查看差额 ─────────────────────────────────────────────────────────────────

export interface NoteBreakdownRow extends ConsolNoteBreakdownCell {
  /** 「项目名 · 列名」 */
  position: string
}

export function noteBreakdownRows(bd: Pick<ConsolNoteBreakdown, 'cells'> | null | undefined): NoteBreakdownRow[] {
  return (bd?.cells || []).map((c) => ({
    ...c,
    position: `${(c.row_label || '').trim() || `第 ${c.row_index + 1} 行`} · ${c.col_name || `第 ${c.col_index + 1} 列`}`,
  }))
}

function dec(v: string | null | undefined): Decimal | null {
  if (v === null || v === undefined || v === '') return null
  try {
    const d = new Decimal(v)
    return d.isFinite() ? d : null
  } catch {
    return null
  }
}

export interface NoteBreakdownCheck {
  checked: number
  mismatched: string[]
  nonlinear: number
  blank: number
}

/** 线性公式：各下级贡献之和 = 合并数（到分）；非线性只计数；取不到数的不核对 */
export function noteBreakdownCheck(bd: Pick<ConsolNoteBreakdown, 'cells' | 'children'> | null | undefined): NoteBreakdownCheck {
  const out: NoteBreakdownCheck = { checked: 0, mismatched: [], nonlinear: 0, blank: 0 }
  const children = bd?.children || []
  for (const cell of noteBreakdownRows(bd)) {
    const total = dec(cell.consolidated)
    if (total === null) {
      out.blank += 1
      continue
    }
    if (!cell.linear) {
      out.nonlinear += 1
      continue
    }
    if (!children.length) continue
    const parts = children.map((ch) => dec(cell.children?.[ch.node_key]))
    if (parts.some((p) => p === null)) {
      out.blank += 1
      continue
    }
    out.checked += 1
    const sum = parts.reduce<Decimal>((s, p) => s.plus(p as Decimal), new Decimal(0))
    if (!sum.equals(total)) out.mismatched.push(cell.position)
  }
  return out
}

export function noteBreakdownCheckText(check: NoteBreakdownCheck): string {
  const parts = [check.mismatched.length
    ? `${check.mismatched.length} 格各下级贡献之和 ≠ 合并数`
    : `${check.checked} 格各下级贡献之和 = 合并数`]
  if (check.nonlinear) parts.push(`${check.nonlinear} 格公式非线性只给合并数`)
  if (check.blank) parts.push(`${check.blank} 格取不到数`)
  return `核对：${parts.join('；')}`
}

const _WS = /[\s\u3000]+/g

/**
 * 编辑区某格 → 差额里的同一单元格。公式按模板行号登记，已保存数据可能插删过行（与后端「按项目名找行」同口径）：
 * 同号同名优先，否则全表唯一同名；第 0 列与无公式的格返回 null。
 */
export function findBreakdownCell<T extends Pick<ConsolNoteBreakdownCell, 'row_index' | 'col_index' | 'row_label'>>(
  cells: ReadonlyArray<T>, rowLabel: string, rowIndex: number, col: number,
): T | null {
  if (col < 1) return null
  const want = (rowLabel || '').replace(_WS, '')
  const sameCol = cells.filter((c) => c.col_index === col)
  const exact = sameCol.find((c) => c.row_index === rowIndex && (c.row_label || '').replace(_WS, '') === want)
  if (exact) return exact
  if (!want) return null
  const hits = sameCol.filter((c) => (c.row_label || '').replace(_WS, '') === want)
  return hits.length === 1 ? hits[0] : null
}
