/**
 * Unit Tests — G6 其他债权投资(ECL组) 公式引擎
 *
 * Spec: .kiro/specs/g6-other-bond-investment-ecl/ Task 11.1
 * Requirements: 6.1
 *
 * Deterministic unit tests for:
 * 1. ECL公式链端到端 (G6-12)
 * 2. parseNum边界值
 * 3. determineStage所有8种组合
 * 4. isDebitCreditBalanced正常/边界
 */
import { describe, it, expect } from 'vitest'
import {
  parseNum,
  calcImpairmentProvision,
  calcImpairmentFromPv,
  calcImpliedLossRate,
  calcImpairmentAdjustmentIdentity,
  calcImpairmentAdjustment,
  calcAdjustedBalance,
  calcAdjustedImpairment,
  calcAdjustedBookValue,
  calcTermAdjustedPd,
  effectivePdHorizonMonths,
  calcEclRateFromPdLgd,
  calcEclRateFromLossRate,
  determineStage,
  isDebitCreditBalanced,
} from '../useG6EclFormulaEngine'

// ═══════════════════════════════════════════════════════════════════
// 1. G6-12 ECL公式链端到端
// ═══════════════════════════════════════════════════════════════════

describe('G6-12 ECL公式链端到端', () => {
  /**
   * 输入: ①=1000万(10000000), ②=1%(0.01), ⑤=200万(2000000), ②A=2%(0.02)
   * 预期:
   *   ③ = 10000000 × 0.01 = 100000
   *   ⑥ = 2000000×0.02 + 10000000×(0.02-0.01) = 40000 + 100000 = 140000
   *   ⑦ = 10000000 + 2000000 = 12000000
   *   ⑧ = 100000 + 140000 = 240000
   *   ⑨ = 12000000 - 240000 = 11760000
   */
  const origBal = 10000000   // ① 摊余成本余额
  const origRate = 0.01      // ② 预期信用损失率
  const balAdj = 2000000     // ⑤ 余额调整
  const adjRate = 0.02       // ②A 调整后信用损失率

  it('③ 坏账准备 = ① × ② = 100000', () => {
    expect(calcImpairmentProvision(origBal, origRate)).toBe(100000)
  })

  it('⑥ 坏账调整 = ⑤×②A + ①×(②A-②) = 140000', () => {
    expect(calcImpairmentAdjustment(balAdj, adjRate, origBal, origRate)).toBe(140000)
  })

  it('⑦ 审定余额 = ① + ⑤ = 12000000', () => {
    expect(calcAdjustedBalance(origBal, balAdj)).toBe(12000000)
  })

  it('⑧ 审定坏账 = ③ + ⑥ = 240000', () => {
    const provision = calcImpairmentProvision(origBal, origRate)
    const impAdj = calcImpairmentAdjustment(balAdj, adjRate, origBal, origRate)
    expect(calcAdjustedImpairment(provision, impAdj)).toBe(240000)
  })

  it('⑨ 审定账面价值 = ⑦ - ⑧ = 11760000', () => {
    const adjBalance = calcAdjustedBalance(origBal, balAdj)
    const provision = calcImpairmentProvision(origBal, origRate)
    const impAdj = calcImpairmentAdjustment(balAdj, adjRate, origBal, origRate)
    const adjImpairment = calcAdjustedImpairment(provision, impAdj)
    expect(calcAdjustedBookValue(adjBalance, adjImpairment)).toBe(11760000)
  })

  it('完整链路端到端一致性', () => {
    const provision = calcImpairmentProvision(origBal, origRate)       // ③
    const impAdj = calcImpairmentAdjustment(balAdj, adjRate, origBal, origRate) // ⑥
    const adjBalance = calcAdjustedBalance(origBal, balAdj)            // ⑦
    const adjImpairment = calcAdjustedImpairment(provision, impAdj)    // ⑧
    const adjBookValue = calcAdjustedBookValue(adjBalance, adjImpairment) // ⑨

    expect(provision).toBe(100000)
    expect(impAdj).toBe(140000)
    expect(adjBalance).toBe(12000000)
    expect(adjImpairment).toBe(240000)
    expect(adjBookValue).toBe(11760000)
    // ⑨ === ⑦ - ⑧
    expect(adjBookValue).toBe(adjBalance - adjImpairment)
  })

  it('Stage3 现值法：③ = max(0, ① − PV)', () => {
    expect(calcImpairmentFromPv(10000000, 8500000)).toBe(1500000)
    expect(calcImpairmentFromPv(100, 150)).toBe(0)
    expect(calcImpliedLossRate(10000000, 1500000)).toBe(0.15)
  })

  it('Stage3 ⑥ 恒等倒挤 = 目标⑧ − ③', () => {
    expect(calcImpairmentAdjustmentIdentity(200000, 150000)).toBe(50000)
  })

  it('G6-13：期限折算PD / PD×LGD / 损失率法', () => {
    expect(calcTermAdjustedPd(0.012, 24)).toBeGreaterThan(0.012)
    expect(calcEclRateFromPdLgd(0.01, 0.45)).toBeCloseTo(0.0045, 6)
    expect(calcEclRateFromLossRate(0.02, 0.01)).toBeCloseTo(0.03, 6)
  })

  it('Stage1 期限 PD 封顶 12 个月；Stage2 用剩余存续期', () => {
    const annual = 0.012
    const capped = calcTermAdjustedPd(annual, 24, 'Stage1')
    const lifetime = calcTermAdjustedPd(annual, 24, 'Stage2')
    expect(capped).toBe(calcTermAdjustedPd(annual, 12))
    expect(lifetime).toBeGreaterThan(capped)
    expect(effectivePdHorizonMonths('Stage1', 36)).toBe(12)
    expect(effectivePdHorizonMonths('Stage2', 36)).toBe(36)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 2. parseNum边界值
// ═══════════════════════════════════════════════════════════════════

describe('parseNum边界值', () => {
  it('null → 0', () => {
    expect(parseNum(null)).toBe(0)
  })

  it('undefined → 0', () => {
    expect(parseNum(undefined)).toBe(0)
  })

  it('NaN → 0', () => {
    expect(parseNum(NaN)).toBe(0)
  })

  it('Infinity → 0', () => {
    expect(parseNum(Infinity)).toBe(0)
  })

  it('"" (空串) → 0', () => {
    expect(parseNum('')).toBe(0)
  })

  it('"  " (纯空格) → 0', () => {
    expect(parseNum('  ')).toBe(0)
  })

  it('"123" (数字字符串) → 123', () => {
    expect(parseNum('123')).toBe(123)
  })

  it('42 (正常数字) → 42', () => {
    expect(parseNum(42)).toBe(42)
  })

  it('-Infinity → 0', () => {
    expect(parseNum(-Infinity)).toBe(0)
  })

  it('"abc" (非数字字符串) → 0', () => {
    expect(parseNum('abc')).toBe(0)
  })

  it('0 → 0', () => {
    expect(parseNum(0)).toBe(0)
  })

  it('-3.14 → -3.14', () => {
    expect(parseNum(-3.14)).toBe(-3.14)
  })
})

// ═══════════════════════════════════════════════════════════════════
// 3. determineStage所有8种组合
// ═══════════════════════════════════════════════════════════════════

describe('determineStage所有8种组合', () => {
  // 8 combinations of 3 booleans — 对齐 G4：低风险豁免可覆盖 SICR
  const cases: [boolean, boolean, boolean, 'Stage1' | 'Stage2' | 'Stage3'][] = [
    // [hasSignificantIncrease, hasLowCreditRisk, hasCreditImpairment, expected]
    [false, false, false, 'Stage1'],
    [false, false, true, 'Stage3'],   // creditImpairment优先
    [false, true, false, 'Stage1'],
    [false, true, true, 'Stage3'],    // creditImpairment优先
    [true, false, false, 'Stage2'],
    [true, false, true, 'Stage3'],    // creditImpairment优先
    [true, true, false, 'Stage1'],    // 低风险豁免覆盖 SICR
    [true, true, true, 'Stage3'],     // creditImpairment优先
  ]

  cases.forEach(([sigIncrease, lowRisk, creditImpaired, expected]) => {
    it(`(${sigIncrease}, ${lowRisk}, ${creditImpaired}) → ${expected}`, () => {
      expect(determineStage(sigIncrease, lowRisk, creditImpaired)).toBe(expected)
    })
  })
})

// ═══════════════════════════════════════════════════════════════════
// 4. isDebitCreditBalanced
// ═══════════════════════════════════════════════════════════════════

describe('isDebitCreditBalanced', () => {
  it('[100, 200] vs [300] → true (平衡)', () => {
    expect(isDebitCreditBalanced([100, 200], [300])).toBe(true)
  })

  it('[100] vs [200] → false (不平衡)', () => {
    expect(isDebitCreditBalanced([100], [200])).toBe(false)
  })

  it('[] vs [] → true (空数组平衡)', () => {
    expect(isDebitCreditBalanced([], [])).toBe(true)
  })

  it('[0.001, 0.002] vs [0.003] → true (微小差异<0.01)', () => {
    expect(isDebitCreditBalanced([0.001, 0.002], [0.003])).toBe(true)
  })

  it('[100] vs [100.005] → true (差额0.005<0.01)', () => {
    expect(isDebitCreditBalanced([100], [100.005])).toBe(true)
  })

  it('[100] vs [100.02] → false (差额0.02≥0.01)', () => {
    expect(isDebitCreditBalanced([100], [100.02])).toBe(false)
  })

  it('[1000000, 500000] vs [1500000] → true (大金额平衡)', () => {
    expect(isDebitCreditBalanced([1000000, 500000], [1500000])).toBe(true)
  })
})
