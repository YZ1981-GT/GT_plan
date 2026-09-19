/**
 * useG10ImportExport — G10 交易性金融负债 导入导出
 * G10-1~8 + 附注 × 3 端点
 */
import { type Ref } from 'vue'
import { useWorkpaperImportExport } from './useWorkpaperImportExport'

export type G10ImportableSheet =
  | 'G10-1'
  | 'G10-2'
  | 'G10-3'
  | 'G10-4'
  | 'G10-5'
  | 'G10-6'
  | 'G10-7'
  | 'G10-8'
  | '附注上市'
  | '附注国企'

export const G10_API_PREFIX = 'g10'

export const G10_IMPORTABLE_SHEETS: { code: G10ImportableSheet; label: string }[] = [
  { code: 'G10-1', label: 'G10-1 审定表' },
  { code: 'G10-2', label: 'G10-2 明细表' },
  { code: 'G10-3', label: 'G10-3 调整分录' },
  { code: 'G10-4', label: 'G10-4 分类适当性检查' },
  { code: 'G10-5', label: 'G10-5 公允价值测试' },
  { code: 'G10-6', label: 'G10-6 L3调节表' },
  { code: 'G10-7', label: 'G10-7 凭证检查' },
  { code: 'G10-8', label: 'G10-8 衍生工具核查' },
  { code: '附注上市', label: '附注披露（上市公司）' },
  { code: '附注国企', label: '附注披露（国企）' },
]

export function resolveG10ImportableSheet(sheetName: string): G10ImportableSheet | null {
  if (/附注/.test(sheetName || '')) {
    return /国企|国有/.test(sheetName) ? '附注国企' : '附注上市'
  }
  const m = (sheetName || '').match(/G10-(\d+)/)
  if (!m) return null
  const code = `G10-${m[1]}` as G10ImportableSheet
  return G10_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export function useG10ImportExport(options: { wpId: Ref<string> }) {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G10_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G10_IMPORTABLE_SHEETS,
    exportTemplate: (sheet: G10ImportableSheet) => base.exportTemplate(sheet),
    exportData: (sheet: G10ImportableSheet) => base.exportData(sheet),
    importData: (sheet: G10ImportableSheet, file: File) => base.importData(sheet, file),
    apiPrefix: G10_API_PREFIX,
  }
}

export default useG10ImportExport
