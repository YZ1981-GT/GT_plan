/**
 * useF4ImportExport — F4 应付账款导入导出（比照 useF3ImportExport）
 *
 * 7张动态行表格：F4-2/F4-3/F4-5/F4-6/F4-7(五段)/F4-8(debit/credit)/F4-9
 * Spec: .kiro/specs/f4-accounts-payable/ Task 8.2
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

export type F4ImportableSheet =
  | 'F4-1-nature'
  | 'F4-1-aging'
  | 'F4-2'
  | 'F4-3'
  | 'F4-5'
  | 'F4-6'
  | 'F4-7-payment-window'
  | 'F4-7-estimated-inbound'
  | 'F4-7-unprocessed-invoice'
  | 'F4-7-subsequent-payment'
  | 'F4-7-subsequent-increase'
  | 'F4-8-debit'
  | 'F4-8-credit'
  | 'F4-9'

export interface F4ImportResult {
  rowCount: number
  warning?: string
}

export interface UseF4ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onImported?: () => void | Promise<void>
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

export function useF4ImportExport(options: UseF4ImportExportOptions) {
  const { wpId, onImported } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  async function exportTemplate(sheet: F4ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/f4/export-template`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
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

  async function exportData(sheet: F4ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/f4/export-data`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
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

  async function importData(sheet: F4ImportableSheet, file: File): Promise<F4ImportResult | null> {
    lastError.value = null
    importing.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      const response = await http.post(
        `/api/workpapers/${wpId.value}/f4/import-data`,
        formData,
        { params: { sheet }, headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const data: any = response.data?.data ?? response.data
      if (data?.ok === false) {
        const msg = Array.isArray(data.errors) ? data.errors.join('; ') : '导入失败'
        lastError.value = msg
        ElMessage.error(msg)
        return null
      }
      const result: F4ImportResult = {
        rowCount: data.imported_count ?? 0,
        warning: data.warning,
      }
      ElMessage.success(`成功导入 ${result.rowCount} 行${result.warning ? `（${result.warning}）` : ''}`)
      await onImported?.()
      return result
    } catch (err: any) {
      lastError.value = err?.response?.data?.detail || err?.response?.data?.message || err.message || '导入失败'
      ElMessage.error(String(lastError.value))
      return null
    } finally {
      importing.value = false
    }
  }

  return { importing, lastError, exportTemplate, exportData, importData }
}

export default useF4ImportExport
