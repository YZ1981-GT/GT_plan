/**
 * useI1ImportExport — I1 无形资产 导入导出 composable
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（http，NOT native fetch）— 自动带 Authorization header
 * - 多 sheet 支持：明细表(I1-2) + 审定表(I1) + 摊销(I1-10/I1-11) 分 sheet 导出
 * - 导入 xlsx 解析 + 验证 + 确认对话 + 写入
 * - Follow useH1ImportExport pattern
 *
 * Spec: .kiro/specs/i1-intangible-assets/
 * Task: 3.7
 * Requirements: 14.1-14.4
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I1 支持导入导出的 sheet 编码 */
export type I1ImportableSheet =
  | 'I1'        // 审定表
  | 'I1-2'     // 明细表（4区段分sheet导出）
  | 'I1-9'     // 摊销分配
  | 'I1-10'    // 摊销测算（不含减值）
  | 'I1-11'    // 摊销测算（含减值）

export interface I1ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseI1ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** I1-2 的 4 区段定义（多sheet导出） */
export const I1_DETAIL_SEGMENTS = [
  { key: 'basic', label: '基础信息(1-8列)' },
  { key: 'cost', label: '原值变动(9-16列)' },
  { key: 'amortization', label: '摊销变动(17-28列)' },
  { key: 'impairment', label: '减值+净值(29-56列)' },
] as const

export const I1_IMPORTABLE_SHEETS: { code: I1ImportableSheet; label: string }[] = [
  { code: 'I1', label: 'I1 审定表(93行9列)' },
  { code: 'I1-2', label: 'I1-2 明细表(56列4区段)' },
  { code: 'I1-9', label: 'I1-9 摊销分配(10列)' },
  { code: 'I1-10', label: 'I1-10 摊销测算(不含减值)' },
  { code: 'I1-11', label: 'I1-11 摊销测算(含减值)' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1ImportExport(options: UseI1ImportExportOptions) {
  const { wpId, onImported } = options

  const importing = ref(false)
  const exporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  /**
   * POST /api/workpapers/{wpId}/i1/export-template?sheet=xxx
   * 导出空白模板（含列头/说明/格式/数据验证）
   */
  async function exportTemplate(sheet: I1ImportableSheet): Promise<void> {
    lastError.value = null
    exporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/i1/export-template`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `I1_${sheet}_模板.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '模板导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    } finally {
      exporting.value = false
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  /**
   * POST /api/workpapers/{wpId}/i1/export-data?sheet=xxx
   * 导出当前数据（I1-2多区段分sheet导出）
   * 支持 multi-sheet：detail+adjudication+amortization 可分别导出
   */
  async function exportData(sheet: I1ImportableSheet): Promise<void> {
    lastError.value = null
    exporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/i1/export-data`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      const timestamp = new Date().toISOString().slice(0, 10)
      _downloadBlob(response.data, `I1_${sheet}_数据_${timestamp}.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '数据导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    } finally {
      exporting.value = false
    }
  }

  /**
   * 批量导出全部sheet（明细+审定+摊销分别为独立sheet页签）
   */
  async function exportAllSheets(): Promise<void> {
    lastError.value = null
    exporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/i1/export-data`,
        null,
        { params: { sheet: 'all' }, responseType: 'blob' },
      )
      const timestamp = new Date().toISOString().slice(0, 10)
      _downloadBlob(response.data, `I1_无形资产_全量数据_${timestamp}.xlsx`)
      ElMessage.success('全量数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '全量导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    } finally {
      exporting.value = false
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  /**
   * POST /api/workpapers/{wpId}/i1/import-data?sheet=xxx
   * 导入 xlsx 文件 + 验证 + 确认对话
   */
  async function importData(sheet: I1ImportableSheet, file: File): Promise<I1ImportResult | null> {
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
        `/api/workpapers/${wpId.value}/i1/import-data`,
        formData,
        { params: { sheet }, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: I1ImportResult = {
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

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    importing,
    exporting,
    lastError,
    exportTemplate,
    exportData,
    exportAllSheets,
    importData,
    sheets: I1_IMPORTABLE_SHEETS,
    segments: I1_DETAIL_SEGMENTS,
  }
}

export default useI1ImportExport
