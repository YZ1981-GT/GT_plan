/**
 * useBulkTabImportExport — 项目级底稿批量 Tab 导入导出 composable
 *
 * 封装与后端 bulk-tab 端点（wp_bulk_router.py）的交互：
 * - POST /api/projects/{projectId}/bulk-tab/export-templates → ZIP 下载
 * - POST /api/projects/{projectId}/bulk-tab/export-data → ZIP 下载
 * - POST /api/projects/{projectId}/bulk-tab/import → multipart ZIP 上传
 *
 * Requirements: 5.1, 5.2, 5.3
 *
 * NOTE: 本文件由 Task 6.1 创建桩结构，Task 6.4 完整实现 API 调用。
 */
import { ref } from 'vue'
import type { ConflictStrategy } from './WpBulkDialog.vue'

export interface ImportReportSheet {
  sheet_code: string
  status: 'success' | 'partial' | 'failed' | 'missing' | 'unlisted' | 'blocked_by_status' | 'conflict_rejected'
  rows?: number
  warnings?: string[]
  reason?: string
}

export interface ImportReport {
  import_id: string
  strategy: ConflictStrategy
  dry_run: boolean
  snapshots: Array<{ wp_id: string; snapshot_id: string }>
  sheets: ImportReportSheet[]
  summary: {
    success: number
    partial: number
    failed: number
    blocked: number
    missing: number
  }
}

export function useBulkTabImportExport() {
  const loading = ref(false)

  /**
   * 导出全部模板 ZIP
   */
  async function exportTemplates(projectId: string, cycles: string[]): Promise<void> {
    loading.value = true
    try {
      const { default: http } = await import('@/utils/http')
      const res = await http.post(
        `/api/projects/${projectId}/bulk-tab/export-templates`,
        { cycles },
        { responseType: 'blob' },
      )
      downloadBlob(res.data, `bulk-templates-${cycles.join('')}.zip`)
    } finally {
      loading.value = false
    }
  }

  /**
   * 导出全部数据 ZIP
   */
  async function exportData(
    projectId: string,
    cycles: string[],
    onlyWithData: boolean,
  ): Promise<void> {
    loading.value = true
    try {
      const { default: http } = await import('@/utils/http')
      const res = await http.post(
        `/api/projects/${projectId}/bulk-tab/export-data`,
        { cycles, only_with_data: onlyWithData },
        { responseType: 'blob' },
      )
      downloadBlob(res.data, `bulk-data-${cycles.join('')}.zip`)
    } finally {
      loading.value = false
    }
  }

  /**
   * 导入全部数据（multipart ZIP）
   */
  async function importData(
    projectId: string,
    file: File,
    cycles: string[],
    strategy: ConflictStrategy,
    dryRun: boolean,
  ): Promise<ImportReport> {
    loading.value = true
    try {
      const { default: http } = await import('@/utils/http')
      const formData = new FormData()
      formData.append('file', file)
      formData.append('cycles', JSON.stringify(cycles))
      formData.append('strategy', strategy)
      formData.append('dry_run', String(dryRun))

      const res = await http.post(
        `/api/projects/${projectId}/bulk-tab/import`,
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      // ResponseWrapperMiddleware 包装: { code, message, data }
      return res.data?.data ?? res.data
    } finally {
      loading.value = false
    }
  }

  return {
    exportTemplates,
    exportData,
    importData,
    loading,
  }
}

// ─── 辅助 ───

function downloadBlob(data: Blob | ArrayBuffer, filename: string) {
  const blob = data instanceof Blob ? data : new Blob([data])
  const url = URL.createObjectURL(blob)
  const a = document.createElement('a')
  a.href = url
  a.download = filename
  document.body.appendChild(a)
  a.click()
  document.body.removeChild(a)
  URL.revokeObjectURL(url)
}
