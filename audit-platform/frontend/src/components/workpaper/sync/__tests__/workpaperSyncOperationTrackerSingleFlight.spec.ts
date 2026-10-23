// spec: writeback-followup-issue-closure · R6（前端轮询不得在后端堆积）
//
// 原状：`setInterval` 固定间隔不管上一轮回没回来，后端一慢请求就叠起来（http 层的同 URL GET
// 去重只取消浏览器这头，后端照样每个都算完）；失败时 `utils/http` 对 5xx 自动重发两次，
// 一次轮询放大成三次。判据：
// 1. 单飞：任一时刻最多一个读在飞；飞行中的定时轮询 / 事件补读合并成读完后的一次补读；
// 2. 连续失败按 2 的幂退避、封顶 5 s，成功即回到基准间隔；窗口超时照常生效；
// 3. operation 读取带 `_silent`（不弹全局提示、不走 5xx 自动重发）。
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args), post: vi.fn() },
}))
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: () => ({ close: () => {} }),
}))

import { getOperation } from '../workpaperSyncApi'
import type { WorkpaperSyncOperationSnapshot } from '../workpaperSyncDto'
import { POLL_BACKOFF_CAP_MS, WorkpaperSyncOperationTracker } from '../workpaperSyncOperationTracker'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`
const SCOPE = { projectId: UUID(101), wpId: UUID(102), entryId: 'xlsx/gt-d2-accounts-receivable' } as const

function snapshot(state = 'accepted', resultRevision: number | null = null): WorkpaperSyncOperationSnapshot {
  return {
    requestedOperationId: UUID(30), canonicalOperationId: UUID(30), followedDuplicate: false,
    state, shape: 'pre_correlation', applicationId: null, duplicateOfOperationId: null,
    errorCode: null, errorStage: null, acceptedAt: null, applicationBoundAt: null,
    operationFinishedAt: null, resultRevision, conflictCount: null, logicalResultCode: null,
    definitionBundleId: null, definitionBundleSha256: null, authorityModelDefinitionSha256: null,
    durableAt: null, finishedAt: null, terminal: false,
  } as WorkpaperSyncOperationSnapshot
}

function deferred<T>() {
  let resolve!: (value: T) => void
  let reject!: (error: unknown) => void
  const promise = new Promise<T>((res, rej) => {
    resolve = res
    reject = rej
  })
  return { promise, resolve, reject }
}

function tracker(poll: (...args: unknown[]) => Promise<WorkpaperSyncOperationSnapshot>, extra: Record<string, unknown> = {}) {
  let onEvent: (payload: unknown) => void = () => {}
  const t = new WorkpaperSyncOperationTracker({
    scope: SCOPE,
    operationId: UUID(30),
    onSnapshot: () => {},
    poll: poll as never,
    subscribe: (context) => {
      onEvent = context.onEvent
      return { close: () => {} }
    },
    ...extra,
  })
  return { t, fire: (payload: unknown) => onEvent(payload) }
}

beforeEach(() => {
  vi.useFakeTimers()
  mockGet.mockReset()
})

afterEach(() => {
  vi.useRealTimers()
})

describe('单飞', () => {
  it('上一轮没回来时定时轮询不再发请求；回来后只补读一次，再按间隔继续', async () => {
    const first = deferred<WorkpaperSyncOperationSnapshot>()
    const poll = vi.fn()
    poll.mockImplementationOnce(() => first.promise)
    poll.mockImplementation(async () => snapshot())
    const { t } = tracker(poll, { pollIntervalMs: 500 })
    const started = t.start()
    await vi.advanceTimersByTimeAsync(5200)
    expect(poll, '后端慢的 5 秒里只能有一个请求在飞').toHaveBeenCalledTimes(1)
    first.resolve(snapshot())
    await started
    expect(poll, '飞行期间到期的轮询合并成读完后的一次补读').toHaveBeenCalledTimes(2)
    // 下一轮从「读回来」起算 500 ms（5700），不是按固定节拍（5500）
    await vi.advanceTimersByTimeAsync(499)
    expect(poll).toHaveBeenCalledTimes(2)
    await vi.advanceTimersByTimeAsync(1)
    expect(poll).toHaveBeenCalledTimes(3)
    t.stop()
  })

  it('飞行期间到达的多条内容事件只合并成一次补读', async () => {
    const first = deferred<WorkpaperSyncOperationSnapshot>()
    const poll = vi.fn()
    poll.mockImplementationOnce(() => first.promise)
    poll.mockImplementation(async () => snapshot('applied', 13))
    const { t, fire } = tracker(poll)
    const started = t.start()
    for (const revision of [11, 12, 13]) fire({ wp_id: SCOPE.wpId, revision })
    expect(poll).toHaveBeenCalledTimes(1)
    first.resolve(snapshot())
    await started
    await vi.advanceTimersByTimeAsync(0)
    expect(poll).toHaveBeenCalledTimes(2)
    t.stop()
  })
})

describe('失败退避', () => {
  it('连续失败按 2 的幂退避、封顶 5 s；成功后回到基准间隔', async () => {
    const at: number[] = []
    const t0 = Date.now()
    let calls = 0
    const poll = vi.fn(async () => {
      at.push(Date.now() - t0)
      calls += 1
      if (calls <= 4) throw new Error('500')
      return snapshot('accepted', calls)
    })
    const { t } = tracker(poll, { pollIntervalMs: 500 })
    await t.start().catch(() => {})
    await vi.advanceTimersByTimeAsync(13_000)
    t.stop()
    // 0 初读失败；500 首个定时轮询失败（失败 2 次）⇒ 2000；再失败 ⇒ 4000；再失败 ⇒ 封顶 5000；
    // 11500 成功 ⇒ 间隔回到 500
    expect(at.slice(0, 7)).toEqual([0, 500, 2500, 6500, 11_500, 12_000, 12_500])
    expect(POLL_BACKOFF_CAP_MS).toBe(5000)
  })

  it('退避中照常到点超时，超时后不再发请求', async () => {
    const onDeadline = vi.fn()
    const poll = vi.fn(async () => {
      throw new Error('500')
    })
    const { t } = tracker(poll, { pollIntervalMs: 500, deadlineMs: 3000, onDeadline })
    await t.start().catch(() => {})
    await vi.advanceTimersByTimeAsync(20_000)
    expect(onDeadline).toHaveBeenCalledTimes(1)
    const calls = poll.mock.calls.length
    await vi.advanceTimersByTimeAsync(20_000)
    expect(poll.mock.calls.length).toBe(calls)
  })

  it('stop() 取消排着的下一轮（含退避中的）', async () => {
    const poll = vi.fn(async () => {
      throw new Error('500')
    })
    const { t } = tracker(poll, { pollIntervalMs: 500 })
    await t.start().catch(() => {})
    await vi.advanceTimersByTimeAsync(600)
    const calls = poll.mock.calls.length
    t.stop()
    await vi.advanceTimersByTimeAsync(30_000)
    expect(poll.mock.calls.length).toBe(calls)
  })
})

describe('operation 读取由调用方自管失败', () => {
  it('带 _silent：不弹全局提示、不走 5xx 自动重发', async () => {
    mockGet.mockResolvedValue({
      data: {
        requested_operation_id: UUID(30), canonical_operation_id: UUID(30), followed_duplicate: false,
        state: 'accepted', application_id: null, duplicate_of_operation_id: null, error_code: null,
        error_stage: null, accepted_at: null, application_bound_at: null, operation_finished_at: null,
        result_revision: null, conflict_count: null, logical_result_code: null, definition_bundle_id: null,
        definition_bundle_sha256: null, authority_model_definition_sha256: null, durable_at: null,
        finished_at: null,
      },
    })
    await getOperation(SCOPE, UUID(30))
    const config = mockGet.mock.calls[0][1] as { _silent?: boolean }
    expect(config._silent).toBe(true)
  })
})
