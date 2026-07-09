/**
 * useH6ImportExport — H6 固定资产清理 导入导出 composable
 *
 * Spec: .kiro/specs/h6-asset-disposal-clearing/ Task 3.3
 * Requirements: 3.6
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - StreamingResponse 中文文件名 RFC5987 编码解析
 * - Blob + createObjectURL 下载 + FormData 上传
 * - 只有动态行表格需要导入：H6-2明细表, H6-3调整分录, H6-4检查表
 * - Follow useH4ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H6 支持导入导出的 sheet 编码 */
export type H6ImportableSheet =
  | 'H6-2'      // 明细表（25列2区块）
  | 'H6-3'      // 调整分录
  | 'H6-4'      // 检查表（18列）

export interface H6ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH6ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** H6 可导入导出的 sheet 列表 */
export const H6_IMPORTABLE_SHEETS: { code: H6ImportableSheet; label: string }[] = [
  { code: 'H6-2', label: 'H6-2 明细表' },
  { code: 'H6-3', label: 'H6-3 调整分录' },
  { code: 'H6-4', label: 'H6-4 检查表' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH6ImportExport(options: UseH6ImportExportOptions) {
  const { wpId, onImported } = options

  const isExporting = ref(false)
  const isImporting = ref(false)
  const importResult = ref<H6ImportResult | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet: H6ImportableSheet): Promise<void> {
    isExporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h6/export-template`,
        null,
        { params: { sheet_name: sheet }, responseType: 'blob' },
      )
      const filename = _parseFilename(response) || `H6_${sheet}_模板.xlsx`
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

  async function exportData(sheet: H6ImportableSheet): Promise<void> {
    isExporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h6/export-data`,
        null,
        { params: { sheet_name: sheet }, responseType: 'blob' },
      )
      const filename = _parseFilename(response) || `H6_${sheet}_数据.xlsx`
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

  async function importData(sheet: H6ImportableSheet, file: File): Promise<H6ImportResult | null> {
    importResult.value = null
    isImporting.value = true
    try {
      // 确认对话
      await ElMessageBox.confirm(
        `即将导入文件「${file.name}」到 ${sheet}，已有数据将被覆盖。确认导入？`,
        '导入确认',
        { confirmButtonText: '确认导入', cancelButtonText: '取消', type: 'warning' },
      )

      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(
        `/api/workpapers/${wpId.value}/h6/import-data`,
        formData,
        {
          params: { sheet_name: sheet },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      const data = response.data?.data ?? response.data
      const result: H6ImportResult = {
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

    // RFC5987: filename*=UTF-8''%E5%9B%BA%E5%AE%9A%E8%B5%84%E4%BA%A7%E6%B8%85%E7%90%86.xlsx
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
    sheets: H6_IMPORTABLE_SHEETS,
  }
}

export default useH6ImportExport
