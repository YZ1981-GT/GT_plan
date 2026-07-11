/**
 * useCutoffAutoSampling — 单元测试
 *
 * Spec: .kiro/specs/cutoff-test-auto-sampling/
 * Task: 14.2
 *
 * 测试范围：
 * - 配置初始化：accountCode → accountCodes 数组
 * - 校验逻辑：缺 cutoffDate 失败、缺 accountCodes 失败
 * - 统计计算：选中/取消选中后金额合计变化
 * - 填充映射：tb_ledger 字段 → sample 字段对应关系（applyFillMode）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'

// ─── Mock http ───────────────────────────────────────────────────────────────
vi.mock('@/utils/http', () => ({
  default: {
    post: vi.fn(),
    get: vi.fn(),
  },
}))

// ─── Mock element-plus ───────────────────────────────────────────────────────
vi.mock('element-plus', () => ({
  ElMessage: { success: vi.fn(), warning: vi.fn(), error: vi.fn(), info: vi.fn() },
}))

import {
  useCutoffAutoSampling,
  applyFillMode,
  type ExtractedVoucher,
  type CutoffAutoSamplingOptions,
} from '../composables/useCutoffAutoSampling'
import http from '@/utils/http'

const mockPost = vi.mocked(http.post)

// ─── Helpers ─────────────────────────────────────────────────────────────────

function makeOptions(overrides?: Partial<CutoffAutoSamplingOptions>): CutoffAutoSamplingOptions {
  return {
    projectId: ref('proj-001'),
    year: ref(2025),
    workpaperId: ref('wp-001'),
    accountCode: '1122',
    cutoffDirection: 'post_cutoff',
    ...overrides,
  }
}

function makeVoucher(partial: Partial<ExtractedVoucher> = {}): ExtractedVoucher {
  return {
    voucherNo: 'V-001',
    voucherDate: '2025-01-05',
    summary: '测试摘要',
    debitAmount: '1000.00',
    creditAmount: null,
    accountCode: '112201',
    accountName: '应收账款-客户A',
    counterpartAccount: '600101',
    voucherType: '记',
    cutoffStatus: '正常',
    remark: '',
    selected: true,
    ...partial,
  }
}

// ═══════════════════════════════════════════════════════════════════════════════
// 1. 配置初始化
// ═══════════════════════════════════════════════════════════════════════════════

describe('useCutoffAutoSampling - 配置初始化', () => {
  it('accountCode="1122" → config.accountCodes = ["1122"]', () => {
    const { config } = useCutoffAutoSampling(makeOptions({ accountCode: '1122' }))
    expect(config.value.accountCodes).toEqual(['1122'])
  })

  it('accountCode="1405,1403" → config.accountCodes = ["1405", "1403"]', () => {
    const { config } = useCutoffAutoSampling(makeOptions({ accountCode: '1405,1403' }))
    expect(config.value.accountCodes).toEqual(['1405', '1403'])
  })

  it('accountCode 含空格 "1405, 1403" → 自动 trim', () => {
    const { config } = useCutoffAutoSampling(makeOptions({ accountCode: '1405, 1403' }))
    expect(config.value.accountCodes).toEqual(['1405', '1403'])
  })

  it('year=2025 → config.cutoffDate = "2025-12-31"', () => {
    const { config } = useCutoffAutoSampling(makeOptions({ year: ref(2025) }))
    expect(config.value.cutoffDate).toBe('2025-12-31')
  })

  it('year=2024 → config.cutoffDate = "2024-12-31"', () => {
    const { config } = useCutoffAutoSampling(makeOptions({ year: ref(2024) }))
    expect(config.value.cutoffDate).toBe('2024-12-31')
  })

  it('默认 daysBefore=5, daysAfter=10', () => {
    const { config } = useCutoffAutoSampling(makeOptions())
    expect(config.value.daysBefore).toBe(5)
    expect(config.value.daysAfter).toBe(10)
  })

  it('默认 excludeExtracted=true', () => {
    const { config } = useCutoffAutoSampling(makeOptions())
    expect(config.value.excludeExtracted).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 2. 校验逻辑
// ═══════════════════════════════════════════════════════════════════════════════

describe('useCutoffAutoSampling - 校验逻辑', () => {
  it('validateConfig() 返回 false 当 cutoffDate 为空', () => {
    const { config, validateConfig, configErrors } = useCutoffAutoSampling(makeOptions())
    config.value.cutoffDate = ''

    expect(validateConfig()).toBe(false)
    expect(configErrors.value.cutoffDate).toBeDefined()
  })

  it('validateConfig() 返回 false 当 accountCodes 为空数组', () => {
    const { config, validateConfig, configErrors } = useCutoffAutoSampling(makeOptions())
    config.value.accountCodes = []

    expect(validateConfig()).toBe(false)
    expect(configErrors.value.accountCodes).toBeDefined()
  })

  it('validateConfig() 返回 true 当 cutoffDate 和 accountCodes 都有值', () => {
    const { validateConfig, configErrors } = useCutoffAutoSampling(makeOptions())

    expect(validateConfig()).toBe(true)
    expect(Object.keys(configErrors.value)).toHaveLength(0)
  })

  it('cutoffDate 和 accountCodes 同时为空 → 两个错误', () => {
    const { config, validateConfig, configErrors } = useCutoffAutoSampling(makeOptions())
    config.value.cutoffDate = ''
    config.value.accountCodes = []

    expect(validateConfig()).toBe(false)
    expect(configErrors.value.cutoffDate).toBeDefined()
    expect(configErrors.value.accountCodes).toBeDefined()
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 3. 统计计算
// ═══════════════════════════════════════════════════════════════════════════════

describe('useCutoffAutoSampling - 统计计算', () => {
  it('selectedCount 正确统计已选中凭证数量', () => {
    const { extractedVouchers, selectedCount } = useCutoffAutoSampling(makeOptions())

    extractedVouchers.value = [
      makeVoucher({ voucherNo: 'V-001', selected: true }),
      makeVoucher({ voucherNo: 'V-002', selected: false }),
      makeVoucher({ voucherNo: 'V-003', selected: true }),
    ]

    expect(selectedCount.value).toBe(2)
  })

  it('selectedDebitTotal 仅合计选中项的借方金额', () => {
    const { extractedVouchers, selectedDebitTotal } = useCutoffAutoSampling(makeOptions())

    extractedVouchers.value = [
      makeVoucher({ voucherNo: 'V-001', selected: true, debitAmount: '100.50' }),
      makeVoucher({ voucherNo: 'V-002', selected: false, debitAmount: '200.00' }),
      makeVoucher({ voucherNo: 'V-003', selected: true, debitAmount: '300.25' }),
    ]

    expect(selectedDebitTotal.value).toBeCloseTo(400.75, 2)
  })

  it('selectedCreditTotal 仅合计选中项的贷方金额', () => {
    const { extractedVouchers, selectedCreditTotal } = useCutoffAutoSampling(makeOptions())

    extractedVouchers.value = [
      makeVoucher({ voucherNo: 'V-001', selected: true, creditAmount: '500.00', debitAmount: null }),
      makeVoucher({ voucherNo: 'V-002', selected: true, creditAmount: '250.50', debitAmount: null }),
      makeVoucher({ voucherNo: 'V-003', selected: false, creditAmount: '1000.00', debitAmount: null }),
    ]

    expect(selectedCreditTotal.value).toBeCloseTo(750.50, 2)
  })

  it('cutoffErrorCount 仅统计选中且 cutoffStatus="可能跨期" 的条目', () => {
    const { extractedVouchers, cutoffErrorCount } = useCutoffAutoSampling(makeOptions())

    extractedVouchers.value = [
      makeVoucher({ voucherNo: 'V-001', selected: true, cutoffStatus: '可能跨期' }),
      makeVoucher({ voucherNo: 'V-002', selected: true, cutoffStatus: '正常' }),
      makeVoucher({ voucherNo: 'V-003', selected: false, cutoffStatus: '可能跨期' }),
      makeVoucher({ voucherNo: 'V-004', selected: true, cutoffStatus: '可能跨期' }),
    ]

    expect(cutoffErrorCount.value).toBe(2)
  })

  it('取消选中后统计更新', () => {
    const { extractedVouchers, selectedCount, selectedDebitTotal } = useCutoffAutoSampling(makeOptions())

    extractedVouchers.value = [
      makeVoucher({ voucherNo: 'V-001', selected: true, debitAmount: '100.00' }),
      makeVoucher({ voucherNo: 'V-002', selected: true, debitAmount: '200.00' }),
    ]

    expect(selectedCount.value).toBe(2)
    expect(selectedDebitTotal.value).toBeCloseTo(300.00, 2)

    // 取消选中第一条
    extractedVouchers.value[0].selected = false

    expect(selectedCount.value).toBe(1)
    expect(selectedDebitTotal.value).toBeCloseTo(200.00, 2)
  })

  it('debitAmount 为 null 时按 0 处理', () => {
    const { extractedVouchers, selectedDebitTotal } = useCutoffAutoSampling(makeOptions())

    extractedVouchers.value = [
      makeVoucher({ voucherNo: 'V-001', selected: true, debitAmount: null }),
      makeVoucher({ voucherNo: 'V-002', selected: true, debitAmount: '50.00' }),
    ]

    expect(selectedDebitTotal.value).toBeCloseTo(50.00, 2)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 4. applyFillMode 纯函数
// ═══════════════════════════════════════════════════════════════════════════════

describe('applyFillMode - 填充策略', () => {
  const existing: ExtractedVoucher[] = [
    makeVoucher({ voucherNo: 'E-001', debitAmount: '100.00' }),
    makeVoucher({ voucherNo: 'E-002', debitAmount: '200.00' }),
  ]

  const selected: ExtractedVoucher[] = [
    makeVoucher({ voucherNo: 'S-001', debitAmount: '300.00' }),
    makeVoucher({ voucherNo: 'S-002', debitAmount: '400.00' }),
  ]

  describe('append 模式', () => {
    it('结果包含所有 existing + 所有 selected', () => {
      const result = applyFillMode(existing, selected, 'append')
      expect(result.length).toBe(4)
      expect(result[0].voucherNo).toBe('E-001')
      expect(result[1].voucherNo).toBe('E-002')
      expect(result[2].voucherNo).toBe('S-001')
      expect(result[3].voucherNo).toBe('S-002')
    })

    it('existing 为空时仅返回 selected', () => {
      const result = applyFillMode([], selected, 'append')
      expect(result.length).toBe(2)
      expect(result[0].voucherNo).toBe('S-001')
    })
  })

  describe('replace 模式', () => {
    it('结果仅包含 selected', () => {
      const result = applyFillMode(existing, selected, 'replace')
      expect(result.length).toBe(2)
      expect(result[0].voucherNo).toBe('S-001')
      expect(result[1].voucherNo).toBe('S-002')
    })

    it('selected 为空时返回空数组', () => {
      const result = applyFillMode(existing, [], 'replace')
      expect(result.length).toBe(0)
    })
  })

  describe('merge 模式', () => {
    it('按 voucherNo 去重，仅添加新凭证', () => {
      const existingWithOverlap = [
        makeVoucher({ voucherNo: 'V-001' }),
        makeVoucher({ voucherNo: 'V-002' }),
      ]
      const selectedWithOverlap = [
        makeVoucher({ voucherNo: 'V-002' }), // 重复
        makeVoucher({ voucherNo: 'V-003' }), // 新
      ]

      const result = applyFillMode(existingWithOverlap, selectedWithOverlap, 'merge')
      expect(result.length).toBe(3) // V-001, V-002, V-003
      const nos = result.map(v => v.voucherNo)
      expect(nos).toContain('V-001')
      expect(nos).toContain('V-002')
      expect(nos).toContain('V-003')
    })

    it('无重复时等同 append', () => {
      const result = applyFillMode(existing, selected, 'merge')
      expect(result.length).toBe(4) // no overlap between E-* and S-*
    })

    it('全部重复时长度不变', () => {
      const same = [makeVoucher({ voucherNo: 'E-001' }), makeVoucher({ voucherNo: 'E-002' })]
      const result = applyFillMode(existing, same, 'merge')
      expect(result.length).toBe(2)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// 5. triggerCutoffFetch — 一键取数（四表库凭证库联动，Req 25）
// ═══════════════════════════════════════════════════════════════════════════════

describe('useCutoffAutoSampling - triggerCutoffFetch 一键取数', () => {
  beforeEach(() => {
    mockPost.mockReset()
  })

  it('只读态禁用一键取数，不调用后端（R25.6）', async () => {
    const { triggerCutoffFetch } = useCutoffAutoSampling(
      makeOptions({ readonly: ref(true) }),
    )
    await triggerCutoffFetch()
    expect(mockPost).not.toHaveBeenCalled()
  })

  it('调用 voucher-extract 并携带 filters.date_from/date_to 窗口边界（R25.1/R25.3）', async () => {
    mockPost.mockResolvedValueOnce({ data: { items: [], stats: {} } })
    const { triggerCutoffFetch } = useCutoffAutoSampling(
      makeOptions({ year: ref(2025), accountCode: '1122' }),
    )
    await triggerCutoffFetch()

    expect(mockPost).toHaveBeenCalledTimes(1)
    const [url, body] = mockPost.mock.calls[0]
    expect(url).toContain('/sampling/voucher-extract')
    // 基准日 2025-12-31，前5后10 → 2025-12-26 至 2026-01-10
    expect(body.filters.date_from).toBe('2025-12-26')
    expect(body.filters.date_to).toBe('2026-01-10')
    expect(body.filters.account_codes).toEqual(['1122'])
  })

  it('映射返回项为 ExtractedVoucher，并标注跨期疑点（R25.4/R25.5）', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        items: [
          // 窗口内、基准日之前 → 不跨期
          {
            voucher_no: 'V-100',
            voucher_date: '2025-12-28',
            summary: '期前入账',
            debit_amount: '1000.00',
            credit_amount: null,
            account_code: '112201',
            account_name: '应收账款',
            voucher_type: '记',
          },
          // 窗口内、基准日之后、无业务发生日期 → 单日期降级为跨期疑点
          {
            voucher_no: 'V-200',
            voucher_date: '2026-01-05',
            summary: '期后结转',
            debit_amount: null,
            credit_amount: '2000.00',
            account_code: '112201',
            account_name: '应收账款',
            voucher_type: '转',
          },
        ],
        stats: { population_count: 2 },
      },
    })

    const { triggerCutoffFetch, extractedVouchers, previewVisible } = useCutoffAutoSampling(
      makeOptions({ year: ref(2025) }),
    )
    await triggerCutoffFetch()

    expect(extractedVouchers.value.length).toBe(2)
    const before = extractedVouchers.value.find(v => v.voucherNo === 'V-100')!
    const after = extractedVouchers.value.find(v => v.voucherNo === 'V-200')!

    expect(before.cutoffStatus).toBe('正常')
    expect(before.remark).toBe('')
    expect(before.debitAmount).toBe('1000.00')

    expect(after.cutoffStatus).toBe('可能跨期')
    expect(after.remark).toBe('跨期疑点')
    expect(after.creditAmount).toBe('2000.00')

    expect(previewVisible.value).toBe(true)
  })

  it('窗口外凭证被 filterByCutoffWindow 兜底裁剪（R25.3）', async () => {
    mockPost.mockResolvedValueOnce({
      data: {
        items: [
          { voucher_no: 'IN', voucher_date: '2026-01-05', debit_amount: '1', account_code: '112201' },
          { voucher_no: 'OUT', voucher_date: '2026-03-01', debit_amount: '1', account_code: '112201' },
        ],
        stats: {},
      },
    })

    const { triggerCutoffFetch, extractedVouchers } = useCutoffAutoSampling(
      makeOptions({ year: ref(2025) }),
    )
    await triggerCutoffFetch()

    const nos = extractedVouchers.value.map(v => v.voucherNo)
    expect(nos).toContain('IN')
    expect(nos).not.toContain('OUT')
  })
})
