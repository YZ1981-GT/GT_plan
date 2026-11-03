/**
 * AI 复核疑点的来源地址解析（spec llm-linkage-audit-practice-closure 任务 10）。
 *
 * 模型给出的 `sheet_location` 常见三种写法：`审定表D2-1!C8`、`C8`、`审定表D2-1`。
 * 带单元格时走平台统一的 `workpaper:locate-cell` 定位到格；只有表名时仍切到该表。
 */
export interface FindingLocation {
  sheetName: string | null
  cellRef: string | null
}

const CELL_RE = /^\$?([A-Za-z]{1,3})\$?(\d{1,7})$/

export function parseFindingLocation(raw: string | null | undefined): FindingLocation {
  const text = (raw ?? '').trim()
  if (!text) return { sheetName: null, cellRef: null }
  const bang = text.lastIndexOf('!')
  const sheetPart = bang >= 0 ? text.slice(0, bang).trim().replace(/^'(.*)'$/, '$1') : ''
  const tail = (bang >= 0 ? text.slice(bang + 1) : text).trim()
  const cell = CELL_RE.exec(tail)
  if (cell) {
    return { sheetName: sheetPart || null, cellRef: `${cell[1].toUpperCase()}${cell[2]}` }
  }
  return { sheetName: text, cellRef: null }
}
