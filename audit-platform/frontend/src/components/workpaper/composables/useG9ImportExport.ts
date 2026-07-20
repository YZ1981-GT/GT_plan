/**
 * useG9ImportExport — G9 其他非流动金融资产 导入导出
 * G9-2~6 + 附注上市/国企
 */
import { type Ref } from 'vue'
import { useWorkpaperImportExport } from './useWorkpaperImportExport'

export type G9ImportableSheet =
  | 'G9-2'
  | 'G9-3'
  | 'G9-4'
  | 'G9-5'
  | 'G9-6'
  | '附注上市'
  | '附注国企'

export const G9_API_PREFIX = 'g9'

export const G9_IMPORTABLE_SHEETS: { code: G9ImportableSheet; label: string }[] = [
  { code: 'G9-2', label: 'G9-2 明细表' },
  { code: 'G9-3', label: 'G9-3 调整分录' },
  { code: 'G9-4', label: 'G9-4 公允价值测试' },
  { code: 'G9-5', label: 'G9-5 L3调节表' },
  { code: 'G9-6', label: 'G9-6 凭证检查' },
  { code: '附注上市', label: '附注披露（上市公司）' },
  { code: '附注国企', label: '附注披露（国企）' },
]

export function resolveG9ImportableSheet(sheetName: string): G9ImportableSheet | null {
  if (/附注/.test(sheetName || '')) {
    return /国企|国有/.test(sheetName) ? '附注国企' : '附注上市'
  }
  const m = (sheetName || '').match(/G9-(\d+)/)
  if (!m) return null
  const code = `G9-${m[1]}` as G9ImportableSheet
  return G9_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export function useG9ImportExport(options: { wpId: Ref<string> }) {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G9_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G9_IMPORTABLE_SHEETS,
    exportTemplate: (sheet: G9ImportableSheet) => base.exportTemplate(sheet),
    exportData: (sheet: G9ImportableSheet) => base.exportData(sheet),
    importData: (sheet: G9ImportableSheet, file: File) => base.importData(sheet, file),
    apiPrefix: G9_API_PREFIX,
  }
}

export default useG9ImportExport
