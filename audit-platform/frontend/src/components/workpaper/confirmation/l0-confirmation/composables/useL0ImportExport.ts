/**
 * useL0ImportExport — L0 债务循环函证 导入导出 composable
 *
 * 复用共享 useWorkpaperImportExport（apiPrefix='l0'），调用后端三端点：
 *   POST /api/workpapers/{wpId}/l0/export-template?sheet=L0-5
 *   POST /api/workpapers/{wpId}/l0/export-data?sheet=L0-5
 *   POST /api/workpapers/{wpId}/l0/import-data?sheet=L0-5
 *
 * L0-5（长期应付款/借款替代程序）按 4 区块分 sheet 导出/导入。
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from '../../composables/useWorkpaperImportExport'

export type L0ImportableSheet = 'L0-5'

export const L0_API_PREFIX = 'l0'

export interface UseL0ImportExportOptions {
  wpId: Ref<string>
}

export interface UseL0ImportExportReturn {
  importing: Ref<boolean>
  lastError: Ref<string | null>
  exportTemplate: (sheet: L0ImportableSheet) => Promise<void>
  exportData: (sheet: L0ImportableSheet) => Promise<void>
  importData: (sheet: L0ImportableSheet, file: File) => Promise<ImportExportResult | null>
  apiPrefix: string
}

export function useL0ImportExport(options: UseL0ImportExportOptions): UseL0ImportExportReturn {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: L0_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    exportTemplate: (sheet) => base.exportTemplate(sheet),
    exportData: (sheet) => base.exportData(sheet),
    importData: (sheet, file) => base.importData(sheet, file),
    apiPrefix: L0_API_PREFIX,
  }
}

export default useL0ImportExport
