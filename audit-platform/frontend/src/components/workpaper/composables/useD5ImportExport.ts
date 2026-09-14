/**
 * useD5ImportExport — D5 应收款项融资导入导出（比照 D3/D4）
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export type D5ImportableSheet = 'D5-1' | 'D5-2' | 'D5-3' | 'D5-4'

export interface D5ImportResult {
  success: boolean
  rowCount: number
  fieldCount: number
  warning?: string
  errors?: string[]
}

export interface UseD5ImportExportOptions {
  wpId: Ref<string>
  sheetCode: D5ImportableSheet
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

export function useD5ImportExport(options: UseD5ImportExportOptions) {
  const { wpId, sheetCode, sheetLabel = sheetCode, onImported } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  async function exportTemplate(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d5/export-template`,
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
        `/api/workpapers/${wpId.value}/d5/export-data`,
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

  async function importData(file: File): Promise<D5ImportResult> {
    lastError.value = null
    importing.value = true
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d5/import-data`,
        formData,
        { params: { sheet: sheetCode }, headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const data = res.data?.data ?? res.data
      const result: D5ImportResult = {
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

export default useD5ImportExport
