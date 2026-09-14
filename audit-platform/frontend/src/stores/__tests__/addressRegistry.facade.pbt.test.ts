/**
 * addressRegistry.facade.pbt.test.ts — useAddressRegistry ACNR facade 契约不变性 属性 + 单元测试
 *
 * spec acnr-consumer-wiring Task 18.4（store facade 由 18.1 收敛）
 *
 * 覆盖：
 *  - **Property 21: Store Facade Contract Invariance**
 *      store 的 resolve / validate / search 无论走 ACNR-hit 还是 legacy-fallback，
 *      返回值 shape（ResolveResult / ValidateResult / AddressEntry[]）恒一致。
 *  - 单测：ACNR-hit vs legacy-fallback 分支各自返回契约形态
 *
 * **Validates: Requirements 16.1, 16.2, 16.4**
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import * as fc from 'fast-check'

// ─── Mock http（get/post 受控；vi.hoisted 保证 factory 前初始化） ───────────────
const { mockHttpGet, mockHttpPost } = vi.hoisted(() => ({
  mockHttpGet: vi.fn(),
  mockHttpPost: vi.fn(),
}))
vi.mock('@/utils/http', () => ({
  default: { get: mockHttpGet, post: mockHttpPost },
}))

// ─── Mock useAcnr（受控 hit/miss） ─────────────────────────────────────────────
const {
  mockAcnrResolveUri,
  mockAcnrResolveFormula,
  mockAcnrListSheets,
  mockAcnrListCells,
  mockAcnrClearCache,
} = vi.hoisted(() => ({
  mockAcnrResolveUri: vi.fn(),
  mockAcnrResolveFormula: vi.fn(),
  mockAcnrListSheets: vi.fn(),
  mockAcnrListCells: vi.fn(),
  mockAcnrClearCache: vi.fn(),
}))
vi.mock('@/services/acnr/useAcnr', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/services/acnr/useAcnr')>()
  return {
    ...actual,
    useAcnr: () => ({
      resolveUri: mockAcnrResolveUri,
      resolveFormula: mockAcnrResolveFormula,
      listSheets: mockAcnrListSheets,
      listCells: mockAcnrListCells,
      clearCache: mockAcnrClearCache,
    }),
  }
})

// ─── Import after mocks ───────────────────────────────────────────────────────
import { createPinia, setActivePinia } from 'pinia'
import { useAddressRegistry } from '../addressRegistry'

// ─── Shape 断言辅助 ────────────────────────────────────────────────────────────

/** ResolveResult 必备契约：found:boolean + uri:string */
function assertResolveShape(r: any) {
  expect(r).toBeTypeOf('object')
  expect(typeof r.found).toBe('boolean')
  expect(typeof r.uri).toBe('string')
}

/** ValidateResult 必备契约：valid:boolean + issues:array + formula:string */
function assertValidateShape(r: any) {
  expect(r).toBeTypeOf('object')
  expect(typeof r.valid).toBe('boolean')
  expect(Array.isArray(r.issues)).toBe(true)
  expect(typeof r.formula).toBe('string')
}

/** AddressEntry[] 契约：数组，每项含 AddressEntry 必备键 */
const ADDRESS_ENTRY_KEYS = ['uri', 'domain', 'source', 'path', 'cell', 'label', 'formula_ref', 'jump_route']
function assertSearchShape(rows: any) {
  expect(Array.isArray(rows)).toBe(true)
  for (const e of rows) {
    for (const k of ADDRESS_ENTRY_KEYS) expect(e).toHaveProperty(k)
  }
}

// 后端 legacy 响应固定形态（模拟真实契约）
const LEGACY_RESOLVE = {
  found: true,
  uri: 'wp://D2/明细表D2-2#E100',
  label: '期末余额',
  formula_ref: "WP('D2','明细表D2-2','E100')",
  jump_route: '/workpaper/D2',
  domain: 'wp',
  tags: [],
}
const LEGACY_VALIDATE = { valid: true, issues: [], formula: '' }
const LEGACY_SEARCH_ENTRY = {
  uri: 'tb://1122',
  domain: 'tb',
  source: '1122',
  path: '',
  cell: '',
  label: '银行存款',
  formula_ref: "TB('1122','审定数')",
  jump_route: '',
}
const ACNR_HIT_RESOLVE = {
  found: true,
  addr_id: 'D2/D2-2/E100',
  uri: 'wp://D2/明细表D2-2#E100',
  semantic_label: '期末余额',
  formula_ref: "WP('D2','明细表D2-2','E100')",
  jump_route: '/workpaper/D2',
}

function freshStore() {
  setActivePinia(createPinia())
  return useAddressRegistry()
}

describe('Store facade — 基础契约（ACNR-hit vs legacy-fallback 分支）', () => {
  let store: ReturnType<typeof useAddressRegistry>
  beforeEach(() => {
    vi.clearAllMocks()
    store = freshStore()
  })
  afterEach(() => store.dispose())

  it('resolve — ACNR-hit 返回 ResolveResult 契约形态', async () => {
    mockAcnrResolveUri.mockResolvedValue(ACNR_HIT_RESOLVE)
    const r = await store.resolve('wp://D2/明细表D2-2#E100')
    assertResolveShape(r)
    expect(r.found).toBe(true)
    expect(r.uri).toBe('wp://D2/明细表D2-2#E100')
    expect(r.formula_ref).toBe("WP('D2','明细表D2-2','E100')")
    // 未经 legacy http
    expect(mockHttpGet).not.toHaveBeenCalled()
  })

  it('resolve — ACNR miss → legacy fallback 返回 ResolveResult 契约形态', async () => {
    mockAcnrResolveUri.mockResolvedValue({ found: false, error: 'invalid_uri' })
    mockHttpGet.mockResolvedValue({ data: LEGACY_RESOLVE })
    await store.refresh('pid-1', 2025) // 设置 _projectId，使 legacy 分支可达
    mockHttpGet.mockResolvedValue({ data: LEGACY_RESOLVE })

    const r = await store.resolve('wp://D2/明细表D2-2#E100')
    assertResolveShape(r)
    expect(r.found).toBe(true)
    // legacy 分支确实被调用
    expect(mockAcnrResolveUri).toHaveBeenCalled()
  })

  it('validate — ACNR-hit（found=true）判定 valid，契约形态一致', async () => {
    mockAcnrResolveFormula.mockResolvedValue({ found: true })
    const r = await store.validate("WP('D2','明细表D2-2','E100')")
    assertValidateShape(r)
    expect(r.valid).toBe(true)
    expect(r.issues).toEqual([])
  })

  it('validate — ACNR miss → legacy fallback，契约形态一致', async () => {
    mockAcnrResolveFormula.mockResolvedValue({ found: false })
    await store.refresh('pid-1', 2025)
    mockHttpPost.mockResolvedValue({
      data: { valid: false, issues: [{ ref: 'X', reason: 'not_found' }], formula: 'X+Y' },
    })
    const r = await store.validate('X+Y')
    assertValidateShape(r)
    expect(r.valid).toBe(false)
    expect(r.issues.length).toBe(1)
  })

  it('search — wp 域走 ACNR listSheets/listCells，返回 AddressEntry[] 契约', async () => {
    await store.refresh('pid-1', 2025)
    mockHttpGet.mockResolvedValue({ data: { items: [] } })
    mockAcnrListSheets.mockResolvedValue([
      { addr_id: 'D2/D2-2', domain: 'wp', cycle: 'D', parent_wp_code: 'D2', sheet_code: 'D2-2', sheet_name: '明细表D2-2' },
    ])
    mockAcnrListCells.mockResolvedValue([
      { addr_id: 'D2/D2-2/E100', parent_addr_id: 'D2/D2-2', domain: 'wp', cell_address: 'E100', semantic_label: '期末余额', formula_ref: "WP('D2','明细表D2-2','E100')" },
    ])

    const rows = await store.search('D2', 'wp')
    assertSearchShape(rows)
    expect(rows.length).toBeGreaterThan(0)
    expect(mockAcnrListSheets).toHaveBeenCalled()
  })

  it('search — 非 wp 域走 legacy，返回 AddressEntry[] 契约', async () => {
    await store.refresh('pid-1', 2025)
    mockHttpGet.mockResolvedValue({ data: { items: [LEGACY_SEARCH_ENTRY] } })
    const rows = await store.search('1122', 'tb')
    assertSearchShape(rows)
  })
})

// ══════════════════════════════════════════════════════════════════════════════
// Property 21 — Store Facade Contract Invariance
// ══════════════════════════════════════════════════════════════════════════════

describe('Property 21 — Store facade 契约不变性（ACNR-hit ⇔ legacy-fallback shape 恒一致）', () => {
  afterEach(() => {
    try {
      useAddressRegistry().dispose()
    } catch {
      /* pinia 未激活时忽略 */
    }
  })

  it('resolve — 任意 uri × {ACNR-hit, ACNR-miss+legacy} 均返回同一 ResolveResult 契约', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 40 }),
        fc.boolean(),
        async (uri, acnrHit) => {
          vi.clearAllMocks()
          const store = freshStore()
          if (acnrHit) {
            mockAcnrResolveUri.mockResolvedValue({ ...ACNR_HIT_RESOLVE, uri })
          } else {
            mockAcnrResolveUri.mockResolvedValue({ found: false, error: 'invalid_uri' })
            await store.refresh('pid-x', 2025)
            mockHttpGet.mockResolvedValue({ data: { ...LEGACY_RESOLVE, uri } })
          }
          const r = await store.resolve(uri)
          assertResolveShape(r)
          store.dispose()
        },
      ),
      { numRuns: 30 },
    )
  })

  it('validate — 任意 formula × {ACNR-hit, ACNR-miss+legacy} 均返回同一 ValidateResult 契约', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 1, maxLength: 40 }),
        fc.boolean(),
        async (formula, acnrHit) => {
          vi.clearAllMocks()
          const store = freshStore()
          if (acnrHit) {
            mockAcnrResolveFormula.mockResolvedValue({ found: true })
          } else {
            mockAcnrResolveFormula.mockResolvedValue({ found: false })
            await store.refresh('pid-x', 2025)
            mockHttpPost.mockResolvedValue({ data: { ...LEGACY_VALIDATE, formula } })
          }
          const r = await store.validate(formula)
          assertValidateShape(r)
          expect(r.formula).toBe(formula)
          store.dispose()
        },
      ),
      { numRuns: 30 },
    )
  })

  it('search — wp 域（ACNR）与非 wp 域（legacy）均返回 AddressEntry[] 契约', async () => {
    await fc.assert(
      fc.asyncProperty(
        fc.string({ minLength: 0, maxLength: 20 }),
        fc.constantFrom('wp', 'tb', 'report', 'note', 'aux'),
        async (keyword, domain) => {
          vi.clearAllMocks()
          const store = freshStore()
          await store.refresh('pid-x', 2025)
          mockHttpGet.mockResolvedValue({ data: { items: [LEGACY_SEARCH_ENTRY] } })
          mockAcnrListSheets.mockResolvedValue([
            { addr_id: 'D2/D2-2', domain: 'wp', cycle: 'D', parent_wp_code: 'D2', sheet_code: 'D2-2', sheet_name: '明细表D2-2' },
          ])
          mockAcnrListCells.mockResolvedValue([])
          const rows = await store.search(keyword, domain)
          assertSearchShape(rows)
          store.dispose()
        },
      ),
      { numRuns: 30 },
    )
  })
})
