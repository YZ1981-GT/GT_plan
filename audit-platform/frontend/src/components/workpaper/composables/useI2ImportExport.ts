/**
 * useI2ImportExport — I2 开发支出 导入导出 composable
 *
 * el-dropdown 三级 UI（导出模板 / 导出数据 / 导入数据）
 * - axios 请求（NOT fetch）— 自动带 Authorization header
 * - 多sheet导出（I2-2明细 + I2-7项目构成 + I2-1审定）
 * - 导入 xlsx 解析 + 验证 + 确认对话 + 写入
 *
 * API endpoints:
 * - POST /api/workpapers/{wpId}/i2/export-template
 * - POST /api/workpapers/{wpId}/i2/export-data
 * - POST /api/workpapers/{wpId}/i2/import-data
 *
 * Spec: .kiro/specs/i2-development-expenditure/
 * Task: 3.7
 * Requirements: 底稿导入导出统一规范
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

// ─── Types ───────────────────────────────────────────────────────────────────

/** I2 支持导入导出的 sheet 编码 */
export type I2ImportableSheet =
  | 'I2-1'      // 审定表
  | 'I2-2'      // 明细表（61列4区段分sheet导出）
  | 'I2-7'      // 项目构成明细表（73列5区段分sheet导出）

export interface I2ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseI2ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  /** 导入完成后刷新数据回调 */
  onImported?: () => void | Promise<void>
}

/** I2-2 的 4 区段定义 */
export const I2_DETAIL_SEGMENTS = [
  { key: 'basic', label: '基础信息(项目名/立项日/阶段)' },
  { key: 'investment', label: '本期投入(材料/人工/折旧/其他)' },
  { key: 'capitalization', label: '资本化(起点/金额/转入I1)' },
  { key: 'summary', label: '期末汇总' },
] as const

/** I2-7 的 5 区段定义 */
export const I2_PROJECT_SEGMENTS = [
  { key: 'basic', label: '基础信息' },
  { key: 'material', label: '材料费' },
  { key: 'labor', label: '人工费' },
  { key: 'depreciation', label: '折旧摊销' },
  { key: 'other', label: '其他费用' },
] as const

export const I2_IMPORTABLE_SHEETS: { code: I2ImportableSheet; label: string }[] = [
  { code: 'I2-1', label: 'I2-1 审定表' },
  { code: 'I2-2', label: 'I2-2 明细表(61列4区段)' },
  { code: 'I2-7', label: 'I2-7 项目构成(73列5区段)' },
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI2ImportExport(options: UseI2ImportExportOptions) {
  const { wpId, onImported } = options

  const isExporting = ref(false)
  const isImporting = ref(false)
  const lastError = ref<string | null>(null)

  // ─── Export Template ─────────────────────────────────────────────────────

  async function exportTemplate(sheet?: I2ImportableSheet): Promise<void> {
    lastError.value = null
    isExporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/i2/export-template`,
        null,
        { params: sheet ? { sheet } : {}, responseType: 'blob' },
      )
      const filename = sheet ? `I2_${sheet}_模板.xlsx` : 'I2_模板.xlsx'
      _downloadBlob(response.data, filename)
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

  async function exportData(sheet?: I2ImportableSheet): Promise<void> {
    lastError.value = null
    isExporting.value = true
    try {
      const response = await http.post(
        `/api/workpapers/${wpId.value}/i2/export-data`,
        null,
        { params: sheet ? { sheet } : {}, responseType: 'blob' },
      )
      const filename = sheet ? `I2_${sheet}_数据.xlsx` : 'I2_数据.xlsx'
      _downloadBlob(response.data, filename)
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

  async function importData(file: File, sheet?: I2ImportableSheet): Promise<I2ImportResult | null> {
    lastError.value = null
    isImporting.value = true
    try {
      const targetLabel = sheet
        ? I2_IMPORTABLE_SHEETS.find((s) => s.code === sheet)?.label ?? sheet
        : 'I2全部表'

      await ElMessageBox.confirm(
        `即将导入文件「${file.name}」到 ${targetLabel}，已有数据将被覆盖。确认导入？`,
        '导入确认',
        { confirmButtonText: '确认导入', cancelButtonText: '取消', type: 'warning' },
      )

      const formData = new FormData()
      formData.append('file', file)

      const response = await http.post(
        `/api/workpapers/${wpId.value}/i2/import-data`,
        formData,
        { params: sheet ? { sheet } : {}, headers: { 'Content-Type': 'multipart/form-data' } },
      )

      const data = response.data?.data ?? response.data
      if (!data) {
        ElMessage.warning('导入完成，但未返回结果')
        return null
      }

      const result: I2ImportResult = {
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
    isExporting,
    isImporting,
    lastError,
    exportTemplate,
    exportData,
    importData,
    sheets: I2_IMPORTABLE_SHEETS,
    detailSegments: I2_DETAIL_SEGMENTS,
    projectSegments: I2_PROJECT_SEGMENTS,
  }
}

export default useI2ImportExport
