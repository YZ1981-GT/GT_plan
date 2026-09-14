/**
 * useAcnr 缓存失效机制测试（acnr-invalidation-overlay-hardening）
 *
 * 非 SSE：getCacheEpoch / invalidateModuleCache / clearCache / TTL 缓存命中。
 * SSE（P8 项目隔离精细失效）：
 *   - 项目级 acnr:invalidate（仅 project_id）→ 只清该项目 resolve 缓存，不 bump 全局 epoch、不清目录缓存
 *   - 携带新 catalog_version → 清全局目录缓存 + bump epoch
 *   - 项目隔离：项目 A 的失效不影响项目 B 的 resolve 缓存
 *
 * **Validates: R4.1/R4.2/R4.3；Property P8**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'

const PID_A = 'aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa'
const PID_B = 'bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb'

// ─── Mock http ────────────────────────────────────────────────────────────────
const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: any[]) => mockGet(...args) },
}))

// ─── Mock vue lifecycle ───────────────────────────────────────────────────────
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return {
    ...actual,
    onUnmounted: vi.fn(),
  }
})

// ─── Mock createSSE（fetch-based SSE：Authorization header，token 不入 URL）──────
// 复盘 #1：useAcnr 改用 createSSE 传 token（header），不再用 native EventSource（URL query token）。
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
  /** 模拟服务端发 named event（createSSE 已 JSON.parse，回调收到对象 + event 名） */
  _emitInvalidate(payload: Record<string, unknown>) {
    this.msgHandler?.(payload, 'acnr:invalidate')
  }
  static byProject(pid: string): MockSSEConn | undefined {
    return MockSSEConn.instances.find((c) => c.url.includes(`/api/projects/${pid}/`))
  }
}

const mockCreateSSE = vi.fn((url: string, opts: any) => new MockSSEConn(url, opts))
vi.mock('@/utils/sse', () => ({
  createSSE: (url: string, opts: any) => mockCreateSSE(url, opts),
}))

describe('useAcnr — 缓存失效机制 (R4, P8)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    MockSSEConn.instances = []
    vi.resetModules()
    ;(globalThis as any).sessionStorage = {
      getItem: (k: string) => (k === 'token' ? 'jwt-abc' : null),
    }
    ;(globalThis as any).localStorage = { getItem: () => null }
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function loadModule() {
    return await import('./useAcnr')
  }

  // ─── 非 SSE：epoch / 缓存基本行为 ─────────────────────────────────────

  it('getCacheEpoch 初始值为 0', async () => {
    const { getCacheEpoch } = await loadModule()
    expect(getCacheEpoch()).toBe(0)
  })

  it('invalidateModuleCache 递增 epoch', async () => {
    const { getCacheEpoch, invalidateModuleCache } = await loadModule()
    const before = getCacheEpoch()
    invalidateModuleCache()
    expect(getCacheEpoch()).toBe(before + 1)
  })

  it('invalidateModuleCache 多次调用 epoch 单调递增', async () => {
    const { getCacheEpoch, invalidateModuleCache } = await loadModule()
    invalidateModuleCache()
    invalidateModuleCache()
    invalidateModuleCache()
    expect(getCacheEpoch()).toBe(3)
  })

  it('clearCache 递增 epoch 并清空响应式状态', async () => {
    const { useAcnr, getCacheEpoch } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValueOnce({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })
    await acnr.listSheets('D')
    expect(acnr.sheets.value.length).toBe(1)

    const epochBefore = getCacheEpoch()
    acnr.clearCache()
    expect(getCacheEpoch()).toBe(epochBefore + 1)
    expect(acnr.sheets.value).toEqual([])
    expect(acnr.cells.value).toEqual([])
  })

  it('listSheets 在缓存命中时不发请求', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()
    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('invalidateModuleCache 后 listSheets 重新发请求', async () => {
    const { useAcnr, invalidateModuleCache } = await loadModule()
    const acnr = useAcnr()
    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)
    invalidateModuleCache()
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('getEpoch 返回当前 epoch', async () => {
    const { useAcnr, invalidateModuleCache } = await loadModule()
    const acnr = useAcnr()
    expect(acnr.getEpoch()).toBe(0)
    invalidateModuleCache()
    expect(acnr.getEpoch()).toBe(1)
  })

  it('多个 useAcnr 实例共享同一缓存和 epoch', async () => {
    const { useAcnr } = await loadModule()
    const acnr1 = useAcnr()
    const acnr2 = useAcnr()
    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })
    await acnr1.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)
    await acnr2.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)
    acnr1.clearCache()
    await acnr2.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  // ─── SSE 项目隔离精细失效（P8）────────────────────────────────────────

  it('subscribeInvalidation 连接项目级端点（token 不入 URL，走 Authorization header）', async () => {
    const { subscribeInvalidation } = await loadModule()
    subscribeInvalidation(PID_A)
    const conn = MockSSEConn.byProject(PID_A)
    expect(conn).toBeDefined()
    expect(conn!.url).toContain(`/api/projects/${PID_A}/events/stream`)
    // #1 安全：JWT 不再出现在 URL query
    expect(conn!.url).not.toContain('token=')
  })

  it('项目级 acnr:invalidate（仅 project_id）只清该项目 resolve 缓存，不 bump epoch、不清目录缓存', async () => {
    const { useAcnr, subscribeInvalidation, getCacheEpoch } = await loadModule()
    subscribeInvalidation(PID_A)
    const acnr = useAcnr()

    // seed 目录缓存 + 项目 resolve 缓存
    mockGet.mockResolvedValueOnce({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })
    await acnr.listSheets('D')
    mockGet.mockResolvedValue({ data: { found: true, addr_id: 'D2/D2-2/E100' } })
    await acnr.resolveIndex('cell:D2-2!E100', PID_A)
    const callsAfterSeed = mockGet.mock.calls.length
    const epochBefore = getCacheEpoch()

    // 项目级失效（无 catalog_version）
    MockSSEConn.byProject(PID_A)!._emitInvalidate({ project_id: PID_A })

    // epoch 未变（不 bump 全局）
    expect(getCacheEpoch()).toBe(epochBefore)
    // 目录缓存未清 → listSheets 仍命中，不重新请求
    await acnr.listSheets('D')
    expect(mockGet.mock.calls.length).toBe(callsAfterSeed)
    // 项目 resolve 缓存已清 → resolveIndex 重新请求
    await acnr.resolveIndex('cell:D2-2!E100', PID_A)
    expect(mockGet.mock.calls.length).toBe(callsAfterSeed + 1)
  })

  it('携带新 catalog_version → 清全局目录缓存 + bump epoch（R4.2）', async () => {
    const { useAcnr, subscribeInvalidation, getCacheEpoch } = await loadModule()
    subscribeInvalidation(PID_A)
    const acnr = useAcnr()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })
    await acnr.listSheets('D')
    const callsAfterSeed = mockGet.mock.calls.length
    const epochBefore = getCacheEpoch()

    MockSSEConn.byProject(PID_A)!._emitInvalidate({
      project_id: PID_A,
      catalog_version: 'v-new-2026',
    })

    // 全局失效 → epoch bump
    expect(getCacheEpoch()).toBe(epochBefore + 1)
    // 目录缓存已清 → listSheets 重新请求
    await acnr.listSheets('D')
    expect(mockGet.mock.calls.length).toBe(callsAfterSeed + 1)
  })

  it('项目隔离：项目 A 的失效不影响项目 B 的 resolve 缓存', async () => {
    const { useAcnr, subscribeInvalidation } = await loadModule()
    subscribeInvalidation(PID_A)
    subscribeInvalidation(PID_B)
    const acnr = useAcnr()

    mockGet.mockResolvedValue({ data: { found: true, addr_id: 'D2/D2-2/E100' } })
    await acnr.resolveIndex('cell:D2-2!E100', PID_A)
    await acnr.resolveIndex('cell:D3-2!E100', PID_B)
    const callsAfterSeed = mockGet.mock.calls.length

    // 失效项目 A
    MockSSEConn.byProject(PID_A)!._emitInvalidate({ project_id: PID_A })

    // 项目 B resolve 缓存仍命中，不重新请求
    await acnr.resolveIndex('cell:D3-2!E100', PID_B)
    expect(mockGet.mock.calls.length).toBe(callsAfterSeed)
    // 项目 A resolve 缓存已清 → 重新请求
    await acnr.resolveIndex('cell:D2-2!E100', PID_A)
    expect(mockGet.mock.calls.length).toBe(callsAfterSeed + 1)
  })
})
