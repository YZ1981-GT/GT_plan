/**
 * G4 债权投资(main组) — 集成测试 Part 2: 公式链端到端验证
 *
 * 验证：
 * 1. 借方余额公式链：期初+借方-贷方=期末未审 → +AJE+RJE=审定
 * 2. G4-2 五区段公式链：期初→本期变动→期末→摊余成本→账面价值
 * 3. G4-4 实际利率法完整流程：初始入账→多期利息→期末余额
 *
 * 使用纯函数直接测试（无Vue组件挂载），覆盖公式引擎14个纯函数的组合正确性。
 *
 * **Validates: Requirements 3.3~3.5, 5.2~5.11, 7.2~7.7**
 */
import { describe, it, expect } from 'vitest'

import {
  calcDebitBalance,
  calcAdjustedAmount,
  calcBalanceSubtotal,
  calcAmortizedCost,
  calcEffectiveInterest,
  calcCashInflow,
  calcEndingBalance,
  calcInitialCarryingAmount,
  calcPeriodEndComponent,
  calcChangeRate,
  calcOneYearMaturity,
  calcBookValue,
  isDebitCreditBalanced,
  parseNum,
} from '@/composables/useG4MainFormulaEngine'

// ---------------------------------------------------------------------------
// 1. 借方余额公式链完整性（期初+借方-贷方=期末未审→+AJE+RJE=审定）
// ---------------------------------------------------------------------------
describe('G4 集成: 借方余额公式链（审定表G4-1）', () => {
  it('Step1: 期末未审 = 期初审定 + 借方发生额 - 贷方发生额', () => {
    const openingAdjusted = 5000000 // 期初审定：500万
    const debitAmount = 2000000    // 借方：新增债权投资200万
    const creditAmount = 500000    // 贷方：到期收回50万

    const closingUnadjusted = calcDebitBalance(openingAdjusted, debitAmount, creditAmount)
    expect(closingUnadjusted).toBe(6500000) // 500万 + 200万 - 50万 = 650万
  })

  it('Step2: 审定数 = 未审 + AJE + RJE', () => {
    const closingUnadjusted = 6500000
    const aje = -100000  // 调减10万（减值准备补提）
    const rje = 50000    // 重分类5万

    const closingAdjusted = calcAdjustedAmount(closingUnadjusted, aje, rje)
    expect(closingAdjusted).toBe(6450000)
  })

  it('完整链路：期初→借方→贷方→未审→AJE→RJE→审定', () => {
    const opening = 5000000
    const debit = 2000000
    const credit = 500000
    const aje = -100000
    const rje = 50000

    const unadjusted = calcDebitBalance(opening, debit, credit)
    const adjusted = calcAdjustedAmount(unadjusted, aje, rje)

    // 验证链等价于一步计算
    expect(adjusted).toBe(opening + debit - credit + aje + rje)
    expect(adjusted).toBe(6450000)
  })

  it('三层结构汇总：原值 - 减值 = 摊余成本', () => {
    // 一、原值审定
    const costAdjusted = calcAdjustedAmount(
      calcDebitBalance(8000000, 3000000, 1000000), -50000, 20000,
    ) // (8M+3M-1M) + (-50K) + (20K) = 9,970,000

    // 二、减值准备审定
    const impairmentAdjusted = calcAdjustedAmount(
      calcDebitBalance(200000, 100000, 30000), 50000, 0,
    ) // (200K+100K-30K) + 50K + 0 = 320,000

    // 三、摊余成本 = 原值 - 减值
    const amortized = calcAmortizedCost(costAdjusted, impairmentAdjusted)
    expect(amortized).toBe(9970000 - 320000) // 9,650,000
  })

  it('变动率公式：(期末审定 - 期初审定) / 期初审定', () => {
    const priorAdjusted = 5000000
    const currentAdjusted = 6450000
    const rate = calcChangeRate(priorAdjusted, currentAdjusted)
    expect(rate).not.toBeNull()
    expect(rate!).toBeCloseTo((6450000 - 5000000) / 5000000, 6)
    expect(rate!).toBeCloseTo(0.29, 2) // 29% > 20% → 橙色高亮
  })

  it('差异 = 审定 - 试算表数', () => {
    const audited = 6450000
    const trialBalance = 6500000
    const variance = audited - trialBalance
    expect(variance).toBe(-50000) // 差异5万 → 红色高亮
    expect(variance !== 0).toBe(true)
  })

  it('变动率：期初=0 返回null（除零保护）', () => {
    expect(calcChangeRate(0, 100000)).toBeNull()
  })

  it('变动率方向性：增长为正，下降为负', () => {
    expect(calcChangeRate(1000000, 1200000)!).toBeGreaterThan(0) // 增长20%
    expect(calcChangeRate(1000000, 800000)!).toBeLessThan(0)     // 下降20%
  })
})

// ---------------------------------------------------------------------------
// 2. G4-2 五区段公式链（期初→本期变动→期末→摊余成本→账面价值）
// ---------------------------------------------------------------------------
describe('G4 集成: G4-2 五区段公式链', () => {
  // 模拟一笔债权投资的完整数据
  const bondData = {
    // 基础信息
    investProject: '国开行2025-01',
    faceValue: 10000000,       // 面值1000万
    couponRate: 0.035,          // 票面利率3.5%
    effectiveRate: 0.04,        // 实际利率4.0%

    // 期初余额
    openingCost: 9800000,       // 期初成本 (折价购入)
    openingInterestAdj: 150000, // 期初利息调整
    openingAccruedInterest: 87500, // 期初应计利息
    openingImpairment: 50000,   // 期初减值

    // 本期变动
    periodCostChange: 0,          // 本期成本变动
    periodInterestAdjChange: 20000,  // 本期利息调整变动（实际利率法摊销）
    periodAccruedInterestChange: 175000, // 本期应计利息变动（票面利率×面值×天数/365）

    // 期末减值
    closingImpairment: 80000,
    // 一年内到期
    oneYearBalance: 2000000,
    oneYearImpairment: 10000,
  }

  it('期初小计 = 期初成本 + 期初利息调整 + 期初应计利息 (Req 5.2)', () => {
    const openingSubtotal = calcBalanceSubtotal(
      bondData.openingCost,
      bondData.openingInterestAdj,
      bondData.openingAccruedInterest,
    )
    expect(openingSubtotal).toBe(9800000 + 150000 + 87500) // 10,037,500
  })

  it('期初摊余成本 = 期初小计 - 期初减值准备 (Req 5.3)', () => {
    const openingSubtotal = calcBalanceSubtotal(
      bondData.openingCost,
      bondData.openingInterestAdj,
      bondData.openingAccruedInterest,
    )
    const openingAmortized = calcAmortizedCost(openingSubtotal, bondData.openingImpairment)
    expect(openingAmortized).toBe(10037500 - 50000) // 9,987,500
  })

  it('本期变动小计 = 三项变动之和 (Req 5.4)', () => {
    const periodChangeSubtotal = calcBalanceSubtotal(
      bondData.periodCostChange,
      bondData.periodInterestAdjChange,
      bondData.periodAccruedInterestChange,
    )
    expect(periodChangeSubtotal).toBe(0 + 20000 + 175000) // 195,000
  })

  it('期末成本 = 期初成本 + 本期成本变动 (Req 5.5)', () => {
    const closingCost = calcPeriodEndComponent(bondData.openingCost, bondData.periodCostChange)
    expect(closingCost).toBe(9800000 + 0) // 9,800,000
  })

  it('期末利息调整 = 期初利息调整 + 本期利息调整变动 (Req 5.6)', () => {
    const closingInterestAdj = calcPeriodEndComponent(bondData.openingInterestAdj, bondData.periodInterestAdjChange)
    expect(closingInterestAdj).toBe(150000 + 20000) // 170,000
  })

  it('期末应计利息 = 期初应计利息 + 本期应计利息变动 (Req 5.7)', () => {
    const closingAccruedInterest = calcPeriodEndComponent(bondData.openingAccruedInterest, bondData.periodAccruedInterestChange)
    expect(closingAccruedInterest).toBe(87500 + 175000) // 262,500
  })

  it('期末小计 = 期末成本 + 期末利息调整 + 期末应计利息 (Req 5.8)', () => {
    const closingCost = calcPeriodEndComponent(bondData.openingCost, bondData.periodCostChange)
    const closingInterestAdj = calcPeriodEndComponent(bondData.openingInterestAdj, bondData.periodInterestAdjChange)
    const closingAccruedInterest = calcPeriodEndComponent(bondData.openingAccruedInterest, bondData.periodAccruedInterestChange)

    const closingSubtotal = calcBalanceSubtotal(closingCost, closingInterestAdj, closingAccruedInterest)
    expect(closingSubtotal).toBe(9800000 + 170000 + 262500) // 10,232,500
  })

  it('摊余成本 = 期末小计 - 减值准备期末数 (Req 5.9)', () => {
    const closingSubtotal = calcBalanceSubtotal(
      calcPeriodEndComponent(bondData.openingCost, bondData.periodCostChange),
      calcPeriodEndComponent(bondData.openingInterestAdj, bondData.periodInterestAdjChange),
      calcPeriodEndComponent(bondData.openingAccruedInterest, bondData.periodAccruedInterestChange),
    )
    const amortizedCost = calcAmortizedCost(closingSubtotal, bondData.closingImpairment)
    expect(amortizedCost).toBe(10232500 - 80000) // 10,152,500
  })

  it('一年内到期小计 = 一年内到期账面余额 - 一年内到期减值 (Req 5.10)', () => {
    const oneYearSubtotal = calcOneYearMaturity(bondData.oneYearBalance, bondData.oneYearImpairment)
    expect(oneYearSubtotal).toBe(2000000 - 10000) // 1,990,000
  })

  it('期末账面价值 = 摊余成本 - 一年内到期小计 (Req 5.11)', () => {
    const closingSubtotal = calcBalanceSubtotal(
      calcPeriodEndComponent(bondData.openingCost, bondData.periodCostChange),
      calcPeriodEndComponent(bondData.openingInterestAdj, bondData.periodInterestAdjChange),
      calcPeriodEndComponent(bondData.openingAccruedInterest, bondData.periodAccruedInterestChange),
    )
    const amortizedCost = calcAmortizedCost(closingSubtotal, bondData.closingImpairment)
    const oneYearSubtotal = calcOneYearMaturity(bondData.oneYearBalance, bondData.oneYearImpairment)
    const bookValue = calcBookValue(amortizedCost, oneYearSubtotal)
    expect(bookValue).toBe(10152500 - 1990000) // 8,162,500
  })

  it('完整链路验证（五区段依次计算一致性）', () => {
    // 期初区段
    const openingSub = calcBalanceSubtotal(bondData.openingCost, bondData.openingInterestAdj, bondData.openingAccruedInterest)
    const openingAmort = calcAmortizedCost(openingSub, bondData.openingImpairment)

    // 变动区段
    const periodSub = calcBalanceSubtotal(bondData.periodCostChange, bondData.periodInterestAdjChange, bondData.periodAccruedInterestChange)

    // 期末区段（期末小计 = 期初小计 + 本期变动小计 恒等）
    const closingSub = calcBalanceSubtotal(
      calcPeriodEndComponent(bondData.openingCost, bondData.periodCostChange),
      calcPeriodEndComponent(bondData.openingInterestAdj, bondData.periodInterestAdjChange),
      calcPeriodEndComponent(bondData.openingAccruedInterest, bondData.periodAccruedInterestChange),
    )
    // 期末小计 == 期初小计 + 本期变动小计（加法结合律）
    expect(closingSub).toBeCloseTo(openingSub + periodSub, 6)

    // 摊余成本区段
    const amortized = calcAmortizedCost(closingSub, bondData.closingImpairment)
    const oneYear = calcOneYearMaturity(bondData.oneYearBalance, bondData.oneYearImpairment)
    const bookVal = calcBookValue(amortized, oneYear)

    // 最终账面价值 > 0
    expect(bookVal).toBeGreaterThan(0)
  })
})

// ---------------------------------------------------------------------------
// 3. G4-4 实际利率法完整流程（初始入账→多期利息→期末余额）
// ---------------------------------------------------------------------------
describe('G4 集成: G4-4 实际利率法完整流程', () => {
  // 模拟一项债券投资：面值1000万，5年期，折价购入
  const investment = {
    projectName: '工商银行次级债2025-01',
    faceValue: 10000000,      // 面值1000万
    purchasePrice: 9500000,    // 购买对价950万
    transactionCost: 20000,    // 交易费用2万
    couponRate: 0.035,          // 票面利率3.5%
    effectiveRate: 0.04,        // 实际利率4.0%
  }

  it('初始入账价值 = 购买对价 + 交易费用 (Req 7.2)', () => {
    const initial = calcInitialCarryingAmount(investment.purchasePrice, investment.transactionCost)
    expect(initial).toBe(9520000) // 952万
  })

  it('期初摊余成本余额 = 期初账面总额 - 期初减值准备余额 (Req 7.3)', () => {
    const openingBalance = 9520000  // 第一期期初 = 初始入账价值
    const impairment = 0             // Stage1 无减值
    const amortizedCost = calcAmortizedCost(openingBalance, impairment)
    expect(amortizedCost).toBe(9520000)
  })

  it('Stage1/2实际利息收入 = 摊余成本 × 实际利率 × 计息天数/365 (Req 7.4)', () => {
    const amortizedCost = 9520000
    const days = 182 // 半年（2025-01-01 至 2025-06-30）
    const interest = calcEffectiveInterest(amortizedCost, investment.effectiveRate, days)
    // 9,520,000 × 0.04 × 182/365 = 189,864.11 (约)
    expect(interest).toBeCloseTo(9520000 * 0.04 * 182 / 365, 2)
  })

  it('Stage3实际利息收入 = 摊余成本 × 实际利率 × days/365 (Req 7.5)', () => {
    // Stage3时减值更大，导致摊余成本基数更低
    const openingBalance = 9520000
    const impairment = 500000  // Stage3 减值50万
    const amortizedCost = calcAmortizedCost(openingBalance, impairment) // 9,020,000
    const days = 182
    const interest = calcEffectiveInterest(amortizedCost, investment.effectiveRate, days)
    // 9,020,000 × 0.04 × 182/365 ≈ 179,912.33
    expect(interest).toBeCloseTo(9020000 * 0.04 * 182 / 365, 2)
    // Stage3 利息 < Stage1 利息（因为减值更大→基数更低）
    const stage1Interest = calcEffectiveInterest(9520000, investment.effectiveRate, days)
    expect(interest).toBeLessThan(stage1Interest)
  })

  it('现金流入：整年 = 面值 × 票面利率 (Req 7.6)', () => {
    const cashInflow = calcCashInflow(investment.faceValue, investment.couponRate)
    expect(cashInflow).toBe(10000000 * 0.035) // 350,000
  })

  it('现金流入：非整年 = 面值 × 票面利率 × days/365 (Req 7.6)', () => {
    const days = 182
    const cashInflow = calcCashInflow(investment.faceValue, investment.couponRate, days)
    expect(cashInflow).toBeCloseTo(10000000 * 0.035 * 182 / 365, 2)
  })

  it('期末账面总额 = 期初 + 利息收入 - 现金流入 - 已收回本金 (Req 7.7)', () => {
    const opening = 9520000
    const days = 365
    const interest = calcEffectiveInterest(opening, investment.effectiveRate, days) // 整年
    const cashInflow = calcCashInflow(investment.faceValue, investment.couponRate, days)
    const principalRepaid = 0

    const ending = calcEndingBalance(opening, interest, cashInflow, principalRepaid)
    // 9,520,000 + 380,800 - 350,000 - 0 = 9,550,800
    expect(ending).toBeCloseTo(9520000 + (9520000 * 0.04) - (10000000 * 0.035), 2)
    // 折价购入 → 每期期末余额递增（摊销溢折价）
    expect(ending).toBeGreaterThan(opening)
  })

  it('多期计息完整链路（3个半年期）', () => {
    let balance = calcInitialCarryingAmount(investment.purchasePrice, investment.transactionCost)
    // 9,520,000

    const periods = [
      { days: 182, impairment: 0, principalRepaid: 0 },      // 第1个半年
      { days: 183, impairment: 0, principalRepaid: 0 },      // 第2个半年
      { days: 182, impairment: 50000, principalRepaid: 0 },  // 第3个半年（出现Stage2减值）
    ]

    const interestResults: number[] = []

    for (const period of periods) {
      const amortized = calcAmortizedCost(balance, period.impairment)
      const interest = calcEffectiveInterest(amortized, investment.effectiveRate, period.days)
      const cashIn = calcCashInflow(investment.faceValue, investment.couponRate, period.days)
      const newBalance = calcEndingBalance(balance, interest, cashIn, period.principalRepaid)

      interestResults.push(interest)
      balance = newBalance
    }

    // 验证每期利息收入 > 0
    for (const interest of interestResults) {
      expect(interest).toBeGreaterThan(0)
    }

    // 折价购入 → 账面余额逐期递增（向面值靠拢）
    expect(balance).toBeGreaterThan(9520000)
  })

  it('利息测算合计 vs G4-1审定表比对差异 (Req 7.11)', () => {
    // 模拟两个投资项目的年度利息合计
    const project1Interest = calcEffectiveInterest(9520000, 0.04, 365) // 380,800
    const project2Interest = calcEffectiveInterest(5000000, 0.05, 365) // 250,000
    const totalCalculated = project1Interest + project2Interest // 630,800

    // G4-1审定表的利息收入审定数
    const g41InterestAdjusted = 630750 // 假设审定数略有不同

    const variance = Math.abs(totalCalculated - g41InterestAdjusted)
    // 差异 = |630800 - 630750| = 50 > 0.01 → 红色高亮
    expect(variance).toBeGreaterThan(0.01)

    // 差异在可接受范围
    const isAcceptable = variance <= 0.01
    expect(isAcceptable).toBe(false) // 差异50元需关注
  })

  it('借贷平衡校验（G4-3调整分录联动）', () => {
    // AJE分录：借方减值损失10万，贷方减值准备10万
    const debits = [100000]
    const credits = [100000]
    expect(isDebitCreditBalanced(debits, credits)).toBe(true)

    // 不平衡
    expect(isDebitCreditBalanced([100000], [99000])).toBe(false)
  })

  it('parseNum容错：null/undefined/空串/NaN → 0', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum(undefined)).toBe(0)
    expect(parseNum('')).toBe(0)
    expect(parseNum(NaN)).toBe(0)
    expect(parseNum('abc')).toBe(0)
    expect(parseNum(123.45)).toBe(123.45)
    expect(parseNum('678.9')).toBe(678.9)
  })
})
