import { api } from '@/services/apiProxy'
import { subscribeProjectEvent } from '@/services/sse/projectEventStream'
import { newUuid } from '@/utils/uuid'

export type AiTaskKind = 'note_batch_prefill' | 'workpaper_batch_review'
export type AiTaskJobStatus =
  | 'queued' | 'running' | 'cancelling'
  | 'succeeded' | 'partial_failed' | 'failed' | 'cancelled'
export type AiTaskItemStatus =
  | 'queued' | 'running' | 'retry_wait' | 'succeeded' | 'failed' | 'cancelled'

export interface AiTaskItem {
  item_id: string
  ordinal: number
  target_type: 'note_section' | 'workpaper'
  target_id: string
  target_key: string | null
  status: AiTaskItemStatus
  generation_id: string
  message_id: string | null
  attempt_count: number
  max_attempts: number
  next_attempt_at: string | null
  baseline_version: string | null
  before_hash: string | null
  started_at: string | null
  finished_at: string | null
  result: Record<string, any> | null
  error_code: string | null
  error_message: string | null
}

export interface AiTaskJobSnapshot {
  job_id: string
  project_id: string
  year: number
  task_kind: AiTaskKind
  status: AiTaskJobStatus
  version: number
  progress_total: number
  progress_done: number
  failed_count: number
  cancelled_count: number
  cancel_requested: boolean
  created_at: string | null
  started_at: string | null
  finished_at: string | null
  updated_at: string | null
  items: AiTaskItem[]
  reused?: boolean
}

export interface AiTaskCreatePayload {
  task_kind: AiTaskKind
  year: number
  doc_filter?: string[]
  wp_code_prefix?: string
}

const TERMINAL = new Set<AiTaskJobStatus>([
  'succeeded', 'partial_failed', 'failed', 'cancelled',
])

interface StoredJobRef {
  requestKey: string
  idempotencyKey: string
  jobId?: string
}

function storageKey(projectId: string, scope: string): string {
  return `gt:ai-task:${projectId}:${scope}`
}

function readStored(projectId: string, scope: string): StoredJobRef | null {
  try {
    const raw = localStorage.getItem(storageKey(projectId, scope))
    return raw ? JSON.parse(raw) as StoredJobRef : null
  } catch {
    return null
  }
}

function writeStored(projectId: string, scope: string, value: StoredJobRef): void {
  try {
    localStorage.setItem(storageKey(projectId, scope), JSON.stringify(value))
  } catch {
    // 隐私模式/配额不足不影响服务端幂等，当前页面仍持有 key。
  }
}

export function isAiTaskTerminal(status: AiTaskJobStatus): boolean {
  return TERMINAL.has(status)
}

export async function getAiTaskJob(projectId: string, jobId: string): Promise<AiTaskJobSnapshot> {
  return api.get(`/api/projects/${projectId}/ai-task-jobs/${jobId}`, { _silent: true } as any)
}

export async function createOrResumeAiTaskJob(
  projectId: string,
  scope: string,
  payload: AiTaskCreatePayload,
): Promise<AiTaskJobSnapshot> {
  const requestKey = JSON.stringify(payload)
  let stored = readStored(projectId, scope)
  if (!stored || stored.requestKey !== requestKey) {
    stored = { requestKey, idempotencyKey: newUuid() }
    writeStored(projectId, scope, stored)
  }

  if (stored.jobId) {
    try {
      const existing = await getAiTaskJob(projectId, stored.jobId)
      if (!isAiTaskTerminal(existing.status)) return existing
      stored = { requestKey, idempotencyKey: newUuid() }
      writeStored(projectId, scope, stored)
    } catch {
      // 任务不存在或旧引用已失效时，以原幂等键重放创建请求。
    }
  }

  const snapshot = await api.post<AiTaskJobSnapshot>(
    `/api/projects/${projectId}/ai-task-jobs`,
    { ...payload, idempotency_key: stored.idempotencyKey },
    { _silent: true } as any,
  )
  writeStored(projectId, scope, { ...stored, jobId: snapshot.job_id })
  return snapshot
}

export async function cancelAiTaskJob(
  projectId: string,
  jobId: string,
): Promise<AiTaskJobSnapshot> {
  return api.post(`/api/projects/${projectId}/ai-task-jobs/${jobId}/cancel`, undefined, { _silent: true } as any)
}

export async function retryAiTaskItem(
  projectId: string,
  jobId: string,
  itemId: string,
): Promise<AiTaskJobSnapshot> {
  return api.post(
    `/api/projects/${projectId}/ai-task-jobs/${jobId}/items/${itemId}/retry`,
    undefined,
    { _silent: true } as any,
  )
}

export async function waitForAiTaskJob(
  projectId: string,
  initial: AiTaskJobSnapshot,
  onSnapshot: (snapshot: AiTaskJobSnapshot) => void,
  signal?: AbortSignal,
): Promise<AiTaskJobSnapshot> {
  let current = initial
  let loading = false
  let wake: (() => void) | null = null

  const reload = async () => {
    if (loading || signal?.aborted || isAiTaskTerminal(current.status)) return
    loading = true
    try {
      const next = await getAiTaskJob(projectId, current.job_id)
      if (next.version >= current.version) {
        current = next
        onSnapshot(next)
      }
    } finally {
      loading = false
      wake?.()
    }
  }
  const subscription = subscribeProjectEvent(
    projectId,
    'ai.task.updated',
    (event: any) => {
      const payload = event?.extra ?? event
      if (payload?.job_id === current.job_id) void reload()
    },
    { onReconnect: reload },
  )
  try {
    onSnapshot(current)
    while (!signal?.aborted && !isAiTaskTerminal(current.status)) {
      await Promise.race([
        new Promise<void>((resolve) => { wake = resolve }),
        new Promise<void>((resolve) => setTimeout(resolve, 1500)),
      ])
      wake = null
      await reload()
    }
    return current
  } finally {
    subscription.close()
  }
}
