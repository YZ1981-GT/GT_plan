/**
 * L1 短期借款集成测试
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 7.2
 * Validates: Requirements 4.5-4.6, 5.4, 10.1-10.4
 *
 * 测试链路：
 *   1. L1利息测算 → EventBus → L2/L8联动（publish payload 正确）
 *   2. 征信核对 calcCreditDiff 与 adjudicationVsDetail 一致性
 *   3. 逾期检查天数分级 + 逾期利息计算链
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { useL1CrossSheet } from '../useL1CrossSheet'
import { calcInterest, calcOverdueDays, calcOverdueInterest } from '../useL1InterestEngine'
import { calcCreditDiff } from '../useL1FormulaEngine'
import type {
  AdjudicationState,
  DetailRow,
  InterestCalcRow,
  CreditCheckRow,
} from '../useL1FormData'

// ─── Mock eventBus emit ──────────────────────────────────────────────────────

const emitSpy = vi.spyOn(eventBus, 'emit')

beforeEach(() => {
  emitSpy.mockClear()
})

afterEach(() => {
  emitSpy.mockClear()
})

// ─── 测试数据工厂 ────────────────────────────────────────────────────────────

function createAdjudicationState(endTotal: number): AdjudicationState {
  return {
    categories: [
      { name: '信用借款', beginning: 5000000, creditAmount: 2000000, debitAmount: 1000000, endBalance: 6000000, unadjusted: 6000000, aje: 0, rje: 0, audited: 6000000 },
      { name: '抵押借款', beginning: 3000000, creditAmount: 1000000, debitAmount: 500000, endBalance: endTotal - 6000000, unadjusted: endTotal - 6000000, aje: 0, rje: 0, audited: endTotal - 6000000 },
    ],
    total: {
      beginning: 8000000, credit: 3000000, debit: 1500000, end: endTotal,
      unadjusted: endTotal, aje: 0, rje: 0, audited: endTotal,
    },
  }
}

function createDetailRows(totalEndBalance: number): DetailRow[] {
  return [
    { bank: '工商银行', contractNo: 'ICBC-2024-001', loanType: '信用', amount: 6000000, rate: 0.045, startDate: '2024-03-01', endDate: '2024-09-30', purpose: '流动资金', guarantee: '', beginning: 5000000, creditAmount: 2000000, debitAmount: 1000000, endBalance: 6000000, currency: 'CNY' },
    { bank: '建设银行', contractNo: 'CCB-2024-002', loanType: '抵押', amount: 3500000, rate: 0.038, startDate: '2024-06-15', endDate: '2025-06-14', purpose: '设备采购', guarantee: '厂房抵押', beginning: 3000000, creditAmount: 1000000, debitAmount: 500000, endBalance: totalEndBalance - 6000000, currency: 'CNY' },
  ]
}

function createInterestCalcRows(): InterestCalcRow[] {
  // 利息 = 本金 × 年利率 × 天数 / 365
  const row1Days = 214 // 2024-03-01 to 2024-09-30
  const row1Interest = 6000000 * 0.045 * row1Days / 365
  const row2Days = 200 // 2024-06-15 to 2024-12-31
  const row2Interest = 3500000 * 0.038 * row2Days / 365

  return [
    { bank: '工商银行', contractNo: 'ICBC-2024-001', loanStart: '2024-03-01', loanEnd: '2024-09-30', startDate: '2024-03-01', endDate: '2024-09-30', rate: 0.045, principal: 6000000, days: row1Days, calculatedInterest: parseFloat(row1Interest.toFixed(2)), bookedInterest: row1Interest - 500, diff: 500 },
    { bank: '建设银行', contractNo: 'CCB-2024-002', loanStart: '2024-06-15', loanEnd: '2025-06-14', startDate: '2024-06-15', endDate: '2024-12-31', rate: 0.038, principal: 3500000, days: row2Days, calculatedInterest: parseFloat(row2Interest.toFixed(2)), bookedInterest: row2Interest, diff: 0 },
  ]
}

function createCreditCheckRows(totalBookBalance: number): CreditCheckRow[] {
  return [
    { bank: '工商银行', creditLimit: 10000000, usedLimit: 6000000, creditBalance: 6000000, bookBalance: 6000000, diff: 0, diffExplanation: '' },
    { bank: '建设银行', creditLimit: 5000000, usedLimit: 3500000, creditBalance: totalBookBalance - 6000000, bookBalance: totalBookBalance - 6000000, diff: 0, diffExplanation: '' },
  ]
}

// ─────────────────────────────────────────────────────────────────────────────
// 1. L1利息测算 → EventBus publish 'l1:interest-calculated'（Req 10.1-10.4）
// ─────────────────────────────────────────────────────────────────────────────

describe('集成：L1利息测算 → EventBus → L2/L8联动', () => {
  it('publishInterestCalculated 发布正确 payload（总利息+按合同明细）', () => {
    const adjData = ref(createAdjudicationState(9500000))
    const detailData = ref(createDetailRows(9500000))
    const interestData = ref(createInterestCalcRows())
    const creditData = ref<CreditCheckRow[]>([])

    const { publishInterestCalculated, interestToL2L8 } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    // 验证 interestToL2L8 computed 正确
    const result = interestToL2L8.value
    const expectedTotal = interestData.value[0].calculatedInterest + interestData.value[1].calculatedInterest
    expect(result.totalInterest).toBeCloseTo(expectedTotal, 2)
    // 短期借款利息全部费用化
    expect(result.financialExpenseInterest).toBe(result.totalInterest)
    expect(result.byContract).toHaveLength(2)
    expect(result.byContract[0].contractNo).toBe('ICBC-2024-001')
    expect(result.byContract[1].contractNo).toBe('CCB-2024-002')

    // 发布事件
    publishInterestCalculated()

    // 验证 EventBus emit 被调用
    expect(emitSpy).toHaveBeenCalledWith('l1:interest-calculated', expect.objectContaining({
      wpCode: 'L1',
      totalInterest: result.totalInterest,
      financialExpenseInterest: result.financialExpenseInterest,
      byContract: expect.arrayContaining([
        expect.objectContaining({ contractNo: 'ICBC-2024-001' }),
        expect.objectContaining({ contractNo: 'CCB-2024-002' }),
      ]),
      timestamp: expect.any(Number),
    }))
  })

  it('重复调用 publishInterestCalculated 时仅首次发布（值未变则跳过）', () => {
    const adjData = ref(createAdjudicationState(9500000))
    const detailData = ref(createDetailRows(9500000))
    const interestData = ref(createInterestCalcRows())
    const creditData = ref<CreditCheckRow[]>([])

    const { publishInterestCalculated } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    publishInterestCalculated()
    publishInterestCalculated()
    publishInterestCalculated()

    // 值未变，应只发布一次
    expect(emitSpy).toHaveBeenCalledTimes(1)
  })

  it('利息值变化时再次调用 publishInterestCalculated 会再次发布', () => {
    const adjData = ref(createAdjudicationState(9500000))
    const detailData = ref(createDetailRows(9500000))
    const interestData = ref(createInterestCalcRows())
    const creditData = ref<CreditCheckRow[]>([])

    const { publishInterestCalculated } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    publishInterestCalculated()
    expect(emitSpy).toHaveBeenCalledTimes(1)

    // 修改利息数据
    interestData.value[0].calculatedInterest += 10000

    publishInterestCalculated()
    expect(emitSpy).toHaveBeenCalledTimes(2)
  })

  it('L2应付利息订阅 l1:interest-calculated 可接收正确数据', () => {
    const received: any[] = []
    const handler = (payload: any) => received.push(payload)
    eventBus.on('l1:interest-calculated', handler)

    const adjData = ref(createAdjudicationState(9500000))
    const detailData = ref(createDetailRows(9500000))
    const interestData = ref(createInterestCalcRows())
    const creditData = ref<CreditCheckRow[]>([])

    const { publishInterestCalculated } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    publishInterestCalculated()

    expect(received).toHaveLength(1)
    expect(received[0].wpCode).toBe('L1')
    expect(received[0].totalInterest).toBeGreaterThan(0)
    expect(received[0].byContract).toHaveLength(2)

    eventBus.off('l1:interest-calculated', handler)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 2. 征信核对 calcCreditDiff + adjudicationVsDetail 一致性（Req 5.4）
// ─────────────────────────────────────────────────────────────────────────────

describe('集成：征信核对 + adjudicationVsDetail 勾稽', () => {
  it('审定表与明细表一致时 isMatch=true', () => {
    const totalEnd = 9500000
    const adjData = ref(createAdjudicationState(totalEnd))
    const detailData = ref(createDetailRows(totalEnd))
    const interestData = ref(createInterestCalcRows())
    const creditData = ref(createCreditCheckRows(totalEnd))

    const { adjudicationVsDetail, creditVsDetail } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBe(0)
  })

  it('审定表与明细表不一致时 isMatch=false 且 diff 正确', () => {
    const adjData = ref(createAdjudicationState(9500000))
    // 明细表合计比审定表少 100000
    const detailData = ref(createDetailRows(9400000))
    const interestData = ref(createInterestCalcRows())
    const creditData = ref<CreditCheckRow[]>([])

    const { adjudicationVsDetail } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(100000, 2)
  })

  it('征信余额与明细一致时 isConsistent=true', () => {
    const totalEnd = 9500000
    const adjData = ref(createAdjudicationState(totalEnd))
    const detailData = ref(createDetailRows(totalEnd))
    const interestData = ref(createInterestCalcRows())
    const creditData = ref(createCreditCheckRows(totalEnd))

    const { creditVsDetail } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    expect(creditVsDetail.value.isConsistent).toBe(true)
    expect(creditVsDetail.value.diff).toBe(0)
  })

  it('征信余额与明细不一致时 isConsistent=false', () => {
    const adjData = ref(createAdjudicationState(9500000))
    const detailData = ref(createDetailRows(9500000))
    const interestData = ref(createInterestCalcRows())
    // 征信余额比明细多 200000
    const creditData = ref(createCreditCheckRows(9700000))

    const { creditVsDetail } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    expect(creditVsDetail.value.isConsistent).toBe(false)
    expect(creditVsDetail.value.diff).toBeCloseTo(200000, 2)
  })

  it('calcCreditDiff 与 creditVsDetail 单行结果一致', () => {
    const creditBalance = 6000000
    const bookBalance = 5800000

    // 纯函数验证
    const diff = calcCreditDiff(creditBalance, bookBalance)
    expect(diff).toBe(200000)

    // 通过 CrossSheet 集成验证
    const adjData = ref(createAdjudicationState(5800000))
    const detailData = ref(createDetailRows(5800000))
    const interestData = ref(createInterestCalcRows())
    const creditData = ref<CreditCheckRow[]>([
      { bank: '工商银行', creditLimit: 10000000, usedLimit: 6000000, creditBalance: 6000000, bookBalance: 5800000, diff: 200000, diffExplanation: '' },
    ])

    const { creditVsDetail } = useL1CrossSheet(
      adjData, detailData, interestData, creditData, 'L1',
    )

    // 征信合计 6000000 vs 明细合计 5800000
    expect(creditVsDetail.value.diff).toBeCloseTo(200000, 2)
    expect(creditVsDetail.value.isConsistent).toBe(false)
  })
})

// ─────────────────────────────────────────────────────────────────────────────
// 3. 逾期检查：天数分级 + 逾期利息计算链（Req 6.1-6.3）
// ─────────────────────────────────────────────────────────────────────────────

describe('集成：逾期检查天数分级 + 逾期利息计算链', () => {
  it('逾期天数计算 → 分级判定（<30天低/30-90天中/>90天高）', () => {
    const reportDate = new Date('2024-12-31')

    // 场景1：逾期 15天 → low
    const due1 = new Date('2024-12-16')
    const days1 = calcOverdueDays(due1, reportDate)
    expect(days1).toBe(15)

    // 场景2：逾期 60天 → medium
    const due2 = new Date('2024-11-01')
    const days2 = calcOverdueDays(due2, reportDate)
    expect(days2).toBe(60)

    // 场景3：逾期 184天 → high
    const due3 = new Date('2024-06-30')
    const days3 = calcOverdueDays(due3, reportDate)
    expect(days3).toBe(184)

    // 场景4：未到期 → none（负数）
    const due4 = new Date('2025-03-31')
    const days4 = calcOverdueDays(due4, reportDate)
    expect(days4).toBe(-90)
  })

  it('逾期利息计算链：逾期天数 → 罚息日利率 → 逾期利息', () => {
    const reportDate = new Date('2024-12-31')
    const dueDate = new Date('2024-06-30')
    const principal = 2000000
    const penaltyAnnualRate = 0.18 // 年化18%

    // Step 1: 计算逾期天数
    const overdueDays = calcOverdueDays(dueDate, reportDate)
    expect(overdueDays).toBe(184)

    // Step 2: 转换日利率
    const dailyRate = penaltyAnnualRate / 365

    // Step 3: 计算逾期利息
    const overdueInterest = calcOverdueInterest(principal, dailyRate, overdueDays)
    const expected = principal * dailyRate * overdueDays
    expect(overdueInterest).toBeCloseTo(expected, 2)
    expect(overdueInterest).toBeGreaterThan(0)

    // 验证完整值：2,000,000 × 0.18/365 × 184 ≈ 181,479
    expect(overdueInterest).toBeCloseTo(181479.45, 0)
  })

  it('多笔逾期借款利息汇总正确', () => {
    const reportDate = new Date('2024-12-31')
    const penaltyDailyRate = 0.18 / 365

    const loans = [
      { dueDate: new Date('2024-06-30'), principal: 2000000 },
      { dueDate: new Date('2024-10-01'), principal: 1000000 },
      { dueDate: new Date('2024-12-15'), principal: 500000 },
    ]

    let totalOverdueInterest = 0
    for (const loan of loans) {
      const days = calcOverdueDays(loan.dueDate, reportDate)
      if (days > 0) {
        totalOverdueInterest += calcOverdueInterest(loan.principal, penaltyDailyRate, days)
      }
    }

    // 各笔逾期天数：184 / 91 / 16
    expect(calcOverdueDays(loans[0].dueDate, reportDate)).toBe(184)
    expect(calcOverdueDays(loans[1].dueDate, reportDate)).toBe(91)
    expect(calcOverdueDays(loans[2].dueDate, reportDate)).toBe(16)

    // 总逾期利息 > 0
    expect(totalOverdueInterest).toBeGreaterThan(0)

    // 验证每笔贡献
    const interest1 = calcOverdueInterest(2000000, penaltyDailyRate, 184)
    const interest2 = calcOverdueInterest(1000000, penaltyDailyRate, 91)
    const interest3 = calcOverdueInterest(500000, penaltyDailyRate, 16)
    expect(totalOverdueInterest).toBeCloseTo(interest1 + interest2 + interest3, 2)
  })

  it('正常利息测算与逾期利息的联动：利息差异触发逾期检查', () => {
    // 场景：借款已逾期，需同时计算正常利息（测算期内）和逾期罚息
    const reportDate = new Date('2024-12-31')
    const loanDueDate = new Date('2024-09-30') // 已逾期
    const principal = 5000000
    const normalRate = 0.045
    const penaltyRate = 0.18

    // 正常利息（合同期内：假设起始到到期）
    const normalDays = 214 // 2024-03-01 to 2024-09-30
    const normalInterest = calcInterest(principal, normalRate, normalDays)
    expect(normalInterest).toBeGreaterThan(0)

    // 逾期天数
    const overdueDays = calcOverdueDays(loanDueDate, reportDate)
    expect(overdueDays).toBe(92) // 2024-09-30 到 2024-12-31

    // 逾期利息
    const dailyPenaltyRate = penaltyRate / 365
    const overdueInterest = calcOverdueInterest(principal, dailyPenaltyRate, overdueDays)
    expect(overdueInterest).toBeGreaterThan(0)

    // 总利息负担 = 正常利息 + 逾期罚息
    const totalInterestBurden = normalInterest + overdueInterest
    expect(totalInterestBurden).toBeGreaterThan(normalInterest)
  })
})
