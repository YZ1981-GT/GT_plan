/**
 * useH2ImportExport — H2 在建工程 导入导出 composable
 *
 * Spec: .kiro/specs/h2-construction-in-progress/ Task 6.3
 * Requirements: 14.3-14.4
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - H2-2 50列按 3 区段分 sheet 导出
 * - 导入 xlsx 解析 + 验证 + 确认对话 + 写入
 * - ~150 行，follow useH1ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H2 支持导入导出的 sheet 编码 */
export type H2ImportableSheet =
  | 'H2-2'      // 明细表（3区段分sheet导出）
  | 'H2-13'     // 盘点检查表

export interface H2ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH2ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** H2-2 的 3 区段定义 */
export const H2_DETAIL_SEGMENTS = [
  { key: 'basic', label: '基本信息(1-16列)' },
  { key: 'changes', label: '增减变动(17-36列)' },
  { key: 'completion', label: '竣工结转(37-50列)' },
] as const

export const H2_IMPORTABLE_SHEETS: { code: H2ImportableSheet; label: string }[] = [
  { code: 'H2-2', label: 'H2-2 明细表(50列3区段)' },
  { code: 'H2-13', label: 'H2-13 盘点检查表' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH2ImportExport(options: UseH2ImportExportOptions) {
  const { wpId, onImported } = options

  const importing = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet: H2ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h2/export-template`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `H2_${sheet}_模板.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  async function exportData(sheet: H2ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h2/export-data`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `H2_${sheet}_数据.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  async function importData(sheet: H2ImportableSheet, file: File): Promise<H2ImportResult | null> {
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
        `/api/workpapers/${wpId.value}/h2/import-data`,
        formData,
        { params: { sheet }, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: H2ImportResult = {
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
    sheets: H2_IMPORTABLE_SHEETS,
    segments: H2_DETAIL_SEGMENTS,
  }
}

export default useH2ImportExport
