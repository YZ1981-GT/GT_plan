/**
 * 高级查询共享 xlsx 导出工具（advanced-query-consolidation Req2）
 *
 * CustomQueryDialog / CustomQueryTab 三方复用，消除各自内联 XLSX.utils.aoa_to_sheet 重复实现。
 * AdvancedQueryBuilder 保留后端 blob 导出路径（大数据），仅复用 sanitizeExportName 对齐文件名。
 */

import { resolveColumnLabel } from './queryColumnLabels'

export interface QueryExportInput {
  /** 列 key 顺序 */
  columns: string[]
  /** 结果行 */
  rows: Record<string, any>[]
  /** 列标题解析函数，缺省用 resolveColumnLabel */
  labelFn?: (key: string) => string
  /** 已按调用方规则拼好的文件名（不含 .xlsx 后缀） */
  fileName: string
  /** sheet 名称，默认「查询结果」 */
  sheetName?: string
}

/**
 * 前端 xlsx 导出（动态 import('xlsx')）。
 * 首行 = labelFn(key) 中文标题；数据行 = row[key] ?? ''；列宽默认 16。
 */
export async function exportQueryResultToXlsx(input: QueryExportInput): Promise<void> {
  const { columns, rows, fileName, sheetName = '查询结果' } = input
  const labelFn = input.labelFn || resolveColumnLabel

  const XLSX = await import('xlsx')
  const wb = XLSX.utils.book_new()
  const headers = columns.map(c => labelFn(c))
  const dataRows = rows.map(r => columns.map(c => r[c] ?? ''))
  const ws = XLSX.utils.aoa_to_sheet([headers, ...dataRows])
  ws['!cols'] = headers.map(() => ({ wch: 16 }))
  XLSX.utils.book_append_sheet(wb, ws, sheetName)
  XLSX.writeFile(wb, `${sanitizeExportName(fileName)}.xlsx`)
}

/** 文件名清洗：去 Windows 非法字符 + emoji + 前后空白 */
export function sanitizeExportName(s: string): string {
  return s
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/[\u{1F000}-\u{1FFFF}\u{2600}-\u{27BF}\u{FE00}-\u{FE0F}\u{200D}]/gu, '')
    .trim() || '导出'
}
