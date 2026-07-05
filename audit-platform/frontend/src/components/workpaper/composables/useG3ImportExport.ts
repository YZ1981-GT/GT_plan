/**
 * useG3ImportExport — G3 应收股利 导入导出 composable
 *
 * Spec: .kiro/specs/g3-dividend-receivable/ Task 8.2 / Req 14.1~14.4
 *
 * 复用共享 useWorkpaperImportExport（apiPrefix='g3'，http/axios 带 Authorization），
 * 调用后端三端点：
 *   POST /api/workpapers/{wpId}/g3/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g3/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g3/import-data?sheet={code}
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）。
 * 支持 5 张动态行表格：G3-1/G3-2/G3-3/G3-4/G3-5。
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from './useWorkpaperImportExport'

/** G3 支持导入导出的 sheet 编码（5 张动态行表格） */
export type G3ImportableSheet =
  | 'G3-1'
  | 'G3-2'
  | 'G3-3'
  | 'G3-4'
  | 'G3-5'

export const G3_API_PREFIX = 'g3'

/** 5 张可导入导出 sheet 的中文标签（供下拉菜单展示） */
export const G3_IMPORTABLE_SHEETS: { code: G3ImportableSheet; label: string }[] = [
  { code: 'G3-1', label: 'G3-1 审定表' },
  { code: 'G3-2', label: 'G3-2 明细表' },
  { code: 'G3-3', label: 'G3-3 调整分录' },
  { code: 'G3-4', label: 'G3-4 测算及检查表' },
  { code: 'G3-5', label: 'G3-5 长期未收回检查' },
]

/** sheetName → 可导入导出 sheet code（用于按当前 sheet 过滤下拉项） */
export function resolveG3ImportableSheet(sheetName: string): G3ImportableSheet | null {
  const m = (sheetName || '').match(/G3-(\d+)/)
  if (!m) return null
  const code = `G3-${m[1]}` as G3ImportableSheet
  return G3_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export interface UseG3ImportExportOptions {
  wpId: Ref<string>
}

export interface UseG3ImportExportReturn {
  importing: Ref<boolean>
  lastError: Ref<string | null>
  sheets: { code: G3ImportableSheet; label: string }[]
  exportTemplate: (sheet: G3ImportableSheet) => Promise<void>
  exportData: (sheet: G3ImportableSheet) => Promise<void>
  importData: (sheet: G3ImportableSheet, file: File) => Promise<ImportExportResult | null>
  apiPrefix: string
}

export function useG3ImportExport(options: UseG3ImportExportOptions): UseG3ImportExportReturn {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G3_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G3_IMPORTABLE_SHEETS,
    exportTemplate: (sheet) => base.exportTemplate(sheet),
    exportData: (sheet) => base.exportData(sheet),
    importData: (sheet, file) => base.importData(sheet, file),
    apiPrefix: G3_API_PREFIX,
  }
}

export default useG3ImportExport
