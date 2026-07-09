/**
 * useWorkpaperImportExport — 底稿循环通用导入导出（D4 模式）
 *
 * POST /api/workpapers/{wpId}/{apiPrefix}/export-template?sheet=xxx
 * POST /api/workpapers/{wpId}/{apiPrefix}/export-data?sheet=xxx
 * POST /api/workpapers/{wpId}/{apiPrefix}/import-data?sheet=xxx
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export interface ImportExportResult {
  rowCount: number
  fieldCount: number
  warning?: string
}

export interface UseWorkpaperImportExportOptions {
  wpId: Ref<string>
  /** API 路径前缀，如 f1 / f2 / d4 */
  apiPrefix: string
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export function useWorkpaperImportExport(options: UseWorkpaperImportExportOptions) {
  const { wpId, apiPrefix } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}/${apiPrefix}`
  }

  async function exportTemplate(sheet: string): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(`${apiBase()}/export-template`, null, {
        params: { sheet },
        responseType: 'blob',
      })
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      downloadBlob(blob, `${sheet}-模板.xlsx`)
      ElMessage.success(`${sheet} 模板已导出`)
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出模板失败'
      ElMessage.error(lastError.value!)
    }
  }

  async function exportData(sheet: string): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(`${apiBase()}/export-data`, null, {
        params: { sheet },
        responseType: 'blob',
      })
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      downloadBlob(blob, `${sheet}-数据.xlsx`)
      ElMessage.success(`${sheet} 数据已导出`)
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出数据失败'
      ElMessage.error(lastError.value!)
    }
  }

  async function importData(sheet: string, file: File): Promise<ImportExportResult | null> {
    lastError.value = null
    importing.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await http.post(`${apiBase()}/import-data`, formData, {
        params: { sheet },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const data: any = response.data?.data ?? response.data
      if (data.ok === false) {
        const msg = (data.errors || []).join('；') || '导入失败'
        lastError.value = msg
        ElMessage.error(msg)
        return null
      }
      const result: ImportExportResult = {
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        fieldCount: data.fieldCount ?? 0,
        warning: data.warning,
      }
      let msg = `成功导入 ${result.rowCount} 行数据`
      if (result.warning) msg += `（${result.warning}）`
      ElMessage.success(msg)
      return result
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail || err?.response?.data?.message || err.message || '导入数据失败'
      lastError.value = Array.isArray(errMsg) ? errMsg.join(', ') : String(errMsg)
      ElMessage.error(lastError.value!)
      return null
    } finally {
      importing.value = false
    }
  }

  return { importing, lastError, exportTemplate, exportData, importData }
}

/** F1 预付账款 */
export type F1ImportableSheet = 'F1-2' | 'F1-5' | 'F1-6' | 'F1-7' | 'F1-7-post'
export type F1ImportSheet = F1ImportableSheet

export function useF1ImportExport(opts: { wpId: Ref<string>; projectId?: Ref<string> }) {
  return useWorkpaperImportExport({ wpId: opts.wpId, apiPrefix: 'f1' })
}

/** F2 存货明细 */
export function useF2ImportExport(opts: { wpId: Ref<string> }) {
  return useWorkpaperImportExport({ wpId: opts.wpId, apiPrefix: 'f2' })
}

/** F3 应付票据 */
export function useF3ImportExport(opts: { wpId: Ref<string> }) {
  return useWorkpaperImportExport({ wpId: opts.wpId, apiPrefix: 'f3' })
}

/** F4 应付账款 */
export function useF4ImportExport(opts: { wpId: Ref<string> }) {
  return useWorkpaperImportExport({ wpId: opts.wpId, apiPrefix: 'f4' })
}

/** F5 营业成本 */
export function useF5ImportExport(opts: { wpId: Ref<string> }) {
  return useWorkpaperImportExport({ wpId: opts.wpId, apiPrefix: 'f5' })
}

/** S 类计算型底稿（S20/S21）— 独立 composable，此处仅 re-export */
export { useSEstimateImportExport } from './useSEstimateImportExport'

export default useWorkpaperImportExport
