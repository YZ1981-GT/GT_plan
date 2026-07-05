/**
 * useD4ImportExport — D4 营业收入导入导出通用 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 19.1
 *
 * 职责：
 * - 导出空白模板（xlsx含表头+格式）
 * - 导出当前数据（xlsx含行数据）
 * - 导入xlsx数据（解析→回写checklist_responses）
 * - 状态管理（importing/lastError）
 * - 成功/失败消息提示
 *
 * Requirements: 20.2, 20.6, 20.7
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 支持导入导出的D4 Sheet */
export type D4ImportableSheet =
  | 'D4-1'
  | 'D4-2'
  | 'D4-3'
  | 'D4-6'
  | 'D4-7'
  | 'D4-8'
  | 'D4-9'
  | 'D4-10'
  | 'D4-11'
  | 'D4-12'
  | 'D4-14'
  | 'D4-15'
  | 'D4-16'
  | 'D4-17'
  | 'D4-18'
  | 'D4-19'
  | 'D4-20'
  | 'D4-20-provision'
  | 'D4-20-current'
  | 'D4-20-post'
  | 'D4-21'
  | 'D4-23'
  | 'D4-24'
  | 'D4-25'
  | 'D4-26'
  | 'D4-27'
  | 'D4-28'
  | 'D4-29'
  | 'D4-30'
  | 'D4-31'
  | 'D4-32'
  | 'D4-33'
  | 'D4-34'
  | 'D4-35'
  | 'D4-36'

export interface D4ImportResult {
  rowCount: number
  fieldCount: number
  warning?: string
}

export interface UseD4ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
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

export function useD4ImportExport(options: UseD4ImportExportOptions) {
  const { wpId } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const importing = ref<boolean>(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ───────────────────────────────────────────────────

  /**
   * 导出空白xlsx模板（含表头+格式+编制说明）
   * POST /api/workpapers/{wp_id}/d4/export-template?sheet=xxx
   */
  async function exportTemplate(sheet: D4ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/d4/export-template`,
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

  // ─── Export Data ───────────────────────────────────────────────────────

  /**
   * 导出当前数据为xlsx
   * POST /api/workpapers/{wp_id}/d4/export-data?sheet=xxx
   */
  async function exportData(sheet: D4ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/d4/export-data`,
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

  // ─── Import Data ───────────────────────────────────────────────────────

  /**
   * 导入xlsx数据
   * POST /api/workpapers/{wp_id}/d4/import-data?sheet=xxx (multipart/form-data)
   */
  async function importData(sheet: D4ImportableSheet, file: File): Promise<D4ImportResult | null> {
    lastError.value = null
    importing.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(
        `/api/workpapers/${wpId.value}/d4/import-data`,
        formData,
        {
          params: { sheet },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      const data: any = response.data?.data ?? response.data
      const result: D4ImportResult = {
        rowCount: data.imported_count ?? data.rowCount ?? 0,
        fieldCount: data.fieldCount ?? 0,
        warning: data.warning,
      }

      let msg = `成功导入${result.rowCount}行数据`
      if (result.warning) {
        msg += `（${result.warning}）`
      }
      ElMessage.success(msg)
      return result
    } catch (err: any) {
      const errMsg = err?.response?.data?.detail || err?.response?.data?.message || err.message || '导入数据失败'
      // 格式校验失败（400）
      if (Array.isArray(errMsg)) {
        lastError.value = `列名不匹配: ${errMsg.join(', ')}`
      } else {
        lastError.value = errMsg
      }
      ElMessage.error(lastError.value!)
      return null
    } finally {
      importing.value = false
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    importing,
    lastError,

    // 操作
    exportTemplate,
    exportData,
    importData,
  }
}

export default useD4ImportExport
