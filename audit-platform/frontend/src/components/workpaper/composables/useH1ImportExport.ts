/**
 * useH1ImportExport — H1 固定资产 导入导出 composable
 *
 * Spec: .kiro/specs/h1-fixed-assets/ Task 6.3
 * Requirements: 18.3-18.4, 18.7-18.8
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - H1-2 54列按 4 区段分 sheet 导出
 * - 导入 xlsx 解析 + 验证 + 确认对话 + 写入
 * - ~150 行，follow useF4ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H1 支持导入导出的 sheet 编码 */
export type H1ImportableSheet =
  | 'H1-2'      // 明细表（4区段分sheet导出）
  | 'H1-10'     // 盘点检查表
  | 'H1-12'     // 折旧测算（企业台账）
  | 'H1-18'     // 关联交易检查表

export interface H1ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH1ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** H1-2 的 4 区段定义 */
export const H1_DETAIL_SEGMENTS = [
  { key: 'basic', label: '基本信息(1-14列)' },
  { key: 'cost', label: '原值变动(15-28列)' },
  { key: 'depreciation', label: '折旧变动(29-42列)' },
  { key: 'impairment', label: '减值+净值(43-54列)' },
] as const

export const H1_IMPORTABLE_SHEETS: { code: H1ImportableSheet; label: string }[] = [
  { code: 'H1-2', label: 'H1-2 明细表(54列4区段)' },
  { code: 'H1-10', label: 'H1-10 盘点检查表' },
  { code: 'H1-12', label: 'H1-12 折旧测算(企业台账)' },
  { code: 'H1-18', label: 'H1-18 关联交易检查表' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1ImportExport(options: UseH1ImportExportOptions) {
  const { wpId, onImported } = options

  const importing = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet: H1ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h1/export-template`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `H1_${sheet}_模板.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  async function exportData(sheet: H1ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h1/export-data`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `H1_${sheet}_数据.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  async function importData(sheet: H1ImportableSheet, file: File): Promise<H1ImportResult | null> {
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
        `/api/workpapers/${wpId.value}/h1/import-data`,
        formData,
        { params: { sheet }, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: H1ImportResult = {
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

  // ─── Helper: Blob下载 ────────────────────────────────────────────────────

  function _downloadBlob(blob: Blob, filename: string): void {
    const url = URL.createObjectURL(new Blob([blob]))
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return {
    importing,
    lastError,
    exportTemplate,
    exportData,
    importData,
    sheets: H1_IMPORTABLE_SHEETS,
    segments: H1_DETAIL_SEGMENTS,
  }
}

export default useH1ImportExport
