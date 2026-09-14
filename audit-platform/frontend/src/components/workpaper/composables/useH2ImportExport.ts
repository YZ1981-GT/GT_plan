/**
 * useH2ImportExport — H2 在建工程导入导出
 *
 * H2-2：4区段多 sheet（基本信息/账面原值/审定原值/减值与净值）
 * 字段对齐 useH2Detail；抵押标志可联动附注受限披露
 */
import { ref, type Ref } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import http from '@/utils/http'

export type H2ImportableSheet =
  | 'H2-2'
  | 'H2-2-base'
  | 'H2-2-cost-unadj'
  | 'H2-2-cost-aud'
  | 'H2-2-impair'
  | 'H2-5'
  | 'H2-5-cip'
  | 'H2-8'
  | 'H2-9'
  | 'H2-13'
  | 'H2-17'

export interface H2ImportResult {
  success: boolean
  rowCount: number
  warning?: string
}

export interface UseH2ImportExportOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  onImported?: () => void | Promise<void>
}

/** H2-2 四区段（与后端 _H2_2_SEGMENTS / H2TabDetail 一致） */
export const H2_DETAIL_SEGMENTS = [
  { key: 'basic', code: 'H2-2-base' as const, label: '基本信息' },
  { key: 'costUnadj', code: 'H2-2-cost-unadj' as const, label: '账面原值' },
  { key: 'costAud', code: 'H2-2-cost-aud' as const, label: '审定原值' },
  { key: 'impair', code: 'H2-2-impair' as const, label: '减值与净值' },
] as const

export const H2_IMPORTABLE_SHEETS: { code: H2ImportableSheet; label: string }[] = [
  { code: 'H2-2', label: 'H2-2 明细表(4区段)' },
  { code: 'H2-13', label: 'H2-13 盘点检查表' },
  { code: 'H2-17', label: 'H2-17 关联交易检查表' },
]

function _downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(new Blob([blob]))
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function useH2ImportExport(options: UseH2ImportExportOptions) {
  const { wpId, onImported } = options
  const importing = ref(false)
  const lastError = ref<string | null>(null)

  async function exportTemplate(sheet: H2ImportableSheet = 'H2-2'): Promise<void> {
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

  async function exportData(sheet: H2ImportableSheet = 'H2-2'): Promise<void> {
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

  async function importData(sheet: H2ImportableSheet, file: File): Promise<H2ImportResult | null> {
    lastError.value = null
    importing.value = true
    try {
      await ElMessageBox.confirm(
        `即将导入「${file.name}」到 ${sheet}，已有数据将被覆盖或按工程名合并。确认？`,
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
      const result: H2ImportResult = {
        success: true,
        rowCount: data?.imported_count ?? data?.row_count ?? 0,
        warning: data?.warning,
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

  /** 选择本地文件并导入 */
  function pickAndImport(sheet: H2ImportableSheet = 'H2-2'): void {
    const input = document.createElement('input')
    input.type = 'file'
    input.accept = '.xlsx,.xls'
    input.onchange = () => {
      const file = input.files?.[0]
      if (file) void importData(sheet, file)
    }
    input.click()
  }

  return {
    importing,
    lastError,
    exportTemplate,
    exportData,
    importData,
    pickAndImport,
    sheets: H2_IMPORTABLE_SHEETS,
    segments: H2_DETAIL_SEGMENTS,
  }
}

export default useH2ImportExport
