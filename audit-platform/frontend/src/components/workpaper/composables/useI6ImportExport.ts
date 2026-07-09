/**
 * useI6ImportExport — I6 研发费用 导入导出 composable
 *
 * Spec: .kiro/specs/i6-research-development-expense/ Task 3.6
 * Requirements: 导入导出统一规范 (memory)
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - 动态行表格需要导入导出：I6-2 明细表 / I6-3 调整分录
 * - StreamingResponse + RFC5987 编码中文文件名
 * - Follow useI5ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I6 支持导入导出的 sheet 编码 */
export type I6ImportableSheet =
  | 'I6-2'      // 明细表（月度12列横向65列，动态行）
  | 'I6-3'      // 调整分录（动态行）

export interface I6ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseI6ImportExportOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

export const I6_IMPORTABLE_SHEETS: { code: I6ImportableSheet; label: string }[] = [
  { code: 'I6-2', label: 'I6-2 明细表(月度12列横向65列)' },
  { code: 'I6-3', label: 'I6-3 调整分录' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI6ImportExport(options: UseI6ImportExportOptions) {
  const { wpId, sheetName, onImported } = options

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet?: I6ImportableSheet): Promise<void> {
    const targetSheet = sheet || _resolveSheet()
    if (!targetSheet) return

    lastError.value = null
    isExporting.value = true
    try {
      const response = await http.get(
        `/api/workpapers/${wpId.value}/i6/export-template`,
        { params: { sheet: targetSheet }, responseType: 'blob' },
      )
      _downloadBlob(response, `I6_${targetSheet}_模板.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    } finally {
      isExporting.value = false
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  async function exportData(sheet?: I6ImportableSheet): Promise<void> {
    const targetSheet = sheet || _resolveSheet()
    if (!targetSheet) return

    lastError.value = null
    isExporting.value = true
    try {
      const response = await http.get(
        `/api/workpapers/${wpId.value}/i6/export-data`,
        { params: { sheet: targetSheet }, responseType: 'blob' },
      )
      _downloadBlob(response, `I6_${targetSheet}_数据.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    } finally {
      isExporting.value = false
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  async function importData(file: File, sheet?: I6ImportableSheet): Promise<I6ImportResult | null> {
    const targetSheet = sheet || _resolveSheet()
    if (!targetSheet) return null

    lastError.value = null
    isImporting.value = true
    try {
      // 确认对话
      await ElMessageBox.confirm(
        `即将导入文件「${file.name}」到 ${targetSheet}，已有数据将被覆盖。确认导入？`,
        '导入确认',
        { confirmButtonText: '确认导入', cancelButtonText: '取消', type: 'warning' },
      )

      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(
        `/api/workpapers/${wpId.value}/i6/import-data`,
        formData,
        { params: { sheet: targetSheet }, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: I6ImportResult = {
        success: true,
        rowCount: data.imported_count ?? data.row_count ?? 0,
        warning: data.warning,
      }

      ElMessage.success(`成功导入 ${result.rowCount} 行${result.warning ? `（${result.warning}）` : ''}`)
      await onImported?.()
      return result
    } catch (err: any) {
      if (err === 'cancel' || err?.toString?.().includes('cancel')) return null
      const msg = err?.response?.data?.message || err.message || '导入失败'
      lastError.value = msg
      ElMessage.error(msg)
      return null
    } finally {
      isImporting.value = false
    }
  }

  // ─── Helper: 从 sheetName ref 解析 sheet 编码 ────────────────────────────

  function _resolveSheet(): I6ImportableSheet | null {
    if (!sheetName?.value) return null
    const match = sheetName.value.match(/I6-\d+/)
    const code = match?.[0] as I6ImportableSheet | undefined
    if (code && I6_IMPORTABLE_SHEETS.some((s) => s.code === code)) return code
    return null
  }

  // ─── Helper: Blob下载（支持RFC5987中文文件名） ────────────────────────────

  function _downloadBlob(response: any, fallbackFilename: string): void {
    const blob = response.data instanceof Blob ? response.data : new Blob([response.data])
    const filename = _extractFilename(response) || fallbackFilename
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  /**
   * 从 Content-Disposition header 提取文件名
   * 支持 RFC5987 编码 (filename*=UTF-8''xxx) 和普通 filename="xxx"
   */
  function _extractFilename(response: any): string | null {
    const disposition = response.headers?.['content-disposition']
    if (!disposition) return null

    // RFC5987: filename*=UTF-8''%E6%A8%A1%E6%9D%BF.xlsx
    const rfc5987Match = disposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
    if (rfc5987Match) {
      try {
        return decodeURIComponent(rfc5987Match[1].trim())
      } catch { /* fallthrough */ }
    }

    // 普通: filename="模板.xlsx"
    const normalMatch = disposition.match(/filename="?(.+?)"?(?:;|$)/)
    if (normalMatch) {
      return normalMatch[1].trim()
    }

    return null
  }

  return {
    isExporting,
    isImporting,
    lastError,
    exportTemplate,
    exportData,
    importData,
    sheets: I6_IMPORTABLE_SHEETS,
  }
}

export default useI6ImportExport
