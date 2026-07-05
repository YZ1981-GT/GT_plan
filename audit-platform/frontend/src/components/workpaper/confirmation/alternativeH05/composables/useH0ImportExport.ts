/**
 * useH0ImportExport — H0 固定资产循环函证 导入导出 composable
 *
 * 复用共享 useWorkpaperImportExport（apiPrefix='h0'），调用后端三端点：
 *   POST /api/workpapers/{wpId}/h0/export-template?sheet=H0-5
 *   POST /api/workpapers/{wpId}/h0/export-data?sheet=H0-5
 *   POST /api/workpapers/{wpId}/h0/import-data?sheet=H0-5
 *
 * H0-5 按 4 区块分 sheet 导出（列定义与 blockColumnConfigsH05.ts 对齐）。
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from '../../composables/useWorkpaperImportExport'

export type H0ImportableSheet = 'H0-5'

export const H0_API_PREFIX = 'h0'

export interface UseH0ImportExportOptions {
  wpId: Ref<string>
}

export interface UseH0ImportExportReturn {
  importing: Ref<boolean>
  lastError: Ref<string | null>
  exportTemplate: (sheet: H0ImportableSheet) => Promise<void>
  exportData: (sheet: H0ImportableSheet) => Promise<void>
  importData: (sheet: H0ImportableSheet, file: File) => Promise<ImportExportResult | null>
  apiPrefix: string
}

export function useH0ImportExport(options: UseH0ImportExportOptions): UseH0ImportExportReturn {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: H0_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    exportTemplate: (sheet) => base.exportTemplate(sheet),
    exportData: (sheet) => base.exportData(sheet),
    importData: (sheet, file) => base.importData(sheet, file),
    apiPrefix: H0_API_PREFIX,
  }
}

export default useH0ImportExport
