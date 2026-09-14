/**
 * useWpExportImport — 底稿导入导出 composable
 *
 * 封装导出/导入/批量导出/模板复制/版本历史全部 API 调用与状态管理。
 * 下载统一用 downloadFile（axios blob + Bearer header），禁止 window.open。
 *
 * Requirements: 1.1, 2.1, 2.6, 3.3, 4.3, 4.4, 5.1, 5.6, 6.1, 6.2, 7.1, 7.4, 7.5
 */

import { ref } from 'vue'
import http, { downloadFile } from '@/utils/http'
import { api } from '@/services/apiProxy'

// ─── API 路径 ────────────────────────────────────────────────────────────────

const wpExportPaths = {
  exportWithMetadata: (pid: string, wpId: string) =>
    `/api/projects/${pid}/workpapers/${wpId}/export-with-metadata`,
  batchExportEnhanced: (pid: string) =>
    `/api/projects/${pid}/workpapers/batch-export-enhanced`,
  exportHistory: (pid: string, wpId: string) =>
    `/api/projects/${pid}/workpapers/${wpId}/export-history`,
  importValidate: (pid: string, wpId: string) =>
    `/api/projects/${pid}/workpapers/${wpId}/import-validate`,
  importEnhanced: (pid: string) =>
    `/api/projects/${pid}/workpapers/import-enhanced`,
  importResolve: (pid: string) =>
    `/api/projects/${pid}/workpapers/import/resolve`,
  versions: (pid: string, wpId: string) =>
    `/api/projects/${pid}/workpapers/${wpId}/versions`,
  templateCopy: (pid: string) =>
    `/api/projects/${pid}/workpapers/template-copy`,
}

// ─── 类型定义 ────────────────────────────────────────────────────────────────

export interface ValidationItem {
  level: 'passed' | 'warning' | 'error'
  location: string
  message: string
  field?: string
}

export interface ValidationReport {
  overall: 'passed' | 'warning' | 'error'
  items: ValidationItem[]
  passed_count: number
  warning_count: number
  error_count: number
}

export interface ConflictResult {
  has_conflict: boolean
  conflict_type?: string
  server_version: number
  imported_version: number
  last_modifier?: string
  last_modified_at?: string
  is_substantive: boolean
}

export interface ImportResult {
  status: string
  wp_id: string
  new_version?: number
  validation_report?: ValidationReport
  conflict_result?: ConflictResult
}

export interface VersionArchiveItem {
  id: string
  working_paper_id: string
  project_id: string
  version_no: number
  source: string
  content_hash?: string
  file_size_bytes?: number
  archive_path?: string
  file_retained: boolean
  created_by?: string
  created_at?: string
}

export interface ExportHistoryItem {
  id: string
  working_paper_id: string
  project_id: string
  file_version: number
  snapshot_hash: string
  exported_by?: string
  exported_at?: string
  file_format: string
  file_size_bytes?: number
  metadata_bundle?: Record<string, any>
}

export interface CopyResult {
  source_wp_code: string
  target_wp_id?: string
  status: string
  message?: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useWpExportImport() {
  const loading = ref(false)
  const error = ref<string | null>(null)

  /**
   * 导出单份底稿（带元数据）
   * 使用 downloadFile（axios blob + Bearer header）
   */
  async function exportWithMetadata(projectId: string, wpId: string) {
    loading.value = true
    error.value = null
    try {
      await downloadFile(wpExportPaths.exportWithMetadata(projectId, wpId), {
        method: 'post',
      })
    } catch (e: any) {
      error.value = e?.message || '导出失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 批量增强导出（ZIP）
   */
  async function batchExportEnhanced(
    projectId: string,
    auditCycles: string[],
    statusFilter?: string[],
  ) {
    loading.value = true
    error.value = null
    try {
      await downloadFile(wpExportPaths.batchExportEnhanced(projectId), {
        method: 'post',
        data: {
          audit_cycles: auditCycles,
          status_filter: statusFilter || null,
        },
        fileName: '底稿批量导出.zip',
      })
    } catch (e: any) {
      error.value = e?.message || '批量导出失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 增强导入（元数据+校验+冲突检测）
   */
  async function importEnhanced(
    projectId: string,
    file: File,
    forceOverwrite = false,
  ): Promise<ImportResult> {
    loading.value = true
    error.value = null
    try {
      const formData = new FormData()
      formData.append('file', file)
      const url = `${wpExportPaths.importEnhanced(projectId)}?force_overwrite=${forceOverwrite}`
      const { data } = await http.post(url, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      return data as ImportResult
    } catch (e: any) {
      // 409 冲突 / 422 校验失败 都在 detail 里
      if (e?.response?.status === 409 || e?.response?.status === 422) {
        const detail = e.response.data?.detail || e.response.data
        return detail as ImportResult
      }
      error.value = e?.message || '导入失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 仅校验导入文件
   */
  async function importValidate(
    projectId: string,
    wpId: string,
    file: File,
  ): Promise<ValidationReport> {
    loading.value = true
    error.value = null
    try {
      const formData = new FormData()
      formData.append('file', file)
      const { data } = await http.post(
        wpExportPaths.importValidate(projectId, wpId),
        formData,
        { headers: { 'Content-Type': 'multipart/form-data' } },
      )
      return data as ValidationReport
    } catch (e: any) {
      error.value = e?.message || '校验失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 冲突解决
   */
  async function importResolve(
    projectId: string,
    wpId: string,
    resolution: 'force_overwrite' | 'parallel_version' | 'cancel',
    fileContentB64?: string,
    filename?: string,
  ): Promise<ImportResult> {
    loading.value = true
    error.value = null
    try {
      const result = await api.post<ImportResult>(
        wpExportPaths.importResolve(projectId),
        {
          wp_id: wpId,
          resolution,
          file_content_b64: fileContentB64 || null,
          filename: filename || null,
        },
      )
      return result
    } catch (e: any) {
      error.value = e?.message || '冲突解决失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 模板复制
   */
  async function templateCopy(
    projectId: string,
    params: {
      source_wp_id?: string
      source_project_id?: string
      audit_cycle?: string
      overwrite?: boolean
    },
  ): Promise<CopyResult | CopyResult[]> {
    loading.value = true
    error.value = null
    try {
      const result = await api.post<CopyResult | CopyResult[]>(
        wpExportPaths.templateCopy(projectId),
        params,
      )
      return result
    } catch (e: any) {
      error.value = e?.message || '模板复制失败'
      throw e
    } finally {
      loading.value = false
    }
  }

  /**
   * 获取导出历史
   */
  async function getExportHistory(
    projectId: string,
    wpId: string,
  ): Promise<ExportHistoryItem[]> {
    return api.get<ExportHistoryItem[]>(
      wpExportPaths.exportHistory(projectId, wpId),
    )
  }

  /**
   * 获取版本历史
   */
  async function getVersionHistory(
    projectId: string,
    wpId: string,
  ): Promise<VersionArchiveItem[]> {
    return api.get<VersionArchiveItem[]>(
      wpExportPaths.versions(projectId, wpId),
    )
  }

  return {
    loading,
    error,
    exportWithMetadata,
    batchExportEnhanced,
    importEnhanced,
    importValidate,
    importResolve,
    templateCopy,
    getExportHistory,
    getVersionHistory,
  }
}
