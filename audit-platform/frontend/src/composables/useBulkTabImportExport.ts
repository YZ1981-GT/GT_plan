/**
 * useBulkTabImportExport — 项目级底稿批量 Tab 导入导出 composable
 *
 * Spec: .kiro/specs/workpaper-bulk-tab-import-export/
 * Task: 6.4
 * Requirements: 5.1, 5.2, 5.3
 *
 * 职责：
 * - 封装 5 个后端端点（走 http/axios 带 Authorization，不用原生 fetch）：
 *   - POST /api/projects/{project_id}/bulk-tab/export-templates — 导出全部模板 ZIP
 *   - POST /api/projects/{project_id}/bulk-tab/export-data      — 导出全部数据 ZIP
 *   - POST /api/projects/{project_id}/bulk-tab/import            — 上传 ZIP（multipart），返回 ImportReport
 *   - POST /api/projects/{project_id}/bulk-tab/import/rollback   — 回滚
 *   - GET  /api/projects/{project_id}/bulk-tab/progress/{task_id} — SSE 进度
 *
 * - ZIP 下载：responseType: 'blob' + URL.createObjectURL + <a> click
 * - ZIP 上传：FormData with File
 * - SSE 进度：复用 @/utils/sse 的 createSSE（fetch + ReadableStream，Authorization header）
 * - 中文文件名：从 Content-Disposition 解析 RFC5987 编码
 * - loading / error 状态管理
 *
 * 工程铁律：
 * - 必须用 http (axios) 不能用原生 fetch（Authorization header → 401）
 * - SSE 例外：进度订阅用 @/utils/sse createSSE（内部 fetch + Authorization header）
 */
import { ref, computed, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import http from '@/utils/http'
import { createSSE, type SSEConnection } from '@/utils/sse'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 导入报告中每个 sheet 的状态（与后端 bulk_import_service.SheetStatus 对齐） */
export type SheetImportStatus =
  | 'success'
  | 'partial'
  | 'failed'
  | 'missing'
  | 'unlisted'
  | 'blocked_by_status'
  | 'conflict_rejected'
  | 'skipped'

/** 导入报告中单个 sheet 的结果 */
export interface SheetReportItem {
  sheet_code: string
  status: SheetImportStatus
  rows?: number
  warnings?: string[]
  reason?: string
  errors?: string[]
}

/** 快照记录 */
export interface SnapshotEntry {
  wp_id: string
  snapshot_id: string
}

/** 导入报告汇总（后端只回显 count>0 的键，故除已知外均可选） */
export interface ImportReportSummary {
  success?: number
  partial?: number
  failed?: number
  blocked?: number
  missing?: number
  unlisted?: number
  conflict_rejected?: number
  skipped?: number
}

/** 完整导入报告 */
export interface ImportReport {
  import_id: string
  strategy: string
  dry_run: boolean
  snapshots: SnapshotEntry[]
  sheets: SheetReportItem[]
  summary: ImportReportSummary
  /** 失败回滚标记（all-or-nothing 策略触发） */
  rolled_back?: boolean
}

/** 冲突策略 */
export type ConflictStrategy = 'overwrite' | 'fill-empty' | 'reject'

/** 导入选项 */
export interface BulkImportOptions {
  dryRun?: boolean
  strategy?: ConflictStrategy
  /** 循环多选（仅记录，导入范围以 ZIP manifest 为准） */
  cycles?: string[]
}

/** SSE 进度事件数据 */
export interface BulkProgressEvent {
  task_id: string
  current: number
  total: number
  message?: string
  status?: 'running' | 'completed' | 'failed'
  error?: string
}

// ─── API 路径 ────────────────────────────────────────────────────────────────

function buildPaths(projectId: string) {
  const base = `/api/projects/${projectId}/bulk-tab`
  return {
    exportTemplates: `${base}/export-templates`,
    exportData: `${base}/export-data`,
    import: `${base}/import`,
    rollback: `${base}/import/rollback`,
    progress: (taskId: string) => `${base}/progress/${taskId}`,
  }
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 从 Content-Disposition 解析文件名（支持 RFC5987 编码的中文名）
 */
function parseFilename(contentDisposition: string | undefined | null, fallback: string): string {
  if (!contentDisposition) return fallback

  // 优先匹配 filename*=UTF-8''xxx（RFC5987）
  const rfc5987Match = contentDisposition.match(/filename\*=UTF-8''(.+?)(?:;|$)/i)
  if (rfc5987Match?.[1]) {
    try {
      return decodeURIComponent(rfc5987Match[1])
    } catch {
      // 解码失败用 fallback
    }
  }

  // 兜底 filename="xxx"
  const plainMatch = contentDisposition.match(/filename="?(.+?)"?(?:;|$)/)
  if (plainMatch?.[1]) return plainMatch[1]

  return fallback
}

/**
 * 下载 Blob 为文件（URL.createObjectURL + <a> click）
 */
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

/**
 * 从 axios 错误提取 detail 信息
 */
function extractError(err: unknown, fallback: string): string {
  const e = err as {
    response?: { data?: { detail?: unknown; message?: unknown } }
    message?: string
  }
  const detail = e?.response?.data?.detail ?? e?.response?.data?.message
  if (typeof detail === 'string') return detail
  if (e?.message) return e.message
  return fallback
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useBulkTabImportExport(projectId: Ref<string>) {
  const loading = ref(false)
  const error = ref<string | null>(null)
  const downloadProgress = ref(0)
  let sseConnection: SSEConnection | null = null

  /** 当前是否正在执行操作 */
  const busy = computed(() => loading.value)

  // ─── 导出模板 ZIP ───────────────────────────────────────────────────────

  /**
   * 导出全部模板 ZIP
   * POST /api/projects/{project_id}/bulk-tab/export-templates
   * @param cycles 可选循环筛选（如 ['D'] 或 ['D','K']），空则导出全部
   */
  async function exportTemplates(cycles?: string[]): Promise<void> {
    loading.value = true
    error.value = null
    downloadProgress.value = 0
    try {
      const paths = buildPaths(projectId.value)
      const response = await http.post(
        paths.exportTemplates,
        { cycles: cycles || null },
        {
          responseType: 'blob',
          timeout: 300000,  // 5 min timeout for large exports
          onDownloadProgress: (evt: any) => {
            if (evt.total) {
              downloadProgress.value = Math.round((evt.loaded / evt.total) * 100)
            }
          },
        },
      )
      const contentDisposition = response.headers?.['content-disposition'] as string | undefined
      const filename = parseFilename(contentDisposition, '底稿批量模板.zip')
      downloadBlob(response.data as Blob, filename)
      ElMessage.success('模板 ZIP 已导出')
    } catch (e: unknown) {
      const msg = extractError(e, '导出模板失败')
      error.value = msg
      ElMessage.error(msg)
      throw e
    } finally {
      loading.value = false
      downloadProgress.value = 0
    }
  }

  // ─── 导出数据 ZIP ──────────────────────────────────────────────────────

  /**
   * 导出全部数据 ZIP
   * POST /api/projects/{project_id}/bulk-tab/export-data
   * @param cycles 可选循环筛选
   * @param onlyWithData 仅导出有数据的 Tab（跳过空表）
   * @param incremental 增量导出（跳过未变更 Tab）
   * @param password ZIP 密码保护（可选）
   */
  async function exportData(
    cycles?: string[],
    onlyWithData?: boolean,
    incremental?: boolean,
    password?: string,
  ): Promise<void> {
    loading.value = true
    error.value = null
    downloadProgress.value = 0
    try {
      const paths = buildPaths(projectId.value)
      const response = await http.post(
        paths.exportData,
        {
          cycles: cycles || null,
          only_with_data: onlyWithData ?? false,
          incremental: incremental ?? false,
          password: password || null,
        },
        {
          responseType: 'blob',
          timeout: 300000,  // 5 min timeout for large exports
          onDownloadProgress: (evt: any) => {
            if (evt.total) {
              downloadProgress.value = Math.round((evt.loaded / evt.total) * 100)
            }
          },
        },
      )
      const contentDisposition = response.headers?.['content-disposition'] as string | undefined
      const filename = parseFilename(contentDisposition, '底稿批量数据.zip')
      downloadBlob(response.data as Blob, filename)
      ElMessage.success('数据 ZIP 已导出')
    } catch (e: unknown) {
      const msg = extractError(e, '导出数据失败')
      error.value = msg
      ElMessage.error(msg)
      throw e
    } finally {
      loading.value = false
      downloadProgress.value = 0
    }
  }

  // ─── 导入 ZIP（含 DryRun）──────────────────────────────────────────────

  /**
   * 导入 ZIP（正式或 DryRun 预检）
   * POST /api/projects/{project_id}/bulk-tab/import (multipart/form-data)
   * @param file 上传的 ZIP 文件
   * @param options dryRun / strategy
   */
  async function importData(
    file: File,
    options: BulkImportOptions = {},
  ): Promise<ImportReport | null> {
    loading.value = true
    error.value = null
    try {
      const paths = buildPaths(projectId.value)
      const formData = new FormData()
      formData.append('file', file)
      // 后端用 FastAPI Form(...) 读取，必须放 multipart 表单体（放 query 无法命中）
      formData.append('dry_run', String(options.dryRun ?? false))
      formData.append('strategy', options.strategy ?? 'overwrite')
      if (options.cycles && options.cycles.length > 0) {
        formData.append('cycles', JSON.stringify(options.cycles))
      }

      const response = await http.post(paths.import, formData, {
        headers: { 'Content-Type': 'multipart/form-data' },
      })
      const data = (response.data?.data ?? response.data) as ImportReport

      if (options.dryRun) {
        ElMessage.info('预检完成，请查看报告')
      } else {
        const s = data.summary
        ElMessage.success(
          `导入完成：成功 ${s.success ?? 0}，部分 ${s.partial ?? 0}，失败 ${s.failed ?? 0}`,
        )
      }
      return data
    } catch (e: unknown) {
      const msg = extractError(e, '导入失败')
      error.value = msg
      ElMessage.error(msg)
      return null
    } finally {
      loading.value = false
    }
  }

  // ─── 回滚 ─────────────────────────────────────────────────────────────

  /**
   * 回滚导入
   * POST /api/projects/{project_id}/bulk-tab/import/rollback
   * @param importId 导入 ID
   * @param snapshots 快照列表（来自 ImportReport.snapshots）
   */
  async function rollback(importId: string, snapshots: SnapshotEntry[]): Promise<boolean> {
    loading.value = true
    error.value = null
    try {
      const paths = buildPaths(projectId.value)
      await http.post(paths.rollback, {
        import_id: importId,
        snapshots,
      })
      ElMessage.success('回滚成功，数据已恢复到导入前状态')
      return true
    } catch (e: unknown) {
      const msg = extractError(e, '回滚失败')
      error.value = msg
      ElMessage.error(msg)
      return false
    } finally {
      loading.value = false
    }
  }

  // ─── SSE 进度订阅 ─────────────────────────────────────────────────────

  /**
   * 订阅异步任务进度（SSE）
   * GET /api/projects/{project_id}/bulk-tab/progress/{task_id}
   *
   * 使用 @/utils/sse createSSE（fetch + ReadableStream + Authorization header）
   * @param taskId 异步任务 ID
   * @param onProgress 进度回调
   * @returns cleanup 函数，组件卸载时调用
   */
  function subscribeProgress(
    taskId: string,
    onProgress: (data: BulkProgressEvent) => void,
  ): () => void {
    // 关闭已有连接
    if (sseConnection) {
      sseConnection.close()
      sseConnection = null
    }

    const paths = buildPaths(projectId.value)
    const sseUrl = paths.progress(taskId)

    sseConnection = createSSE(sseUrl, { maxRetries: 3, retryInterval: 2000 })

    sseConnection.onMessage((data: unknown) => {
      if (data && typeof data === 'object') {
        onProgress(data as BulkProgressEvent)
      }
    })

    sseConnection.onError(() => {
      // SSE 断开，createSSE 内部有自动重连逻辑
    })

    // 返回 cleanup 函数
    return () => {
      if (sseConnection) {
        sseConnection.close()
        sseConnection = null
      }
    }
  }

  /**
   * 关闭 SSE 连接（组件卸载时调用）
   */
  function closeProgress(): void {
    if (sseConnection) {
      sseConnection.close()
      sseConnection = null
    }
  }

  return {
    // 状态
    loading,
    error,
    busy,
    downloadProgress,
    // 导出
    exportTemplates,
    exportData,
    // 导入
    importData,
    // 回滚
    rollback,
    // SSE 进度
    subscribeProgress,
    closeProgress,
  }
}

export default useBulkTabImportExport
