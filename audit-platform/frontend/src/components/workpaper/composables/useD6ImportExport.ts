/**
 * useD6ImportExport — D6 合同资产导入导出（比照 D5）
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export type D6ImportableSheet =
  | 'D6-2'
  | 'D6-3'
  | 'D6-4'
  | 'D6-5'
  | 'D6-6-period'
  | 'D6-6-post'
  | 'D6-8'
  | 'D6-9-reversal'
  | 'D6-9-writeoff'
  | 'D6-note-major-change'
  | 'D6-note-groups'

export interface D6ImportResult {
  success: boolean
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

export interface UseD6ImportExportOptions {
  wpId: Ref<string>
  sheetCode: D6ImportableSheet
  sheetLabel?: string
  onImported?: () => Promise<void> | void
}

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function useD6ImportExport(options: UseD6ImportExportOptions) {
  const { wpId, sheetCode, sheetLabel = sheetCode, onImported } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  async function exportTemplate(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d6/export-template`,
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
        `/api/workpapers/${wpId.value}/d6/export-data`,
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

  async function importData(file: File): Promise<D6ImportResult> {
    lastError.value = null
    importing.value = true
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d6/import-data`,
        formData,
        { params: { sheet: sheetCode }, headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const data = res.data?.data ?? res.data
      const result: D6ImportResult = {
        success: data?.ok !== false,
        rowCount: data?.imported_count ?? data?.row_count ?? 0,
        fieldCount: data?.field_count ?? 0,
        warning: data?.warning,
      }
      if (!result.success) {
        result.errors = data?.errors ?? ['导入失败']
      } else {
        ElMessage.success(`成功导入 ${result.rowCount} 行`)
        await onImported?.()
      }
      return result
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.message || err.message || '导入失败'
      lastError.value = Array.isArray(msg) ? msg.join(', ') : msg
      ElMessage.error(lastError.value!)
      return { success: false, rowCount: 0, fieldCount: 0, errors: [lastError.value!] }
    } finally {
      importing.value = false
    }
  }

  return { importing, lastError, exportTemplate, exportData, importData }
}

export default useD6ImportExport
