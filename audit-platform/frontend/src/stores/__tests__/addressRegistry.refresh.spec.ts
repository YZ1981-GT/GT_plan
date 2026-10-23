/**
 * 地址库整库加载：上限 50000、截断回报、刷新单飞与换项目丢弃旧响应（spec formula-fetch-and-wp-generation-defect-closure R3）。
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { isReactive } from 'vue'

const { mockHttpGet } = vi.hoisted(() => ({ mockHttpGet: vi.fn() }))
vi.mock('@/utils/http', () => ({ default: { get: mockHttpGet, post: vi.fn() } }))
vi.mock('@/services/acnr/useAcnr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/acnr/useAcnr')>()
  return {
    ...actual,
    useAcnr: () => ({
      listSheets: vi.fn().mockResolvedValue([]),
      listCells: vi.fn().mockResolvedValue([]),
      resolveUri: vi.fn(),
      resolveFormula: vi.fn(),
      clearCache: vi.fn(),
    }),
  }
})

import { createPinia, setActivePinia } from 'pinia'
import { ADDRESS_REGISTRY_FULL_LOAD_LIMIT, useAddressRegistry } from '../addressRegistry'

function entry(domain: string, label: string) {
  return { uri: `${domain}://${label}`, domain, source: '', path: '', cell: '', label, formula_ref: '', jump_route: '' }
}

function response(items: unknown[], extra: Record<string, unknown> = {}) {
  return { data: { items, total: items.length, returned: items.length, truncated: false, truncated_domains: [], ...extra } }
}

/** 可手动决定何时返回的请求 */
function deferred<T>() {
  let resolve!: (v: T) => void
  const promise = new Promise<T>((r) => { resolve = r })
  return { promise, resolve }
}

describe('useAddressRegistry 整库加载', () => {
  let store: ReturnType<typeof useAddressRegistry>
  beforeEach(() => {
    setActivePinia(createPinia())
    mockHttpGet.mockReset()
    store = useAddressRegistry()
  })
  afterEach(() => store.dispose())

  it('一次取 50000 条（与后端上限同一个数）', async () => {
    expect(ADDRESS_REGISTRY_FULL_LOAD_LIMIT).toBe(50000)
    mockHttpGet.mockResolvedValueOnce(response([entry('tb', 'a')]))
    await store.refresh('p1', 2025, 'soe')
    expect(mockHttpGet.mock.calls[0][1].params.limit).toBe(50000)
    expect(store.loaded).toBe(true)
  })

  it('地址数组不做深层响应式（上万条只整体替换）', async () => {
    mockHttpGet.mockResolvedValueOnce(response([entry('tb', 'a')]))
    await store.refresh('p1', 2025, 'soe')
    expect(isReactive(store.addresses)).toBe(false)
  })

  it('同一项目并发刷新共用一个请求', async () => {
    const d = deferred<any>()
    mockHttpGet.mockReturnValueOnce(d.promise)
    const a = store.refresh('p1', 2025, 'soe')
    const b = store.refresh('p1', 2025, 'soe')
    d.resolve(response([entry('tb', 'a')]))
    await Promise.all([a, b])
    expect(mockHttpGet).toHaveBeenCalledTimes(1)
    expect(store.addresses).toHaveLength(1)
  })

  it('A 项目加载中切到 B：B 另发请求；A 的响应晚到也不覆盖 B 的数据', async () => {
    const da = deferred<any>()
    const db = deferred<any>()
    mockHttpGet.mockReturnValueOnce(da.promise).mockReturnValueOnce(db.promise)
    const a = store.refresh('pA', 2025, 'soe')
    const b = store.refresh('pB', 2025, 'soe')
    expect(mockHttpGet).toHaveBeenCalledTimes(2)
    expect(mockHttpGet.mock.calls[1][1].params.project_id).toBe('pB')
    db.resolve(response([entry('tb', 'B 的科目')]))
    await b
    da.resolve(response([entry('tb', 'A 的科目')]))
    await a
    expect(store.addresses.map((e) => e.label)).toEqual(['B 的科目'])
    expect(store.loading).toBe(false)
  })

  it('A 的响应先到但绑定已切到 B：丢弃 A，B 回来之前不算已加载', async () => {
    const da = deferred<any>()
    const db = deferred<any>()
    mockHttpGet.mockReturnValueOnce(da.promise).mockReturnValueOnce(db.promise)
    const a = store.refresh('pA', 2025, 'soe')
    const b = store.refresh('pB', 2025, 'soe')
    da.resolve(response([entry('tb', 'A 的科目')]))
    await a
    expect(store.addresses).toEqual([])
    expect(store.loaded).toBe(false)
    expect(store.loading).toBe(true)
    db.resolve(response([entry('tb', 'B 的科目')]))
    await b
    expect(store.addresses.map((e) => e.label)).toEqual(['B 的科目'])
    expect(store.loading).toBe(false)
  })

  it('A 已加载后切到 B：立即清掉 A 的数据（加载完成前选择器拿不到上一个项目的地址）', async () => {
    mockHttpGet.mockResolvedValueOnce(response([entry('tb', 'A 的科目')]))
    await store.refresh('pA', 2025, 'soe')
    const db = deferred<any>()
    mockHttpGet.mockReturnValueOnce(db.promise)
    const b = store.refresh('pB', 2025, 'soe')
    expect(store.loaded).toBe(false)
    expect(store.addresses).toEqual([])
    expect(store.isDomainComplete('tb')).toBe(false)
    db.resolve(response([entry('tb', 'B 的科目')]))
    await b
    expect(store.isDomainComplete('tb')).toBe(true)
  })

  it('被截断的域不算完整；该域的搜索改走后端按关键词搜', async () => {
    mockHttpGet.mockResolvedValueOnce(
      response([entry('report', 'r'), entry('note', 'n')], { truncated: true, truncated_domains: ['note'], total: 60000 }),
    )
    await store.refresh('p1', 2025, 'soe')
    expect(store.truncatedDomains).toEqual(['note'])
    expect(store.isDomainComplete('report')).toBe(true)
    expect(store.isDomainComplete('note')).toBe(false)

    mockHttpGet.mockResolvedValueOnce({ data: { items: [entry('note', '后端命中')] } })
    const got = await store.search('货币', 'note')
    expect(got.map((e) => e.label)).toEqual(['后端命中'])
    expect(mockHttpGet.mock.calls[1][1].params).toMatchObject({ keyword: '货币', domain: 'note' })

    const local = await store.search('r', 'report')
    expect(local.map((e) => e.label)).toEqual(['r'])
    expect(mockHttpGet).toHaveBeenCalledTimes(2) // 完整的域仍在本地过滤
  })
})
