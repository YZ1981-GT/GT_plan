/**
 * useG1ImportExport — G1 交易性金融资产 导入导出 composable
 *
 * Spec: .kiro/specs/g1-trading-financial-assets/ Task 8.2 / Req 15.1~15.2
 *
 * 复用共享 useWorkpaperImportExport（apiPrefix='g1'，http/axios 带 Authorization），
 * 调用后端三端点：
 *   POST /api/workpapers/{wpId}/g1/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g1/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g1/import-data?sheet={code}
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）。
 * 支持 10 张动态行表格：G1-2/G1-3/G1-4/G1-5/G1-6/G1-7/G1-11/G1-12/G1-13/G1-14。
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from './useWorkpaperImportExport'

/** G1 支持导入导出的 sheet 编码（10 张动态行表格） */
export type G1ImportableSheet =
  | 'G1-2'
  | 'G1-3'
  | 'G1-4'
  | 'G1-5'
  | 'G1-6'
  | 'G1-7'
  | 'G1-11'
  | 'G1-12'
  | 'G1-13'
  | 'G1-14'

export const G1_API_PREFIX = 'g1'

/** 10 张可导入导出 sheet 的中文标签（供下拉菜单展示） */
export const G1_IMPORTABLE_SHEETS: { code: G1ImportableSheet; label: string }[] = [
  { code: 'G1-2', label: 'G1-2 明细表' },
  { code: 'G1-3', label: 'G1-3 调整分录' },
  { code: 'G1-4', label: 'G1-4 结存表' },
  { code: 'G1-5', label: 'G1-5 收益测算表' },
  { code: 'G1-6', label: 'G1-6 公允价值测试表' },
  { code: 'G1-7', label: 'G1-7 第三层次调节表' },
  { code: 'G1-11', label: 'G1-11 有价证券监盘表' },
  { code: 'G1-12', label: 'G1-12 盘点倒轧表' },
  { code: 'G1-13', label: 'G1-13 检查表' },
  { code: 'G1-14', label: 'G1-14 衍生金融工具核查表' },
]

/** sheetName → 可导入导出 sheet code（用于按当前 sheet 过滤下拉项） */
export function resolveG1ImportableSheet(sheetName: string): G1ImportableSheet | null {
  const m = (sheetName || '').match(/G1-(\d+)/)
  if (!m) return null
  const code = `G1-${m[1]}` as G1ImportableSheet
  return G1_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export interface UseG1ImportExportOptions {
  wpId: Ref<string>
}

export interface UseG1ImportExportReturn {
  importing: Ref<boolean>
  lastError: Ref<string | null>
  sheets: { code: G1ImportableSheet; label: string }[]
  exportTemplate: (sheet: G1ImportableSheet) => Promise<void>
  exportData: (sheet: G1ImportableSheet) => Promise<void>
  importData: (sheet: G1ImportableSheet, file: File) => Promise<ImportExportResult | null>
  apiPrefix: string
}

export function useG1ImportExport(options: UseG1ImportExportOptions): UseG1ImportExportReturn {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G1_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G1_IMPORTABLE_SHEETS,
    exportTemplate: (sheet) => base.exportTemplate(sheet),
    exportData: (sheet) => base.exportData(sheet),
    importData: (sheet, file) => base.importData(sheet, file),
    apiPrefix: G1_API_PREFIX,
  }
}

export default useG1ImportExport
