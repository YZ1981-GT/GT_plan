/**

 * useD5TabImportExport — D5 子 Tab 导入导出（导入后 reloadWorkpaperData）

 */

import { inject, type Ref } from 'vue'

import { useD5ImportExport, type D5ImportableSheet } from './useD5ImportExport'



const SHEET_LABELS: Record<D5ImportableSheet, string> = {

  'D5-1': '审定表',

  'D5-2': '明细表',

  'D5-3': '调整分录',

  'D5-4': '公允价值测算',

}



export function useD5TabImportExport(wpId: Ref<string>, sheet: D5ImportableSheet) {

  const reloadWorkpaperData = inject<(() => Promise<void> | void) | null>('reloadWorkpaperData', null)



  const { exportTemplate, exportData, importData, importing } = useD5ImportExport({

    wpId,

    sheetCode: sheet,

    sheetLabel: SHEET_LABELS[sheet],

    onImported: async () => {

      if (reloadWorkpaperData) await reloadWorkpaperData()

    },

  })



  async function onExportTemplate(): Promise<void> {

    await exportTemplate()

  }



  async function onExportData(): Promise<void> {

    await exportData()

  }



  async function onImportFile(file: File): Promise<boolean> {

    await importData(file)

    return false

  }



  return { importing, onExportTemplate, onExportData, onImportFile }

}



export default useD5TabImportExport

