/**
 * useG4SppiImportExport — G4 债权投资(SPPI组) 导入导出 composable
 *
 * 复用共享 useWorkpaperImportExport（apiPrefix='g4-sppi'），
 * 调用后端三端点：
 *   POST /api/workpapers/{wpId}/g4-sppi/export-template?sheet={code}
 *   POST /api/workpapers/{wpId}/g4-sppi/export-data?sheet={code}
 *   POST /api/workpapers/{wpId}/g4-sppi/import-data?sheet={code}
 *
 * sheet codes: G4-5 / G4-6 / G4-7 / G4-8
 * G4-6 按8段产品表分sheet；G4-8 按3区段分sheet
 *
 * UI 铁律：el-dropdown「导入导出 ▾」（导出模板/导出数据/导入数据）
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from './useWorkpaperImportExport'

/** G4(SPPI) 支持导入导出的 sheet 编码（4 张动态行表格） */
export type G4SppiImportableSheet = 'G4-5' | 'G4-6' | 'G4-7' | 'G4-8'

export const G4_SPPI_API_PREFIX = 'g4-sppi'

/** 4 张可导入导出 sheet 的中文标签 */
export const G4_SPPI_IMPORTABLE_SHEETS: { code: G4SppiImportableSheet; label: string; multiSheet?: boolean }[] = [
  { code: 'G4-5', label: 'G4-5 业务模式分析问卷' },
  { code: 'G4-6', label: 'G4-6 合同现金流量特征分析', multiSheet: true },
  { code: 'G4-7', label: 'G4-7 有价证券盘点表' },
  { code: 'G4-8', label: 'G4-8 盘点倒轧表', multiSheet: true },
]

/** sheetName → 可导入导出 sheet code */
export function resolveG4SppiImportableSheet(sheetName: string): G4SppiImportableSheet | null {
  const m = (sheetName || '').match(/G4-([5-8])/)
  if (!m) return null
  const code = `G4-${m[1]}` as G4SppiImportableSheet
  return G4_SPPI_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export interface UseG4SppiImportExportOptions {
  wpId: Ref<string>
}

export interface UseG4SppiImportExportReturn {
  importing: Ref<boolean>
  lastError: Ref<string | null>
  sheets: { code: G4SppiImportableSheet; label: string; multiSheet?: boolean }[]
  exportTemplate: (sheet: G4SppiImportableSheet) => Promise<void>
  exportData: (sheet: G4SppiImportableSheet) => Promise<void>
  importData: (sheet: G4SppiImportableSheet, file: File) => Promise<ImportExportResult | null>
  apiPrefix: string
}

export function useG4SppiImportExport(options: UseG4SppiImportExportOptions): UseG4SppiImportExportReturn {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G4_SPPI_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G4_SPPI_IMPORTABLE_SHEETS,
    exportTemplate: (sheet) => base.exportTemplate(sheet),
    exportData: (sheet) => base.exportData(sheet),
    importData: (sheet, file) => base.importData(sheet, file),
    apiPrefix: G4_SPPI_API_PREFIX,
  }
}

export default useG4SppiImportExport
