/**
 * useJ3ImportExport — J3 股份支付导入导出
 *
 * el-dropdown 三级：导出模板 / 导出数据 / 导入数据
 * 后端三端点：template / export / import
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 2.7
 */
import { ref } from 'vue'
import http from '@/utils/http'
import { ElMessage } from 'element-plus'

export function useJ3ImportExport(wpId: string) {
  const isExporting = ref(false)
  const isImporting = ref(false)

  // ── 导出模板 ──────────────────────────────────────────────────────────────

  async function exportTemplate() {
    isExporting.value = true
    try {
      const res = await http.get(
        `/api/workpapers/${wpId}/import-export/template`,
        { responseType: 'blob' },
      )
      downloadBlob(res.data, 'J3_股份支付_模板.xlsx')
      ElMessage.success('模板导出成功')
    } catch (e) {
      ElMessage.error('模板导出失败')
      console.error('[J3 ImportExport] template export failed:', e)
    } finally {
      isExporting.value = false
    }
  }

  // ── 导出数据 ──────────────────────────────────────────────────────────────

  async function exportData() {
    isExporting.value = true
    try {
      const res = await http.get(
        `/api/workpapers/${wpId}/import-export/export`,
        { responseType: 'blob' },
      )
      downloadBlob(res.data, 'J3_股份支付_数据.xlsx')
      ElMessage.success('数据导出成功')
    } catch (e) {
      ElMessage.error('数据导出失败')
      console.error('[J3 ImportExport] data export failed:', e)
    } finally {
      isExporting.value = false
    }
  }

  // ── 导入数据 ──────────────────────────────────────────────────────────────

  async function importData(file: File): Promise<boolean> {
    isImporting.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      await http.post(
        `/api/workpapers/${wpId}/import-export/import`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      ElMessage.success('数据导入成功')
      return true
    } catch (e) {
      ElMessage.error('数据导入失败')
      console.error('[J3 ImportExport] data import failed:', e)
      return false
    } finally {
      isImporting.value = false
    }
  }

  // ── 工具 ──────────────────────────────────────────────────────────────────

  function downloadBlob(blob: Blob, filename: string) {
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = filename
    a.click()
    URL.revokeObjectURL(url)
  }

  return {
    isExporting,
    isImporting,
    exportTemplate,
    exportData,
    importData,
  }
}
