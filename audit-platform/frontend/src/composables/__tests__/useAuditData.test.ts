/**
 * Unit tests for useAuditData SDK
 *
 * Feature: platform-global-hardening
 * Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useAuditData,
  normalizeTbRow,
  normalizeLedgerEntry,
  resolveKoujing,
  detectAccountDomain,
  isDebitAccount,
} from '../useAuditData'

// ─── Mocks ─────────────────────────────────────────────────────────────────────

vi.mock('@/services/apiProxy', () => ({
  api: {
    get: vi.fn(),
    post: vi.fn(),
  },
}))

vi.mock('@/composables/useLedgerCache', () => ({
  useLedgerCache: () => ({
    getEntries: vi.fn().mockResolvedValue([
      {
        voucherDate: '2025-03-15',
        voucherNo: 'PZ-001',
        accountCode: '1122',
        accountName: '应收账款',
        debitAmount: 50000,
        creditAmount: 0,
        summary: '销售收入',
        preparer: '张三',
      },
      {
        voucherDate: '2025-04-01',
        voucherNo: 'PZ-002',
        accountCode: '6001',
        accountName: '主营业务收入',
        debitAmount: 0,
        creditAmount: 80000,
        summary: '产品销售',
        preparer: '李四',
      },
    ]),
  }),
  LedgerCacheEntry: {},
}))

// ─── normalizeTbRow tests (Task 7.2) ───────────────────────────────────────────

describe('normalizeTbRow - 字段归一化层', () => {
  it('should normalize snake_case fields', () => {
    const row = {
      account_code: '1122',
      account_name: '应收账款',
      debit_amount: 100000,
      credit_amount: 50000,
      balance: 50000,
      unadjusted_amount: 48000,
      audited_amount: 50000,
      aje_adjustment: 2000,
      direction: '借',
    }
    const result = normalizeTbRow(row)
    expect(result.accountCode).toBe('1122')
    expect(result.accountName).toBe('应收账款')
    expect(result.debitAmount).toBe(100000)
    expect(result.creditAmount).toBe(50000)
    expect(result.balance).toBe(50000)
    expect(result.unadjustedAmount).toBe(48000)
    expect(result.auditedAmount).toBe(50000)
    expect(result.ajeAdjustment).toBe(2000)
    expect(result.direction).toBe('借')
  })

  it('should normalize camelCase fields', () => {
    const row = {
      accountCode: '2202',
      accountName: '应付账款',
      debitAmount: 30000,
      creditAmount: 80000,
      endingBalance: 50000,
      unadjustedAmount: 49000,
      auditedAmount: 50000,
      ajeAdjustment: 1000,
    }
    const result = normalizeTbRow(row)
    expect(result.accountCode).toBe('2202')
    expect(result.balance).toBe(50000)
    expect(result.unadjustedAmount).toBe(49000)
  })

  it('should handle alternative field names', () => {
    const row = {
      standard_account_code: '1001',
      name: '货币资金',
      debit: 200000,
      credit: 100000,
      ending_balance: 100000,
      unadjusted: 95000,
      audited: 100000,
      aje: 5000,
      debit_credit: '借',
    }
    const result = normalizeTbRow(row)
    expect(result.accountCode).toBe('1001')
    expect(result.accountName).toBe('货币资金')
    expect(result.debitAmount).toBe(200000)
    expect(result.creditAmount).toBe(100000)
    expect(result.direction).toBe('借')
  })

  it('should default to 0 for missing numeric fields', () => {
    const row = {}
    const result = normalizeTbRow(row)
    expect(result.accountCode).toBe('')
    expect(result.debitAmount).toBe(0)
    expect(result.creditAmount).toBe(0)
    expect(result.balance).toBe(0)
    expect(result.unadjustedAmount).toBe(0)
    expect(result.auditedAmount).toBe(0)
  })
})

// ─── normalizeLedgerEntry tests (Task 7.2) ──────────────────────────────────────

describe('normalizeLedgerEntry - 序时账归一化', () => {
  it('should normalize snake_case entry', () => {
    const raw = {
      voucher_date: '2025-06-15',
      voucher_no: 'PZ-100',
      account_code: '6001',
      account_name: '主营业务收入',
      debit_amount: 0,
      credit_amount: 120000,
      summary: '产品销售',
      preparer: '王五',
    }
    const result = normalizeLedgerEntry(raw)
    expect(result.voucherDate).toBe('2025-06-15')
    expect(result.voucherNo).toBe('PZ-100')
    expect(result.accountCode).toBe('6001')
    expect(result.creditAmount).toBe(120000)
    expect(result.preparer).toBe('王五')
  })

  it('should handle alternative field names', () => {
    const raw = {
      date: '2025-01-01',
      no: 'V-001',
      code: '1001',
      name: '库存现金',
      debit: 5000,
      credit: 0,
      abstract: '备用金',
      maker: '赵六',
    }
    const result = normalizeLedgerEntry(raw)
    expect(result.voucherDate).toBe('2025-01-01')
    expect(result.voucherNo).toBe('V-001')
    expect(result.accountCode).toBe('1001')
    expect(result.summary).toBe('备用金')
    expect(result.preparer).toBe('赵六')
  })
})

// ─── detectAccountDomain tests (Task 7.3) ───────────────────────────────────────

describe('detectAccountDomain - 科目数据域判定', () => {
  it('should detect asset domain for 1xxx codes', () => {
    expect(detectAccountDomain('1001')).toBe('asset')
    expect(detectAccountDomain('1122')).toBe('asset')
    expect(detectAccountDomain('1601')).toBe('asset')
  })

  it('should detect liability domain for 2xxx codes', () => {
    expect(detectAccountDomain('2001')).toBe('liability')
    expect(detectAccountDomain('2202')).toBe('liability')
    expect(detectAccountDomain('2501')).toBe('liability')
  })

  // 现行企业会计准则科目表：4xxx 所有者权益（4001 实收资本 / 4002 资本公积 / 4003 其他综合收益 /
  // 4101 盈余公积 / 4104 利润分配 / 4201 库存股 / 4301 专项储备 / 4401 其他权益工具）。
  // 旧版本按旧制科目表把 4001 判成损益、3xxx 判成权益 —— 实收资本会去取发生额。
  it('should detect equity domain for 4xxx codes', () => {
    expect(detectAccountDomain('4001')).toBe('equity')
    expect(detectAccountDomain('4003')).toBe('equity')
    expect(detectAccountDomain('4104')).toBe('equity')
    expect(detectAccountDomain('4201')).toBe('equity')
    expect(detectAccountDomain('4401')).toBe('equity')
  })

  it('should treat 3xxx common and 5xxx cost codes as balance (asset) accounts', () => {
    expect(detectAccountDomain('3101')).toBe('asset') // 衍生工具
    expect(detectAccountDomain('3201')).toBe('asset') // 套期工具
    expect(detectAccountDomain('5001')).toBe('asset') // 生产成本
    expect(detectAccountDomain('5301')).toBe('asset') // 研发支出
  })

  it('should detect income_expense domain for 6xxx codes', () => {
    expect(detectAccountDomain('6001')).toBe('income_expense')
    expect(detectAccountDomain('6403')).toBe('income_expense')
    expect(detectAccountDomain('6711')).toBe('income_expense')
  })

  it('should default to asset for unknown codes', () => {
    expect(detectAccountDomain('')).toBe('asset')
    expect(detectAccountDomain('7001')).toBe('asset')
    expect(detectAccountDomain('9999')).toBe('asset')
  })
})

// ─── resolveKoujing tests (Task 7.3) ────────────────────────────────────────────

describe('resolveKoujing - 三口径按数据域', () => {
  it('should return v1_debit_positive for asset codes', () => {
    expect(resolveKoujing('1001')).toBe('v1_debit_positive')
    expect(resolveKoujing('1122')).toBe('v1_debit_positive')
    expect(resolveKoujing('1601')).toBe('v1_debit_positive')
  })

  it('should return v2_positive for liability codes', () => {
    expect(resolveKoujing('2001')).toBe('v2_positive')
    expect(resolveKoujing('2202')).toBe('v2_positive')
  })

  it('should return v2_positive for equity codes', () => {
    expect(resolveKoujing('4001')).toBe('v2_positive')
    expect(resolveKoujing('4201')).toBe('v2_positive')
  })

  it('should return pl_occurrence for income/expense codes', () => {
    expect(resolveKoujing('6001')).toBe('pl_occurrence')
    expect(resolveKoujing('6403')).toBe('pl_occurrence')
  })

  it('should return v1_debit_positive (balance) for 3xxx common / 5xxx cost codes', () => {
    expect(resolveKoujing('3101')).toBe('v1_debit_positive')
    expect(resolveKoujing('5001')).toBe('v1_debit_positive')
  })
})

// ─── isDebitAccount tests ───────────────────────────────────────────────────────

describe('isDebitAccount', () => {
  it('should identify asset accounts as debit', () => {
    expect(isDebitAccount('1001')).toBe(true)
    expect(isDebitAccount('1122')).toBe(true)
  })

  it('should identify 4201 treasury stock (and its sub-accounts) and 5xxx cost codes as debit', () => {
    expect(isDebitAccount('4201')).toBe(true)
    expect(isDebitAccount('4201-01')).toBe(true)
    expect(isDebitAccount('5001')).toBe(true)
  })

  it('should return false for liability/equity/income codes', () => {
    expect(isDebitAccount('2001')).toBe(false)
    expect(isDebitAccount('4001')).toBe(false)
    expect(isDebitAccount('4002')).toBe(false)
    expect(isDebitAccount('6001')).toBe(false)
  })
})

// ─── useAuditData composable tests (Task 7.1 + 7.4) ────────────────────────────

import { api } from '@/services/apiProxy'

describe('useAuditData - composable 骨架与错误降级', () => {
  const mockedGet = vi.mocked(api.get)

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('should return all expected methods and refs', () => {
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    expect(sdk.getTbAmount).toBeTypeOf('function')
    expect(sdk.getAging).toBeTypeOf('function')
    expect(sdk.getLedgerEntries).toBeTypeOf('function')
    expect(sdk.getPrevYear).toBeTypeOf('function')
    expect(sdk.loading).toBeDefined()
    expect(sdk.error).toBeDefined()
    expect(sdk.loading.value).toBe(false)
    expect(sdk.error.value).toBe('')
  })

  it('should resolve year from parameter when provided', () => {
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)
    // The year is used internally, we verify it through API calls
    expect(sdk).toBeDefined()
  })

  it('should degrade gracefully on getTbAmount failure', async () => {
    mockedGet.mockRejectedValue(new Error('Network error'))
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    const result = await sdk.getTbAmount('1122')
    expect(result).toBe(0)
    expect(sdk.error.value).toBe('Network error')
  })

  it('should degrade gracefully on getAging failure', async () => {
    mockedGet.mockRejectedValue(new Error('Server error'))
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    const result = await sdk.getAging('D2')
    expect(result).toEqual([])
    expect(sdk.error.value).toBe('Server error')
  })

  it('should degrade gracefully on getPrevYear failure', async () => {
    mockedGet.mockRejectedValue(new Error('Timeout'))
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    const result = await sdk.getPrevYear('1122')
    expect(result).toBe(0)
    expect(sdk.error.value).toBe('Timeout')
  })

  it('should return 0 when projectId is empty', async () => {
    const projectId = ref('')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    const result = await sdk.getTbAmount('1122')
    expect(result).toBe(0)
  })

  it('should use ledger cache for getLedgerEntries', async () => {
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    const entries = await sdk.getLedgerEntries()
    expect(entries.length).toBe(2)
    expect(entries[0].accountCode).toBe('1122')
  })

  it('should filter ledger entries by accountCode', async () => {
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    const entries = await sdk.getLedgerEntries({ accountCode: '6001' })
    expect(entries.length).toBe(1)
    expect(entries[0].accountCode).toBe('6001')
  })

  it('取数走试算表唯一入口：带年度与科目前缀，不再分 tb-balance / trial-balance 两个端点', async () => {
    mockedGet.mockResolvedValue([{ standard_account_code: '1122', audited_amount: '50000', unadjusted_amount: '48000' }])
    const sdk = useAuditData(ref('proj-1'), ref(2025))

    await sdk.getTbAmount('1122')
    expect(mockedGet).toHaveBeenCalledWith(
      '/api/projects/proj-1/trial-balance',
      expect.objectContaining({ params: { year: 2025, account_prefix: '1122' } }),
    )
  })

  it('should return audited amount by default（科目及其明细科目之和，与报表 TB() 同口径）', async () => {
    mockedGet.mockResolvedValue([
      { standard_account_code: '1122', audited_amount: '50000', unadjusted_amount: '48000' },
      { standard_account_code: '112201', audited_amount: '100', unadjusted_amount: '100' },
    ])
    const sdk = useAuditData(ref('proj-1'), ref(2025))

    expect(await sdk.getTbAmount('1122')).toBe(50100)
  })

  it('should return unadjusted amount when basis is unadjusted', async () => {
    mockedGet.mockResolvedValue([{ standard_account_code: '1122', audited_amount: '50000', unadjusted_amount: '48000' }])
    const sdk = useAuditData(ref('proj-1'), ref(2025))

    expect(await sdk.getTbAmount('1122', { basis: 'unadjusted' })).toBe(48000)
  })

  it('损益类取试算表单边发生额（收入贷方），不再用端点不返回的借 / 贷字段算「借 − 贷」', async () => {
    mockedGet.mockResolvedValue([
      { standard_account_code: '6001', direction: 'credit', audited_amount: '150000', unadjusted_amount: '140000' },
    ])
    const sdk = useAuditData(ref('proj-1'), ref(2025))

    expect(await sdk.getTbAmount('6001')).toBe(150000)
    expect(await sdk.getTbAmount('6001', { basis: 'unadjusted' })).toBe(140000)
  })

  it('科目不在试算表：返回 0 并写明原因（不静默）', async () => {
    mockedGet.mockResolvedValue([])
    const sdk = useAuditData(ref('proj-1'), ref(2025))

    expect(await sdk.getTbAmount('1122')).toBe(0)
    expect(sdk.error.value).toContain('1122')
  })

  it('getPrevYear 取上年审定数（include_prior，来源同报表上期），不拿「年度 − 1」去取本项目', async () => {
    mockedGet.mockResolvedValue([{ standard_account_code: '1122', audited_amount: '50000', prior_audited_amount: '45000' }])
    const sdk = useAuditData(ref('proj-1'), ref(2025))

    expect(await sdk.getPrevYear('1122')).toBe(45000)
    expect(mockedGet).toHaveBeenCalledWith(
      '/api/projects/proj-1/trial-balance',
      expect.objectContaining({ params: { year: 2025, account_prefix: '1122', include_prior: true } }),
    )
  })

  it('getPrevYear 上年没有该科目：返回 0 并写明原因', async () => {
    mockedGet.mockResolvedValue([{ standard_account_code: '1122', audited_amount: '50000', prior_audited_amount: null }])
    const sdk = useAuditData(ref('proj-1'), ref(2025))

    expect(await sdk.getPrevYear('1122')).toBe(0)
    expect(sdk.error.value).toContain('上年审定数')
  })

  it('年度不合法 / 未传：不带 year，由后端按项目审计年度取（不按日历猜）', async () => {
    mockedGet.mockResolvedValue([])
    const sdk = useAuditData(ref('proj-1'), ref(NaN))

    await sdk.getTbAmount('1122')
    const params = (mockedGet.mock.calls[0][1] as any).params
    expect(params).toEqual({ account_prefix: '1122' })
    expect(params.year).toBeUndefined()
  })

  it('序时账没有年度：不取、写明原因', async () => {
    const sdk = useAuditData(ref('proj-1'))
    expect(await sdk.getLedgerEntries()).toEqual([])
    expect(sdk.error.value).toContain('未设置审计年度')
  })

  it('should never throw uncaught exception (error degradation)', async () => {
    mockedGet.mockRejectedValue(new Error('Catastrophic failure'))
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    // All methods should resolve without throwing
    await expect(sdk.getTbAmount('1122')).resolves.toBe(0)
    await expect(sdk.getAging('D2')).resolves.toEqual([])
    await expect(sdk.getPrevYear('1122')).resolves.toBe(0)
  })

  it('should pass _silent: true with requests', async () => {
    mockedGet.mockResolvedValue({ items: [] })
    const projectId = ref('proj-1')
    const year = ref(2025)
    const sdk = useAuditData(projectId, year)

    await sdk.getTbAmount('1122')
    expect(mockedGet).toHaveBeenCalledWith(
      expect.any(String),
      expect.objectContaining({ _silent: true }),
    )
  })
})
