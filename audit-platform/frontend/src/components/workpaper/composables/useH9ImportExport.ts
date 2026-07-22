/**
 * useH9ImportExport — H9 租赁负债 导入导出 composable
 *
 * Spec: .kiro/specs/h9-lease-liabilities/ Task 3.3
 * Requirements: 3.6
 *
 * 对齐后端 GET/POST ?sheet= 契约（与 H8 cycle IE 一致）：
 * - GET  /api/h9-lease-liabilities/{wpId}/export-template?sheet=
 * - GET  /api/h9-lease-liabilities/{wpId}/export-data?sheet=
 * - POST /api/h9-lease-liabilities/{wpId}/import-data?sheet= (multipart)
 *
 * 动态行 sheets: H9-2 / H9-3 / H9-4（历史别名 H9-5 → H9-4）
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H9 支持导入导出的 sheet 编码 */
export type H9ImportableSheet =
  | 'H9-2'      // 租赁负债明细表（按合同动态行）
  | 'H9-3'      // 未确认融资费用明细表（动态行）
  | 'H9-4'      // 调整分录汇总（Excel）
  | 'H9-5'      // 历史别名 → H9-4

export interface H9ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH9ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 当前 sheet 编码（导入与默认导出目标） */
  sheetCode?: H9ImportableSheet | string
  /** 导入完成后刷新数据回调（应走 reloadFromServer，勿用 htmlData selfLoad） */
  onImported?: () => void | Promise<void>
}

/** H9 可导入导出的 sheet 列表 */
export const H9_IMPORTABLE_SHEETS: { code: H9ImportableSheet; label: string }[] = [
  { code: 'H9-2', label: 'H9-2 租赁负债明细表' },
  { code: 'H9-3', label: 'H9-3 未确认融资费用明细表' },
  { code: 'H9-4', label: 'H9-4 调整分录汇总' },
]

/** 将 UI/历史编码归一为后端可识别编码 */
export function normalizeH9ImportSheet(code: string): string {
  return code === 'H9-5' ? 'H9-4' : code
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9ImportExport(options: UseH9ImportExportOptions) {
  const { wpId, sheetCode, onImported } = options

  const isExporting = ref(false)
  const isImporting = ref(false)
  const importResult = ref<H9ImportResult | null>(null)

  function _resolveSheet(sheets?: string[]): string {
    const raw = sheets?.[0] || sheetCode
    if (!raw) throw new Error('未指定 H9 sheet 编码')
    return normalizeH9ImportSheet(raw)
  }

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheets?: string[]): Promise<void> {
    isExporting.value = true
    try {
      const sheet = _resolveSheet(sheets)
      const response = await http.get(
        `/api/h9-lease-liabilities/${wpId.value}/export-template`,
        { params: { sheet }, responseType: 'blob' },
      )
      const filename = _parseFilename(response) || `H9租赁负债_${sheet}_模板.xlsx`
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
      const sheet = _resolveSheet(sheets)
      const response = await http.get(
        `/api/h9-lease-liabilities/${wpId.value}/export-data`,
        { params: { sheet }, responseType: 'blob' },
      )
      const filename = _parseFilename(response) || `H9租赁负债_${sheet}_数据.xlsx`
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

  async function importData(file: File, sheets?: string[]): Promise<H9ImportResult | null> {
    importResult.value = null
    isImporting.value = true
    try {
      const sheet = _resolveSheet(sheets)
      await ElMessageBox.confirm(
        `即将导入文件「${file.name}」到 ${sheet}，已有数据将被覆盖。确认导入？`,
        '导入确认',
        { confirmButtonText: '确认导入', cancelButtonText: '取消', type: 'warning' },
      )

      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(
        `/api/h9-lease-liabilities/${wpId.value}/import-data`,
        formData,
        {
          params: { sheet },
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

    const rfc5987Match = disposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
    if (rfc5987Match?.[1]) {
      try { return decodeURIComponent(rfc5987Match[1]) } catch { /* fallthrough */ }
    }

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
