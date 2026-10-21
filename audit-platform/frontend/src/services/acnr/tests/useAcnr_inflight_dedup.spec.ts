/**
 * useAcnr 在途请求合并测试
 *
 * spec: frontend-test-network-isolation-and-load-dedup（R3.1~R3.3；design §3）
 *
 * 缺陷：listSheets / listCells 的模块级缓存只在响应回来后写入，同参数并发调用全部穿透，
 * 公式管理弹窗打开时发两次相同 GET；http GET 去重取消先发的那一发，被取消方当成失败
 * （打「listSheets 失败」告警、先写空目录）。
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const mockGet = vi.fn()
vi.mock('@/utils/http', () => ({
  default: { get: (...args: unknown[]) => mockGet(...args) },
}))
vi.mock('vue', async () => {
  const actual = await vi.importActual<typeof import('vue')>('vue')
  return { ...actual, onUnmounted: vi.fn() }
})

const SHEETS = [{ addr_id: 'D2/D2-2', sheet_code: 'D2-2' }]
const CELLS = [{ addr_id: 'D2/D2-2/E100', cell: 'E100' }]

function deferred<T>() {
  let resolve!: (v: T) => void
  let reject!: (e: unknown) => void
  const promise = new Promise<T>((res, rej) => { resolve = res; reject = rej })
  return { promise, resolve, reject }
}

async function loadModule() {
  return import('../useAcnr')
}

describe('useAcnr — 同参并发调用只发一次请求', () => {
  beforeEach(() => {
    mockGet.mockReset()
    vi.resetModules()
  })
  afterEach(() => {
    vi.restoreAllMocks()
  })

  it('listSheets：两个实例并发同参 → 1 次请求，两边拿到同一结果、各自 sheets/loading 正确', async () => {
    const { useAcnr } = await loadModule()
    const a = useAcnr()
    const b = useAcnr()
    const d = deferred<{ data: unknown }>()
    mockGet.mockReturnValue(d.promise)
    const pa = a.listSheets()
    const pb = b.listSheets()
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(a.loading.value).toBe(true)
    expect(b.loading.value).toBe(true)
    d.resolve({ data: SHEETS })
    const [ra, rb] = await Promise.all([pa, pb])
    expect(ra).toEqual(SHEETS)
    expect(rb).toBe(ra)
    expect(a.sheets.value).toEqual(SHEETS)
    expect(b.sheets.value).toEqual(SHEETS)
    expect(a.loading.value).toBe(false)
    expect(b.loading.value).toBe(false)
    // 落定后进了缓存：再调不发请求
    await a.listSheets()
    expect(mockGet).toHaveBeenCalledTimes(1)
  })

  it('listSheets：参数不同各发一次', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()
    mockGet.mockResolvedValue({ data: SHEETS })
    await Promise.all([acnr.listSheets('D'), acnr.listSheets('E'), acnr.listSheets('D', true)])
    expect(mockGet).toHaveBeenCalledTimes(3)
  })

  it('listCells：同参并发 → 1 次请求；不同 sheet 各一次', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()
    mockGet.mockResolvedValue({ data: CELLS })
    const [r1, r2] = await Promise.all([acnr.listCells('D2', 'D2-2'), acnr.listCells('D2', 'D2-2')])
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(r2).toBe(r1)
    await Promise.all([acnr.listCells('D2', 'D2-3'), acnr.listCells('D2', 'D2-4')])
    expect(mockGet).toHaveBeenCalledTimes(3)
  })

  it('在途期间缓存被失效：之后的调用另发请求，旧响应不写回缓存', async () => {
    const { useAcnr, invalidateModuleCache } = await loadModule()
    const acnr = useAcnr()
    const stale = deferred<{ data: unknown }>()
    mockGet.mockReturnValueOnce(stale.promise)
    const p1 = acnr.listSheets('D')
    invalidateModuleCache()
    mockGet.mockResolvedValueOnce({ data: [{ addr_id: 'NEW', sheet_code: 'NEW' }] })
    const fresh = await acnr.listSheets('D')
    expect(mockGet).toHaveBeenCalledTimes(2)
    expect(fresh[0].addr_id).toBe('NEW')
    stale.resolve({ data: SHEETS })
    expect(await p1).toEqual(SHEETS)
    // 旧响应没有覆盖缓存：再取仍是新目录、不发请求
    const again = await acnr.listSheets('D')
    expect(again[0].addr_id).toBe('NEW')
    expect(mockGet).toHaveBeenCalledTimes(2)
  })

  it('在途请求失败：每个调用方各自降级为 []，下一次调用重新请求', async () => {
    const { useAcnr } = await loadModule()
    const acnr = useAcnr()
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    mockGet.mockRejectedValueOnce(new Error('boom'))
    const [r1, r2] = await Promise.all([acnr.listSheets(), acnr.listSheets()])
    expect(r1).toEqual([])
    expect(r2).toEqual([])
    expect(mockGet).toHaveBeenCalledTimes(1)
    expect(warn).toHaveBeenCalled()
    mockGet.mockResolvedValueOnce({ data: SHEETS })
    expect(await acnr.listSheets()).toEqual(SHEETS)
    expect(mockGet).toHaveBeenCalledTimes(2)
  })
})
