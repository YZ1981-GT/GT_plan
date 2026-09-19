/**
 * useI3ImportExport — I3 商誉 导入导出 composable
 *
 * 动态行：I3-1 审定 / I3-2 明细滚动 / I3-3 调整 / I3-4 入账 / I3-6 减值 / I3-7 DCF
 * axios 请求（自动带 Authorization）
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type I3ImportableSheet =
  | 'I3-1'
  | 'I3-2'
  | 'I3-3'
  | 'I3-4'
  | 'I3-6'
  | 'I3-7'

export interface I3ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseI3ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onImported?: () => void | Promise<void>
}

export const I3_DETAIL_SEGMENTS = [
  { key: 'cost', label: '原值滚动(期初/增加/减少/期末/未审/调整/审定)' },
  { key: 'impairment', label: '减值滚动(期初/计提/减少/期末/未审/调整/审定/净值)' },
  { key: 'entry', label: '入账测算(合并成本/公允份额/测算商誉)' },
  { key: 'basic', label: '基础信息(控制类型/合并方式/CGU)' },
] as const

export const I3_IMPORTABLE_SHEETS: { code: I3ImportableSheet; label: string }[] = [
  { code: 'I3-1', label: 'I3-1 审定表' },
  { code: 'I3-2', label: 'I3-2 明细表(原值/减值滚动)' },
  { code: 'I3-3', label: 'I3-3 调整分录汇总' },
  { code: 'I3-4', label: 'I3-4 入账价值测算' },
  { code: 'I3-6', label: 'I3-6 商誉减值测试' },
  { code: 'I3-7', label: 'I3-7 可收回金额(DCF)' },
]

export function useI3ImportExport(options: UseI3ImportExportOptions) {
  const { wpId, onImported } = options

  const importing = ref(false)
  const lastError = ref<string | null>(null)

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

  async function importData(sheet: I3ImportableSheet, file: File): Promise<I3ImportResult | null> {
    lastError.value = null
    importing.value = true
    try {
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
