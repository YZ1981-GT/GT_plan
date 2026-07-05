/**
 * useG0ImportExport — G0 投资循环函证 导入导出 composable
 *
 * 复用共享 useWorkpaperImportExport（apiPrefix='g0'，http/axios 带 Authorization），
 * 调用后端三端点：
 *   POST /api/workpapers/{wpId}/g0/export-template?sheet=G0-3S|G0-6
 *   POST /api/workpapers/{wpId}/g0/export-data?sheet=G0-3S|G0-6
 *   POST /api/workpapers/{wpId}/g0/import-data?sheet=G0-3S|G0-6
 *
 * UI 铁律：el-dropdown「导入导出 ▾」→ 复用 CycleImportExportDropdown（apiPrefix='g0'）。
 * G0-3S 单 sheet；G0-6 按 4 区块分 sheet 导出。
 */
import { type Ref } from 'vue'
import {
  useWorkpaperImportExport,
  type ImportExportResult,
} from '../../composables/useWorkpaperImportExport'

/** G0 支持导入导出的 sheet 编码 */
export type G0ImportableSheet = 'G0-3S' | 'G0-6'

export const G0_API_PREFIX = 'g0'

export interface UseG0ImportExportOptions {
  wpId: Ref<string>
}

export interface UseG0ImportExportReturn {
  importing: Ref<boolean>
  lastError: Ref<string | null>
  exportTemplate: (sheet: G0ImportableSheet) => Promise<void>
  exportData: (sheet: G0ImportableSheet) => Promise<void>
  importData: (sheet: G0ImportableSheet, file: File) => Promise<ImportExportResult | null>
  apiPrefix: string
}

export function useG0ImportExport(options: UseG0ImportExportOptions): UseG0ImportExportReturn {
  const base = useWorkpaperImportExport({ wpId: options.wpId, apiPrefix: G0_API_PREFIX })
  return {
    importing: base.importing,
    lastError: base.lastError,
    exportTemplate: (sheet) => base.exportTemplate(sheet),
    exportData: (sheet) => base.exportData(sheet),
    importData: (sheet, file) => base.importData(sheet, file),
    apiPrefix: G0_API_PREFIX,
  }
}

export default useG0ImportExport
