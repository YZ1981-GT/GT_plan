/**
 * useH3ImportExport — H3 投资性房地产 导入导出 composable
 *
 * Spec: .kiro/specs/h3-investment-property/ Task 6.3
 * Requirements: 16.3
 *
 * - el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - 根据 measurement_model 导出对应版本
 * - 导入 xlsx 解析 + 验证 + 确认对话 + 写入
 * - Follow useH1ImportExport / useH2ImportExport pattern
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** H3 支持导入导出的 sheet 编码 */
export type H3ImportableSheet =
  | 'H3-2'      // 明细表（成本49列/公允31列，按区段分sheet导出）
  | 'H3-9'      // 盘点检查表
  | 'H3-12'     // 产权核对表
  | 'H3-13'     // 关联交易检查表
  | 'H3-14'     // 租金收入测算表

export interface H3ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH3ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 当前计量模式 — 影响导出版本 */
  measurementModel: Ref<'cost' | 'fair_value'>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** H3 可导入导出的 sheet 列表 */
export const H3_IMPORTABLE_SHEETS: { code: H3ImportableSheet; label: string }[] = [
  { code: 'H3-2', label: 'H3-2 明细表' },
  { code: 'H3-9', label: 'H3-9 盘点检查表' },
  { code: 'H3-12', label: 'H3-12 产权核对表' },
  { code: 'H3-13', label: 'H3-13 关联交易检查表' },
  { code: 'H3-14', label: 'H3-14 租金收入测算表' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH3ImportExport(options: UseH3ImportExportOptions) {
  const { wpId, measurementModel, onImported } = options

  const importing = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet: H3ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h3/export-template`,
        null,
        { params: { sheet, measurement_model: measurementModel.value }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `H3_${sheet}_模板_${measurementModel.value}.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Export Data ─────────────────────────────────────────────────────────

  async function exportData(sheet: H3ImportableSheet): Promise<void> {
    lastError.value = null
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/h3/export-data`,
        null,
        { params: { sheet, measurement_model: measurementModel.value }, responseType: 'blob' },
      )
      _downloadBlob(response.data, `H3_${sheet}_数据_${measurementModel.value}.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      const msg = err?.response?.data?.message || err.message || '导出失败'
      lastError.value = msg
      ElMessage.error(msg)
    }
  }

  // ─── Import Data ─────────────────────────────────────────────────────────

  async function importData(sheet: H3ImportableSheet, file: File): Promise<H3ImportResult | null> {
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
        `/api/workpapers/${wpId.value}/h3/import-data`,
        formData,
        { params: { sheet, measurement_model: measurementModel.value }, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: H3ImportResult = {
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
    sheets: H3_IMPORTABLE_SHEETS,
  }
}

export default useH3ImportExport
