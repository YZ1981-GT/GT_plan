/**
 * useD3ImportExport — D3 预收账款导入导出通用 composable（比照 D4）
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import {
  parseAuxImportResponse,
  auxImportPrompt,
  AUX_IMPORT_NETWORK_ERROR_PROMPT,
} from './fourTableAuxImportFeedback'

export type D3ImportableSheet =
  | 'D3-1'
  | 'D3-2'
  | 'D3-3'
  | 'D3-4-debit'
  | 'D3-4-credit'
  | 'D3-5'
  | 'D3-6'
  | 'D3-7'

export interface D3ImportResult {
  success: boolean
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

export interface UseD3ImportExportOptions {
  wpId: Ref<string>
  sheetCode: D3ImportableSheet
  sheetLabel?: string
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function useD3ImportExport(options: UseD3ImportExportOptions) {
  const { wpId, sheetCode, sheetLabel = sheetCode } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  async function exportTemplate(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d3/export-template`,
        null,
        { params: { sheet: sheetCode }, responseType: 'blob' },
      )
      downloadBlob(
        new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
        `${sheetCode}_${sheetLabel}模板.xlsx`,
      )
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出模板失败'
      ElMessage.error(lastError.value!)
    }
  }

  async function exportData(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d3/export-data`,
        null,
        { params: { sheet: sheetCode }, responseType: 'blob' },
      )
      downloadBlob(
        new Blob([res.data], { type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet' }),
        `${sheetCode}_${sheetLabel}数据.xlsx`,
      )
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出数据失败'
      ElMessage.error(lastError.value!)
    }
  }

  async function importData(file: File): Promise<D3ImportResult> {
    lastError.value = null
    importing.value = true
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d3/import-data`,
        formData,
        { params: { sheet: sheetCode }, headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const data = res.data?.data ?? res.data
      const result: D3ImportResult = {
        success: data?.ok !== false,
        rowCount: data?.imported_count ?? data?.row_count ?? 0,
        fieldCount: data?.field_count ?? 0,
        warning: data?.warning,
      }
      if (!result.success) {
        result.errors = data?.errors ?? ['导入失败']
      }
      return result
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.message || err.message || '导入失败'
      lastError.value = Array.isArray(msg) ? msg.join(', ') : msg
      return { success: false, rowCount: 0, fieldCount: 0, errors: [lastError.value!] }
    } finally {
      importing.value = false
    }
  }

  /**
   * D3-2 专用：从辅助余额表导入.
   *
   * 🔴 迁移后端（spec four-table-extraction-entry-completion / Task 4）已改为**服务端
   * merge 落库**并返回 reason 码（imported_count / reason / message），不再返回 rows[]。
   * 故前端不再客户端拼行，成功后返回 true 让宿主 reloadWorkpaperData 级联刷新；
   * 0 行按 reason 码给可辨别中文提示（Requirement 4.4），不再一律「成功导入 0 行」。
   */
  async function importFromAuxBalance(): Promise<boolean> {
    try {
      const res = await http.post(`/api/workpapers/${wpId.value}/d3/import-aux-balance`, null)
      const outcome = parseAuxImportResponse(res)
      const { level, text } = auxImportPrompt(outcome)
      ElMessage[level]({ message: text })
      return true
    } catch {
      const { level, text } = AUX_IMPORT_NETWORK_ERROR_PROMPT
      ElMessage[level]({ message: text })
      return false
    }
  }

  return { importing, lastError, exportTemplate, exportData, importData, importFromAuxBalance }
}

export default useD3ImportExport
