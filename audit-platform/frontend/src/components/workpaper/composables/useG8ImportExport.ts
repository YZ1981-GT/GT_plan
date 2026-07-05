/**
 * useG8ImportExport — G8 其他权益工具投资 导入导出
 * 4 张表 × 3 端点 = 12：G8-2 / G8-3 / G8-4 / G8-6
 */
import { type Ref } from 'vue'
import { useWorkpaperImportExport } from './useWorkpaperImportExport'
import { G8_IMPORTABLE_SHEETS, type G8ImportableSheet } from './g8Constants'

export type { G8ImportableSheet }

export const G8_API_PREFIX = 'g8'

export { G8_IMPORTABLE_SHEETS }

export function resolveG8ImportableSheet(sheetName: string): G8ImportableSheet | null {
  const m = (sheetName || '').match(/G8-(\d+)/)
  if (!m) return null
  const code = `G8-${m[1]}` as G8ImportableSheet
  return G8_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export function useG8ImportExport(options: { wpId: Ref<string> }) {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G8_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G8_IMPORTABLE_SHEETS,
    exportTemplate: (sheet: G8ImportableSheet) => base.exportTemplate(sheet),
    exportData: (sheet: G8ImportableSheet) => base.exportData(sheet),
    importData: (sheet: G8ImportableSheet, file: File) => base.importData(sheet, file),
    apiPrefix: G8_API_PREFIX,
  }
}

export default useG8ImportExport
