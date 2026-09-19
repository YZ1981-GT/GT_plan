/**
 * useI4ImportExport — I4 长期待摊费用 导入导出 composable
 *
 * Spec（归档）: .kiro/specs/_archive/05-business-features/i4-long-term-prepaid/ Task 3.5
 * Requirements: 导入导出统一规范 (memory)
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - 动态行：I4-2 明细滚转 / I4-6 直线 / I4-7 工作量（后端 `_I4_SPECS` 仅此三表）
 * - 多区块分sheet导出
 * - StreamingResponse + RFC5987 编码中文文件名
 * - Follow useI3ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I4 支持导入导出的 sheet 编码（与后端 `_I4_SPECS` 对齐：仅 2/6/7） */
export type I4ImportableSheet =
  | 'I4-2'      // 明细表（滚转动态行）
  | 'I4-6'      // 摊销测算-直线法
  | 'I4-7'      // 摊销测算-工作量法

export interface I4ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseI4ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** I4-2 滚转区段（导入模板分 sheet 标签） */
export const I4_DETAIL_SEGMENTS = [
  { key: 'unadj', label: '未审滚动(期初/增加/摊销/其他减少/期末)' },
  { key: 'aje', label: '调整与审定(AJE/审定滚转)' },
  { key: 'amortization', label: '摊销信息(方法/期限/已摊月数)' },
  { key: 'basic', label: '基础信息(项目名/发生日/类型/原始金额)' },
] as const

export const I4_IMPORTABLE_SHEETS: { code: I4ImportableSheet; label: string }[] = [
  { code: 'I4-2', label: 'I4-2 明细表(滚转四区段)' },
  { code: 'I4-6', label: 'I4-6 摊销测算-直线法(测算vs账面)' },
  { code: 'I4-7', label: 'I4-7 摊销测算-工作量法(测算vs账面)' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI4ImportExport(options: UseI4ImportExportOptions) {
  const { wpId, onImported } = options

  const importing = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet: I4ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.get(
        `/api/workpapers/${wpId.value}/i4/export-template`,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response, `I4_${sheet}_模板.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  async function exportData(sheet: I4ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.get(
        `/api/workpapers/${wpId.value}/i4/export-data`,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response, `I4_${sheet}_数据.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  async function importData(sheet: I4ImportableSheet, file: File): Promise<I4ImportResult | null> {
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
        `/api/workpapers/${wpId.value}/i4/import-data`,
        formData,
        { params: { sheet }, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: I4ImportResult = {
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
    sheets: I4_IMPORTABLE_SHEETS,
    segments: I4_DETAIL_SEGMENTS,
  }
}

export default useI4ImportExport
