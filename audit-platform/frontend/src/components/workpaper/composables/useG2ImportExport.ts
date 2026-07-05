/**
 * useG2ImportExport — G2 应收利息 导入导出 composable
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 8.2 / Req 14.1~14.4
 *
 * 复用共享 useWorkpaperImportExport（apiPrefix='g2'，http/axios 带 Authorization），
 * 调用后端三端点：
 *   POST /api/workpapers/{wpId}/g2/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g2/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g2/import-data?sheet={code}
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）。
 * 支持 7 张动态行表格：G2-2/G2-3/G2-4/G2-5/G2-6/G2-7/G2-8。
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from './useWorkpaperImportExport'

/** G2 支持导入导出的 sheet 编码（7 张动态行表格） */
export type G2ImportableSheet =
  | 'G2-2'
  | 'G2-3'
  | 'G2-4'
  | 'G2-5'
  | 'G2-6'
  | 'G2-7'
  | 'G2-8'

export const G2_API_PREFIX = 'g2'

/** 7 张可导入导出 sheet 的中文标签（供下拉菜单展示） */
export const G2_IMPORTABLE_SHEETS: { code: G2ImportableSheet; label: string }[] = [
  { code: 'G2-2', label: 'G2-2 明细表' },
  { code: 'G2-3', label: 'G2-3 坏账准备明细' },
  { code: 'G2-4', label: 'G2-4 调整分录' },
  { code: 'G2-5', label: 'G2-5 利息测算表' },
  { code: 'G2-6', label: 'G2-6 长期未收回检查' },
  { code: 'G2-7', label: 'G2-7 坏账准备测算' },
  { code: 'G2-8', label: 'G2-8 凭证检查表' },
]

/** sheetName → 可导入导出 sheet code（用于按当前 sheet 过滤下拉项） */
export function resolveG2ImportableSheet(sheetName: string): G2ImportableSheet | null {
  const m = (sheetName || '').match(/G2-(\d+)/)
  if (!m) return null
  const code = `G2-${m[1]}` as G2ImportableSheet
  return G2_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export interface UseG2ImportExportOptions {
  wpId: Ref<string>
}

export interface UseG2ImportExportReturn {
  importing: Ref<boolean>
  lastError: Ref<string | null>
  sheets: { code: G2ImportableSheet; label: string }[]
  exportTemplate: (sheet: G2ImportableSheet) => Promise<void>
  exportData: (sheet: G2ImportableSheet) => Promise<void>
  importData: (sheet: G2ImportableSheet, file: File) => Promise<ImportExportResult | null>
  apiPrefix: string
}

export function useG2ImportExport(options: UseG2ImportExportOptions): UseG2ImportExportReturn {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G2_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G2_IMPORTABLE_SHEETS,
    exportTemplate: (sheet) => base.exportTemplate(sheet),
    exportData: (sheet) => base.exportData(sheet),
    importData: (sheet, file) => base.importData(sheet, file),
    apiPrefix: G2_API_PREFIX,
  }
}

export default useG2ImportExport
