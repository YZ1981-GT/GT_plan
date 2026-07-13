/**
 * useJ1ImportExport — J1 导入导出 composable
 *
 * 标准三端点：导出模板/导出数据/导入数据
 * 动态行表格：明细表(J1-2) + 5类检查表(J1-6~J1-10)
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 */
import { ref } from 'vue'
import http from '@/utils/http'
import { ElMessage } from 'element-plus'

export function useJ1ImportExport(wpId: string) {
  const isExporting = ref(false)
  const isImporting = ref(false)

  async function exportTemplate(sheetType: string) {
    isExporting.value = true
    try {
      const res = await http.get(
        `/api/workpapers/${wpId}/j1/export-template`,
        { params: { sheet_type: sheetType }, responseType: 'blob' },
      )
      downloadBlob(res.data, `J1_${sheetType}_模板.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (e) {
      ElMessage.error('模板导出失败')
      console.error('[J1 ImportExport] exportTemplate:', e)
    } finally {
      isExporting.value = false
    }
  }

  async function exportData(sheetType: string) {
    isExporting.value = true
    try {
      const res = await http.get(
        `/api/workpapers/${wpId}/j1/export-data`,
        { params: { sheet_type: sheetType }, responseType: 'blob' },
      )
      downloadBlob(res.data, `J1_${sheetType}_数据.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (e) {
      ElMessage.error('数据导出失败')
      console.error('[J1 ImportExport] exportData:', e)
    } finally {
      isExporting.value = false
    }
  }

  async function importData(sheetType: string, file: File): Promise<boolean> {
    isImporting.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      formData.append('sheet_type', sheetType)
      await http.post(`/api/workpapers/${wpId}/j1/import-data`, formData)
      ElMessage.success('数据导入成功')
      return true
    } catch (e) {
      ElMessage.error('数据导入失败')
      console.error('[J1 ImportExport] importData:', e)
      return false
    } finally {
      isImporting.value = false
    }
  }

  function downloadBlob(data: Blob, filename: string) {
    const url = URL.createObjectURL(data)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return { isExporting, isImporting, exportTemplate, exportData, importData }
}
