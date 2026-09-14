/**
 * useI5ImportExport — I5 其他非流动资产 导入导出 composable
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/ Task 3.4
 * Requirements: 导入导出统一规范 (memory)
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - 仅动态行表格需要导入导出：I5-2 明细表
 * - StreamingResponse + RFC5987 编码中文文件名
 * - Follow useI4ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I5 支持导入导出的 sheet 编码 */
export type I5ImportableSheet =
  | 'I5-2'      // 明细表（原值|减值|净值滚动）
  | 'I5-3'      // 调整分录汇总

export const I5_ADJUSTMENT_COLUMNS = [
  'description', 'category', 'reportItem', 'accountCode', 'accountName',
  'noteItem', 'projectName', 'debitAmount', 'creditAmount', 'indexRef', 'remark',
] as const

export interface I5ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseI5ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** I5-2 的区段定义（对齐 Excel 原值|减值|净值） */
export const I5_DETAIL_SEGMENTS = [
  { key: 'gross-unadj', label: '原值未审(期初/增/减/期末)' },
  { key: 'gross-adj', label: '原值调整与审定' },
  { key: 'impairment', label: '减值准备' },
  { key: 'net', label: '净值与索引' },
] as const

export const I5_IMPORTABLE_SHEETS: { code: I5ImportableSheet; label: string }[] = [
  { code: 'I5-2', label: 'I5-2 明细表(原值/减值/净值)' },
  { code: 'I5-3', label: 'I5-3 调整分录汇总' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI5ImportExport(options: UseI5ImportExportOptions) {
  const { wpId, onImported } = options

  const importing = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet: I5ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.get(
        `/api/workpapers/${wpId.value}/i5/export-template`,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response, `I5_${sheet}_模板.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  async function exportData(sheet: I5ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.get(
        `/api/workpapers/${wpId.value}/i5/export-data`,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response, `I5_${sheet}_数据.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  async function importData(sheet: I5ImportableSheet, file: File): Promise<I5ImportResult | null> {
    lastError.value = null
    importing.value = true
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
        `/api/workpapers/${wpId.value}/i5/import-data`,
        formData,
        { params: { sheet }, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: I5ImportResult = {
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
      importing.value = false
    }
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
    importing,
    lastError,
    exportTemplate,
    exportData,
    importData,
    sheets: I5_IMPORTABLE_SHEETS,
    segments: I5_DETAIL_SEGMENTS,
  }
}

export default useI5ImportExport
