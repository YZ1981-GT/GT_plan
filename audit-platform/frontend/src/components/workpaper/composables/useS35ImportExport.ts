/**
 * useS35ImportExport — S35 明细核查子表导入导出
 *
 * Spec: .kiro/specs/s35-refinancing-bundle/  Task 4.2
 * Requirements: 4.3
 *
 * 三级导入导出：导出模板 / 导出数据 / 导入数据
 * 复用 useWorkpaperImportExport 模式（http/axios，非 fetch）
 * 中文文件名 RFC5987
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export type S35ImportableSheet = 'S35-1-1' | 'S35-2-1' | 'S35-3-1'

export interface S35ImportResult {
  success: boolean
  rowCount: number
  warning?: string
  errors?: string[]
}

export interface UseS35ImportExportOptions {
  wpId: Ref<string>
  sheetCode: S35ImportableSheet
  sheetLabel?: string
  onImported?: () => Promise<void> | void
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

export function useS35ImportExport(options: UseS35ImportExportOptions) {
  const { wpId, sheetCode, sheetLabel = sheetCode, onImported } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  function apiBase(): string {
    return `/api/workpapers/${wpId.value}/s35`
  }

  async function exportTemplate(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.post(`${apiBase()}/export-template`, null, {
        params: { sheet: sheetCode },
        responseType: 'blob',
      })
      downloadBlob(
        new Blob([res.data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }),
        `${sheetLabel}模板.xlsx`,
      )
      ElMessage.success(`${sheetLabel} 模板已导出`)
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出模板失败'
      ElMessage.error(lastError.value!)
    }
  }

  async function exportData(): Promise<void> {
    lastError.value = null
    try {
      const res = await http.post(`${apiBase()}/export-data`, null, {
        params: { sheet: sheetCode },
        responseType: 'blob',
      })
      downloadBlob(
        new Blob([res.data], {
          type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        }),
        `${sheetLabel}数据.xlsx`,
      )
      ElMessage.success(`${sheetLabel} 数据已导出`)
    } catch (err: any) {
      lastError.value = err?.response?.data?.message || err.message || '导出数据失败'
      ElMessage.error(lastError.value!)
    }
  }

  async function importData(file: File): Promise<S35ImportResult> {
    lastError.value = null
    importing.value = true
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(`${apiBase()}/import-data`, formData, {
        params: { sheet: sheetCode },
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const data = res.data?.data ?? res.data
      const result: S35ImportResult = {
        success: data?.ok !== false,
        rowCount: data?.imported_count ?? data?.row_count ?? 0,
        warning: data?.warning,
      }
      if (!result.success) {
        result.errors = data?.errors ?? ['导入失败']
        const msg = result.errors!.join('；')
        lastError.value = msg
        ElMessage.error(msg)
      } else {
        let msg = `成功导入 ${result.rowCount} 行`
        if (result.warning) msg += `（${result.warning}）`
        ElMessage.success(msg)
        await onImported?.()
      }
      return result
    } catch (err: any) {
      const msg = err?.response?.data?.detail || err?.response?.data?.message || err.message || '导入失败'
      lastError.value = Array.isArray(msg) ? msg.join(', ') : String(msg)
      ElMessage.error(lastError.value!)
      return { success: false, rowCount: 0, errors: [lastError.value!] }
    } finally {
      importing.value = false
    }
  }

  return { importing, lastError, exportTemplate, exportData, importData }
}

export default useS35ImportExport
