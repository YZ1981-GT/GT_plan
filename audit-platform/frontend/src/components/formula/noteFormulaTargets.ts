/**
 * 附注公式目标单元格（spec note-pull-header-formula-closure R3 / ADR-4）。
 *
 * 目标串与后端 `note_formula_tables.formula_key` 同一写法：第 1 张表 `行:列`（兼容旧数据），第 n+1 张 `t{n}:行:列`；
 * 行、列从 0 起，列不含标签列。目标清单（逐表行名 / 列名）由公式列表接口 `targets` 给出（与执行器同一份表格）。
 */

export interface NoteFormulaTargetTable {
  index: number
  name: string
  rows: string[]
  columns: string[]
}

export interface NoteFormulaCell {
  table: number
  row: number
  col: number
}

const KEY_RE = /^\s*(?:[tT](\d+)\s*:\s*)?(\d+)\s*:\s*(\d+)\s*$/

export function formulaKey(cell: NoteFormulaCell): string {
  return cell.table === 0 ? `${cell.row}:${cell.col}` : `t${cell.table}:${cell.row}:${cell.col}`
}

export function parseFormulaKey(key: unknown): NoteFormulaCell | null {
  const m = KEY_RE.exec(String(key ?? ''))
  if (!m) return null
  return { table: Number(m[1] ?? 0), row: Number(m[2]), col: Number(m[3]) }
}

/** 「表名 · 行名 · 列名」；认不出 / 超出范围返回原目标串。 */
export function describeFormulaTarget(target: unknown, tables: NoteFormulaTargetTable[]): string {
  const cell = parseFormulaKey(target)
  const table = cell ? tables.find((t) => t.index === cell.table) : undefined
  if (!cell || !table || cell.row >= table.rows.length || cell.col >= table.columns.length) return String(target ?? '')
  return `${table.name} · ${table.rows[cell.row]} · ${table.columns[cell.col]}`
}

/** 应用自动运算的结果提示：更新格数 + 没写入的原因（前 3 种，带次数）。 */
export function describeApplyResult(result: any, verb = '公式已应用'): string {
  const executed = Number(result?.executed || 0)
  const updated = Number(result?.updated || 0)
  const skipped = (Array.isArray(result?.results) ? result.results : []).filter((r: any) => r?.status === 'skipped')
  let text = `${verb}：执行 ${executed} 个，更新 ${updated} 个单元格`
  if (skipped.length) {
    const counts = new Map<string, number>()
    for (const r of skipped) {
      const why = String(r?.reason || '未写入')
      counts.set(why, (counts.get(why) || 0) + 1)
    }
    const top = [...counts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 3)
    text += `；${skipped.length} 个未写入（${top.map(([why, n]) => `${why} ${n} 个`).join('、')}）`
  }
  return text
}
