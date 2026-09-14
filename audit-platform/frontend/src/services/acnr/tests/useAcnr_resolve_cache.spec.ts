/**
 * useAcnr resolve 结果 LRU 缓存测试
 *
 * 验证 Req-20: 非 wp 域 resolve 结果前端缓存
 * - Req-20.1: resolve 级缓存（key = 输入参数哈希）
 * - Req-20.2: 与 sheets/cells 缓存共享同一 _cacheEpoch 失效机制
 * - Req-20.3: 独立 MAX_RESOLVE_CACHE_SIZE（默认 200 条）LRU 淘汰策略
 * - Req-20.4: found=false 不缓存
 *
 * **Validates: Requirements 1.2**
 *
 * Property P22: 非 wp 域 resolve 缓存命中率
 * vitest：连续 2 次 resolveFormula 同输入 → 第 2 次不触发 HTTP
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

describe('useAcnr — resolve 结果 LRU 缓存 (Req-20, P22)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    MockEventSource.instances = []
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function loadModule() {
    const mod = await import('../useAcnr')
    return mod
  }

  // ─── P22: 连续 2 次 resolveFormula 同输入 → 第 2 次不触发 HTTP ─────────────

  it('P22: resolveFormula 第二次同输入命中缓存不触发 HTTP', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({
      data: { found: true, addr_id: 'D2/D2-2/E100', entry_type: 'cell' },
    })

    // 第一次：发请求
    const r1 = await acnr.resolveFormula("WP('D2','明细表D2-2','E100')")
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(r1.found).toBe(true)
    expect(r1.addr_id).toBe('D2/D2-2/E100')

    // 第二次：同输入，命中缓存不发请求
    const r2 = await acnr.resolveFormula("WP('D2','明细表D2-2','E100')")
    expect(mockGet).toHaveBeenCalledTimes(1) // 仍然只有 1 次
    expect(r2).toEqual(r1)
  })

  it('resolveUri 第二次同输入命中缓存不触发 HTTP', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({
      data: { found: true, addr_id: 'tb/1001', entry_type: 'cell' },
    })

    const r1 = await acnr.resolveUri('tb://1001')
    expect(mockGet).toHaveBeenCalledTimes(1)

    const r2 = await acnr.resolveUri('tb://1001')
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(r2).toEqual(r1)
  })

  it('resolveAddr 第二次同输入命中缓存不触发 HTTP', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({
      data: { found: true, addr_id: 'D2/D2-2/E100' },
    })

    const r1 = await acnr.resolveAddr('D2/D2-2/E100')
    expect(mockGet).toHaveBeenCalledTimes(1)

    const r2 = await acnr.resolveAddr('D2/D2-2/E100')
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(r2).toEqual(r1)
  })

  it('resolveIndex 第二次同输入命中缓存不触发 HTTP', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({
      data: { found: true, addr_id: 'D2/D2-2/E100' },
    })

    const r1 = await acnr.resolveIndex('cell:D2-2!E100')
    expect(mockGet).toHaveBeenCalledTimes(1)

    const r2 = await acnr.resolveIndex('cell:D2-2!E100')
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(r2).toEqual(r1)
  })

  // ─── Req-20.4: found=false 不缓存 ──────────────────────────────────────────

  it('found=false 的结果不被缓存，下次仍发 HTTP', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    // 第一次返回 found=false
    mockGet.mockResolvedValueOnce({
      data: { found: false, error: 'not_found' },
    })

    const r1 = await acnr.resolveFormula("WP('X99','X99-1','Z999')")
    expect(r1.found).toBe(false)
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 第二次同输入：由于 found=false 未缓存，应再次发请求
    mockGet.mockResolvedValueOnce({
      data: { found: true, addr_id: 'X99/X99-1/Z999' },
    })

    const r2 = await acnr.resolveFormula("WP('X99','X99-1','Z999')")
    expect(mockGet).toHaveBeenCalledTimes(2) // 确实发了第二次
    expect(r2.found).toBe(true)
  })

  // ─── Req-20.2: epoch 变清空 resolve 缓存 ───────────────────────────────────

  it('epoch 变化后 resolve 缓存被清空，再次请求走 HTTP', async () => {
    const { useAcnr, invalidateModuleCache } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({
      data: { found: true, addr_id: 'D2/D2-2/E100' },
    })

    // 第一次：写入缓存
    await acnr.resolveFormula("WP('D2','明细表D2-2','E100')")
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 触发 epoch 变化（模拟 SSE invalidate）
    invalidateModuleCache()

    // 第二次：缓存已清，重新发请求
    await acnr.resolveFormula("WP('D2','明细表D2-2','E100')")
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  // ─── Req-20.3: LRU 淘汰策略（max 200） ─────────────────────────────────────

  it('MAX_RESOLVE_CACHE_SIZE 默认为 200', async () => {
    const { MAX_RESOLVE_CACHE_SIZE } = await loadModule()
    expect(MAX_RESOLVE_CACHE_SIZE).toBe(200)
  })

  it('超过 MAX_RESOLVE_CACHE_SIZE 时最旧条目被淘汰', async () => {
    const { useAcnr, MAX_RESOLVE_CACHE_SIZE } = await loadModule()
    const acnr = useAcnr()

    // 填满 200 条不同的 resolve 请求
    for (let i = 0; i < MAX_RESOLVE_CACHE_SIZE; i++) {
      mockGet.mockResolvedValueOnce({
        data: { found: true, addr_id: `D2/D2-2/E${i}` },
      })
      await acnr.resolveAddr(`D2/D2-2/E${i}`)
    }
    expect(mockGet).toHaveBeenCalledTimes(MAX_RESOLVE_CACHE_SIZE)

    // 再加入第 201 条 → 第 0 条（最旧）应被淘汰
    mockGet.mockResolvedValueOnce({
      data: { found: true, addr_id: 'D2/D2-2/ENEW' },
    })
    await acnr.resolveAddr('D2/D2-2/ENEW')
    expect(mockGet).toHaveBeenCalledTimes(MAX_RESOLVE_CACHE_SIZE + 1)

    // 请求第 0 条：已被淘汰，应重新发请求
    mockGet.mockResolvedValueOnce({
      data: { found: true, addr_id: 'D2/D2-2/E0' },
    })
    await acnr.resolveAddr('D2/D2-2/E0')
    expect(mockGet).toHaveBeenCalledTimes(MAX_RESOLVE_CACHE_SIZE + 2)

    // 请求第 199 条：仍在缓存中（未被淘汰），不发请求
    // (E0 被淘汰后重新写入 → E1 成为最旧被淘汰；E2..E199 + ENEW + E0 = 200)
    // E199 仍在缓存
    await acnr.resolveAddr('D2/D2-2/E199')
    expect(mockGet).toHaveBeenCalledTimes(MAX_RESOLVE_CACHE_SIZE + 2)
  })

  // ─── 不同输入参数不命中缓存 ─────────────────────────────────────────────────

  it('不同输入参数各自独立缓存', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValueOnce({
      data: { found: true, addr_id: 'D2/D2-2/E100' },
    })
    mockGet.mockResolvedValueOnce({
      data: { found: true, addr_id: 'D2/D2-2/E200' },
    })

    await acnr.resolveAddr('D2/D2-2/E100')
    await acnr.resolveAddr('D2/D2-2/E200')
    expect(mockGet).toHaveBeenCalledTimes(2)

    // 两者都命中各自缓存
    await acnr.resolveAddr('D2/D2-2/E100')
    await acnr.resolveAddr('D2/D2-2/E200')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  // ─── 多实例共享 resolve 缓存 ────────────────────────────────────────────────

  it('多个 useAcnr 实例共享 resolve 缓存', async () => {
    const { useAcnr } = await loadModule()
    const acnr1 = useAcnr()
    const acnr2 = useAcnr()

    mockGet.mockResolvedValue({
      data: { found: true, addr_id: 'D2/D2-2/E100' },
    })

    // acnr1 发请求
    await acnr1.resolveFormula("WP('D2','明细表D2-2','E100')")
    expect(mockGet).toHaveBeenCalledTimes(1)

    // acnr2 同输入命中共享缓存
    await acnr2.resolveFormula("WP('D2','明细表D2-2','E100')")
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  // ─── 网络错误不缓存 ─────────────────────────────────────────────────────────

  it('网络错误返回 found=false 不缓存', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()

    // 第一次网络错误
    mockGet.mockRejectedValueOnce(new Error('Network error'))
    const r1 = await acnr.resolveFormula("WP('D2','明细表D2-2','E100')")
    expect(r1.found).toBe(false)
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 第二次应重新发请求（错误结果未缓存）
    mockGet.mockResolvedValueOnce({
      data: { found: true, addr_id: 'D2/D2-2/E100' },
    })
    const r2 = await acnr.resolveFormula("WP('D2','明细表D2-2','E100')")
    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(r2.found).toBe(true)
  })
})
