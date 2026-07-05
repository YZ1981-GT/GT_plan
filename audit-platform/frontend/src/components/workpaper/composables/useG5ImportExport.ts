/**
 * useG5ImportExport — G5 长期应收款 导入导出
 * 8 张动态行表格：G5-2~G5-7 / G5-11~G5-12（G5-10 待 G4-10 完成后补齐）
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from './useWorkpaperImportExport'

export type G5ImportableSheet =
  | 'G5-2' | 'G5-3' | 'G5-4' | 'G5-5' | 'G5-6'
  | 'G5-7' | 'G5-11' | 'G5-12'

export const G5_API_PREFIX = 'g5'

export const G5_IMPORTABLE_SHEETS: { code: G5ImportableSheet; label: string }[] = [
  { code: 'G5-2', label: 'G5-2 余额明细' },
  { code: 'G5-3', label: 'G5-3 坏账准备明细' },
  { code: 'G5-4', label: 'G5-4 调整分录' },
  { code: 'G5-5', label: 'G5-5 融资租赁测算' },
  { code: 'G5-6', label: 'G5-6 分期销售测算' },
  { code: 'G5-7', label: 'G5-7 保理核查' },
  { code: 'G5-11', label: 'G5-11 转回核销' },
  { code: 'G5-12', label: 'G5-12 凭证检查' },
]

export function resolveG5ImportableSheet(sheetName: string): G5ImportableSheet | null {
  const m = (sheetName || '').match(/G5-(\d+)/)
  if (!m) return null
  const code = `G5-${m[1]}` as G5ImportableSheet
  return G5_IMPORTABLE_SHEETS.some((s) => s.code === code) ? code : null
}

export function useG5ImportExport(options: { wpId: Ref<string> }) {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G5_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    sheets: G5_IMPORTABLE_SHEETS,
    exportTemplate: (sheet: G5ImportableSheet) => base.exportTemplate(sheet),
    exportData: (sheet: G5ImportableSheet) => base.exportData(sheet),
    importData: (sheet: G5ImportableSheet, file: File) => base.importData(sheet, file),
    apiPrefix: G5_API_PREFIX,
  }
}

export default useG5ImportExport
