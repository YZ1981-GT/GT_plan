/**
 * useH9ImportExport — H9 租赁负债 导入导出 composable
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 3.3
 * Requirements: 3.6
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - StreamingResponse 中文文件名 RFC5987 编码解析
 * - Blob + createObjectURL 下载 + FormData 上传
 * - Follow useH8ImportExport pattern
 *
 * Backend endpoints (Phase 5):
 * - POST /api/h9-lease-liabilities/{wpId}/export-template
 * - POST /api/h9-lease-liabilities/{wpId}/export-data
 * - POST /api/h9-lease-liabilities/{wpId}/import-data (multipart)
 *
 * 动态行 sheets:
 * - H9-2 租赁负债明细表（按合同动态行）
 * - H9-3 未确认融资费用明细表（动态行）
 * - H9-5 调整分录汇总（动态调整行）
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H9 支持导入导出的 sheet 编码 */
export type H9ImportableSheet =
  | 'H9-2'      // 租赁负债明细表（按合同动态行）
  | 'H9-3'      // 未确认融资费用明细表（动态行）
  | 'H9-5'      // 调整分录汇总（动态调整行）

export interface H9ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH9ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 当前 sheet 编码（可选，用于单 sheet 导出） */
  sheetCode?: string
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** H9 可导入导出的 sheet 列表 */
export const H9_IMPORTABLE_SHEETS: { code: H9ImportableSheet; label: string }[] = [
  { code: 'H9-2', label: 'H9-2 租赁负债明细表' },
  { code: 'H9-3', label: 'H9-3 未确认融资费用明细表' },
  { code: 'H9-5', label: 'H9-5 调整分录' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9ImportExport(options: UseH9ImportExportOptions) {
  const { wpId, onImported } = options

  const isExporting = ref(false)
  const isImporting = ref(false)
  const importResult = ref<H9ImportResult | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheets?: string[]): Promise<void> {
    isExporting.value = true
    try {
      const response = await http.post(
        `/api/h9-lease-liabilities/${wpId.value}/export-template`,
        { sheets: sheets ?? null },
        { responseType: 'blob' },
      )
      const filename = _parseFilename(response) || 'H9_租赁负债_模板.xlsx'
      _downloadBlob(response.data, filename)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出模板失败'
      ElMessage.error(msg)
    } finally {
      isExporting.value = false
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  async function exportData(sheets?: string[]): Promise<void> {
    isExporting.value = true
    try {
      const response = await http.post(
        `/api/h9-lease-liabilities/${wpId.value}/export-data`,
        { sheets: sheets ?? null },
        { responseType: 'blob' },
      )
      const filename = _parseFilename(response) || 'H9_租赁负债_数据.xlsx'
      _downloadBlob(response.data, filename)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出数据失败'
      ElMessage.error(msg)
    } finally {
      isExporting.value = false
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  async function importData(file: File): Promise<H9ImportResult | null> {
    importResult.value = null
    isImporting.value = true
    try {
      // 确认对话
      await ElMessageBox.confirm(
        `即将导入文件「${file.name}」到 H9 租赁负债，已有数据将被覆盖。确认导入？`,
        '导入确认',
        { confirmButtonText: '确认导入', cancelButtonText: '取消', type: 'warning' },
      )

      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(
        `/api/h9-lease-liabilities/${wpId.value}/import-data`,
        formData,
        {
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      const data = response.data?.data ?? response.data
      const result: H9ImportResult = {
        success: true,
        rowCount: data?.imported_count ?? data?.row_count ?? 0,
        warning: data?.warning,
      }

      importResult.value = result
      ElMessage.success(`成功导入 ${result.rowCount} 行${result.warning ? `（${result.warning}）` : ''}`)
      await onImported?.()
      return result
    } catch (err: any) {
      if (err === 'cancel' || err?.toString?.().includes('cancel')) return null
      const msg = err?.response?.data?.message || err.message || '导入失败'
      ElMessage.error(msg)
      return null
    } finally {
      isImporting.value = false
    }
  }

  // ─── Helper: RFC5987 filename 解析 ───────────────────────────────────────

  function _parseFilename(response: any): string | null {
    const disposition = response.headers?.['content-disposition']
    if (!disposition) return null

    // RFC5987: filename*=UTF-8''%E4%BD%BF%E7%94%A8%E6%9D%83%E8%B5%84%E4%BA%A7.xlsx
    const rfc5987Match = disposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
    if (rfc5987Match?.[1]) {
      try { return decodeURIComponent(rfc5987Match[1]) } catch { /* fallthrough */ }
    }

    // 普通 filename="xxx.xlsx"
    const simpleMatch = disposition.match(/filename="?([^";\n]+)"?/i)
    if (simpleMatch?.[1]) return simpleMatch[1].trim()

    return null
  }

  // ─── Helper: Blob下载 ────────────────────────────────────────────────────

  function _downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    document.body.appendChild(a)
    a.click()
    document.body.removeChild(a)
    URL.revokeObjectURL(url)
  }

  return {
    isExporting,
    isImporting,
    importResult,
    exportTemplate,
    exportData,
    importData,
    sheets: H9_IMPORTABLE_SHEETS,
  }
}

export default useH9ImportExport
