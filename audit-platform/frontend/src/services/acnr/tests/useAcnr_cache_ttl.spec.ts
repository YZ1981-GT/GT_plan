/**
 * useAcnr 缓存 TTL 兜底测试
 *
 * 验证 Req-15.1: 前端 module-level cache 为每条缓存项设置 maxAge（默认 300 秒 / 5 分钟），
 * 超时后下次访问自动失效并重新请求。
 *
 * **Validates: Requirements 15.1**
 *
 * Property P17: 前端 TTL 过期后重新请求
 * vitest：写入 cache → sleep 300s(mock) → 下次 resolve 走网络
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

// ─── Mock http ────────────────────────────────────────────────────────────────
const mockGet = vi.fn()
const mockPost = vi.fn()
vi.mock('@/utils/http', () => ({
  default: {
    get: (...args: any[]) => mockGet(...args),
    post: (...args: any[]) => mockPost(...args),
  },
}))

// ─── Mock vue lifecycle ───────────────────────────────────────────────────────
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onUnmounted: vi.fn(),
  }
})

// ─── Mock EventSource ─────────────────────────────────────────────────────────
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  listeners: Record<string, Function[]> = {}
  onmessage: ((ev: any) => void) | null = null
  onerror: (() => void) | null = null
  onopen: (() => void) | null = null
  closed = false

  constructor(url: string) {
    this.url = url
    MockEventSource.instances.push(this)
  }
  addEventListener(event: string, handler: Function) {
    if (!this.listeners[event]) this.listeners[event] = []
    this.listeners[event].push(handler)
  }
  close() {
    this.closed = true
  }
}
;(globalThis as any).EventSource = MockEventSource

describe('useAcnr — 缓存 TTL 兜底 (Req-15.1, P17)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    vi.useFakeTimers()
    MockEventSource.instances = []
    vi.resetModules()
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.restoreAllMocks()
  })

  async function loadModule() {
    const mod = await import('../useAcnr')
    return mod
  }

  it('MAX_AGE 等于 300_000ms（5 分钟）', async () => {
    const { MAX_AGE } = await loadModule()
    expect(MAX_AGE).toBe(300_000)
  })

  it('缓存未过期时 listSheets 不发请求（TTL 内命中）', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })

    // 第一次：发请求
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 前进 299 秒（未超 TTL）
    vi.advanceTimersByTime(299_000)

    // 第二次：缓存仍有效，不发请求
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('缓存过期后 listSheets 重新发请求（TTL 超时）', async () => {
    const { useAcnr, MAX_AGE } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })

    // 第一次：发请求并写入缓存
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 前进超过 MAX_AGE（300 秒 + 1ms）
    vi.advanceTimersByTime(MAX_AGE + 1)

    // 第二次：缓存已过期，重新发请求
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('缓存过期后 listCells 重新发请求', async () => {
    const { useAcnr, MAX_AGE } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2/E100', cell_address: 'E100' }] })

    // 第一次：发请求
    await acnr.listCells('D2', 'D2-2')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 缓存命中（未过期）
    await acnr.listCells('D2', 'D2-2')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 前进超过 TTL
    vi.advanceTimersByTime(MAX_AGE + 1)

    // 缓存过期，重新请求
    await acnr.listCells('D2', 'D2-2')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('SSE 失效优先于 TTL（不等过期）', async () => {
    const { useAcnr, invalidateModuleCache } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })

    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 仅前进 10 秒（远未到 TTL）但收到 SSE invalidate
    vi.advanceTimersByTime(10_000)
    invalidateModuleCache()

    // 缓存已被 SSE 清空，需重新请求
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('batchResolve 发送 POST 请求到 resolve-batch', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    const mockResults = [
      { found: true, addr_id: 'D2/D2-2/E100' },
      { found: true, addr_id: 'D2/D2-2/E200' },
    ]
    mockPost.mockResolvedValue({ data: mockResults })

    const inputs = [
      { addr_id: 'D2/D2-2/E100' },
      { addr_id: 'D2/D2-2/E200' },
    ]
    const results = await acnr.batchResolve(inputs, 'project-123')

    expect(mockPost).toHaveBeenCalledTimes(1)
    expect(mockPost).toHaveBeenCalledWith('/api/acnr/resolve-batch', {
      items: inputs,
      project_id: 'project-123',
    })
    expect(results).toHaveLength(2)
    expect(results[0].found).toBe(true)
  })

  it('batchResolve 空输入返回空数组不发请求', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    const results = await acnr.batchResolve([])
    expect(results).toEqual([])
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('batchResolve 网络失败返回等长错误数组', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    mockPost.mockRejectedValue(new Error('Network error'))

    const inputs = [
      { addr_id: 'D2/D2-2/E100' },
      { formula_ref: "WP('D2','D2-2','E200')" },
    ]
    const results = await acnr.batchResolve(inputs)

    expect(results).toHaveLength(2)
    expect(results[0]).toEqual({ found: false, error: 'batch_resolve_failed' })
    expect(results[1]).toEqual({ found: false, error: 'batch_resolve_failed' })
  })
})
