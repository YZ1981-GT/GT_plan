/**
 * 地址库保存前校验：只有「整条公式就是单个 WP 引用」才用 ACNR 命中短路，其余一律走带项目的数据校验
 * （spec formula-fetch-followup-defect-closure R5.4）。
 *
 * 原状：先问 ACNR，`found` 即判有效 —— 而 ACNR 对试算表 / 报表 / 附注引用只做写法换算就 `found=true`，复合表达式取第一个
 * 引用也判命中 ⇒ `TB('9999',…)`、`WP(…)+TB('9999',…)` 这类悬空引用被短路放行，后端数据校验根本没被调用。
 */
import { beforeEach, describe, expect, it, vi } from 'vitest'

const { mockHttpGet, mockHttpPost, mockResolveFormula, mockResolveUri } = vi.hoisted(() => ({
  mockHttpGet: vi.fn(), mockHttpPost: vi.fn(), mockResolveFormula: vi.fn(), mockResolveUri: vi.fn(),
}))
vi.mock('@/utils/http', () => ({ default: { get: mockHttpGet, post: mockHttpPost } }))
vi.mock('@/services/acnr/useAcnr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/acnr/useAcnr')>()
  return {
    ...actual,
    useAcnr: () => ({
      resolveUri: mockResolveUri, resolveFormula: mockResolveFormula,
      listSheets: vi.fn().mockResolvedValue([]), listCells: vi.fn().mockResolvedValue([]), clearCache: vi.fn(),
    }),
  }
})

import { createPinia, setActivePinia } from 'pinia'
import { SINGLE_WP_REF, useAddressRegistry } from '../addressRegistry'

const DANGLING = { valid: false, issues: [{ ref: "TB('9999','期末余额')", message: '本年度（2025）试算表没有科目 9999' }] }

async function storeBoundTo(pid: string) {
  setActivePinia(createPinia())
  const store = useAddressRegistry()
  mockHttpGet.mockResolvedValue({ data: { items: [] } })
  await store.refresh(pid, 2025, 'listed')
  return store
}

describe('地址库 validate 的 ACNR 短路范围', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockResolveFormula.mockResolvedValue({ found: true })  // 假设 ACNR 一律说「存在」（原状）
    mockHttpPost.mockResolvedValue({ data: DANGLING })
  })

  it.each([
    "TB('9999','期末余额')",
    "NOTE('五、1','不存在的行','期末余额')",
    "WP('D2','明细表D2-2','E100')+TB('9999','期末余额')",
    "WP('D2','明细表D2-2','E100') * 2",
  ])('不是单个 WP 引用：不问 ACNR，走带项目的数据校验并如实报悬空 —— %s', async (formula) => {
    const store = await storeBoundTo('pid-1')
    const r = await store.validate(formula)
    expect(mockResolveFormula).not.toHaveBeenCalled()
    expect(mockHttpPost).toHaveBeenCalledWith(expect.stringContaining('/validate'), {
      formula, project_id: 'pid-1', year: 2025, template_type: 'listed',
    })
    expect(r.valid).toBe(false)
  })

  it.each(["WP('D2','明细表D2-2','E100')", " WP( 'CUST-01' , 'B7' ) "])('单个 WP 引用：ACNR 命中即有效，且带项目 —— %s', async (formula) => {
    const store = await storeBoundTo('pid-1')
    const r = await store.validate(formula)
    expect(r).toEqual({ valid: true, issues: [], formula })
    expect(mockResolveFormula).toHaveBeenCalledWith(formula, 'pid-1')
    expect(mockHttpPost).not.toHaveBeenCalled()
  })

  it('单个 WP 引用但 ACNR 未命中：照样回退数据校验', async () => {
    mockResolveFormula.mockResolvedValue({ found: false })
    const store = await storeBoundTo('pid-1')
    await store.validate("WP('X9','X9-1','Z1')")
    expect(mockHttpPost).toHaveBeenCalledTimes(1)
  })

  it('SINGLE_WP_REF 只认两参 / 三参的单个 WP 引用', () => {
    for (const s of ["WP('a','b')", "WP('a','b','c')", "  WP( 'a' , 'b' , 'c' )  "]) expect(SINGLE_WP_REF.test(s)).toBe(true)
    for (const s of ["WP('a')", "WP('a','b','c','d')", "WP('a','b')+1", "TB('1001','期末余额')", "PREV('a','b','c')"]) {
      expect(SINGLE_WP_REF.test(s)).toBe(false)
    }
  })

  it('resolve 带当前绑定的项目（非底稿域按项目数据判存在）', async () => {
    mockResolveUri.mockResolvedValue({ found: true, uri: 'tb://1001#期末余额' })
    const store = await storeBoundTo('pid-1')
    await store.resolve('tb://1001#期末余额')
    expect(mockResolveUri).toHaveBeenCalledWith('tb://1001#期末余额', 'pid-1')
  })
})
