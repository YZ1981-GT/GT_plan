/**
 * useD2TabImportExport — D2 子 Tab 导入导出快捷封装
 * 绑定 sheet 编码（固定或 computed），配合 el-upload before-upload 使用
 */
import { computed, unref, isRef, type ComputedRef, type Ref, inject } from 'vue'
import { ElMessage } from 'element-plus'
import { useD2ImportExport, type ImportableSheet } from './useD2ImportExport'

type SheetSource = ImportableSheet | Ref<ImportableSheet | null> | ComputedRef<ImportableSheet | null>

function resolveSheet(source: SheetSource): ImportableSheet | null {
  return unref(source)
}

export function useD2TabImportExport(
  wpId: Ref<string>,
  projectId: Ref<string>,
  sheet: SheetSource,
) {
  const { exportTemplate, exportData, importData, importing } = useD2ImportExport({
    wpId,
    projectId,
  })

  const activeSheet = isRef(sheet) || (typeof sheet === 'object' && 'value' in sheet)
    ? computed(() => resolveSheet(sheet))
    : computed(() => sheet as ImportableSheet)

  const importExportEnabled = computed(() => activeSheet.value !== null)

  function warnIfDisabled(): boolean {
    if (activeSheet.value) return false
    ElMessage.info('当前 sheet 不支持导入导出')
    return true
  }

  async function onExportTemplate(): Promise<void> {
    if (warnIfDisabled() || !activeSheet.value) return
    await exportTemplate(activeSheet.value)
  }

  async function onExportData(): Promise<void> {
    if (warnIfDisabled() || !activeSheet.value) return
    await exportData(activeSheet.value)
  }

  /** el-upload before-upload：返回 false 阻止默认上传 */
  const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)

  async function onImportFile(file: File): Promise<boolean> {
    if (warnIfDisabled() || !activeSheet.value) return false
    const result = await importData(activeSheet.value, file)
    if (result && reloadWorkpaperData) await reloadWorkpaperData()
    return false
  }

  return {
    activeSheet,
    importExportEnabled,
    importing,
    onExportTemplate,
    onExportData,
    onImportFile,
  }
}

export default useD2TabImportExport
