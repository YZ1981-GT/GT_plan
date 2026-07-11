/**
 * useK0ImportExport — K0 管理循环函证 导入导出 composable
 *
 * 复用共享 useWorkpaperImportExport（apiPrefix='k0'），调用后端三端点：
 *   POST /api/workpapers/{wpId}/k0/export-template?sheet={K0-5|K0-6}
 *   POST /api/workpapers/{wpId}/k0/export-data?sheet={K0-5|K0-6}
 *   POST /api/workpapers/{wpId}/k0/import-data?sheet={K0-5|K0-6}
 *
 * K0-5（其他应收款替代程序）和 K0-6（其他应付款替代程序）按 4 区块分 sheet 导出/导入，
 * 通过 sheet 参数区分。
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from '../../../composables/useWorkpaperImportExport'

export type K0ImportableSheet = 'K0-5' | 'K0-6'

export const K0_API_PREFIX = 'k0'

export interface UseK0ImportExportOptions {
  wpId: Ref<string>
}

export interface UseK0ImportExportReturn {
  importing: Ref<boolean>
  lastError: Ref<string | null>
  exportTemplate: (sheet: K0ImportableSheet) => Promise<void>
  exportData: (sheet: K0ImportableSheet) => Promise<void>
  importData: (sheet: K0ImportableSheet, file: File) => Promise<ImportExportResult | null>
  apiPrefix: string
}

export function useK0ImportExport(options: UseK0ImportExportOptions): UseK0ImportExportReturn {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: K0_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    exportTemplate: (sheet) => base.exportTemplate(sheet),
    exportData: (sheet) => base.exportData(sheet),
    importData: (sheet, file) => base.importData(sheet, file),
    apiPrefix: K0_API_PREFIX,
  }
}

export default useK0ImportExport
