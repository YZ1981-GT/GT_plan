/**
 * useH8ImportExport — H8 使用权资产 导入导出 composable
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ Task 3.3
 * Requirements: 3.3
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - StreamingResponse 中文文件名 RFC5987 编码解析
 * - Blob + createObjectURL 下载 + FormData 上传
 * - 对齐 cycle IE：POST /api/workpapers/{wpId}/h8/{export-template|export-data|import-data}?sheet=
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H8 支持导入导出的 sheet 编码 */
export type H8ImportableSheet =
  | 'H8-2'      // 明细表（58列4区段）
  | 'H8-3'      // 调整分录
  | 'H8-4'      // 租赁识别（H8-4-records）
  | 'H8-5'      // 租赁期确定（H8-5-records）
  | 'H8-7'      // 租赁变更
  | 'H8-12'     // 减少检查表（租赁终止）
  | 'H8-13'     // 简化处理检查表
  | 'H8-14'     // 关联交易检查表（使用权资产）
  | 'H8-14L'    // 关联交易检查表（租赁负债）

export interface H8ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH8ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 当前 sheet 编码（导入与默认导出目标） */
  sheetCode?: H8ImportableSheet | string
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** H8 可导入导出的 sheet 列表 */
export const H8_IMPORTABLE_SHEETS: { code: H8ImportableSheet; label: string }[] = [
  { code: 'H8-2', label: 'H8-2 明细表' },
  { code: 'H8-3', label: 'H8-3 调整分录' },
  { code: 'H8-4', label: 'H8-4 租赁识别' },
  { code: 'H8-5', label: 'H8-5 租赁期确定' },
  { code: 'H8-7', label: 'H8-7 租赁变更' },
  { code: 'H8-12', label: 'H8-12 减少检查表' },
  { code: 'H8-13', label: 'H8-13 简化处理检查表' },
  { code: 'H8-14', label: 'H8-14 关联交易检查表（使用权资产）' },
  { code: 'H8-14L', label: 'H8-14 关联交易检查表（租赁负债）' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH8ImportExport(options: UseH8ImportExportOptions) {
  const { wpId, sheetCode, onImported } = options

  const isExporting = ref(false)
  const isImporting = ref(false)
  const importResult = ref<H8ImportResult | null>(null)

  function _resolveSheet(sheets?: string[]): string {
    const sheet = sheets?.[0] || sheetCode
    if (!sheet) throw new Error('未指定 H8 sheet 编码')
    return sheet
  }

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheets?: string[]): Promise<void> {
    isExporting.value = true
    try {
      const sheet = _resolveSheet(sheets)
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h8/export-template`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      const filename = _parseFilename(response) || `H8_${sheet}_模板.xlsx`
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
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h8/export-data`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      const filename = _parseFilename(response) || `H8_${sheet}_数据.xlsx`
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

  async function importData(file: File, sheets?: string[]): Promise<H8ImportResult | null> {
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
        `/api/workpapers/${wpId.value}/h8/import-data`,
        formData,
        {
          params: { sheet },
          headers: { 'Content-Type': 'multipart/form-data' },
        },
      )

      const data = response.data?.data ?? response.data
      const result: H8ImportResult = {
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
  }
}

export default useH8ImportExport
