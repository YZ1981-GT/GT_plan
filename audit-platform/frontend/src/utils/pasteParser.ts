/**
 * pasteParser — 剪贴板数据解析工具（纯函数，无框架依赖）
 * 
 * 从 useCopyPaste composable 抽出的纯解析逻辑，方便单独测试。
 */

/** 粘贴 diff 预览中单个单元格的变更 */
export interface PasteDiffCell { rowIdx: number; colIdx: number; key: string; oldValue: string; newValue: string }
/** 粘贴 diff 预览结果 */
export interface PasteDiffResult { cells: PasteDiffCell[]; rowCount: number; colCount: number; overflowCount: number }
/** 审计日志摘要（不含剪贴板原文） */
export interface PasteAuditSummary { action: 'paste'; timestamp: number; rowCount: number; colCount: number; cellCount: number; startRow: number; startCol: number; sampleChanges: Array<{ key: string; row: number; old: string; new: string }> }
/** Undo stack 条目 */
export interface UndoEntry { type: 'paste'; timestamp: number; changes: Array<{ rowIdx: number; colIdx: number; key: string; oldValue: string; newValue: string }> }

/**
 * 解析金额字符串：千分位、括号负数、百分比、空白/横杠
 */
export function parseAmountString(raw: string): string {
  if (raw == null) return ''
  const trimmed = raw.trim()
  if (trimmed === '' || trimmed === '-' || trimmed === '\u2014' || trimmed === '\u2013') return ''
  if (trimmed.endsWith('%')) {
    const np = trimmed.slice(0, -1).replace(/,/g, '').trim()
    const n = Number(np)
    if (!isNaN(n)) return String(n / 100)
    return trimmed
  }
  const bm = trimmed.match(/^\((.+)\)$/)
  if (bm) {
    const inner = bm[1].replace(/,/g, '').trim()
    const n = Number(inner)
    if (!isNaN(n)) return String(-n)
    return trimmed
  }
  const nc = trimmed.replace(/,/g, '')
  const n = Number(nc)
  if (!isNaN(n) && nc !== '') return String(n)
  return trimmed
}

/**
 * 从 HTML 中解析 table 为二维字符串数组
 */
export function parseHtmlTable(html: string): string[][] | null {
  if (!html || !/<table[\s>]/i.test(html)) return null
  const parser = new DOMParser()
  const doc = parser.parseFromString(html, 'text/html')
  const table = doc.querySelector('table')
  if (!table) return null
  const trs = table.querySelectorAll('tr')
  if (trs.length === 0) return null
  const matrix: string[][] = []
  for (const tr of trs) {
    const cells = tr.querySelectorAll('td, th')
    const row: string[] = []
    for (const cell of cells) row.push((cell.textContent || '').trim())
    if (row.length > 0) matrix.push(row)
  }
  return matrix.length > 0 ? matrix : null
}

/**
 * 从纯文本解析为二维矩阵（制表符/换行分隔）
 */
export function parseTextMatrix(text: string): string[][] {
  if (!text || !text.trim()) return []
  return text.split(/\r?\n/).filter(l => l.length > 0).map(l => l.split('\t'))
}

/**
 * 生成粘贴 diff 预览（纯函数）
 */
export function buildPasteDiff(
  pasteMatrix: string[][],
  startRow: number,
  startCol: number,
  tableData: Record<string, any>[],
  columns: { key: string; label: string }[],
  normalizeAmounts = true,
): PasteDiffResult {
  const cells: PasteDiffCell[] = []
  let overflowCount = 0
  if (!pasteMatrix.length) return { cells, rowCount: 0, colCount: 0, overflowCount: 0 }
  for (let ri = 0; ri < pasteMatrix.length; ri++) {
    const tR = startRow + ri
    if (tR >= tableData.length) { overflowCount += pasteMatrix[ri].length; continue }
    for (let ci = 0; ci < pasteMatrix[ri].length; ci++) {
      const tC = startCol + ci
      if (tC >= columns.length) { overflowCount++; continue }
      const cd = columns[tC]
      const nv = normalizeAmounts ? parseAmountString(pasteMatrix[ri][ci]) : pasteMatrix[ri][ci]
      const ov = String(tableData[tR][cd.key] ?? '')
      if (ov !== nv) cells.push({ rowIdx: tR, colIdx: tC, key: cd.key, oldValue: ov, newValue: nv })
    }
  }
  return { cells, rowCount: pasteMatrix.length, colCount: pasteMatrix.length > 0 ? Math.max(...pasteMatrix.map(r => r.length)) : 0, overflowCount }
}
