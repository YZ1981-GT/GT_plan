/**
 * Property-Based Tests for useAuditData SDK
 *
 * Feature: platform-global-hardening, Property 6/7/8/9
 * Requirements: 5.2, 5.3, 5.4, 5.6
 *
 * Uses vitest + fast-check with { numRuns: 100 }
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import * as fc from 'fast-check'
import {
  useAuditData,
  normalizeTbRow,
  normalizeLedgerEntry,
  resolveKoujing,
  detectAccountDomain,
} from '../useAuditData'

// ─── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn().mockResolvedValue({ items: [] }),
    post: vi.fn(),
  },
}))

vi.mock('@/composables/useLedgerCache', () => ({
  useLedgerCache: () => ({
    getEntries: vi.fn().mockResolvedValue([]),
  }),
  LedgerCacheEntry: {},
}))

import { api } from '@/services/apiProxy'

// ─── Helpers ────────────────────────────────────────────────────────────────────

const mockedGet = vi.mocked(api.get)

/** Generate a valid year (2001..2099) */
const arbValidYear = fc.integer({ min: 2001, max: 2099 })

/** Generate an invalid/problematic year value (NaN, undefined-like, <=2000) */
const arbInvalidYear = fc.oneof(
  fc.constant(NaN),
  fc.constant(0),
  fc.constant(-1),
  fc.constant(2000),
  fc.constant(1999),
  fc.constant(Infinity),
  fc.constant(-Infinity),
)

// ─── Property 6: year 自动解析后底层请求永不缺失 year ────────────────────────────
// **Validates: Requirements 5.2**

describe('Property 6: year 自动解析后底层请求永不缺失 year', () => {
  beforeEach(() => {
    vi.clearAllMocks()
    mockedGet.mockResolvedValue({ items: [] })
  })

  it('for any valid year, getTbAmount request SHALL have a finite integer year > 2000', async () => {
    await fc.assert(
      fc.asyncProperty(arbValidYear, fc.constantFrom('1001', '2202', '6001'), async (year, code) => {
        vi.clearAllMocks()
        mockedGet.mockResolvedValue({ items: [] })

        const projectId = ref('proj-test')
        const yearRef = ref(year)
        const sdk = useAuditData(projectId, yearRef)

        await sdk.getTbAmount(code)

        expect(mockedGet).toHaveBeenCalled()
        const callArgs = mockedGet.mock.calls[0]
        const params = (callArgs[1] as any)?.params
        expect(params).toBeDefined()
        expect(params.year).toBeDefined()
        expect(Number.isFinite(params.year)).toBe(true)
        expect(Number.isInteger(params.year)).toBe(true)
        expect(params.year).toBeGreaterThan(2000)
      }),
      { numRuns: 100 },
    )
  })

  it('for any invalid year, getTbAmount SHALL still have a finite integer year > 2000 (fallback)', async () => {
    await fc.assert(
      fc.asyncProperty(arbInvalidYear, async (badYear) => {
        vi.clearAllMocks()
        mockedGet.mockResolvedValue({ items: [] })

        const projectId = ref('proj-test')
        const yearRef = ref(badYear)
        const sdk = useAuditData(projectId, yearRef)

        await sdk.getTbAmount('1122')

        expect(mockedGet).toHaveBeenCalled()
        const callArgs = mockedGet.mock.calls[0]
        const params = (callArgs[1] as any)?.params
        expect(params).toBeDefined()
        expect(params.year).toBeDefined()
        expect(Number.isFinite(params.year)).toBe(true)
        expect(Number.isInteger(params.year)).toBe(true)
        expect(params.year).toBeGreaterThan(2000)
      }),
      { numRuns: 100 },
    )
  })

  it('for any valid year, getPrevYear request SHALL have a finite integer year > 2000', async () => {
    await fc.assert(
      fc.asyncProperty(arbValidYear, async (year) => {
        vi.clearAllMocks()
        mockedGet.mockResolvedValue({ items: [] })

        const projectId = ref('proj-test')
        const yearRef = ref(year)
        const sdk = useAuditData(projectId, yearRef)

        await sdk.getPrevYear('1122')

        expect(mockedGet).toHaveBeenCalled()
        const callArgs = mockedGet.mock.calls[0]
        const params = (callArgs[1] as any)?.params
        expect(params).toBeDefined()
        expect(params.year).toBeDefined()
        expect(Number.isFinite(params.year)).toBe(true)
        expect(Number.isInteger(params.year)).toBe(true)
        // getPrevYear uses year - 1, so it must be > 2000 when year > 2001
        expect(params.year).toBeGreaterThanOrEqual(2000)
      }),
      { numRuns: 100 },
    )
  })

  it('when year ref is omitted (undefined), requests SHALL have a valid fallback year', async () => {
    vi.clearAllMocks()
    mockedGet.mockResolvedValue({ items: [] })

    const projectId = ref('proj-test')
    // No year ref provided
    const sdk = useAuditData(projectId)

    await sdk.getTbAmount('1122')

    expect(mockedGet).toHaveBeenCalled()
    const callArgs = mockedGet.mock.calls[0]
    const params = (callArgs[1] as any)?.params
    expect(params).toBeDefined()
    expect(params.year).toBeDefined()
    expect(Number.isFinite(params.year)).toBe(true)
    expect(Number.isInteger(params.year)).toBe(true)
    expect(params.year).toBeGreaterThan(2000)
  })
})

// ─── Property 7: 字段归一化在任意别名组合下产出稳定语义字段 ─────────────────────
// **Validates: Requirements 5.3**

describe('Property 7: 字段归一化在任意别名组合下产出稳定语义字段', () => {
  // TB row aliases for each semantic field
  const tbAccountCodeAliases = ['account_code', 'accountCode', 'standard_account_code', 'code'] as const
  const tbAccountNameAliases = ['account_name', 'accountName', 'name'] as const
  const tbDebitAliases = ['debit_amount', 'debitAmount', 'debit'] as const
  const tbCreditAliases = ['credit_amount', 'creditAmount', 'credit'] as const
  const tbBalanceAliases = ['balance', 'ending_balance', 'endingBalance'] as const
  const tbUnadjustedAliases = ['unadjusted_amount', 'unadjustedAmount', 'unadjusted'] as const
  const tbAuditedAliases = ['audited_amount', 'auditedAmount', 'audited'] as const
  const tbAjeAliases = ['aje_adjustment', 'ajeAdjustment', 'aje'] as const

  // Ledger entry aliases
  const ledgerDateAliases = ['voucher_date', 'voucherDate', 'date'] as const
  const ledgerNoAliases = ['voucher_no', 'voucherNo', 'no'] as const
  const ledgerCodeAliases = ['account_code', 'accountCode', 'code'] as const
  const ledgerNameAliases = ['account_name', 'accountName', 'name'] as const
  const ledgerDebitAliases = ['debit_amount', 'debitAmount', 'debit'] as const
  const ledgerCreditAliases = ['credit_amount', 'creditAmount', 'credit'] as const
  const ledgerSummaryAliases = ['summary', 'abstract', 'description'] as const
  const ledgerPreparerAliases = ['preparer', 'maker'] as const

  const arbTbRow = fc.record({
    codeAlias: fc.constantFrom(...tbAccountCodeAliases),
    nameAlias: fc.constantFrom(...tbAccountNameAliases),
    debitAlias: fc.constantFrom(...tbDebitAliases),
    creditAlias: fc.constantFrom(...tbCreditAliases),
    balanceAlias: fc.constantFrom(...tbBalanceAliases),
    unadjustedAlias: fc.constantFrom(...tbUnadjustedAliases),
    auditedAlias: fc.constantFrom(...tbAuditedAliases),
    ajeAlias: fc.constantFrom(...tbAjeAliases),
    codeVal: fc.string({ minLength: 1, maxLength: 10 }),
    nameVal: fc.string({ minLength: 1, maxLength: 20 }),
    debitVal: fc.float({ min: 0, max: 1e9, noNaN: true }),
    creditVal: fc.float({ min: 0, max: 1e9, noNaN: true }),
    balanceVal: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
    unadjustedVal: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
    auditedVal: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
    ajeVal: fc.float({ min: -1e9, max: 1e9, noNaN: true }),
  })

  it('normalizeTbRow produces stable semantic fields regardless of alias choice', () => {
    fc.assert(
      fc.property(arbTbRow, (gen) => {
        const raw: Record<string, any> = {}
        raw[gen.codeAlias] = gen.codeVal
        raw[gen.nameAlias] = gen.nameVal
        raw[gen.debitAlias] = gen.debitVal
        raw[gen.creditAlias] = gen.creditVal
        raw[gen.balanceAlias] = gen.balanceVal
        raw[gen.unadjustedAlias] = gen.unadjustedVal
        raw[gen.auditedAlias] = gen.auditedVal
        raw[gen.ajeAlias] = gen.ajeVal

        const result = normalizeTbRow(raw)

        // Stable field names always present
        expect(result).toHaveProperty('accountCode')
        expect(result).toHaveProperty('accountName')
        expect(result).toHaveProperty('debitAmount')
        expect(result).toHaveProperty('creditAmount')
        expect(result).toHaveProperty('balance')
        expect(result).toHaveProperty('unadjustedAmount')
        expect(result).toHaveProperty('auditedAmount')
        expect(result).toHaveProperty('ajeAdjustment')
        expect(result).toHaveProperty('direction')

        // Values preserved (Number coercion applied)
        expect(result.accountCode).toBe(gen.codeVal)
        expect(result.accountName).toBe(gen.nameVal)
        expect(result.debitAmount).toBe(Number(gen.debitVal))
        expect(result.creditAmount).toBe(Number(gen.creditVal))
        expect(result.balance).toBe(Number(gen.balanceVal))
        expect(result.unadjustedAmount).toBe(Number(gen.unadjustedVal))
        expect(result.auditedAmount).toBe(Number(gen.auditedVal))
        expect(result.ajeAdjustment).toBe(Number(gen.ajeVal))
      }),
      { numRuns: 100 },
    )
  })

  it('normalizeLedgerEntry produces stable semantic fields regardless of alias choice', () => {
    const arbLedgerRow = fc.record({
      dateAlias: fc.constantFrom(...ledgerDateAliases),
      noAlias: fc.constantFrom(...ledgerNoAliases),
      codeAlias: fc.constantFrom(...ledgerCodeAliases),
      nameAlias: fc.constantFrom(...ledgerNameAliases),
      debitAlias: fc.constantFrom(...ledgerDebitAliases),
      creditAlias: fc.constantFrom(...ledgerCreditAliases),
      summaryAlias: fc.constantFrom(...ledgerSummaryAliases),
      preparerAlias: fc.constantFrom(...ledgerPreparerAliases),
      dateVal: fc.string({ minLength: 8, maxLength: 10 }),
      noVal: fc.string({ minLength: 1, maxLength: 10 }),
      codeVal: fc.string({ minLength: 1, maxLength: 10 }),
      nameVal: fc.string({ minLength: 1, maxLength: 20 }),
      debitVal: fc.float({ min: 0, max: 1e9, noNaN: true }),
      creditVal: fc.float({ min: 0, max: 1e9, noNaN: true }),
      summaryVal: fc.string({ minLength: 0, maxLength: 50 }),
      preparerVal: fc.string({ minLength: 1, maxLength: 10 }),
    })

    fc.assert(
      fc.property(arbLedgerRow, (gen) => {
        const raw: Record<string, any> = {}
        raw[gen.dateAlias] = gen.dateVal
        raw[gen.noAlias] = gen.noVal
        raw[gen.codeAlias] = gen.codeVal
        raw[gen.nameAlias] = gen.nameVal
        raw[gen.debitAlias] = gen.debitVal
        raw[gen.creditAlias] = gen.creditVal
        raw[gen.summaryAlias] = gen.summaryVal
        raw[gen.preparerAlias] = gen.preparerVal

        const result = normalizeLedgerEntry(raw)

        // Stable field names always present
        expect(result).toHaveProperty('voucherDate')
        expect(result).toHaveProperty('voucherNo')
        expect(result).toHaveProperty('accountCode')
        expect(result).toHaveProperty('accountName')
        expect(result).toHaveProperty('debitAmount')
        expect(result).toHaveProperty('creditAmount')
        expect(result).toHaveProperty('balance')
        expect(result).toHaveProperty('summary')
        expect(result).toHaveProperty('preparer')

        // Values preserved
        expect(result.voucherDate).toBe(gen.dateVal)
        expect(result.voucherNo).toBe(gen.noVal)
        expect(result.accountCode).toBe(gen.codeVal)
        expect(result.accountName).toBe(gen.nameVal)
        expect(result.debitAmount).toBe(Number(gen.debitVal))
        expect(result.creditAmount).toBe(Number(gen.creditVal))
        expect(result.summary).toBe(gen.summaryVal)
        expect(result.preparer).toBe(gen.preparerVal)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 8: 取数口径按数据域正确解析 ───────────────────────────────────────
// **Validates: Requirements 5.4**

describe('Property 8: 取数口径按数据域正确解析', () => {
  /** Generate account code in asset domain (1xxx) */
  const arbAssetCode = fc.integer({ min: 1000, max: 1999 }).map(String)
  /** Generate account code in liability domain (2xxx) */
  const arbLiabilityCode = fc.integer({ min: 2000, max: 2999 }).map(String)
  /** Generate account code in equity domain (3xxx) */
  const arbEquityCode = fc.integer({ min: 3000, max: 3999 }).map(String)
  /** Generate account code in income_expense domain (4xxx/5xxx/6xxx) */
  const arbIncomeExpenseCode = fc.oneof(
    fc.integer({ min: 4000, max: 4999 }).map(String),
    fc.integer({ min: 5000, max: 5999 }).map(String),
    fc.integer({ min: 6000, max: 6999 }).map(String),
  )

  it('asset codes (1xxx) SHALL resolve to v1_debit_positive', () => {
    fc.assert(
      fc.property(arbAssetCode, (code) => {
        const koujing = resolveKoujing(code)
        expect(koujing).toBe('v1_debit_positive')
        expect(detectAccountDomain(code)).toBe('asset')
      }),
      { numRuns: 100 },
    )
  })

  it('liability codes (2xxx) SHALL resolve to v2_positive', () => {
    fc.assert(
      fc.property(arbLiabilityCode, (code) => {
        const koujing = resolveKoujing(code)
        expect(koujing).toBe('v2_positive')
        expect(detectAccountDomain(code)).toBe('liability')
      }),
      { numRuns: 100 },
    )
  })

  it('equity codes (3xxx) SHALL resolve to v2_positive', () => {
    fc.assert(
      fc.property(arbEquityCode, (code) => {
        const koujing = resolveKoujing(code)
        expect(koujing).toBe('v2_positive')
        expect(detectAccountDomain(code)).toBe('equity')
      }),
      { numRuns: 100 },
    )
  })

  it('income/expense codes (4xxx/5xxx/6xxx) SHALL resolve to pl_occurrence', () => {
    fc.assert(
      fc.property(arbIncomeExpenseCode, (code) => {
        const koujing = resolveKoujing(code)
        expect(koujing).toBe('pl_occurrence')
        expect(detectAccountDomain(code)).toBe('income_expense')
      }),
      { numRuns: 100 },
    )
  })

  it('resolveKoujing returns one of three valid koujing values for any valid code', () => {
    const arbAnyValidCode = fc.oneof(
      arbAssetCode,
      arbLiabilityCode,
      arbEquityCode,
      arbIncomeExpenseCode,
    )

    fc.assert(
      fc.property(arbAnyValidCode, (code) => {
        const koujing = resolveKoujing(code)
        expect(['v1_debit_positive', 'v2_positive', 'pl_occurrence']).toContain(koujing)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 9: 取数失败时返回降级值且不抛未捕获异常 ─────────────────────────────
// **Validates: Requirements 5.6**

describe('Property 9: 取数失败时返回降级值且不抛未捕获异常', () => {
  /** Arbitrary failure modes */
  const arbFailureMode = fc.constantFrom(
    'reject-error',
    'reject-string',
    'null-response',
    'undefined-response',
    'empty-object',
    'missing-items',
    'malformed-array',
    'items-null',
    'items-not-array',
  )

  function injectFailure(mode: string) {
    switch (mode) {
      case 'reject-error':
        mockedGet.mockRejectedValue(new Error('Network failure'))
        break
      case 'reject-string':
        mockedGet.mockRejectedValue('connection refused')
        break
      case 'null-response':
        mockedGet.mockResolvedValue(null)
        break
      case 'undefined-response':
        mockedGet.mockResolvedValue(undefined)
        break
      case 'empty-object':
        mockedGet.mockResolvedValue({})
        break
      case 'missing-items':
        mockedGet.mockResolvedValue({ data: null })
        break
      case 'malformed-array':
        mockedGet.mockResolvedValue({ items: 'not-an-array' })
        break
      case 'items-null':
        mockedGet.mockResolvedValue({ items: null })
        break
      case 'items-not-array':
        mockedGet.mockResolvedValue({ items: 42 })
        break
    }
  }

  it('getTbAmount SHALL resolve to 0 and NOT throw for any failure mode', async () => {
    await fc.assert(
      fc.asyncProperty(arbFailureMode, fc.constantFrom('1001', '2202', '6001'), async (mode, code) => {
        vi.clearAllMocks()
        injectFailure(mode)

        const projectId = ref('proj-test')
        const year = ref(2025)
        const sdk = useAuditData(projectId, year)

        // Should never throw
        const result = await sdk.getTbAmount(code)
        expect(result).toBe(0)
      }),
      { numRuns: 100 },
    )
  })

  it('getPrevYear SHALL resolve to 0 and NOT throw for any failure mode', async () => {
    await fc.assert(
      fc.asyncProperty(arbFailureMode, async (mode) => {
        vi.clearAllMocks()
        injectFailure(mode)

        const projectId = ref('proj-test')
        const year = ref(2025)
        const sdk = useAuditData(projectId, year)

        const result = await sdk.getPrevYear('1122')
        expect(result).toBe(0)
      }),
      { numRuns: 100 },
    )
  })

  it('getAging SHALL resolve to [] and NOT throw for any failure mode', async () => {
    await fc.assert(
      fc.asyncProperty(arbFailureMode, async (mode) => {
        vi.clearAllMocks()
        injectFailure(mode)

        const projectId = ref('proj-test')
        const year = ref(2025)
        const sdk = useAuditData(projectId, year)

        const result = await sdk.getAging('D2')
        expect(Array.isArray(result)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })

  it('getLedgerEntries SHALL resolve to [] and NOT throw when cache fails', async () => {
    // For this test, we need to mock the ledger cache to throw
    const { useLedgerCache } = await import('@/composables/useLedgerCache')
    const cache = useLedgerCache()
    vi.mocked(cache.getEntries).mockRejectedValue(new Error('Cache exploded'))

    const projectId = ref('proj-test')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    const result = await sdk.getLedgerEntries()
    expect(Array.isArray(result)).toBe(true)
    expect(result).toEqual([])
  })

  it('all methods resolve without throwing for random error messages', async () => {
    await fc.assert(
      fc.asyncProperty(fc.string({ minLength: 0, maxLength: 100 }), async (errorMsg) => {
        vi.clearAllMocks()
        mockedGet.mockRejectedValue(new Error(errorMsg))

        const projectId = ref('proj-test')
        const year = ref(2025)
        const sdk = useAuditData(projectId, year)

        // None of these should throw
        const [tb, prev, aging] = await Promise.all([
          sdk.getTbAmount('1122'),
          sdk.getPrevYear('2202'),
          sdk.getAging('K1'),
        ])

        expect(tb).toBe(0)
        expect(prev).toBe(0)
        expect(Array.isArray(aging)).toBe(true)
      }),
      { numRuns: 100 },
    )
  })
})
