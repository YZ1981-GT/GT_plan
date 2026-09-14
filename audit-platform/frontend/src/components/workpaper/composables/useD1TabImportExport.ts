/**
 * useD1TabImportExport — D1 子 Tab 导入导出（导入后 reloadWorkpaperData）
 */
import { inject, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD1ImportExport, type ImportResult } from './useD1ImportExport'
import http from '@/utils/http'

export type D1StandardSheet =
  | 'D1-1' | 'D1-2' | 'D1-3' | 'D1-4' | 'D1-5' | 'D1-6' | 'D1-7' | 'D1-8' | 'D1-8T' | 'D1-9'
  | 'D1-10' | 'D1-11' | 'D1-12' | 'D1-13' | 'D1-14' | 'D1-16'

const SHEET_LABELS: Record<string, string> = {
  'D1-1': '审定表',
  'D1-2': '原值明细(按类别)',
  'D1-3': '原值明细(按客户)',
  'D1-4': '坏账准备',
  'D1-5': '调整分录',
  'D1-6': '业务模式',
  'D1-7': '备查簿',
  'D1-8': '已贴现',
  'D1-8T': '已背书',
  'D1-9': '贴息',
  'D1-10': '监盘表',
  'D1-11': '关联方检查',
  'D1-12': '质押检查',
  'D1-13': '一般检查表',
  'D1-14': '会计政策检查',
  'D1-16': '转回核销',
}

function triggerBlobDownload(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  a.click()
  URL.revokeObjectURL(url)
}

export function useD1TabImportExport(wpId: Ref<string>, sheet: D1StandardSheet) {
  const label = SHEET_LABELS[sheet] ?? sheet
  const { exportTemplate, exportData, importData } = useD1ImportExport({
    wpId,
    sheetCode: sheet,
    sheetLabel: label,
  })

  const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)

  async function afterImport(result: ImportResult): Promise<void> {
    if (result.success) {
      ElMessage.success(`成功导入 ${result.rowCount} 行`)
      if (reloadWorkpaperData) await reloadWorkpaperData()
    } else {
      ElMessage.error(result.errors?.[0] ?? '导入失败')
    }
  }

  async function onExportTemplate(): Promise<void> {
    try {
      await exportTemplate()
    } catch {
      ElMessage.error('导出模板失败')
    }
  }

  async function onExportData(): Promise<void> {
    try {
      await exportData()
    } catch {
      ElMessage.error('导出数据失败')
    }
  }

  async function onImportFile(file: File): Promise<boolean> {
    const result = await importData(file)
    await afterImport(result)
    return false
  }

  return { onExportTemplate, onExportData, onImportFile }
}

/** 附注披露专用路径 */
export function useD1DisclosureImportExport(
  wpId: Ref<string>,
  variant: 'listed' | 'soe',
) {
  const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)
  const suffix = variant === 'soe' ? '国企' : '上市'

  async function postBlob(path: string, filename: string): Promise<void> {
    const res = await http.post(path, null, { responseType: 'blob' })
    triggerBlobDownload(new Blob([res.data]), filename)
  }

  async function onExportTemplate(): Promise<void> {
    try {
      await postBlob(
        `/api/workpapers/${wpId.value}/d1/disclosure/export-template?variant=${variant}`,
        `D1-附注${suffix}模板.xlsx`,
      )
    } catch { ElMessage.error('导出模板失败') }
  }

  async function onExportData(): Promise<void> {
    try {
      await postBlob(
        `/api/workpapers/${wpId.value}/d1/disclosure/export-data?variant=${variant}`,
        `D1-附注${suffix}数据.xlsx`,
      )
    } catch { ElMessage.error('导出数据失败') }
  }

  async function onImportFile(file: File): Promise<boolean> {
    const formData = new FormData()
    formData.append('file', file)
    try {
      const res = await http.post(
        `/api/workpapers/${wpId.value}/d1/disclosure/import-data?variant=${variant}`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      const data = res.data?.data ?? res.data
      ElMessage.success(`成功导入${data?.imported_count ?? data?.row_count ?? 0}行`)
      if (reloadWorkpaperData) await reloadWorkpaperData()
    } catch { ElMessage.error('导入失败') }
    return false
  }

  return { onExportTemplate, onExportData, onImportFile }
}

export default useD1TabImportExport
