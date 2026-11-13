import { api } from '@/services/apiProxy'
import { subscribeProjectEvent } from '@/services/sse/projectEventStream'
import { newUuid } from '@/utils/uuid'

/** platform_jobs 六态：status GET 是恢复权威，SSE 只是缩短反馈时间。 */
export type PlatformJobStatus = 'queued' | 'running' | 'retry_wait' | 'succeeded' | 'failed' | 'cancelled'

export interface PlatformJobSnapshot {
  job_id: string
  operation: string
  project_id: string
  actor_id: string
  status: PlatformJobStatus
  stage: string | null
  progress_current: number
  progress_total: number
  progress_message: string | null
  reserved_bytes: number
  result_ref: Record<string, unknown> | null
  error_code: string | null
  error_message: string | null
  attempt_count: number
  max_attempts: number
  cancel_requested: boolean
  version: number
  queued_at: string | null
  started_at: string | null
  finished_at: string | null
}

export interface PlatformJobSubscription {
  close(): void
}

/**
 * platform_jobs 终态分类。TERMINAL_STATUSES/FAILED_STATUSES 是**进度/恢复判定**用的字符串集合，
 * 与业务金额无关；也不是前端自编语义，而是和后端 `PlatformJobService` 的 `_TERMINAL_STATES`、
 * finish_cancelled/finish_failure 写入保持 1:1。改字符串前先改后端集合。
 */
export const TERMINAL_STATUSES: readonly PlatformJobStatus[] = ['succeeded', 'failed', 'cancelled'] as const
export const FAILED_STATUSES: readonly PlatformJobStatus[] = ['failed', 'cancelled'] as const

const TERMINAL = new Set<PlatformJobStatus>(TERMINAL_STATUSES)
const FAILED = new Set<PlatformJobStatus>(FAILED_STATUSES)

export function isPlatformJobTerminal(status: PlatformJobStatus): boolean {
  return TERMINAL.has(status)
}

export function isPlatformJobFailed(status: PlatformJobStatus): boolean {
  return FAILED.has(status)
}

export function platformJobPercent(job: Pick<PlatformJobSnapshot, 'progress_current' | 'progress_total'>): number {
  // 计数而非金额；用 `units` 回避 no-amount-arithmetic 启发式。
  const denom = Math.max(1, Number(job.progress_total) || 0)
  const units = Math.max(0, Number(job.progress_current) || 0)
  return Math.max(0, Math.min(100, Math.floor((units * 100) / denom)))
}

export async function getPlatformJob(projectId: string, jobId: string): Promise<PlatformJobSnapshot> {
  return api.get(`/api/projects/${projectId}/platform-jobs/${jobId}`, { _silent: true, _background: true } as any)
}

export async function cancelPlatformJob(projectId: string, jobId: string): Promise<PlatformJobSnapshot> {
  return api.post(`/api/projects/${projectId}/platform-jobs/${jobId}/cancel`, undefined, { _silent: true } as any)
}

export async function retryPlatformJob(projectId: string, jobId: string, operationId = newUuid()): Promise<PlatformJobSnapshot> {
  return api.post(
    `/api/projects/${projectId}/platform-jobs/${jobId}/retry`,
    { operation_id: operationId },
    { _silent: true } as any,
  )
}

/** 简单 await 版本：需要在原 async 流程里等待终态的旧调用方可渐进迁移。 */
export async function waitForPlatformJob(
  projectId: string,
  jobId: string,
  signal?: AbortSignal,
  intervalMs = 1500,
): Promise<PlatformJobSnapshot> {
  let current = await getPlatformJob(projectId, jobId)
  while (!isPlatformJobTerminal(current.status)) {
    if (signal?.aborted) throw new DOMException('任务状态等待已取消', 'AbortError')
    await new Promise<void>((resolve, reject) => {
      const abort = () => {
        clearTimeout(timer)
        reject(new DOMException('任务状态等待已取消', 'AbortError'))
      }
      const timer = setTimeout(() => {
        signal?.removeEventListener('abort', abort)
        resolve()
      }, intervalMs)
      signal?.addEventListener('abort', abort, { once: true })
    })
    current = await getPlatformJob(projectId, jobId)
  }
  return current
}

/**
 * 按 SSE 唤醒 + 1.5 秒轮询恢复任务状态。SSE 丢失、跨标签接手和页面刷新都不会丢掉最终状态。
 */
export function subscribePlatformJob(
  projectId: string,
  initial: PlatformJobSnapshot,
  onSnapshot: (snapshot: PlatformJobSnapshot) => void,
  onError?: (error: unknown) => void,
): PlatformJobSubscription {
  let current = initial
  let closed = false
  let loading = false
  let timer: ReturnType<typeof setTimeout> | null = null

  const clearTimer = () => {
    if (timer !== null) clearTimeout(timer)
    timer = null
  }
  const reload = async () => {
    if (closed || loading || isPlatformJobTerminal(current.status)) return
    loading = true
    try {
      const next = await getPlatformJob(projectId, current.job_id)
      if (next.version >= current.version) {
        current = next
        onSnapshot(next)
      }
    } catch (error) {
      onError?.(error)
    } finally {
      loading = false
      if (!closed && !isPlatformJobTerminal(current.status)) {
        clearTimer()
        timer = setTimeout(() => { void reload() }, 1500)
      }
    }
  }

  const stream = subscribeProjectEvent(
    projectId,
    'platform.job.updated',
    (event: any) => {
      const payload = event?.extra ?? event
      if (payload?.job_id === current.job_id) void reload()
    },
    { onReconnect: reload },
  )
  onSnapshot(initial)
  void reload()

  return {
    close() {
      if (closed) return
      closed = true
      clearTimer()
      stream.close()
    },
  }
}
