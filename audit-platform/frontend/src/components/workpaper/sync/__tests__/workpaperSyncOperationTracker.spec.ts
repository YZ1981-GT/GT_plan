// spec: workpaper-html-onlyoffice-bidirectional-writeback-closure · Wave 3 Task 31
//
// SSE 优先 / 轮询恢复 / 按 operation+revision 去重的**行为侧**判据。
//
// Validates: Requirements 4.2, 11.9, 11.11
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockSubscribe = vi.fn()
vi.mock('@/services/sse/projectEventStream', () => ({
  subscribeProjectEvent: (...args: unknown[]) => mockSubscribe(...args),
}))

import {
  WORKPAPER_CONTENT_UPDATED_EVENT,
  WorkpaperSyncOperationTracker,
  contentUpdateDedupeKey,
  operationSnapshotDedupeKey,
} from '../workpaperSyncOperationTracker'
import type { WorkpaperSyncOperationSnapshot } from '../workpaperSyncDto'

const UUID = (n: number) => `00000000-0000-0000-0000-${String(n).padStart(12, '0')}`

const SCOPE = {
  projectId: UUID(101),
  wpId: UUID(102),
  entryId: 'xlsx/d4/analysis/d4-tab-customer-price',
} as const

function snapshot(over: Partial<WorkpaperSyncOperationSnapshot> = {}): WorkpaperSyncOperationSnapshot {
  return {
    requestedOperationId: UUID(30),
    canonicalOperationId: UUID(30),
    followedDuplicate: false,
    state: 'accepted',
    shape: 'pre_correlation',
    applicationId: null,
    duplicateOfOperationId: null,
    errorCode: null,
    errorStage: null,
    acceptedAt: null,
    applicationBoundAt: null,
    operationFinishedAt: null,
    resultRevision: null,
    conflictCount: null,
    logicalResultCode: null,
    definitionBundleId: null,
    definitionBundleSha256: null,
    authorityModelDefinitionSha256: null,
    durableAt: null,
    finishedAt: null,
    terminal: false,
    ...over,
  }
}

interface Harness {
  tracker: WorkpaperSyncOperationTracker
  delivered: WorkpaperSyncOperationSnapshot[]
  poll: ReturnType<typeof vi.fn>
  close: ReturnType<typeof vi.fn>
  fire: (payload: unknown) => void
  reconnect: () => void
  degrade: () => void
}

function harness(
  queue: WorkpaperSyncOperationSnapshot[] = [snapshot()],
  options: { injectSubscribe?: boolean } = { injectSubscribe: true },
): Harness {
  const delivered: WorkpaperSyncOperationSnapshot[] = []
  const poll = vi.fn(async () => queue[Math.min(poll.mock.calls.length, queue.length - 1)])
  const close = vi.fn()
  let onEvent: (payload: unknown) => void = () => {}
  let onReconnect: () => void = () => {}
  let onDegraded: () => void = () => {}
  const tracker = new WorkpaperSyncOperationTracker({
    scope: SCOPE,
    operationId: UUID(30),
    onSnapshot: (snap) => delivered.push(snap),
    poll: poll as never,
    degradedPollIntervalMs: 1000,
    ...(options.injectSubscribe
      ? {
          subscribe: (context) => {
            onEvent = context.onEvent
            onReconnect = context.onReconnect
            onDegraded = context.onDegraded
            return { close }
          },
        }
      : {}),
  })
  return {
    tracker,
    delivered,
    poll,
    close,
    fire: (payload) => onEvent(payload),
    reconnect: () => onReconnect(),
    degrade: () => onDegraded(),
  }
}

beforeEach(() => {
  mockSubscribe.mockReset()
  mockSubscribe.mockReturnValue({ close: vi.fn() })
})

afterEach(() => {
  vi.useRealTimers()
})

// ═══════════════════════════════════════════════════════════════════════════
// A. 去重键
// ═══════════════════════════════════════════════════════════════════════════

describe('去重键', () => {
  it('content.updated 按 wp_id + revision（AC 11.9），不含 operation', () => {
    const key = contentUpdateDedupeKey({
      wp_id: UUID(102),
      revision: 12,
      operation_id: UUID(30),
    })
    expect(key).toBe(`${UUID(102)}|12`)
    expect(key).not.toContain(UUID(30))
  })

  it('缺 wp_id 或 revision 的事件无法去重 ⇒ 返回 null 而不是编一个键', () => {
    expect(contentUpdateDedupeKey({ revision: 12 })).toBeNull()
    expect(contentUpdateDedupeKey({ wp_id: UUID(102) })).toBeNull()
    expect(contentUpdateDedupeKey(null)).toBeNull()
  })

  it('operation 去重键含 canonical id / state / result revision 三段', () => {
    const base = snapshot()
    expect(operationSnapshotDedupeKey(base)).toBe(`${UUID(30)}|accepted|-`)
    expect(
      operationSnapshotDedupeKey(snapshot({ state: 'applied', resultRevision: 13 })),
    ).toBe(`${UUID(30)}|applied|13`)
  })

  it('duplicate 跟随 primary 后按 canonical id 去重（不是 requested id）', () => {
    const a = snapshot({ requestedOperationId: UUID(31), canonicalOperationId: UUID(30) })
    const b = snapshot({ requestedOperationId: UUID(32), canonicalOperationId: UUID(30) })
    expect(operationSnapshotDedupeKey(a)).toBe(operationSnapshotDedupeKey(b))
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// B. 去重行为
// ═══════════════════════════════════════════════════════════════════════════

describe('按 operation / revision 去重', () => {
  it('同一事实重复投递只通知一次', async () => {
    const h = harness()
    await h.tracker.start()
    expect(h.delivered).toHaveLength(1)
    expect(h.tracker.deliver(snapshot()).accepted).toBe(false)
    expect(h.delivered).toHaveLength(1)
  })

  it('状态推进必须通知（不能被 operation 级去重吞掉）', async () => {
    const h = harness()
    await h.tracker.start()
    expect(h.tracker.deliver(snapshot({ state: 'application_bound' })).accepted).toBe(true)
    expect(h.delivered.map((s) => s.state)).toEqual(['accepted', 'application_bound'])
  })

  it('同 state 但 revision 推进也必须通知', async () => {
    const h = harness()
    await h.tracker.start()
    h.tracker.deliver(snapshot({ state: 'applied', resultRevision: 12 }))
    const second = h.tracker.deliver(snapshot({ state: 'applied', resultRevision: 13 }))
    expect(second.accepted).toBe(true)
    expect(h.delivered.map((s) => s.resultRevision)).toEqual([null, 12, 13])
  })

  it('同一个 content.updated 事件重复到达只补读一次', async () => {
    const h = harness()
    await h.tracker.start()
    const pollsAfterStart = h.poll.mock.calls.length
    const event = { wp_id: UUID(102), revision: 12 }
    expect(h.tracker.handleContentUpdate(event).accepted).toBe(true)
    expect(h.tracker.handleContentUpdate(event).accepted).toBe(false)
    await Promise.resolve()
    await Promise.resolve()
    expect(h.poll.mock.calls.length).toBe(pollsAfterStart + 1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// C. SSE 优先、轮询恢复
// ═══════════════════════════════════════════════════════════════════════════

describe('SSE 优先、轮询只用于恢复', () => {
  it('SSE 健康时只读一次，之后不轮询', async () => {
    vi.useFakeTimers()
    const h = harness()
    await h.tracker.start()
    expect(h.poll).toHaveBeenCalledTimes(1)
    vi.advanceTimersByTime(60_000)
    expect(h.poll).toHaveBeenCalledTimes(1)
    expect(h.tracker.degraded).toBe(false)
    h.tracker.stop()
  })

  it('断线重连后补读一次（错过的事件靠这次补齐）', async () => {
    const h = harness()
    await h.tracker.start()
    h.reconnect()
    await Promise.resolve()
    await Promise.resolve()
    expect(h.poll).toHaveBeenCalledTimes(2)
    expect(h.tracker.degraded).toBe(false)
  })

  it('SSE 降级后才起轮询，且 stop() 停掉它', async () => {
    vi.useFakeTimers()
    const h = harness()
    await h.tracker.start()
    expect(h.poll).toHaveBeenCalledTimes(1)
    h.degrade()
    expect(h.tracker.degraded).toBe(true)
    vi.advanceTimersByTime(3000)
    expect(h.poll.mock.calls.length).toBeGreaterThanOrEqual(4)
    const before = h.poll.mock.calls.length
    h.tracker.stop()
    vi.advanceTimersByTime(10_000)
    expect(h.poll.mock.calls.length).toBe(before)
  })

  it('stop() 之后 refresh() 不再发请求', async () => {
    const h = harness()
    await h.tracker.start()
    h.tracker.stop()
    await h.tracker.refresh()
    expect(h.poll).toHaveBeenCalledTimes(1)
    expect(h.close).toHaveBeenCalledTimes(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════
// D. 默认 subscribe 真接项目事件总线
// ═══════════════════════════════════════════════════════════════════════════

describe('默认 subscribe 接的是真实项目事件流', () => {
  it('用 projectId + workpaper.content.updated 订阅共享连接', async () => {
    const poll = vi.fn(async () => snapshot())
    const tracker = new WorkpaperSyncOperationTracker({
      scope: SCOPE,
      operationId: UUID(30),
      onSnapshot: () => {},
      poll: poll as never,
    })
    await tracker.start()
    expect(mockSubscribe).toHaveBeenCalledTimes(1)
    const [projectId, eventName, handler, options] = mockSubscribe.mock.calls[0]
    expect(projectId).toBe(SCOPE.projectId)
    expect(eventName).toBe(WORKPAPER_CONTENT_UPDATED_EVENT)
    expect(eventName).toBe('workpaper.content.updated')
    expect(typeof handler).toBe('function')
    expect(typeof options.onReconnect).toBe('function')
    expect(typeof options.onDegraded).toBe('function')
    tracker.stop()
  })
})
