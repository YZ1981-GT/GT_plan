/**
 * 集成测试 — L8 财务费用
 *
 * 覆盖：
 * 1. L1/L3/L4/L5 利息汇聚流程（mock EventBus → verify interest total）
 * 2. 截止测试提取（mock ledger → verify window filtering + cross-period detection）
 * 3. TB回写流程（mock API → verify 科目6603发生额口径）
 * 4. 跨sheet校验（审定表 vs 明细表合计一致性）
 * 5. 审定公式链（10 items → signed subtotal）
 *
 * Spec: .kiro/specs/l8-financial-expenses/ Task 7.2
 * Requirements: 4.1-4.8, 6.1-6.5
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, effectScope } from 'vue'

const { mockPut, mockGet, mockEmit, mockOn, mockOff } = vi.hoisted(() => ({
  mockPut: vi.fn().mockResolvedValue({ data: { code: 0 } }),
  mockGet: vi.fn().mockResolvedValue({ data: [] }),
  mockEmit: vi.fn(),
  mockOn: vi.fn(),
  mockOff: vi.fn(),
}))

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: mockEmit,
    on: mockOn,
    off: mockOff,
  },
}))

// Mock api
vi.mock('@/services/apiProxy', () => ({
  api: {
    get: mockGet,
    put: mockPut,
  },
}))

import {
  calcAuditedAmount,
  calcOccurrence,
  calcNetFinanceExpense,
  calcSubtotal,
  validateAdjudicationVsDetail,
} from '../composables/useL8FormulaEngine'
import {
  aggregateInterest,
  calcInterestDiff,
  calcDeductibleInterest,
  calcExcessInterest,
} from '../composables/useL8InterestEngine'
import {
  extractCutoffWindow,
  extractCrossPeriodEntries,
  calcCrossPeriodTotal,
  calcCrossPeriodRate,
  type LedgerEntry,
} from '../composables/useL8CutoffEngine'

import { eventBus } from '@/utils/eventBus'
import { api } from '@/services/apiProxy'
import type { ChecklistResponse } from '../composables/useL8FormData'

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: L1/L3/L4/L5 → L8 利息汇聚流程
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — L1/L3/L4/L5→L8利息汇聚 (Req 4.1-4.8)', () => {
  it('四来源利息汇总 → 总利息支出', () => {
    // 模拟各底稿利息测算结果
    const l1Interest = 120000 // L1短期借款利息
    const l3Interest = 350000 // L3长期借款利息
    const l4Interest = 180000 // L4应付债券利息费用
    const l5Amortization = 45000 // L5未确认融资费用摊销

    const total = aggregateInterest(l1Interest, l3Interest, l4Interest, l5Amortization)
    expect(total).toBe(695000)
  })


  it('测算利息vs账面利息 → 差异验证', () => {
    // 测算利息（来自L循环）
    const estimated = aggregateInterest(120000, 350000, 180000, 45000) // 695000
    // 账面利息支出（L8-2明细表利息支出行）
    const booked = 680000

    const diff = calcInterestDiff(estimated, booked)
    expect(diff).toBe(15000) // 测算>账面, 可能有利息未入账
  })

  it('全来源为零 → 总利息=0', () => {
    const total = aggregateInterest(0, 0, 0, 0)
    expect(total).toBe(0)
    const diff = calcInterestDiff(total, 0)
    expect(diff).toBe(0)
  })

  it('部分底稿未就绪（值=0）→ 汇总仍正确', () => {
    // L1有值，L3/L4/L5未就绪（为0）
    const total = aggregateInterest(150000, 0, 0, 0)
    expect(total).toBe(150000)
  })

  it('非金融机构利息超标联合检测', () => {
    // L8-4: 非金融机构借款利息测算
    const principal = 5000000
    const agreedRate = 0.08 // 约定利率8%
    const benchmarkRate = 0.0435 // 同期金融机构利率4.35%
    const days = 365

    // 账载利息 = 本金 × 约定利率 × 天数 / 360
    const bookedInterest = (principal * agreedRate * days) / 360
    // 可扣除利息 = 本金 × 基准利率 × 天数 / 360
    const deductible = calcDeductibleInterest(principal, benchmarkRate, days)
    // 超标利息
    const excess = calcExcessInterest(bookedInterest, deductible)

    expect(deductible).toBeCloseTo(220521, 0) // 5M × 4.35% × 365/360
    expect(excess).toBeGreaterThan(0) // 约定利率>基准利率，有超标
    expect(bookedInterest).toBeCloseTo(405556, 0) // 5M × 8% × 365/360
  })

  it('useL8CrossSheet EventBus订阅注册验证', () => {
    // 验证 eventBus.on 被调用注册了L循环利息事件
    const scope = effectScope()
    scope.run(async () => {
      const { useL8CrossSheet } = await import('../composables/useL8CrossSheet')
      const responses = ref(new Map<string, ChecklistResponse>())
      useL8CrossSheet(responses)

      // 验证EventBus订阅了四个利息事件
      expect(eventBus.on).toHaveBeenCalledWith('l1:interest-calculated', expect.any(Function))
      expect(eventBus.on).toHaveBeenCalledWith('l3:interest-calculated', expect.any(Function))
      expect(eventBus.on).toHaveBeenCalledWith('l4:interest-calculated', expect.any(Function))
      expect(eventBus.on).toHaveBeenCalledWith('l5:amortization-calculated', expect.any(Function))
    })
    scope.stop()
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: 截止测试提取（序时账±天数 + 跨期检测）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 截止测试提取 (Req 6.1-6.5)', () => {
  const fullLedger: LedgerEntry[] = [
    { voucherNo: 'FE-001', date: '2024-12-25', summary: '12月利息支出', amount: 80000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '2001' },
    { voucherNo: 'FE-002', date: '2024-12-28', summary: '手续费', amount: 3000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '1002' },
    { voucherNo: 'FE-003', date: '2024-12-30', summary: '汇兑损失', amount: 15000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '1131' },
    { voucherNo: 'FE-004', date: '2024-12-31', summary: '利息计提', amount: 120000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '2211' },
    { voucherNo: 'FE-005', date: '2025-01-02', summary: '12月利息后入账', amount: 50000, attributionPeriod: '2024-12', bookingPeriod: '2025-01', counterAccount: '2001' },
    { voucherNo: 'FE-006', date: '2025-01-03', summary: '1月预付利息', amount: 25000, attributionPeriod: '2025-01', bookingPeriod: '2024-12', counterAccount: '2001' },
    { voucherNo: 'FE-007', date: '2025-01-04', summary: '正常1月费用', amount: 5000, attributionPeriod: '2025-01', bookingPeriod: '2025-01', counterAccount: '1002' },
    { voucherNo: 'FE-008', date: '2025-01-15', summary: '远期费用', amount: 90000, attributionPeriod: '2025-01', bookingPeriod: '2025-01', counterAccount: '2001' },
    { voucherNo: 'FE-009', date: '2024-12-10', summary: '12月初费用', amount: 40000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '2001' },
  ]

  it('±5天窗口提取正确数量', () => {
    const window = extractCutoffWindow(fullLedger, '2024-12-31', 5)
    // 12/26~01/05: FE-002(12/28), FE-003(12/30), FE-004(12/31), FE-005(01/02), FE-006(01/03), FE-007(01/04)
    expect(window.length).toBe(6)
  })


  it('窗口内跨期条目正确识别', () => {
    const crossPeriodEntries = extractCrossPeriodEntries(fullLedger, '2024-12-31', 5)
    // FE-005: 归属2024-12, 入账2025-01 → 跨期
    // FE-006: 归属2025-01, 入账2024-12 → 跨期
    expect(crossPeriodEntries.length).toBe(2)
    expect(crossPeriodEntries.map(e => e.voucherNo)).toContain('FE-005')
    expect(crossPeriodEntries.map(e => e.voucherNo)).toContain('FE-006')
  })

  it('跨期金额合计正确', () => {
    const crossEntries = extractCrossPeriodEntries(fullLedger, '2024-12-31', 5)
    const total = calcCrossPeriodTotal(crossEntries)
    // FE-005(50000) + FE-006(25000) = 75000
    expect(total).toBe(75000)
  })

  it('跨期率计算正确', () => {
    const window = extractCutoffWindow(fullLedger, '2024-12-31', 5)
    const crossEntries = extractCrossPeriodEntries(fullLedger, '2024-12-31', 5)
    const rate = calcCrossPeriodRate(crossEntries.length, window.length)
    // 2/6 × 100 = 33.33%
    expect(rate).toBeCloseTo(33.33, 1)
  })

  it('无跨期数据 → 跨期率=0', () => {
    const cleanLedger: LedgerEntry[] = [
      { voucherNo: 'CL-1', date: '2024-12-31', summary: '正常', amount: 100000, attributionPeriod: '2024-12', bookingPeriod: '2024-12', counterAccount: '2001' },
      { voucherNo: 'CL-2', date: '2025-01-01', summary: '正常', amount: 50000, attributionPeriod: '2025-01', bookingPeriod: '2025-01', counterAccount: '2001' },
    ]
    const crossEntries = extractCrossPeriodEntries(cleanLedger, '2024-12-31', 5)
    expect(crossEntries.length).toBe(0)
    const window = extractCutoffWindow(cleanLedger, '2024-12-31', 5)
    const rate = calcCrossPeriodRate(0, window.length)
    expect(rate).toBe(0)
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: TB回写流程（科目6603发生额口径）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — TB回写 (Req 2.6)', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('writebackTB 调用API正确参数（科目6603, 发生额口径）', async () => {
    const { useL8FormData } = await import('../composables/useL8FormData')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL8FormData({
        wpId: ref('test-wp-l8'),
        projectId: ref('test-project-001'),
      })

      await formData.writebackTB(1_500_000)

      expect(api.put).toHaveBeenCalledWith(
        '/api/projects/test-project-001/trial-balance/writeback',
        {
          account_code: '6603',
          audited_amount: 1_500_000,
        },
      )
    })

    scope.stop()
  })

  it('writebackTB 发布 substantive:adjudicated EventBus (wpCode=L8)', async () => {
    const { useL8FormData } = await import('../composables/useL8FormData')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL8FormData({
        wpId: ref('test-wp-l8-2'),
        projectId: ref('test-project-002'),
      })

      await formData.writebackTB(2_800_000)

      expect(eventBus.emit).toHaveBeenCalledWith(
        'substantive:adjudicated',
        expect.objectContaining({
          accountCode: '6603',
          auditedAmount: 2_800_000,
          wpCode: 'L8',
        }),
      )
    })

    scope.stop()
  })

  it('空projectId时不调用API', async () => {
    const { useL8FormData } = await import('../composables/useL8FormData')
    const scope = effectScope()

    await scope.run(async () => {
      const formData = useL8FormData({
        wpId: ref('test-wp'),
        projectId: ref(''),
      })

      await formData.writebackTB(1_000_000)
      expect(api.put).not.toHaveBeenCalled()
    })

    scope.stop()
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: 跨sheet校验（审定 vs 明细一致性）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 跨sheet校验 adjudicationVsDetail (Req 2.5, 3.6)', () => {
  it('useL8CrossSheet: 审定合计=明细合计 → isMatch=true', () => {
    const scope = effectScope()
    scope.run(async () => {
      const { useL8CrossSheet } = await import('../composables/useL8CrossSheet')
      const responses = ref(new Map<string, ChecklistResponse>([
        ['L8-1-total-audited', { item_id: 'L8-1-total-audited', conclusion: null, remark: '850000' }],
        ['L8-2-netFinExpense', { item_id: 'L8-2-netFinExpense', conclusion: null, remark: '850000' }],
      ]))

      const { adjudicationVsDetail } = useL8CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(true)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 1)
    })
    scope.stop()
  })

  it('useL8CrossSheet: 审定>明细 → diff正数', () => {
    const scope = effectScope()
    scope.run(async () => {
      const { useL8CrossSheet } = await import('../composables/useL8CrossSheet')
      const responses = ref(new Map<string, ChecklistResponse>([
        ['L8-1-total-audited', { item_id: 'L8-1-total-audited', conclusion: null, remark: '1000000' }],
        ['L8-2-netFinExpense', { item_id: 'L8-2-netFinExpense', conclusion: null, remark: '800000' }],
      ]))

      const { adjudicationVsDetail } = useL8CrossSheet(responses)
      expect(adjudicationVsDetail.value.isMatch).toBe(false)
      expect(adjudicationVsDetail.value.diff).toBeCloseTo(200000, 0)
    })
    scope.stop()
  })

  it('纯公式验证: validateAdjudicationVsDetail', () => {
    // 审定表10项发生额签后合计
    const items = [300000, -50000, 120000, 80000, -20000, 45000, 200000, 10000, -5000, 60000]
    const adjTotal = calcSubtotal(items)
    const detailTotal = adjTotal // 明细表与审定表一致

    const result = validateAdjudicationVsDetail(adjTotal, detailTotal)
    expect(result.isMatch).toBe(true)
    expect(result.diff).toBe(0)
    expect(adjTotal).toBe(740000) // 验证10项签后合计
  })
})


// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: 审定公式链（10 items → signed subtotal）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 审定公式链 10项 (Req 2.1-2.4, 8.1-8.4)', () => {
  /** 模拟审定表10行费用项目 */
  interface MockOccurrenceRow {
    itemName: string
    debitOccur: number
    creditOccur: number
    aje: number
    rje: number
  }

  function computeAdjudicationChain(rows: MockOccurrenceRow[]) {
    const computed = rows.map(row => {
      const occurrence = calcOccurrence(row.debitOccur, row.creditOccur)
      const audited = calcAuditedAmount(occurrence, row.aje, row.rje)
      return { ...row, occurrence, audited }
    })

    const totalOccurrence = calcSubtotal(computed.map(r => r.occurrence))
    const totalAudited = calcSubtotal(computed.map(r => r.audited))

    return { computed, totalOccurrence, totalAudited }
  }

  it('10项费用：发生额→审定→合计 完整公式链', () => {
    const rows: MockOccurrenceRow[] = [
      { itemName: '利息支出-短期', debitOccur: 200000, creditOccur: 0, aje: 10000, rje: 0 },
      { itemName: '利息支出-长期', debitOccur: 500000, creditOccur: 0, aje: 0, rje: 0 },
      { itemName: '利息支出-债券', debitOccur: 180000, creditOccur: 0, aje: -5000, rje: 0 },
      { itemName: '利息收入', debitOccur: 0, creditOccur: 80000, aje: 0, rje: 0 },
      { itemName: '汇兑损失', debitOccur: 60000, creditOccur: 10000, aje: 0, rje: 5000 },
      { itemName: '汇兑收益', debitOccur: 5000, creditOccur: 30000, aje: 0, rje: 0 },
      { itemName: '手续费', debitOccur: 25000, creditOccur: 0, aje: 2000, rje: 0 },
      { itemName: '贴现利息', debitOccur: 35000, creditOccur: 0, aje: 0, rje: -3000 },
      { itemName: '融资租赁利息', debitOccur: 45000, creditOccur: 0, aje: 0, rje: 0 },
      { itemName: '其他', debitOccur: 8000, creditOccur: 2000, aje: 1000, rje: 0 },
    ]

    const { totalOccurrence, totalAudited, computed } = computeAdjudicationChain(rows)

    // 验证各行发生额
    expect(computed[0].occurrence).toBe(200000) // 200000-0
    expect(computed[3].occurrence).toBe(-80000) // 0-80000 (利息收入为贷方)
    expect(computed[4].occurrence).toBe(50000)  // 60000-10000
    expect(computed[5].occurrence).toBe(-25000) // 5000-30000 (汇兑收益)

    // 验证各行审定
    expect(computed[0].audited).toBe(210000) // 200000+10000+0
    expect(computed[2].audited).toBe(175000) // 180000+(-5000)+0

    // 验证合计
    // 发生额合计 = 200000+500000+180000+(-80000)+50000+(-25000)+25000+35000+45000+6000 = 936000
    expect(totalOccurrence).toBe(936000)
    // 审定合计 = 各行audited之和
    expect(totalAudited).toBe(946000) // 936000 + AJE(10000-5000+2000+1000=8000) + RJE(5000-3000=2000) = 936000+10000
  })

  it('全零行→合计为0', () => {
    const rows: MockOccurrenceRow[] = Array(10).fill({
      itemName: '', debitOccur: 0, creditOccur: 0, aje: 0, rje: 0,
    })
    const { totalOccurrence, totalAudited } = computeAdjudicationChain(rows)
    expect(totalOccurrence).toBe(0)
    expect(totalAudited).toBe(0)
  })

  it('净财务费用 = 利息支出-利息收入+汇兑+手续费+其他', () => {
    const interestExp = 880000  // 短期+长期+债券
    const interestInc = 80000   // 利息收入
    const fx = 25000            // 汇兑损益净额 (损失50000-收益25000)
    const fee = 25000           // 手续费
    const other = 86000         // 贴现利息+融资租赁+其他

    const net = calcNetFinanceExpense(interestExp, interestInc, fx, fee, other)
    // 880000 - 80000 + 25000 + 25000 + 86000 = 936000
    expect(net).toBe(936000)
  })
})
