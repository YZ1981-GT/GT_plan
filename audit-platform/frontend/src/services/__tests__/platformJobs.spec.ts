import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const state = vi.hoisted(() => ({ get: vi.fn(), post: vi.fn(), subscribe: vi.fn(), close: vi.fn() }))
vi.mock('@/services/apiProxy', () => ({ api: { get: (...args: unknown[]) => state.get(...args), post: (...args: unknown[]) => state.post(...args) } }))
vi.mock('@/services/sse/projectEventStream', () => ({ subscribeProjectEvent: (...args: unknown[]) => state.subscribe(...args) }))
vi.mock('@/utils/uuid', () => ({ newUuid: () => 'retry-operation' }))

import {
  isPlatformJobTerminal,
  platformJobPercent,
  retryPlatformJob,
  subscribePlatformJob,
  waitForPlatformJob,
} from '../platformJobs'

const queued = {
  job_id: 'j1', project_id: 'p1', actor_id: 'u1', operation: 'formula_push', status: 'queued' as const,
  stage: 'authorizing', progress_current: 0, progress_total: 2, progress_message: null,
  reserved_bytes: 0, result_ref: null, error_code: null, error_message: null,
  attempt_count: 1, max_attempts: 3, cancel_requested: false, version: 1,
  queued_at: null, started_at: null, finished_at: null,
}

describe('platformJobs', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    state.get.mockReset()
    state.post.mockReset()
    state.subscribe.mockReset().mockReturnValue({ close: state.close })
    state.close.mockReset()
  })
  afterEach(() => vi.useRealTimers())

  it('终态和百分比按统一六态口径判断', () => {
    expect(isPlatformJobTerminal('queued')).toBe(false)
    expect(isPlatformJobTerminal('retry_wait')).toBe(false)
    expect(isPlatformJobTerminal('succeeded')).toBe(true)
    expect(platformJobPercent({ progress_current: 5, progress_total: 4 })).toBe(100)
    expect(platformJobPercent({ progress_current: -1, progress_total: 0 })).toBe(0)
  })

  it('retry 带客户端 operation id，HTTP 网络重试可复用同一个新任务', async () => {
    state.post.mockResolvedValue({ ...queued, job_id: 'j2' })
    await retryPlatformJob('p1', 'j1')
    expect(state.post).toHaveBeenCalledWith(
      '/api/projects/p1/platform-jobs/j1/retry',
      { operation_id: 'retry-operation' },
      { _silent: true },
    )
  })

  it('waitForPlatformJob 轮询至终态，刷新/断线不依赖 SSE', async () => {
    state.get
      .mockResolvedValueOnce(queued)
      .mockResolvedValueOnce({ ...queued, status: 'succeeded', version: 2, progress_current: 2 })
    const waiting = waitForPlatformJob('p1', 'j1', undefined, 100)
    await vi.advanceTimersByTimeAsync(100)
    await expect(waiting).resolves.toMatchObject({ status: 'succeeded' })
    expect(state.get).toHaveBeenCalledTimes(2)
  })

  it('订阅收到平台 SSE 时立即拉取权威状态，close 停掉轮询', async () => {
    let onEvent!: (event: unknown) => void
    state.subscribe.mockImplementation((_pid: string, _event: string, handler: (event: unknown) => void) => {
      onEvent = handler
      return { close: state.close }
    })
    state.get.mockResolvedValue({ ...queued, status: 'running', version: 2 })
    const seen: any[] = []
    const subscription = subscribePlatformJob('p1', queued, (job) => seen.push(job))
    onEvent({ extra: { job_id: 'j1' } })
    await Promise.resolve()
    await Promise.resolve()
    expect(state.get).toHaveBeenCalled()
    subscription.close()
    expect(state.close).toHaveBeenCalledTimes(1)
  })
})
