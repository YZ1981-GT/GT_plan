/**
 * 高级查询共享 xlsx 导出工具（advanced-query-consolidation Req2）
 *
 * CustomQueryDialog / CustomQueryTab 三方复用，消除各自内联 XLSX.utils.aoa_to_sheet 重复实现。
 * AdvancedQueryBuilder 保留后端 blob 导出路径（大数据），仅复用 sanitizeExportName 对齐文件名。
 */

import { exportData } from '@/composables/useExcelIO'

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
 * 前端 xlsx 导出（走 `useExcelIO` 单一入口）。
 * 首行 = labelFn(key) 中文标题；数据行 = row[key] ?? ''；列宽固定 16。
 *
 * ## 迁移说明（spec: frontend-excel-io-single-entry-convergence，B1 批）
 *
 * 改造前是裸 `await import('xlsx')` + 手搭 `aoa_to_sheet`。收敛到 `exportData` 时
 * **三个显式关闭一个都不能省**，否则产物会变（等价守卫 `excelIoEquivalence.spec.ts`
 * 会打红）：
 * - `applyStyles: false` —— 本导出原本无任何单元格样式；开着会被加上仿宋 + 三线表
 * - `successMessage: false` —— 调用方（CustomQueryDialog / CustomQueryTab）自行弹提示，
 *   封装再弹一次就成了双弹窗
 * - `width: 16` —— 原本是固定 `wch: 16`，不显式给就会落到自适应算法上
 */
export async function exportQueryResultToXlsx(input: QueryExportInput): Promise<void> {
  const { columns, rows, fileName, sheetName = '查询结果' } = input
  const labelFn = input.labelFn || resolveColumnLabel

  await exportData({
    data: rows,
    columns: columns.map(c => ({ key: c, header: labelFn(c), width: 16 })),
    sheetName,
    fileName: `${sanitizeExportName(fileName)}.xlsx`,
    applyStyles: false,
    successMessage: false,
  })
}

/** 文件名清洗：去 Windows 非法字符 + emoji + 前后空白 */
export function sanitizeExportName(s: string): string {
  return s
    .replace(/[\\/:*?"<>|]/g, '_')
    .replace(/[\u{1F000}-\u{1FFFF}\u{2600}-\u{27BF}\u{FE00}-\u{FE0F}\u{200D}]/gu, '')
    .trim() || '导出'
}
