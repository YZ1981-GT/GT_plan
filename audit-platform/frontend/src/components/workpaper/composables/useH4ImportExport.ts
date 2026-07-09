/**
 * useH4ImportExport — H4 工程物资 导入导出 composable
 *
 * Spec: .kiro/specs/h4-engineering-materials/ Task 3.3
 * Requirements: 3.8, 7.6
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - StreamingResponse 中文文件名 RFC5987 编码解析
 * - Blob + createObjectURL 下载 + FormData 上传
 * - Follow useH3ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H4 支持导入导出的 sheet 编码 */
export type H4ImportableSheet =
  | 'H4-2'      // 明细表（67列3区段）
  | 'H4-3'      // 调整分录
  | 'H4-4'      // 增加检查表
  | 'H4-5'      // 减少检查表
  | 'H4-6'      // 盘点检查表
  | 'H4-9'      // 关联交易检查表

export interface H4ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH4ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** H4 可导入导出的 sheet 列表 */
export const H4_IMPORTABLE_SHEETS: { code: H4ImportableSheet; label: string }[] = [
  { code: 'H4-2', label: 'H4-2 明细表' },
  { code: 'H4-3', label: 'H4-3 调整分录' },
  { code: 'H4-4', label: 'H4-4 增加检查表' },
  { code: 'H4-5', label: 'H4-5 减少检查表' },
  { code: 'H4-6', label: 'H4-6 盘点检查表' },
  { code: 'H4-9', label: 'H4-9 关联交易检查表' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH4ImportExport(options: UseH4ImportExportOptions) {
  const { wpId, onImported } = options

  const isExporting = ref(false)
  const isImporting = ref(false)
  const importResult = ref<H4ImportResult | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet: H4ImportableSheet): Promise<void> {
    isExporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h4/export-template`,
        null,
        { params: { sheet_name: sheet }, responseType: 'blob' },
      )
      const filename = _parseFilename(response) || `H4_${sheet}_模板.xlsx`
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

  async function exportData(sheet: H4ImportableSheet): Promise<void> {
    isExporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h4/export-data`,
        null,
        { params: { sheet_name: sheet }, responseType: 'blob' },
      )
      const filename = _parseFilename(response) || `H4_${sheet}_数据.xlsx`
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

  async function importData(sheet: H4ImportableSheet, file: File): Promise<H4ImportResult | null> {
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
        `/api/workpapers/${wpId.value}/h4/import-data`,
        formData,
        {
          params: { sheet_name: sheet },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      const data = response.data?.data ?? response.data
      const result: H4ImportResult = {
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

    // RFC5987: filename*=UTF-8''%E5%B7%A5%E7%A8%8B%E7%89%A9%E8%B5%84.xlsx
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
    sheets: H4_IMPORTABLE_SHEETS,
  }
}

export default useH4ImportExport
