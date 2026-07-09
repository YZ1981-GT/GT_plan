/**
 * useI3ImportExport — I3 商誉 导入导出 composable
 *
 * Spec: .kiro/specs/i3-goodwill/ Task 3.6
 * Requirements: 导入导出统一规范 (memory)
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - 仅动态行表格需要导入导出：I3-2明细 / I3-3调整 / I3-6减值测试
 * - 多区块分sheet导出
 * - Follow useH1ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I3 支持导入导出的 sheet 编码 */
export type I3ImportableSheet =
  | 'I3-2'      // 明细表（30列，动态行）
  | 'I3-3'      // 调整分录汇总（动态行）
  | 'I3-6'      // 减值测试（CGU动态行）

export interface I3ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseI3ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** I3-2 的 3 区段定义 */
export const I3_DETAIL_SEGMENTS = [
  { key: 'basic', label: '基础信息(被投资单位/并购日期/对价/被购方净资产)' },
  { key: 'initial', label: '入账信息(合并成本/可辨认净资产公允/商誉原值)' },
  { key: 'impairment', label: '减值信息(累计减值/本期减值/期末净额)' },
] as const

export const I3_IMPORTABLE_SHEETS: { code: I3ImportableSheet; label: string }[] = [
  { code: 'I3-2', label: 'I3-2 明细表(30列3区段)' },
  { code: 'I3-3', label: 'I3-3 调整分录汇总' },
  { code: 'I3-6', label: 'I3-6 商誉减值测试' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI3ImportExport(options: UseI3ImportExportOptions) {
  const { wpId, onImported } = options

  const importing = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet: I3ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/i3/export-template`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `I3_${sheet}_模板.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  async function exportData(sheet: I3ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/i3/export-data`,
        null,
        { params: { sheet }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `I3_${sheet}_数据.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  async function importData(sheet: I3ImportableSheet, file: File): Promise<I3ImportResult | null> {
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
        `/api/workpapers/${wpId.value}/i3/import-data`,
        formData,
        { params: { sheet }, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: I3ImportResult = {
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
    sheets: I3_IMPORTABLE_SHEETS,
    segments: I3_DETAIL_SEGMENTS,
  }
}

export default useI3ImportExport
