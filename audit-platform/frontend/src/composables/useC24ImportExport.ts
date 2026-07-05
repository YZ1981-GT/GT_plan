/**
 * useC24ImportExport — C24 会计分录细节测试导入导出 composable
 *
 * 对接后端三端点：
 * - GET /api/workpapers/{wp_id}/c24-journal/export-template — 下载空白模板
 * - GET /api/workpapers/{wp_id}/c24-journal/export-data — 下载当前数据
 * - POST /api/workpapers/{wp_id}/c24-journal/import-data — 上传并解析 xlsx
 *
 * 使用 http (axios) 确保 Authorization header 自动附带。
 *
 * Spec: .kiro/specs/c23-c24-journal-entry-testing/
 * Task: 3.2
 * Requirements: 7.1, 7.2, 7.3
 */
import { ref, unref, type MaybeRef } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface C24ImportResult {
  rowCount: number
  warning?: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 下载 Blob 为文件
 */
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

// ─── Composable ──────────────────────────────────────────────────────────────

export function useC24ImportExport(wpId: MaybeRef<string>) {
  const loading = ref(false)

  /**
   * 导出空白模板
   * GET /api/workpapers/{wp_id}/c24-journal/export-template
   */
  async function exportTemplate(): Promise<void> {
    loading.value = true
    try {
      const id = unref(wpId)
      const response = await http.get(
        `/api/workpapers/${id}/c24-journal/export-template`,
        { responseType: 'blob' },
      )
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      downloadBlob(blob, 'C24-分录导入模板.xlsx')
      ElMessage.success('模板已导出')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出模板失败'
      ElMessage.error(msg)
    } finally {
      loading.value = false
    }
  }

  /**
   * 导出当前数据
   * GET /api/workpapers/{wp_id}/c24-journal/export-data
   */
  async function exportData(): Promise<void> {
    loading.value = true
    try {
      const id = unref(wpId)
      const response = await http.get(
        `/api/workpapers/${id}/c24-journal/export-data`,
        { responseType: 'blob' },
      )
      const blob = new Blob([response.data], {
        type: 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
      })
      downloadBlob(blob, 'C24-分录数据.xlsx')
      ElMessage.success('数据已导出')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出数据失败'
      ElMessage.error(msg)
    } finally {
      loading.value = false
    }
  }

  /**
   * 导入分录数据
   * POST /api/workpapers/{wp_id}/c24-journal/import-data (multipart/form-data)
   */
  async function importData(file: File): Promise<C24ImportResult | null> {
    loading.value = true
    try {
      const id = unref(wpId)
      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(
        `/api/workpapers/${id}/c24-journal/import-data`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data: any = response.data?.data ?? response.data
      const result: C24ImportResult = {
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        warning: data.warning,
      }

      let msg = `成功导入 ${result.rowCount} 条分录`
      if (result.warning) {
        msg += `（${result.warning}）`
      }
      ElMessage.success(msg)
      return result
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail
        || err?.response?.data?.message
        || err.message
        || '导入数据失败'
      ElMessage.error(typeof errMsg === 'string' ? errMsg : '导入数据格式错误')
      return null
    } finally {
      loading.value = false
    }
  }

  return {
    exportTemplate,
    exportData,
    importData,
    loading,
  }
}

export default useC24ImportExport
