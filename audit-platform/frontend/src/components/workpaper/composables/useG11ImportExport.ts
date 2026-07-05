/**
 * useG11ImportExport — G11 投资收益 导入导出
 * 5 张表 × 3 端点 = 15：G11-1 / G11-2 / G11-3 / G11-4 / G11-5
 */
import { type Ref } from 'vue'
import { useWorkpaperImportExport } from './useWorkpaperImportExport'

export type G11ImportableSheet = 'G11-1' | 'G11-2' | 'G11-3' | 'G11-4' | 'G11-5'

export const G11_API_PREFIX = 'g11'

export const G11_IMPORTABLE_SHEETS: { code: G11ImportableSheet; label: string }[] = [
  { code: 'G11-1', label: 'G11-1 审定表' },
  { code: 'G11-2', label: 'G11-2 明细分析表' },
  { code: 'G11-3', label: 'G11-3 调整分录' },
  { code: 'G11-4', label: 'G11-4 收益率分析' },
  { code: 'G11-5', label: 'G11-5 凭证检查' },
]

export function resolveG11ImportableSheet(sheetName: string): G11ImportableSheet | null {
  const m = (sheetName || '').match(/G11-(\d+)/)
  if (!m) return null
  const code = `G11-${m[1]}` as G11ImportableSheet
  return G11_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export function useG11ImportExport(options: { wpId: Ref<string> }) {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G11_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G11_IMPORTABLE_SHEETS,
    exportTemplate: (sheet: G11ImportableSheet) => base.exportTemplate(sheet),
    exportData: (sheet: G11ImportableSheet) => base.exportData(sheet),
    importData: (sheet: G11ImportableSheet, file: File) => base.importData(sheet, file),
    apiPrefix: G11_API_PREFIX,
  }
}

export default useG11ImportExport
