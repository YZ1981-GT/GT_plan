/**
 * useH10ImportExport — H10 资产处置损益 导入导出
 * H10-2 / H10-3 × 3 端点
 */
import { type Ref } from 'vue'
import { H10_API_PREFIX, H10_IMPORTABLE_SHEETS, type H10ImportableSheet } from './h10Constants'
import { useWorkpaperImportExport } from './useWorkpaperImportExport'

export { H10_IMPORTABLE_SHEETS, H10_API_PREFIX }
export type { H10ImportableSheet }

export function resolveH10ImportableSheet(sheetName: string): H10ImportableSheet | null {
  const m = (sheetName || '').match(/H10-(\d+)/)
  if (!m) return null
  const code = `H10-${m[1]}` as H10ImportableSheet
  return H10_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export function useH10ImportExport(options: { wpId: Ref<string> }) {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: H10_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: H10_IMPORTABLE_SHEETS,
    exportTemplate: (sheet: H10ImportableSheet) => base.exportTemplate(sheet),
    exportData: (sheet: H10ImportableSheet) => base.exportData(sheet),
    importData: (sheet: H10ImportableSheet, file: File) => base.importData(sheet, file),
    apiPrefix: H10_API_PREFIX,
  }
}

export default useH10ImportExport
