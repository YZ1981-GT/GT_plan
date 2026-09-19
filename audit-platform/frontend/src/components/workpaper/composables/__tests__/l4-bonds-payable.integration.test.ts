/**
 * 集成测试 — L4 应付债券
 *
 * 覆盖：
 * 1. 后续计量2分支末期趋面值（generateSchedule真实数据验证）
 * 2. L4→L2/L8 EventBus publish/subscribe 链
 * 3. 账面核对差异计算（useL4CrossSheet）
 *
 * Spec: .kiro/specs/l4-bonds-payable/ Task 7.2
 * Requirements: 4.5-4.8, 5.1-5.6, 11.1-11.4
 *
 * 科目：2502 应付债券（贷方/负债类！）
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref, nextTick } from 'vue'
import {
  generateSchedule,
  validateSchedule,
  solveEIR,
  calcInterestExpense,
} from '../useL4EIREngine'
import {
  calcLiabilityComponent,
  calcEquityComponent,
} from '../useL4EquityLiabEngine'
import { calcLiabilityEndBalance } from '../useL4FormulaEngine'
import { useL4CrossSheet } from '../useL4CrossSheet'
import type { ChecklistResponse } from '../useL4FormData'

// Mock eventBus
vi.mock('@/utils/eventBus', () => ({
  eventBus: {
    emit: vi.fn(),
    on: vi.fn(),
    off: vi.fn(),
  },
}))

// ═══════════════════════════════════════════════════════════════════════════════
// Section 1: 后续计量2分支末期趋面值（真实债券数据）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 后续计量2分支末期趋面值', () => {
  describe('installment 分支（分期付息到期一次还本）', () => {
    it('典型折价发行5年债：面值1亿，发行价9200万，票面4%，EIR 6%', () => {
      const schedule = generateSchedule(
        92_000_000, // 初始摊余成本（发行价-交易费用）
        100_000_000, // 面值1亿
        0.04, // 票面利率4%
        0.06, // 实际利率6%
        5, // 5年期
        'installment',
      )

      // 验证期数
      expect(schedule).toHaveLength(5)

      // 验证第一期
      expect(schedule[0].beginCost).toBe(92_000_000)
      expect(schedule[0].couponInterest).toBeCloseTo(4_000_000, 2) // 面值×4%
      expect(schedule[0].interestExpense).toBeCloseTo(5_520_000, 2) // 9200万×6%
      expect(schedule[0].amortization).toBeCloseTo(1_520_000, 2) // 折价摊销（正）
      expect(schedule[0].endCost).toBeCloseTo(93_520_000, 2)

      // 验证摊余成本逐期递增（折价摊销→趋向面值）
      for (let i = 1; i < schedule.length; i++) {
        expect(schedule[i].beginCost).toBeGreaterThan(schedule[i - 1].beginCost)
      }

      // 验证末期 endCost 强制等于面值（P6）
      expect(schedule[4].endCost).toBe(100_000_000)

      // validateSchedule 通过
      const { isValid, tailDiff } = validateSchedule(schedule, 100_000_000)
      expect(isValid).toBe(true)
      expect(tailDiff).toBe(0)
    })

    it('典型溢价发行3年债：面值5000万，发行价5400万，票面6%，EIR 3%', () => {
      const schedule = generateSchedule(
        54_000_000,
        50_000_000,
        0.06,
        0.03,
        3,
        'installment',
      )

      expect(schedule).toHaveLength(3)

      // 溢价：实际利息 < 票面利息 → amortization为负 → 摊余成本递减
      expect(schedule[0].interestExpense).toBeCloseTo(1_620_000, 2) // 5400万×3%
      expect(schedule[0].couponInterest).toBeCloseTo(3_000_000, 2) // 5000万×6%
      expect(schedule[0].amortization).toBeLessThan(0)

      // 摊余成本逐期递减
      for (let i = 1; i < schedule.length; i++) {
        expect(schedule[i].beginCost).toBeLessThan(schedule[i - 1].beginCost)
      }

      // 末期 endCost = faceValue
      expect(schedule[2].endCost).toBe(50_000_000)
    })

    it('边界：EIR=couponRate（平价发行，无摊销）', () => {
      const schedule = generateSchedule(
        1_000_000, // 平价
        1_000_000,
        0.05,
        0.05, // EIR=couponRate
        5,
        'installment',
      )

      // 所有期摊销应≈0（除尾差调整期）
      for (let i = 0; i < schedule.length - 1; i++) {
        expect(Math.abs(schedule[i].amortization)).toBeLessThan(0.01)
      }

      expect(schedule[4].endCost).toBe(1_000_000)
    })
  })

  describe('bullet 分支（到期一次还本付息）', () => {
    it('折价发行3年债：面值100万，发行价95万，票面5%，EIR 7%', () => {
      const schedule = generateSchedule(
        950_000,
        1_000_000,
        0.05,
        0.07,
        3,
        'bullet',
      )

      expect(schedule).toHaveLength(3)

      // Bullet分支：全资本化，endCost = begin + interestExpense
      expect(schedule[0].beginCost).toBe(950_000)
      expect(schedule[0].interestExpense).toBeCloseTo(66_500, 2) // 95万×7%
      expect(schedule[0].endCost).toBeCloseTo(1_016_500, 2)

      // 摊余成本严格递增
      for (let i = 1; i < schedule.length; i++) {
        expect(schedule[i].endCost).toBeGreaterThan(schedule[i - 1].endCost)
      }

      // bullet 最终 endCost 远大于面值（含累积利息）
      expect(schedule[2].endCost).toBeGreaterThan(1_000_000)
    })
  })

  describe('solveEIR + generateSchedule 闭环验证', () => {
    it('用solveEIR求出EIR后，generateSchedule末期应趋面值', () => {
      // 面值500万，票面5%，5年，发行价460万（折价）
      const faceValue = 5_000_000
      const couponRate = 0.05
      const periods = 5
      const initialAmount = 4_600_000

      // 构造现金流（分期付息）
      const coupon = faceValue * couponRate
      const cashFlows = Array(periods - 1).fill(coupon)
      cashFlows.push(coupon + faceValue) // 最后一期含本金

      // 求解EIR
      const eir = solveEIR(cashFlows, initialAmount)
      expect(eir).toBeGreaterThan(couponRate) // 折价→EIR>票面利率

      // 用求得的EIR生成摊销表
      const schedule = generateSchedule(
        initialAmount, faceValue, couponRate, eir, periods, 'installment',
      )

      // 末期必须等于面值
      expect(schedule[periods - 1].endCost).toBe(faceValue)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 2: L4→L2/L8 EventBus publish/subscribe 链
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — L4→L2/L8 EventBus 联动', () => {
  let allResponses: ReturnType<typeof ref<Map<string, ChecklistResponse>>>

  beforeEach(() => {
    allResponses = ref(new Map<string, ChecklistResponse>())
    vi.clearAllMocks()
  })

  it('interestToL2L8 从 schedule-rows 正确汇总利息费用', async () => {
    // 模拟 L4-7 摊销表行数据
    const scheduleRows = [
      { period: 1, interestExpense: 55_200 },
      { period: 2, interestExpense: 56_112 },
      { period: 3, interestExpense: 57_059 },
      { period: 4, interestExpense: 58_042 },
      { period: 5, interestExpense: 59_587 }, // 尾差调整
    ]

    allResponses.value.set('L4-L4-7-schedule-rows', {
      item_id: 'L4-L4-7-schedule-rows',
      conclusion: null,
      remark: JSON.stringify(scheduleRows),
    })

    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    const result = crossSheet.interestToL2L8.value
    const expectedTotal = scheduleRows.reduce((s, r) => s + r.interestExpense, 0)
    expect(result.totalInterest).toBeCloseTo(expectedTotal, 2)
  })

  it('publishInterestCalculated 调用 eventBus.emit 传正确 payload', async () => {
    const { eventBus } = await import('@/utils/eventBus')

    const scheduleRows = [
      { period: 1, interestExpense: 60_000 },
      { period: 2, interestExpense: 61_200 },
    ]

    allResponses.value.set('L4-L4-7-schedule-rows', {
      item_id: 'L4-L4-7-schedule-rows',
      conclusion: null,
      remark: JSON.stringify(scheduleRows),
    })

    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    crossSheet.publishInterestCalculated()

    expect(eventBus.emit).toHaveBeenCalledWith(
      'l4:interest-calculated',
      expect.objectContaining({
        wpCode: 'L4',
        totalInterest: expect.closeTo(121_200, 2),
        timestamp: expect.any(Number),
      }),
    )
  })

  it('重复 publish 时仅值变化才触发（去重）', async () => {
    const { eventBus } = await import('@/utils/eventBus')

    allResponses.value.set('L4-L4-7-schedule-rows', {
      item_id: 'L4-L4-7-schedule-rows',
      conclusion: null,
      remark: JSON.stringify([{ period: 1, interestExpense: 50_000 }]),
    })

    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    crossSheet.publishInterestCalculated()
    crossSheet.publishInterestCalculated() // 第二次相同值

    // 仅触发一次
    expect(eventBus.emit).toHaveBeenCalledTimes(1)
  })

  it('crossWpReferences 包含 L2 和 L8', () => {
    const crossSheet = useL4CrossSheet(allResponses)
    const refs = crossSheet.crossWpReferences

    expect(refs).toContainEqual(expect.objectContaining({
      targetWpCode: 'L2',
      direction: 'to',
    }))
    expect(refs).toContainEqual(expect.objectContaining({
      targetWpCode: 'L8',
      direction: 'to',
    }))
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 3: 账面核对差异计算
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 账面核对差异计算', () => {
  let allResponses: ReturnType<typeof ref<Map<string, ChecklistResponse>>>

  beforeEach(() => {
    allResponses = ref(new Map<string, ChecklistResponse>())
  })

  it('bookReconVsSubsequent：账面=测算时 isMatch=true, diff=0', async () => {
    allResponses.value.set('L4-L4-8-book-amortized-cost', {
      item_id: 'L4-L4-8-book-amortized-cost',
      conclusion: null,
      remark: '935200',
    })
    allResponses.value.set('L4-L4-7-calculated-amortized-cost', {
      item_id: 'L4-L4-7-calculated-amortized-cost',
      conclusion: null,
      remark: '935200',
    })

    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    const result = crossSheet.bookReconVsSubsequent.value
    expect(result.diff).toBe(0)
    expect(result.isMatch).toBe(true)
  })

  it('bookReconVsSubsequent：差异超阈值 → isMatch=false', async () => {
    allResponses.value.set('L4-L4-8-book-amortized-cost', {
      item_id: 'L4-L4-8-book-amortized-cost',
      conclusion: null,
      remark: '936000', // 账面比测算多800
    })
    allResponses.value.set('L4-L4-7-calculated-amortized-cost', {
      item_id: 'L4-L4-7-calculated-amortized-cost',
      conclusion: null,
      remark: '935200',
    })

    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    const result = crossSheet.bookReconVsSubsequent.value
    expect(result.diff).toBe(800)
    expect(result.isMatch).toBe(false) // |800| >= 1 (threshold)
  })

  it('bookReconVsSubsequent：微小差异<1元 → isMatch=true（尾差容忍）', async () => {
    allResponses.value.set('L4-L4-8-book-amortized-cost', {
      item_id: 'L4-L4-8-book-amortized-cost',
      conclusion: null,
      remark: '935200.5',
    })
    allResponses.value.set('L4-L4-7-calculated-amortized-cost', {
      item_id: 'L4-L4-7-calculated-amortized-cost',
      conclusion: null,
      remark: '935200',
    })

    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    const result = crossSheet.bookReconVsSubsequent.value
    expect(result.diff).toBe(0.5)
    expect(result.isMatch).toBe(true) // |0.5| < 1
  })

  it('adjudicationVsDetail：审定表合计=明细合计时 isMatch=true', async () => {
    allResponses.value.set('L4-L4-1-adjudication-total', {
      item_id: 'L4-L4-1-adjudication-total',
      conclusion: null,
      remark: '10000000',
    })
    allResponses.value.set('L4-L4-2-rows', {
      item_id: 'L4-L4-2-rows',
      conclusion: null,
      remark: JSON.stringify([
        { auditedAmount: 5000000 },
        { auditedAmount: 3000000 },
        { auditedAmount: 2000000 },
      ]),
    })

    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    const result = crossSheet.adjudicationVsDetail.value
    expect(result.diff).toBe(0)
    expect(result.isMatch).toBe(true)
  })

  it('adjudicationVsDetail：差异>1元 → isMatch=false', async () => {
    allResponses.value.set('L4-L4-1-adjudication-total', {
      item_id: 'L4-L4-1-adjudication-total',
      conclusion: null,
      remark: '10000000',
    })
    allResponses.value.set('L4-L4-2-rows', {
      item_id: 'L4-L4-2-rows',
      conclusion: null,
      remark: JSON.stringify([
        { auditedAmount: 5000000 },
        { auditedAmount: 3000000 },
        { auditedAmount: 1990000 }, // 少了10000
      ]),
    })

    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    const result = crossSheet.adjudicationVsDetail.value
    expect(result.diff).toBe(10000)
    expect(result.isMatch).toBe(false)
  })

  it('空数据时 diff=0，isMatch=true', async () => {
    // 两方都无数据
    const crossSheet = useL4CrossSheet(allResponses)
    await nextTick()

    expect(crossSheet.adjudicationVsDetail.value.diff).toBe(0)
    expect(crossSheet.adjudicationVsDetail.value.isMatch).toBe(true)
    expect(crossSheet.bookReconVsSubsequent.value.diff).toBe(0)
    expect(crossSheet.bookReconVsSubsequent.value.isMatch).toBe(true)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Section 4: 端到端公式链集成（负债类方向+实际利率法+权益划分）
// ═══════════════════════════════════════════════════════════════════════════════

describe('集成测试 — 完整公式链流转', () => {
  it('从初始计量→后续计量→账面核对 全链路数据一致', () => {
    // Step 1: 初始计量
    const faceValue = 10_000_000 // 面值1000万
    const issuePrice = 9_500_000 // 发行价950万
    const transactionCost = 100_000 // 交易费用10万
    const initialCost = issuePrice - transactionCost // 940万
    expect(initialCost).toBe(9_400_000)

    // Step 2: 用solveEIR求解实际利率
    const couponRate = 0.05
    const periods = 5
    const coupon = faceValue * couponRate // 50万/年
    const cashFlows = [...Array(periods - 1).fill(coupon), coupon + faceValue]
    const eir = solveEIR(cashFlows, initialCost)
    expect(eir).toBeGreaterThan(couponRate) // 折价→EIR>票面利率

    // Step 3: 生成后续计量表
    const schedule = generateSchedule(
      initialCost, faceValue, couponRate, eir, periods, 'installment',
    )
    expect(schedule).toHaveLength(periods)
    expect(schedule[periods - 1].endCost).toBe(faceValue)

    // Step 4: 利息费用合计（供L2/L8）
    const totalInterest = schedule.reduce((s, r) => s + r.interestExpense, 0)
    expect(totalInterest).toBeGreaterThan(0)

    // Step 5: 账面核对（账面=测算时差异=0）
    const bookCost = schedule[periods - 1].endCost
    const calcCost = faceValue
    expect(Math.abs(bookCost - calcCost)).toBeLessThan(1)

    // Step 6: 负债类期末余额验证（结合审定表）
    // 期末=期初+贷方(发行)-借方(兑付)，此处是摊余成本维度
    const beginning = initialCost
    const creditIncrease = totalInterest - coupon * periods // 净利息调整
    const debitDecrease = 0 // 本例无提前兑付
    // 验证概念：初始摊余成本+5年净利息调整 应≈ 面值（近似）
    // 实际：initialCost + Σ(interestExpense - coupon) = faceValue
    const netAmortization = schedule.reduce((s, r) => s + r.amortization, 0)
    expect(initialCost + netAmortization).toBeCloseTo(faceValue, 0)
  })

  it('权益负债划分 + 后续计量联动', () => {
    // 可转债：面值800万，发行价800万（平价），票面5%，市场利率8%，3年
    const faceValue = 8_000_000
    const totalProceeds = 8_000_000
    const couponRate = 0.05
    const marketRate = 0.08
    const periods = 3

    // Step 1: 分拆负债成分
    const coupon = faceValue * couponRate
    const cashFlows = [coupon, coupon, coupon + faceValue]
    const liabComponent = calcLiabilityComponent(cashFlows, marketRate)
    const equityComponent = calcEquityComponent(totalProceeds, liabComponent)

    // 负债+权益=发行总额
    expect(liabComponent + equityComponent).toBeCloseTo(totalProceeds, 2)
    expect(equityComponent).toBeGreaterThan(0) // 正常分拆

    // Step 2: 负债成分作为初始摊余成本，后续按 EIR(=marketRate) 摊销
    const schedule = generateSchedule(
      liabComponent, faceValue, couponRate, marketRate, periods, 'installment',
    )

    // 末期趋面值
    expect(schedule[periods - 1].endCost).toBe(faceValue)
  })
})
