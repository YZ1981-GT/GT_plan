/**
 * useH7ImportExport — H7 生产性生物资产导入导出 composable
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 3.3
 * Requirements: 3.4
 *
 * el-dropdown 三级：导出模板 / 导出数据 / 导入数据
 * 后端三端点：/h7/export-template | /h7/export-data | /h7/import-data
 * 多区块分sheet导出，动态行表格才需要导入导出
 */
import { ref, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { api } from '@/services/apiProxy'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface UseH7ImportExportOptions {
  wpId: Ref<string>
  sheetName?: Ref<string>
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH7ImportExport(options: UseH7ImportExportOptions) {
  const { wpId, sheetName } = options
  const isExporting = ref(false)
  const isImporting = ref(false)

  /** 导出模板（空表结构） */
  async function exportTemplate(): Promise<void> {
    isExporting.value = true
    try {
      const resp = await api.get(`/api/workpapers/${wpId.value}/h7/export-template`, {
        params: { sheet: sheetName?.value },
        responseType: 'blob',
      })
      downloadBlob(resp.data, `H7_模板_${sheetName?.value || 'all'}.xlsx`)
      ElMessage.success('模板导出成功')
    } catch (err: any) {
      ElMessage.error('模板导出失败: ' + (err?.message || ''))
    } finally {
      isExporting.value = false
    }
  }

  /** 导出数据（含已填数据） */
  async function exportData(): Promise<void> {
    isExporting.value = true
    try {
      const resp = await api.get(`/api/workpapers/${wpId.value}/h7/export-data`, {
        params: { sheet: sheetName?.value },
        responseType: 'blob',
      })
      downloadBlob(resp.data, `H7_数据_${sheetName?.value || 'all'}.xlsx`)
      ElMessage.success('数据导出成功')
    } catch (err: any) {
      ElMessage.error('数据导出失败: ' + (err?.message || ''))
    } finally {
      isExporting.value = false
    }
  }

  /** 导入数据 */
  async function importData(file: File): Promise<boolean> {
    isImporting.value = true
    try {
      const formData = new FormData()
      formData.append('file', file)
      if (sheetName?.value) formData.append('sheet', sheetName.value)
      await api.post(`/api/workpapers/${wpId.value}/h7/import-data`, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      ElMessage.success('数据导入成功')
      return true
    } catch (err: any) {
      ElMessage.error('数据导入失败: ' + (err?.message || ''))
      return false
    } finally {
      isImporting.value = false
    }
  }

  return {
    isExporting,
    isImporting,
    exportTemplate,
    exportData,
    importData,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function downloadBlob(blob: Blob, filename: string): void {
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}

export default useH7ImportExport
