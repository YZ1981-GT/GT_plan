/**
 * projectEventStream 单例总线单测（frontend-sse-connection-consolidation）
 *
 * P1 单连接 / P2 fan-out / P3 Ref_Count_Lifecycle / P4 项目隔离 / P5 重连通知 /
 * P6 鉴权 URL 无 token / P7 无 projectId no-op / P8 异常隔离 / P9 裸事件分发 /
 * P10 降级不重建+onDegraded。
 *
 * mock `createSSE`（不 mock fetch/ReadableStream）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const PID_A = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const PID_B = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

// ─── Mock createSSE ─────────────────────────────────────────────────────────
class MockSSEConn {
  static instances: MockSSEConn[] = []
  url: string
  opts: any
  msgHandler: ((data: any, event?: string) => void) | null = null
  errHandler: ((e: any) => void) | null = null
  openHandler: (() => void) | null = null
  closed = false
  connected = false

  constructor(url: string, opts: any) {
    this.url = url
    this.opts = opts
    MockSSEConn.instances.push(this)
  }
  onMessage(h: (data: any, event?: string) => void) { this.msgHandler = h }
  onError(h: (e: any) => void) { this.errHandler = h }
  onOpen(h: () => void) { this.openHandler = h }
  close() { this.closed = true; this.connected = false }
  get isConnected() { return this.connected }
  _open() { this.connected = true; this.openHandler?.() }
  _error() { this.connected = false; this.errHandler?.(new Error('sse err')) }
  _emit(event: string, data: any) { this.msgHandler?.(data, event) }
  static byProject(pid: string): MockSSEConn[] {
    return MockSSEConn.instances.filter((c) => c.url.includes(`/api/projects/${pid}/`))
  }
}

const mockCreateSSE = vi.fn((url: string, opts: any) => new MockSSEConn(url, opts))
vi.mock('@/utils/sse', () => ({
  createSSE: (url: string, opts: any) => mockCreateSSE(url, opts),
}))

describe('projectEventStream — 单例总线', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    MockSSEConn.instances = []
    vi.resetModules()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function load() {
    return await import('./projectEventStream')
  }

  // ─── P1 / P3：单连接 + Ref_Count_Lifecycle ──────────────────────────────
  it('P1/P3: 同项目多订阅共享单一连接；末订阅关闭', async () => {
    const { subscribeProjectEvent } = await load()
    const s1 = subscribeProjectEvent(PID_A, 'acnr:invalidate', vi.fn())
    const s2 = subscribeProjectEvent(PID_A, 'consol.refresh.progress', vi.fn())
    // 单连接（P1）
    expect(MockSSEConn.byProject(PID_A).length).toBe(1)
    const conn = MockSSEConn.byProject(PID_A)[0]
    // 释放一个 → 连接仍在
    s1.close()
    expect(conn.closed).toBe(false)
    // 末个释放 → 关闭（P3）
    s2.close()
    expect(conn.closed).toBe(true)
  })

  it('P3: close 幂等（重复调用安全）', async () => {
    const { subscribeProjectEvent, _getProjectRefCount } = await load()
    const s = subscribeProjectEvent(PID_A, 'e1', vi.fn())
    expect(_getProjectRefCount(PID_A)).toBe(1)
    s.close()
    s.close()
    s.close()
    // 不会把 refCount 减成负数 / 不抛
    expect(_getProjectRefCount(PID_A)).toBe(0)
  })

  // ─── P2：fan-out ─────────────────────────────────────────────────────────
  it('P2: 同事件名多订阅者全部收到', async () => {
    const { subscribeProjectEvent } = await load()
    const h1 = vi.fn()
    const h2 = vi.fn()
    subscribeProjectEvent(PID_A, 'acnr:invalidate', h1)
    subscribeProjectEvent(PID_A, 'acnr:invalidate', h2)
    MockSSEConn.byProject(PID_A)[0]._emit('acnr:invalidate', { project_id: PID_A })
    expect(h1).toHaveBeenCalledTimes(1)
    expect(h2).toHaveBeenCalledTimes(1)
    expect(h1).toHaveBeenCalledWith({ project_id: PID_A }, 'acnr:invalidate')
  })

  // ─── P9：裸事件分发（无 event_type）──────────────────────────────────────
  it('P9: 负载无 event_type 的具名事件仍按 event 名投递', async () => {
    const { subscribeProjectEvent } = await load()
    const h = vi.fn()
    subscribeProjectEvent(PID_A, 'consol.refresh.completed', h)
    // 负载不含 event_type
    MockSSEConn.byProject(PID_A)[0]._emit('consol.refresh.completed', { job_id: 'j1' })
    expect(h).toHaveBeenCalledWith({ job_id: 'j1' }, 'consol.refresh.completed')
  })

  it('P2/P9: 只投递订阅的 event 名，无关事件不投递', async () => {
    const { subscribeProjectEvent } = await load()
    const h = vi.fn()
    subscribeProjectEvent(PID_A, 'acnr:invalidate', h)
    MockSSEConn.byProject(PID_A)[0]._emit('LINKAGE_STALE_CHANGED', { x: 1 })
    expect(h).not.toHaveBeenCalled()
  })

  // ─── 通配 '*'：catch-all（ThreeColumnLayout typed 事件等价）──────────────
  it("通配 '*' 订阅者收到所有事件名（catch-all）", async () => {
    const { subscribeProjectEvent, WILDCARD_EVENT } = await load()
    const star = vi.fn()
    subscribeProjectEvent(PID_A, WILDCARD_EVENT, star)
    const conn = MockSSEConn.byProject(PID_A)[0]
    conn._emit('sync.failed', { event_type: 'sync.failed' })
    conn._emit('trial_balance.updated', { event_type: 'trial_balance.updated' })
    conn._emit('acnr:invalidate', { project_id: PID_A }) // 无 event_type 也收到
    expect(star).toHaveBeenCalledTimes(3)
    expect(star).toHaveBeenNthCalledWith(1, { event_type: 'sync.failed' }, 'sync.failed')
  })

  it("通配 '*' 与精确订阅并存：各收各的（精确不因 '*' 漏，'*' 不重复精确）", async () => {
    const { subscribeProjectEvent, WILDCARD_EVENT } = await load()
    const star = vi.fn()
    const exact = vi.fn()
    subscribeProjectEvent(PID_A, WILDCARD_EVENT, star)
    subscribeProjectEvent(PID_A, 'acnr:invalidate', exact)
    MockSSEConn.byProject(PID_A)[0]._emit('acnr:invalidate', { x: 1 })
    expect(exact).toHaveBeenCalledTimes(1)
    expect(star).toHaveBeenCalledTimes(1) // '*' 收到一次，不重复
  })

  // ─── P4：项目隔离 ────────────────────────────────────────────────────────
  it('P4: 不同项目独立连接；A 事件不投递给 B 订阅者', async () => {
    const { subscribeProjectEvent } = await load()
    const hA = vi.fn()
    const hB = vi.fn()
    subscribeProjectEvent(PID_A, 'acnr:invalidate', hA)
    subscribeProjectEvent(PID_B, 'acnr:invalidate', hB)
    expect(MockSSEConn.byProject(PID_A).length).toBe(1)
    expect(MockSSEConn.byProject(PID_B).length).toBe(1)
    MockSSEConn.byProject(PID_A)[0]._emit('acnr:invalidate', { project_id: PID_A })
    expect(hA).toHaveBeenCalledTimes(1)
    expect(hB).not.toHaveBeenCalled()
  })

  // ─── P5：重连通知 ────────────────────────────────────────────────────────
  it('P5: 首次 open 不触发 onReconnect；断后重连触发', async () => {
    const { subscribeProjectEvent } = await load()
    const onReconnect = vi.fn()
    subscribeProjectEvent(PID_A, 'e1', vi.fn(), { onReconnect })
    const conn = MockSSEConn.byProject(PID_A)[0]
    // 首次 open → 不触发
    conn._open()
    expect(onReconnect).not.toHaveBeenCalled()
    // 断 → 重连 open → 触发
    conn._error()
    conn._open()
    expect(onReconnect).toHaveBeenCalledTimes(1)
  })

  // ─── P6：鉴权 URL 无 token ───────────────────────────────────────────────
  it('P6: 共享连接 URL 为项目级端点且不含 token=', async () => {
    const { subscribeProjectEvent } = await load()
    subscribeProjectEvent(PID_A, 'e1', vi.fn())
    const url = MockSSEConn.byProject(PID_A)[0].url
    expect(url).toContain(`/api/projects/${PID_A}/events/stream`)
    expect(url).not.toContain('token=')
  })

  // ─── P7：无 projectId no-op ──────────────────────────────────────────────
  it('P7: 空 projectId / 空 eventName 不建连接，close 安全', async () => {
    const { subscribeProjectEvent } = await load()
    const s1 = subscribeProjectEvent('', 'e1', vi.fn())
    const s2 = subscribeProjectEvent(PID_A, '', vi.fn())
    expect(MockSSEConn.instances.length).toBe(0)
    expect(() => { s1.close(); s2.close() }).not.toThrow()
  })

  // ─── P8：异常隔离 ────────────────────────────────────────────────────────
  it('P8: 一个 handler 抛错不阻断同事件其他 handler', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { subscribeProjectEvent } = await load()
    const bad = vi.fn(() => { throw new Error('boom') })
    const good = vi.fn()
    subscribeProjectEvent(PID_A, 'acnr:invalidate', bad)
    subscribeProjectEvent(PID_A, 'acnr:invalidate', good)
    MockSSEConn.byProject(PID_A)[0]._emit('acnr:invalidate', {})
    expect(bad).toHaveBeenCalled()
    expect(good).toHaveBeenCalled() // 未被 bad 的异常阻断
  })

  // ─── P10：降级不重建 + onDegraded ────────────────────────────────────────
  it('P10: 超重试上限降级 TTL-only + onDegraded 触发 + 不重建', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { subscribeProjectEvent, isProjectStreamDegraded } = await load()
    const onDegraded = vi.fn()
    subscribeProjectEvent(PID_A, 'e1', vi.fn(), { onDegraded })
    const conn = MockSSEConn.byProject(PID_A)[0]

    expect(isProjectStreamDegraded(PID_A)).toBe(false)
    // > maxRetries(5) 次 error → 降级
    for (let i = 0; i < 6; i++) conn._error()

    expect(isProjectStreamDegraded(PID_A)).toBe(true)
    expect(onDegraded).toHaveBeenCalledTimes(1)
    expect(conn.closed).toBe(true)

    // 降级后再订阅不重建（P10）
    const countBefore = MockSSEConn.instances.length
    subscribeProjectEvent(PID_A, 'e2', vi.fn())
    expect(MockSSEConn.instances.length).toBe(countBefore)
  })
})
