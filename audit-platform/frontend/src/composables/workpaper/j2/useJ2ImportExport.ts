/**
 * useJ2ImportExport — J2 导入导出（el-dropdown统一入口）
 *
 * 支持3端点：导出模板 / 导出数据 / 导入数据
 * 多区块分sheet导出（审定表+明细表+附注）
 *
 * Spec: .kiro/specs/j2-defined-benefit-plan/
 * Requirements: 6.5
 */
import { ref } from 'vue'
import { http } from '@/utils/http'
import { ElMessage } from 'element-plus'

export interface J2ImportExportOptions {
  wpId: string
  projectId: string
}

export function useJ2ImportExport(options: J2ImportExportOptions) {
  const isExporting = ref(false)
  const isImporting = ref(false)

  // ── 导出模板 ──────────────────────────────────────────────────────────────

  async function exportTemplate() {
    isExporting.value = true
    try {
      const res = await http.get(
        `/api/workpapers/${options.wpId}/j2/export-template`,
        { responseType: 'blob' },
      )
      downloadBlob(res.data, 'J2_设定受益计划_模板.xlsx')
      ElMessage.success('模板导出成功')
    } catch (e) {
      ElMessage.error('模板导出失败')
      console.error('[J2 ImportExport] exportTemplate failed:', e)
    } finally {
      isExporting.value = false
    }
  }

  // ── 导出数据 ──────────────────────────────────────────────────────────────

  async function exportData() {
    isExporting.value = true
    try {
      const res = await http.get(
        `/api/workpapers/${options.wpId}/j2/export-data`,
        { responseType: 'blob' },
      )
      downloadBlob(res.data, 'J2_设定受益计划_数据.xlsx')
      ElMessage.success('数据导出成功')
    } catch (e) {
      ElMessage.error('数据导出失败')
      console.error('[J2 ImportExport] exportData failed:', e)
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
        `/api/workpapers/${options.wpId}/j2/import-data`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      ElMessage.success('数据导入成功')
      return true
    } catch (e) {
      ElMessage.error('数据导入失败')
      console.error('[J2 ImportExport] importData failed:', e)
      return false
    } finally {
      isImporting.value = false
    }
  }

  // ── 工具函数 ──────────────────────────────────────────────────────────────

  function downloadBlob(data: Blob | ArrayBuffer, filename: string) {
    const blob = data instanceof Blob ? data : new Blob([data])
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
