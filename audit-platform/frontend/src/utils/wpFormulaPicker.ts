/**
 * FormulaEditDialog WP 源表浏览 — 可单测的纯函数（custom-workpaper-formula-binding P4/P13）
 *
 * ACNR 消费者接入（acnr-consumer-wiring Req 14.3/14.5, task 18.3）：
 *   新增 mapAcnrCellsToPickerRows，把 ACNR listCells 返回的坐标锚点映射为
 *   与 mapRegistryToPickerRows 同构的弹窗行，`_ref = cell.formula_ref`（grammar_v1）。
 */

import type { AcnrCellEntry } from '@/services/acnr/useAcnr'

export interface WpPickerRow {
  row_code: string
  row_name: string
  cell?: string
  indent_level?: number
  formula?: string
  _ref?: string
}

export interface RegistryWpEntry {
  wp_code?: string
  label?: string
  cell?: string
  formula_ref?: string
}

/** 地址注册表 WP 域条目 → 弹窗行 */
export function mapRegistryToPickerRows(
  entries: RegistryWpEntry[],
  fallbackRef: (e: RegistryWpEntry) => string,
): WpPickerRow[] {
  return entries.map((e) => ({
    row_code: e.wp_code || '',
    row_name: e.label || '',
    cell: e.cell || '',
    indent_level: 0,
    formula: '',
    _ref: e.formula_ref || fallbackRef(e),
  }))
}

/**
 * ACNR listCells 坐标锚点 → 弹窗行（acnr-consumer-wiring Req 14.3/14.5）
 *
 * 产出与 mapRegistryToPickerRows 完全同构的 WpPickerRow，下游 FormulaEditDialog
 * 逻辑（filteredBrowserRows / onBrowserRowClick / pickerRowsSubsetOfRegistry）无需改动。
 * `_ref` 直接取 ACNR 的 `formula_ref`（grammar_v1 形态，可被 full_resolve/parseUri round-trip）。
 *
 * addr_id 形如 `{wp_code}/{sheet_code}/{coordinate_key}`：
 *   - row_code ← sheet_code（无法拆分时回退 wp_code / cell_address）
 *   - row_name ← semantic_label（回退 cell_address / addr_id）
 *   - cell     ← cell_address
 */
export function mapAcnrCellsToPickerRows(cells: AcnrCellEntry[]): WpPickerRow[] {
  return (cells || []).map((c) => {
    const parts = (c.addr_id || '').split('/')
    const sheetCode = parts.length >= 2 ? parts[1] : parts[0] || ''
    const cellAddr = c.cell_address || (parts.length >= 3 ? parts[2] : '') || ''
    return {
      row_code: sheetCode || cellAddr || '',
      row_name: c.semantic_label || cellAddr || c.addr_id || '',
      cell: cellAddr,
      indent_level: 0,
      formula: '',
      _ref: c.formula_ref || '',
    }
  })
}

/** 与 FormulaEditDialog.filteredBrowserRows 一致 */
export function filterWpBrowserRows(rows: WpPickerRow[], keyword: string): WpPickerRow[] {
  const kw = keyword.toLowerCase().trim()
  if (!kw) return rows
  return rows.filter(
    (r) =>
      (r.row_code || '').toLowerCase().includes(kw) ||
      (r.row_name || '').toLowerCase().includes(kw),
  )
}

/** P4：弹窗可选项必须是注册表条目的子集 */
export function pickerRowsSubsetOfRegistry(
  pickerRows: WpPickerRow[],
  registryRefs: Set<string>,
): boolean {
  return pickerRows.every((r) => (r._ref ? registryRefs.has(r._ref) : true))
}
