/**
 * FormulaEditDialog WP 源表浏览 — 可单测的纯函数（custom-workpaper-formula-binding P4/P13）
 */

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
