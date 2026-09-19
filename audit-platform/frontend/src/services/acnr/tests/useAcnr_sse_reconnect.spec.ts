/**
 * useAcnr 项目级 SSE 订阅测试（acnr-invalidation-overlay-hardening + 复盘 #1）
 *
 * 复盘 #1：useAcnr SSE 改用 fetch-based `createSSE`（Authorization header 传 token，
 * token 不入 URL query）。断线重连 / 指数退避由 createSSE 内部负责（单一真源），
 * useAcnr 层只做：引用计数复用 + 重连后清项目缓存 + 超限降级 TTL-only 观测。
 *
 * 验证 R1（项目级订阅）+ R4.4/R4.5（超限降级 TTL-only / 重连清项目缓存）：
 * 1. subscribeInvalidation(pid) → createSSE 连 /api/projects/{pid}/events/stream（无 token= query）
 * 2. onError 超过 maxRetries 次 → 降级 TTL-only（停止）+ console.warn
 * 3. 重连成功（onOpen）→ 清该项目 resolve 缓存（不 bump 全局 epoch）
 * 4. 降级后 / cleanup 后不再建连接
 * 5. 同项目多次订阅引用计数复用单一连接
 *
 * Property P9: SSE 降级不返回陈旧 —— 超限后 TTL-only（staleness 受 MAX_AGE 约束）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const PID = '11111111-1111-1111-1111-111111111111'

// ─── Mock http ────────────────────────────────────────────────────────────────
const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: any[]) => mockGet(...args) },
}))

// ─── Mock vue lifecycle (onUnmounted is noop in test) ─────────────────────────
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onUnmounted: vi.fn(),
  }
})

// ─── Mock createSSE（fetch-based SSE 连接）──────────────────────────────────────
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
  _emitInvalidate(payload: Record<string, unknown>) {
    this.msgHandler?.(payload, 'acnr:invalidate')
  }
}

const mockCreateSSE = vi.fn((url: string, opts: any) => new MockSSEConn(url, opts))
vi.mock('@/utils/sse', () => ({
  createSSE: (url: string, opts: any) => mockCreateSSE(url, opts),
}))

describe('useAcnr — 项目级 SSE 订阅 (R1/R4, P9)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    MockSSEConn.instances = []
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function loadModule() {
    return await import('../useAcnr')
  }

  it('subscribeInvalidation 连接项目级 stream 端点，token 不入 URL（走 Authorization header）', async () => {
    const { subscribeInvalidation } = await loadModule()
    subscribeInvalidation(PID)

    expect(MockSSEConn.instances.length).toBe(1)
    const url = MockSSEConn.instances[0].url
    expect(url).toContain(`/api/projects/${PID}/events/stream`)
    // #1 安全：JWT 不再放 URL query
    expect(url).not.toContain('token=')
    // 不再是旧的错误全局端点
    expect(url).not.toContain('/api/projects/events?topic=')
  })

  it('无 projectId → 不建连接（R1.3）', async () => {
    const { useAcnr } = await loadModule()
    useAcnr() // 无 projectId
    expect(MockSSEConn.instances.length).toBe(0)
  })

  it('onError 超过 maxRetries 次后降级为 TTL-only 并 console.warn', async () => {
    const warnSpy = vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { subscribeInvalidation, isSSEDegraded } = await loadModule()
    subscribeInvalidation(PID)

    expect(isSSEDegraded(PID)).toBe(false)
    const conn = MockSSEConn.instances[0]

    // createSSE 内部重试上限（maxRetries=5）后仍失败，每次失败回调 onError；
    // useAcnr 层累计 > 5 次 → 降级。
    for (let i = 0; i < 6; i++) {
      conn._error()
    }

    expect(isSSEDegraded(PID)).toBe(true)
    expect(conn.closed).toBe(true)

    const degradedWarn = warnSpy.mock.calls.find(
      (call) => typeof call[0] === 'string' && call[0].includes('TTL-only'),
    )
    expect(degradedWarn).toBeDefined()
    warnSpy.mockRestore()
  })

  it('重连成功（onOpen）清该项目 resolve 缓存，下次 resolve 重新发请求（R4.5）', async () => {
    const { useAcnr, subscribeInvalidation } = await loadModule()
    subscribeInvalidation(PID)
    const acnr = useAcnr()
    const conn = MockSSEConn.instances[0]

    // 首次 onOpen（everConnected=false → 不清缓存）
    conn._open()

    // seed resolve 缓存
    mockGet.mockResolvedValue({ data: { found: true, addr_id: 'D2/D2-2/E100' } })
    await acnr.resolveIndex('cell:D2-2!E100', PID)
    expect(mockGet).toHaveBeenCalledTimes(1)
    // 缓存命中，不再请求
    await acnr.resolveIndex('cell:D2-2!E100', PID)
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 断连 → createSSE 内部重连 → 再次 onOpen（everConnected=true → 清项目缓存）
    conn._error()
    conn._open()

    // 项目 resolve 缓存已清 → 再次 resolve 重新请求
    await acnr.resolveIndex('cell:D2-2!E100', PID)
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('降级后新 subscribeInvalidation 不再尝试建 SSE', async () => {
    vi.spyOn(console, 'warn').mockImplementation(() => {})
    const { subscribeInvalidation, isSSEDegraded } = await loadModule()
    subscribeInvalidation(PID)

    const conn = MockSSEConn.instances[0]
    for (let i = 0; i < 6; i++) {
      conn._error()
    }
    expect(isSSEDegraded(PID)).toBe(true)
    const countAfterDegraded = MockSSEConn.instances.length

    subscribeInvalidation(PID)
    expect(MockSSEConn.instances.length).toBe(countAfterDegraded)
  })

  it('cleanup 后（refCount→0）关闭连接', async () => {
    const { subscribeInvalidation } = await loadModule()
    const cleanup = subscribeInvalidation(PID)

    const conn = MockSSEConn.instances[0]
    cleanup()
    expect(conn.closed).toBe(true)
  })

  it('同项目多次订阅引用计数复用单一连接', async () => {
    const { subscribeInvalidation } = await loadModule()
    const c1 = subscribeInvalidation(PID)
    const c2 = subscribeInvalidation(PID)
    // 复用同一连接
    expect(MockSSEConn.instances.length).toBe(1)
    // 释放一个引用，连接仍在
    c1()
    expect(MockSSEConn.instances[0].closed).toBe(false)
    // 释放最后一个引用，连接关闭
    c2()
    expect(MockSSEConn.instances[0].closed).toBe(true)
  })
})
