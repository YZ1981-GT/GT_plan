/**
 * Unit Tests — K5 预计负债公式引擎 + 或有事项引擎 + 最佳估计引擎（边界/边缘情况）
 *
 * Spec: .kiro/specs/k5-provisions/ Task 7.1
 * Requirements: CP-K5-01~07
 *
 * 与 k5Provisions.pbt.spec.ts 互补：
 * - PBT 验证公式在随机输入下的数学正确性
 * - 本文件验证特定边界情况和边缘条件
 *
 * 科目：2701预计负债（**贷方/负债类**）
 * ⚠️ 负债类！期末 = 期初 + 计提 - 转销（与资产类方向相反！）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '../composables/useK5FormulaEngine'
import {
  determineRecognition,
  type LikelihoodLevel,
  type Recognition,
} from '../composables/useK5ContingencyEngine'
import {
  calcRangeMidpoint,
  calcExpectedValue,
  calcWarrantyProvision,
  calcPresentValue,
} from '../composables/useK5BestEstimateEngine'

// ============================================================
// calcAuditedAmount — 审定数 = 未审 + AJE + RJE (CP-K5-01)
// ============================================================
describe('calcAuditedAmount — edge cases (CP-K5-01)', () => {
  it('all zero inputs → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('negative AJE (审计调减)', () => {
    expect(calcAuditedAmount(1000, -200, 0)).toBe(800)
  })

  it('negative RJE (重分类调出)', () => {
    expect(calcAuditedAmount(500, 0, -500)).toBe(0)
  })

  it('both AJE and RJE negative', () => {
    expect(calcAuditedAmount(1000, -300, -200)).toBe(500)
  })

  it('large numbers (1e12 万亿级)', () => {
    expect(calcAuditedAmount(1e12, 5e11, -2e11)).toBe(1.3e12)
  })

  it('fractional amounts (分级精度)', () => {
    expect(calcAuditedAmount(100.01, 0.99, 0)).toBeCloseTo(101, 5)
  })

  it('NaN input treated as 0', () => {
    expect(calcAuditedAmount(NaN, 10, 20)).toBe(30)
    expect(calcAuditedAmount(100, NaN, NaN)).toBe(100)
  })

  it('undefined input treated as 0', () => {
    expect(calcAuditedAmount(undefined as any, 50, 50)).toBe(100)
  })
})

// ============================================================
// calcLiabilityEndBalance — 负债类期末 = 期初 + 计提 - 转销 (CP-K5-02)
// ⚠️ 负债类！与资产类（期初+借-贷）方向相反！
// ============================================================
describe('calcLiabilityEndBalance — 负债类方向 (CP-K5-02)', () => {
  it('all zero → 0', () => {
    expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
  })

  it('only provision (计提增加负债) → end > begin', () => {
    expect(calcLiabilityEndBalance(1000, 500, 0)).toBe(1500)
  })

  it('only release (转销减少负债) → end < begin', () => {
    expect(calcLiabilityEndBalance(1000, 0, 300)).toBe(700)
  })

  it('release exceeds begin → negative balance (超额转销)', () => {
    expect(calcLiabilityEndBalance(100, 0, 200)).toBe(-100)
  })

  it('equal provision and release → end = begin', () => {
    expect(calcLiabilityEndBalance(5000, 2000, 2000)).toBe(5000)
  })

  it('verify LIABILITY direction: NOT begin + debit - credit (asset style)', () => {
    // 关键测试：负债类 ≠ 资产类
    // 负债类：期初 1000，计提(贷方增加) 500，转销(借方减少) 200
    //   → 期末 = 1000 + 500 - 200 = 1300
    // 如果错误使用资产类公式(begin + debit - credit): 1000 + 200 - 500 = 700 ← 错误！
    const begin = 1000
    const provision = 500  // 计提（贷方增加）
    const release = 200    // 转销（借方减少）
    const result = calcLiabilityEndBalance(begin, provision, release)
    expect(result).toBe(1300)    // 负债类正确答案
    expect(result).not.toBe(700) // 资产类错误答案
  })

  it('NaN inputs treated as 0', () => {
    expect(calcLiabilityEndBalance(NaN, 100, 50)).toBe(50)
    expect(calcLiabilityEndBalance(1000, NaN, NaN)).toBe(1000)
  })

  it('undefined inputs treated as 0', () => {
    expect(calcLiabilityEndBalance(undefined as any, 100, 0)).toBe(100)
  })

  it('large numbers (1e12)', () => {
    expect(calcLiabilityEndBalance(1e12, 5e11, 2e11)).toBe(1.3e12)
  })

  it('precision boundary (浮点精度)', () => {
    expect(calcLiabilityEndBalance(0.1, 0.2, 0.3)).toBeCloseTo(0, 10)
  })

  it('negative begin + provision → correct sum', () => {
    expect(calcLiabilityEndBalance(-100, 300, 0)).toBe(200)
  })
})

// ============================================================
// calcSubtotal — 合计 = Σarr (CP-K5-01 related)
// ============================================================
describe('calcSubtotal — edge cases', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('null/undefined array → 0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('multiple elements', () => {
    expect(calcSubtotal([1000, 2000, 3000])).toBe(6000)
  })

  it('NaN elements treated as 0', () => {
    expect(calcSubtotal([NaN, 5, NaN, 10])).toBe(15)
  })

  it('negative elements', () => {
    expect(calcSubtotal([-100, -200, -300])).toBe(-600)
  })

  it('many elements (模拟K5-1六类型行)', () => {
    const arr = [50000, 200000, 30000, 0, 80000, 10000]
    expect(calcSubtotal(arr)).toBe(370000)
  })
})

// ============================================================
// determineRecognition — 或有事项三级决策确定性 (CP-K5-03)
// ============================================================
describe('determineRecognition — exhaustive check (CP-K5-03)', () => {
  it('very_likely → recognize (确认预计负债)', () => {
    expect(determineRecognition('very_likely')).toBe('recognize')
  })

  it('possible → disclose (披露或有负债)', () => {
    expect(determineRecognition('possible')).toBe('disclose')
  })

  it('remote → ignore (不处理)', () => {
    expect(determineRecognition('remote')).toBe('ignore')
  })

  it('deterministic: same input always same output (多次调用)', () => {
    for (let i = 0; i < 10; i++) {
      expect(determineRecognition('very_likely')).toBe('recognize')
      expect(determineRecognition('possible')).toBe('disclose')
      expect(determineRecognition('remote')).toBe('ignore')
    }
  })

  it('exhaustive mapping covers all 3 levels', () => {
    const levels: LikelihoodLevel[] = ['very_likely', 'possible', 'remote']
    const expected: Recognition[] = ['recognize', 'disclose', 'ignore']
    levels.forEach((level, idx) => {
      expect(determineRecognition(level)).toBe(expected[idx])
    })
  })

  it('return types are exactly the expected union values', () => {
    const validResults = new Set(['recognize', 'disclose', 'ignore'])
    expect(validResults.has(determineRecognition('very_likely'))).toBe(true)
    expect(validResults.has(determineRecognition('possible'))).toBe(true)
    expect(validResults.has(determineRecognition('remote'))).toBe(true)
  })
})

// ============================================================
// calcRangeMidpoint — 区间中值 = (upper + lower) / 2 (CP-K5-04)
// ============================================================
describe('calcRangeMidpoint — edge cases (CP-K5-04)', () => {
  it('equal upper and lower → same value', () => {
    expect(calcRangeMidpoint(1000, 1000)).toBe(1000)
  })

  it('standard case: (100+50)/2 = 75', () => {
    expect(calcRangeMidpoint(100, 50)).toBe(75)
  })

  it('both zero → 0', () => {
    expect(calcRangeMidpoint(0, 0)).toBe(0)
  })

  it('negative range: (-100 + -200) / 2 = -150', () => {
    expect(calcRangeMidpoint(-100, -200)).toBe(-150)
  })

  it('NaN inputs treated as 0 → midpoint = 0 or half', () => {
    expect(calcRangeMidpoint(NaN, 100)).toBe(50)  // (0+100)/2
    expect(calcRangeMidpoint(200, NaN)).toBe(100) // (200+0)/2
    expect(calcRangeMidpoint(NaN, NaN)).toBe(0)   // (0+0)/2
  })

  it('undefined inputs treated as 0', () => {
    expect(calcRangeMidpoint(undefined as any, 100)).toBe(50)
  })

  it('large numbers (1e12)', () => {
    expect(calcRangeMidpoint(2e12, 1e12)).toBe(1.5e12)
  })

  it('precision: (0.1+0.2)/2', () => {
    expect(calcRangeMidpoint(0.2, 0.1)).toBeCloseTo(0.15, 10)
  })
})

// ============================================================
// calcExpectedValue — 期望值 = Σ(amounts × probs) (CP-K5-05)
// ============================================================
describe('calcExpectedValue — edge cases (CP-K5-05)', () => {
  it('empty arrays → 0', () => {
    expect(calcExpectedValue([], [])).toBe(0)
  })

  it('mismatched lengths → 0', () => {
    expect(calcExpectedValue([100, 200], [0.5])).toBe(0)
    expect(calcExpectedValue([100], [0.3, 0.7])).toBe(0)
  })

  it('null inputs → 0', () => {
    expect(calcExpectedValue(null as any, [0.5])).toBe(0)
    expect(calcExpectedValue([100], null as any)).toBe(0)
  })

  it('single scenario → amount × prob', () => {
    expect(calcExpectedValue([1000], [1.0])).toBe(1000)
    expect(calcExpectedValue([500], [0.5])).toBe(250)
  })

  it('two scenarios: 100×0.3 + 200×0.7 = 170', () => {
    expect(calcExpectedValue([100, 200], [0.3, 0.7])).toBeCloseTo(170, 10)
  })

  it('three scenarios weighted', () => {
    const amounts = [100000, 200000, 300000]
    const probs = [0.2, 0.5, 0.3]
    const expected = 100000 * 0.2 + 200000 * 0.5 + 300000 * 0.3 // 210000
    expect(calcExpectedValue(amounts, probs)).toBeCloseTo(expected, 5)
  })

  it('all zero probabilities → 0', () => {
    expect(calcExpectedValue([1000, 2000], [0, 0])).toBe(0)
  })

  it('NaN in amounts treated as 0', () => {
    expect(calcExpectedValue([NaN, 200], [0.5, 0.5])).toBe(100) // 0*0.5 + 200*0.5
  })

  it('NaN in probs treated as 0', () => {
    expect(calcExpectedValue([100, 200], [NaN, 0.5])).toBe(100) // 100*0 + 200*0.5
  })
})

// ============================================================
// calcWarrantyProvision — 保修支出 = revenue × rate (CP-K5-06)
// ============================================================
describe('calcWarrantyProvision — edge cases (CP-K5-06)', () => {
  it('standard case: 1000000 × 0.02 = 20000', () => {
    expect(calcWarrantyProvision(1000000, 0.02)).toBe(20000)
  })

  it('zero revenue → 0', () => {
    expect(calcWarrantyProvision(0, 0.05)).toBe(0)
  })

  it('zero rate → 0', () => {
    expect(calcWarrantyProvision(1000000, 0)).toBe(0)
  })

  it('both zero → 0', () => {
    expect(calcWarrantyProvision(0, 0)).toBe(0)
  })

  it('NaN revenue → 0', () => {
    expect(calcWarrantyProvision(NaN, 0.02)).toBe(0)
  })

  it('NaN rate → 0', () => {
    expect(calcWarrantyProvision(1000000, NaN)).toBe(0)
  })

  it('undefined inputs → 0', () => {
    expect(calcWarrantyProvision(undefined as any, 0.02)).toBe(0)
    expect(calcWarrantyProvision(1000, undefined as any)).toBe(0)
  })

  it('large revenue (1e9) + small rate', () => {
    expect(calcWarrantyProvision(1e9, 0.001)).toBe(1e6)
  })

  it('negative revenue (退货冲回) still calculates', () => {
    expect(calcWarrantyProvision(-500000, 0.02)).toBe(-10000)
  })

  it('rate > 1 (100%以上保修率理论可行)', () => {
    expect(calcWarrantyProvision(1000, 1.5)).toBe(1500)
  })
})

// ============================================================
// calcPresentValue — 现值 = future/(1+rate)^years (CP-K5-07)
// ============================================================
describe('calcPresentValue — edge cases (CP-K5-07)', () => {
  it('standard case: 100000/(1+0.05)^10', () => {
    const expected = 100000 / Math.pow(1.05, 10) // ≈61391.33
    expect(calcPresentValue(100000, 0.05, 10)).toBeCloseTo(expected, 2)
  })

  it('rate = 0 → return future (兜底，不折现)', () => {
    expect(calcPresentValue(100000, 0, 10)).toBe(100000)
  })

  it('rate < 0 → return future (兜底，负利率不折现)', () => {
    expect(calcPresentValue(100000, -0.03, 10)).toBe(100000)
  })

  it('years = 0 → return future (兜底，无折现期)', () => {
    expect(calcPresentValue(100000, 0.05, 0)).toBe(100000)
  })

  it('years < 0 → return future (兜底)', () => {
    expect(calcPresentValue(100000, 0.05, -2)).toBe(100000)
  })

  it('future = 0 → 0', () => {
    expect(calcPresentValue(0, 0.05, 10)).toBe(0)
  })

  it('NaN future → 0', () => {
    expect(calcPresentValue(NaN, 0.05, 10)).toBe(0)
  })

  it('NaN rate → return future (rate≤0 兜底)', () => {
    // NaN → safeNum → 0, rate=0 → return future
    expect(calcPresentValue(100000, NaN, 10)).toBe(100000)
  })

  it('NaN years → return future (years≤0 兜底)', () => {
    // NaN → safeNum → 0, years=0 → return future
    expect(calcPresentValue(100000, 0.05, NaN)).toBe(100000)
  })

  it('undefined inputs → handled gracefully', () => {
    expect(calcPresentValue(undefined as any, 0.05, 10)).toBe(0)
    expect(calcPresentValue(100000, undefined as any, 5)).toBe(100000)
  })

  it('1 year discount: 100000/(1.1)^1 ≈ 90909.09', () => {
    expect(calcPresentValue(100000, 0.1, 1)).toBeCloseTo(90909.09, 1)
  })

  it('high rate (50%): 100000/(1.5)^5 ≈ 13169', () => {
    const expected = 100000 / Math.pow(1.5, 5)
    expect(calcPresentValue(100000, 0.5, 5)).toBeCloseTo(expected, 0)
  })

  it('long term (50 years): approaches 0', () => {
    const result = calcPresentValue(100000, 0.05, 50)
    expect(result).toBeGreaterThan(0)
    expect(result).toBeLessThan(10000) // heavily discounted
  })
})
