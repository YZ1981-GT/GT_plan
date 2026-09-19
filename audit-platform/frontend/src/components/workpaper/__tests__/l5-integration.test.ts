/**
 * 集成测试 — L5 长期应付款
 *
 * 覆盖：
 * 1. 摊销表末期趋零（generateSchedule 真实数据验证）
 * 2. L5→L8联动（EventBus publish 验证）
 * 3. 未确认明细核对（useL5CrossSheet adjudicationVsDetail + unrecognizedVsAmortization）
 * 4. useL5Adjudication 净额计算
 *
 * Spec: .kiro/specs/l5-long-term-payables/ Task 7.2
 * Requirements: 4.4-4.7, 8.4
 *
 * 科目：2701 长期应付款（贷方/负债类！期末=期初+贷方-借方）
 *       未确认融资费用（借方/负债备抵类！期末=期初+借方-贷方）
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  generateSchedule,
  validateSchedule,
} from '../composables/useL5AmortizationEngine'
import { useL5CrossSheet } from '../composables/useL5CrossSheet'
import type { ChecklistResponse } from '../composables/useL5FormData'
import {
  calcNetPayable,
  calcLiabilityEndBalance,
  calcContraLiabilityEndBalance,
  calcAuditedAmount,
  calcSubtotal,
} from '../composables/useL5FormulaEngine'

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

import { eventBus } from '@/utils/eventBus'

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: 摊销表末期趋零（真实业务数据）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 摊销表末期趋零 (Req 4.4)', () => {
  it('融资租赁典型：初始300万，等额月付，EIR 6%年/0.5%月，60期', () => {
    // PMT(0.005, 60, 3000000) ≈ 57,998
    const monthlyPayment = 57_998
    const schedule = generateSchedule(
      3_000_000,
      Array(60).fill(monthlyPayment),
      0.005, // 月利率0.5%
      60,
    )

    expect(schedule).toHaveLength(60)
    // 第一期摊销=300万×0.5%=15,000
    expect(schedule[0].amortization).toBeCloseTo(15_000, 0)
    // 最后一期endCost=0（尾差调整）
    expect(schedule[59].endCost).toBe(0)

    // validateSchedule 通过
    const { isValid, tailDiff } = validateSchedule(schedule)
    expect(isValid).toBe(true)
    expect(tailDiff).toBe(0)
  })

  it('分期付款购置设备：初始500万，年付120万，EIR 8%，5年', () => {
    const schedule = generateSchedule(
      5_000_000,
      Array(5).fill(1_200_000),
      0.08,
      5,
    )

    expect(schedule).toHaveLength(5)
    // 第一期：摊销=500万×8%=40万
    expect(schedule[0].amortization).toBeCloseTo(400_000, 0)
    expect(schedule[0].beginCost).toBe(5_000_000)
    // endCost = 5,000,000 - 1,200,000 + 400,000 = 4,200,000
    expect(schedule[0].endCost).toBeCloseTo(4_200_000, 0)

    // 最后一期强制趋零
    expect(schedule[4].endCost).toBe(0)

    const { isValid } = validateSchedule(schedule)
    expect(isValid).toBe(true)
  })

  it('边界：EIR=0 + 等额还本 → 线性递减至0', () => {
    const schedule = generateSchedule(
      1_000_000,
      Array(10).fill(100_000),
      0.0,
      10,
    )

    expect(schedule).toHaveLength(10)
    // EIR=0，非末期摊销=0
    for (let i = 0; i < 9; i++) {
      expect(schedule[i].amortization).toBe(0)
    }
    // 第一期endCost = 100万 - 10万 + 0 = 90万
    expect(schedule[0].endCost).toBeCloseTo(900_000, 0)
    // 最后一期趋零
    expect(schedule[9].endCost).toBe(0)
  })

  it('摊销合计≈初始未确认融资费用（会计恒等式）', () => {
    const initialCost = 2_000_000
    const schedule = generateSchedule(
      initialCost,
      Array(5).fill(500_000),
      0.06,
      5,
    )

    // 全部摊销额合计 + 全部本金偿还 = 全部还款额
    const totalAmortization = schedule.reduce((s, r) => s + r.amortization, 0)
    const totalRepayment = schedule.reduce((s, r) => s + r.repayment, 0)
    // initialCost = totalRepayment - totalAmortization (因为最终endCost=0)
    expect(totalRepayment - totalAmortization).toBeCloseTo(initialCost, 0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: useL5CrossSheet — adjudicationVsDetail 勾稽
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — useL5CrossSheet adjudicationVsDetail (Req 2.7, 3.6)', () => {
  function createResponses(entries: [string, string | null][]) {
    const map = new Map<string, ChecklistResponse>()
    for (const [itemId, remark] of entries) {
      map.set(itemId, { item_id: itemId, conclusion: null, remark })
    }
    return ref(map)
  }

  it('审定表合计 = 明细表合计 → isMatch=true', () => {
    const responses = createResponses([
      ['L5-L5-1-adjudication-total', '5000000'],
      ['L5-L5-2-rows', JSON.stringify([
        { endBalance: 2000000 },
        { endBalance: 1500000 },
        { endBalance: 1500000 },
      ])],
    ])

    const { adjudicationVsDetail } = useL5CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(true)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(0, 1)
  })

  it('审定表合计 ≠ 明细表合计 → isMatch=false + 差额', () => {
    const responses = createResponses([
      ['L5-L5-1-adjudication-total', '5000000'],
      ['L5-L5-2-rows', JSON.stringify([
        { endBalance: 2000000 },
        { endBalance: 1000000 },
      ])],
    ])

    const { adjudicationVsDetail } = useL5CrossSheet(responses)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(2_000_000, 0)
  })

  it('明细表为空 → 差额=审定数全额', () => {
    const responses = createResponses([
      ['L5-L5-1-adjudication-total', '3000000'],
      ['L5-L5-2-rows', '[]'],
    ])

    const { adjudicationVsDetail } = useL5CrossSheet(responses)
    expect(adjudicationVsDetail.value.diff).toBeCloseTo(3_000_000, 0)
    expect(adjudicationVsDetail.value.isMatch).toBe(false)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: useL5CrossSheet — unrecognizedVsAmortization 一致性
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — useL5CrossSheet unrecognizedVsAmortization (Req 4.5-4.7)', () => {
  function createResponses(entries: [string, string | null][]) {
    const map = new Map<string, ChecklistResponse>()
    for (const [itemId, remark] of entries) {
      map.set(itemId, { item_id: itemId, conclusion: null, remark })
    }
    return ref(map)
  }

  it('L5-3未确认余额 = L5-5摊销表未摊销余额 → isMatch=true', () => {
    const responses = createResponses([
      ['L5-L5-3-rows', JSON.stringify([
        { unrecognizedBalance: 800000 },
        { unrecognizedBalance: 200000 },
      ])],
      ['L5-L5-5-unamortized-total', '1000000'],
    ])

    const { unrecognizedVsAmortization } = useL5CrossSheet(responses)
    expect(unrecognizedVsAmortization.value.isMatch).toBe(true)
    expect(unrecognizedVsAmortization.value.diff).toBeCloseTo(0, 1)
  })

  it('不一致时 → isMatch=false + 差额', () => {
    const responses = createResponses([
      ['L5-L5-3-rows', JSON.stringify([
        { unrecognizedBalance: 500000 },
        { unrecognizedBalance: 300000 },
      ])],
      ['L5-L5-5-unamortized-total', '700000'],
    ])

    const { unrecognizedVsAmortization } = useL5CrossSheet(responses)
    expect(unrecognizedVsAmortization.value.isMatch).toBe(false)
    expect(unrecognizedVsAmortization.value.diff).toBeCloseTo(100_000, 0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: amortizationToL8 + EventBus publish
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — amortizationToL8 + EventBus (Req 4.7, 8.4)', () => {
  function createResponses(entries: [string, string | null][]) {
    const map = new Map<string, ChecklistResponse>()
    for (const [itemId, remark] of entries) {
      map.set(itemId, { item_id: itemId, conclusion: null, remark })
    }
    return ref(map)
  }

  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('从直接值读取本期摊销', () => {
    const responses = createResponses([
      ['L5-L5-5-period-amortization', '250000'],
    ])

    const { amortizationToL8 } = useL5CrossSheet(responses)
    expect(amortizationToL8.value.periodAmortization).toBeCloseTo(250_000, 0)
  })

  it('降级从schedule-rows汇总isCurrent行', () => {
    const responses = createResponses([
      ['L5-L5-5-period-amortization', '0'],
      ['L5-L5-5-schedule-rows', JSON.stringify([
        { amortization: 50000, isCurrent: true },
        { amortization: 45000, isCurrent: false },
        { amortization: 40000, isCurrent: true },
      ])],
    ])

    const { amortizationToL8 } = useL5CrossSheet(responses)
    expect(amortizationToL8.value.periodAmortization).toBeCloseTo(90_000, 0)
  })

  it('publishAmortizationCalculated 发布EventBus事件', () => {
    const responses = createResponses([
      ['L5-L5-5-period-amortization', '150000'],
    ])

    const { publishAmortizationCalculated } = useL5CrossSheet(responses)
    publishAmortizationCalculated()

    expect(eventBus.emit).toHaveBeenCalledWith(
      'l5:amortization-calculated',
      expect.objectContaining({
        wpCode: 'L5',
        periodAmortization: 150_000,
      }),
    )
  })

  it('publishAmortizationCalculated 仅在值变化时发布（防重复）', () => {
    const responses = createResponses([
      ['L5-L5-5-period-amortization', '150000'],
    ])

    const { publishAmortizationCalculated } = useL5CrossSheet(responses)
    publishAmortizationCalculated()
    publishAmortizationCalculated() // 重复调用

    // 仅调用一次
    expect(eventBus.emit).toHaveBeenCalledTimes(1)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 5: useL5Adjudication 净额计算
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 净额计算 (Req 2.6)', () => {
  it('多款项审定表净额计算', () => {
    // 模拟双区块行数据
    const payableRows = [
      { unadjusted: 3_000_000, aje: 100_000, rje: 0 },
      { unadjusted: 2_000_000, aje: -50_000, rje: 0 },
    ]
    const unrecognizedRows = [
      { unadjusted: 800_000, aje: 0, rje: 0 },
      { unadjusted: 200_000, aje: 0, rje: 0 },
    ]

    // 长期应付款审定合计
    const payableAuditedTotal = calcSubtotal(
      payableRows.map(r => calcAuditedAmount(r.unadjusted, r.aje, r.rje)),
    )
    expect(payableAuditedTotal).toBe(5_050_000) // 3100000 + 1950000

    // 未确认融资费用审定合计
    const unrecAuditedTotal = calcSubtotal(
      unrecognizedRows.map(r => calcAuditedAmount(r.unadjusted, r.aje, r.rje)),
    )
    expect(unrecAuditedTotal).toBe(1_000_000) // 800000 + 200000

    // 净额
    const netPayable = calcNetPayable(payableAuditedTotal, unrecAuditedTotal)
    expect(netPayable).toBe(4_050_000)
  })

  it('净额期末余额计算', () => {
    // 长期应付款期末(负债类)
    const payableEnd = calcLiabilityEndBalance(5_000_000, 1_000_000, 500_000) // 5500000
    // 未确认期末(备抵类)
    const unrecEnd = calcContraLiabilityEndBalance(1_000_000, 200_000, 300_000) // 900000
    // 净额
    const net = calcNetPayable(payableEnd, unrecEnd)
    expect(net).toBe(4_600_000) // 5500000 - 900000
  })
})
