/**
 * useD3TabImportExport — D3 子 Tab 导入导出（导入后 reloadWorkpaperData）
 */
import { inject, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { useD3ImportExport, type D3ImportableSheet } from './useD3ImportExport'

const SHEET_LABELS: Record<D3ImportableSheet, string> = {
  'D3-1': '审定表',
  'D3-2': '明细表',
  'D3-3': '调整分录',
  'D3-4-debit': '借方分析',
  'D3-4-credit': '贷方分析',
  'D3-5': '长期检查',
  'D3-6': '关联方',
  'D3-7': '凭证检查',
}

export function useD3TabImportExport(wpId: Ref<string>, sheet: D3ImportableSheet) {
  const { exportTemplate, exportData, importData, importFromAuxBalance } = useD3ImportExport({
    wpId,
    sheetCode: sheet,
    sheetLabel: SHEET_LABELS[sheet],
  })

  const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)

  async function afterImport(success: boolean, rowCount: number, warning?: string, errors?: string[]): Promise<void> {
    if (success) {
      let msg = `成功导入 ${rowCount} 行`
      if (warning) msg += `（${warning}）`
      ElMessage.success(msg)
      if (reloadWorkpaperData) await reloadWorkpaperData()
    } else {
      ElMessage.error(errors?.[0] ?? '导入失败')
    }
  }

  async function onExportTemplate(): Promise<void> {
    await exportTemplate()
  }

  async function onExportData(): Promise<void> {
    await exportData()
  }

  async function onImportFile(file: File): Promise<boolean> {
    const result = await importData(file)
    await afterImport(result.success, result.rowCount, result.warning, result.errors)
    return false
  }

  async function onImportFromAuxBalance(): Promise<void> {
    const ok = await importFromAuxBalance()
    if (ok && reloadWorkpaperData) await reloadWorkpaperData()
  }

  return { onExportTemplate, onExportData, onImportFile, onImportFromAuxBalance }
}

export default useD3TabImportExport
