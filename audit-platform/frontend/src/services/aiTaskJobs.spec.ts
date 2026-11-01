import { beforeEach, describe, expect, it, vi } from 'vitest'

const mocks = vi.hoisted(() => ({
  get: vi.fn(),
  post: vi.fn(),
  eventHandler: null as ((event: any) => void) | null,
  close: vi.fn(),
}))

vi.mock('@/services/apiProxy', () => ({ api: { get: mocks.get, post: mocks.post } }))
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: (_project: string, _event: string, handler: (event: any) => void) => {
    mocks.eventHandler = handler
    return { close: mocks.close }
  },
}))

import {
  createOrResumeAiTaskJob,
  waitForAiTaskJob,
  type AiTaskJobSnapshot,
} from './aiTaskJobs'

const snapshot = (status: AiTaskJobSnapshot['status'], version = 1): AiTaskJobSnapshot => ({
  job_id: '11111111-1111-4111-8111-111111111111',
  project_id: '22222222-2222-4222-8222-222222222222',
  year: 2025,
  task_kind: 'note_batch_prefill',
  status,
  version,
  progress_total: 1,
  progress_done: status === 'succeeded' ? 1 : 0,
  failed_count: 0,
  cancelled_count: 0,
  cancel_requested: false,
  created_at: null,
  started_at: null,
  finished_at: null,
  updated_at: null,
  items: [],
})

describe('aiTaskJobs', () => {
  beforeEach(() => {
    mocks.get.mockReset()
    mocks.post.mockReset()
    mocks.close.mockReset()
    mocks.eventHandler = null
    localStorage.clear()
  })

  it('响应丢失后重试复用同一幂等键', async () => {
    const payload = { task_kind: 'note_batch_prefill' as const, year: 2025 }
    mocks.post.mockRejectedValueOnce(new Error('network')).mockResolvedValueOnce(snapshot('queued'))
    await expect(createOrResumeAiTaskJob('p1', 'notes', payload)).rejects.toThrow('network')
    await createOrResumeAiTaskJob('p1', 'notes', payload)
    expect(mocks.post).toHaveBeenCalledTimes(2)
    expect(mocks.post.mock.calls[0][1].idempotency_key).toBe(mocks.post.mock.calls[1][1].idempotency_key)
  })

  it('已有运行任务先按 job id 恢复，不重复创建', async () => {
    const payload = { task_kind: 'note_batch_prefill' as const, year: 2025 }
    mocks.post.mockResolvedValueOnce(snapshot('queued'))
    await createOrResumeAiTaskJob('p1', 'notes', payload)
    mocks.get.mockResolvedValueOnce(snapshot('running', 2))
    const resumed = await createOrResumeAiTaskJob('p1', 'notes', payload)
    expect(resumed.status).toBe('running')
    expect(mocks.post).toHaveBeenCalledTimes(1)
    expect(mocks.get).toHaveBeenCalledWith(
      '/api/projects/p1/ai-task-jobs/11111111-1111-4111-8111-111111111111',
      { _silent: true },
    )
  })

  it('SSE 只作唤醒，完成状态仍从 DB snapshot 读取', async () => {
    const initial = snapshot('running')
    const final = snapshot('succeeded', 2)
    mocks.get.mockResolvedValueOnce(final)
    const seen: AiTaskJobSnapshot[] = []
    const waiting = waitForAiTaskJob('p1', initial, (value) => seen.push(value))
    await Promise.resolve()
    mocks.eventHandler?.({ extra: { job_id: initial.job_id } })
    await expect(waiting).resolves.toEqual(final)
    expect(seen.at(-1)?.status).toBe('succeeded')
    expect(mocks.close).toHaveBeenCalledTimes(1)
  })
})
