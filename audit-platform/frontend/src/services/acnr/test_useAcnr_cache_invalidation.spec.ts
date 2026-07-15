/**
 * useAcnr 缓存失效测试
 *
 * 验证 Req-7.4: 前端 useAcnr.ts module-level cache 过期
 * （或收到 SSE/WebSocket 通知），前端 SHALL 统一失效并重新请求。
 *
 * **Validates: Requirements 7.4**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'

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
    onUnmounted: vi.fn(), // composable 外部调 onUnmounted 不崩
  }
})

// ─── Mock EventSource ─────────────────────────────────────────────────────────
class MockEventSource {
  static instances: MockEventSource[] = []
  url: string
  listeners: Record<string, Function[]> = {}
  onmessage: ((ev: any) => void) | null = null
  onerror: (() => void) | null = null
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

  // 测试辅助：模拟服务端发送 named event
  _emit(event: string, data?: any) {
    const handlers = this.listeners[event] || []
    for (const h of handlers) h(data)
  }
  // 测试辅助：模拟通用 message
  _emitMessage(data: any) {
    if (this.onmessage) {
      this.onmessage({ data: typeof data === 'string' ? data : JSON.stringify(data) })
    }
  }
}

// 安装全局 mock
;(globalThis as any).EventSource = MockEventSource

describe('useAcnr — 缓存失效机制 (Req-7.4)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    MockEventSource.instances = []

    // 重置模块级状态：每次 re-import 模块
    vi.resetModules()
  })

  afterEach(() => {
    vi.restoreAllMocks()
  })

  async function loadModule() {
    // 动态导入以获取干净的模块级状态
    const mod = await import('./useAcnr')
    return mod
  }

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

    // Seed some data
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

    // 第一次：发请求
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 第二次：缓存命中，不发请求
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('invalidateModuleCache 后 listSheets 重新发请求', async () => {
    const { useAcnr, invalidateModuleCache } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })

    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 外部失效
    invalidateModuleCache()

    // 缓存失效后，下次调用应重新请求
    await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('listCells 缓存命中后 invalidate 导致重新请求', async () => {
    const { useAcnr, invalidateModuleCache } = await loadModule()
    const acnr = useAcnr()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2/E100', cell_address: 'E100' }] })

    await acnr.listCells('D2', 'D2-2')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 缓存命中
    await acnr.listCells('D2', 'D2-2')
    expect(mockGet).toHaveBeenCalledTimes(1)

    // 失效
    invalidateModuleCache()

    await acnr.listCells('D2', 'D2-2')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('SSE acnr:invalidate named event 触发缓存清空', async () => {
    const { useAcnr, getCacheEpoch } = await loadModule()
    useAcnr() // 触发 SSE 连接

    const es = MockEventSource.instances[0]
    expect(es).toBeDefined()
    expect(es.url).toContain('acnr:invalidate')

    const epochBefore = getCacheEpoch()
    // 模拟 SSE named event
    es._emit('acnr:invalidate')
    expect(getCacheEpoch()).toBe(epochBefore + 1)
  })

  it('SSE generic message with type=acnr:invalidate 触发缓存清空', async () => {
    const { useAcnr, getCacheEpoch } = await loadModule()
    useAcnr()

    const es = MockEventSource.instances[0]
    const epochBefore = getCacheEpoch()

    // 模拟通用 message（部分后端用 data.type）
    es._emitMessage({ type: 'acnr:invalidate' })
    expect(getCacheEpoch()).toBe(epochBefore + 1)
  })

  it('SSE generic message with event=acnr:invalidate 触发缓存清空', async () => {
    const { useAcnr, getCacheEpoch } = await loadModule()
    useAcnr()

    const es = MockEventSource.instances[0]
    const epochBefore = getCacheEpoch()

    es._emitMessage({ event: 'acnr:invalidate' })
    expect(getCacheEpoch()).toBe(epochBefore + 1)
  })

  it('SSE 无关 message 不触发缓存失效', async () => {
    const { useAcnr, getCacheEpoch } = await loadModule()
    useAcnr()

    const es = MockEventSource.instances[0]
    const epochBefore = getCacheEpoch()

    es._emitMessage({ type: 'some:other:event' })
    expect(getCacheEpoch()).toBe(epochBefore)
  })

  it('getEpoch 返回当前 epoch', async () => {
    const { useAcnr, invalidateModuleCache } = await loadModule()
    const acnr = useAcnr()

    expect(acnr.getEpoch()).toBe(0)
    invalidateModuleCache()
    expect(acnr.getEpoch()).toBe(1)
    invalidateModuleCache()
    expect(acnr.getEpoch()).toBe(2)
  })

  it('多个 useAcnr 实例共享同一缓存和 epoch', async () => {
    const { useAcnr, getCacheEpoch } = await loadModule()

    const acnr1 = useAcnr()
    const acnr2 = useAcnr()

    mockGet.mockResolvedValue({ data: [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }] })

    // acnr1 加载后，acnr2 应能命中缓存
    await acnr1.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(1)

    await acnr2.listSheets('D')
    // 共享模块缓存，不再请求
    expect(mockGet).toHaveBeenCalledTimes(1)

    // acnr1 失效 → acnr2 也受影响
    acnr1.clearCache()
    await acnr2.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })
})
