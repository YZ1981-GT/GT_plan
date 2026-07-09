/**
 * Unit Tests — K4 其他流动负债公式引擎 useK4FormulaEngine（边界/边缘情况）
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/ Task 7.1
 * Requirements: CP-K4-01~05
 *
 * 与 k4FormulaEngine.pbt.spec.ts 互补：
 * - PBT 验证公式在随机输入下的数学正确性
 * - 本文件验证特定边界情况和边缘条件
 *
 * 科目：2245其他流动负债（**贷方/负债类**）
 * ⚠️ 负债类！期末 = 期初 + 贷方 - 借方（与资产类方向相反！）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcChangeRate,
} from '../composables/useK4FormulaEngine'

// ============================================================
// calcAuditedAmount — 审定数 = 未审 + AJE + RJE (CP-K4-01)
// ============================================================
describe('calcAuditedAmount — edge cases (CP-K4-01)', () => {
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
    const unadj = 1_000_000_000_000
    const aje = 500_000_000
    const rje = -200_000_000
    expect(calcAuditedAmount(unadj, aje, rje)).toBe(1_000_300_000_000)
  })

  it('fractional amounts (分级精度)', () => {
    expect(calcAuditedAmount(100.01, 0.99, 0)).toBeCloseTo(101, 5)
  })

  it('negative unadjusted (少见情况)', () => {
    expect(calcAuditedAmount(-500, 100, 50)).toBe(-350)
  })

  it('NaN input treated as 0', () => {
    expect(calcAuditedAmount(NaN, 10, 20)).toBe(30)
    expect(calcAuditedAmount(100, NaN, NaN)).toBe(100)
  })

  it('overflow boundary (Number.MAX_SAFE_INTEGER)', () => {
    // 超大数值不崩溃
    const result = calcAuditedAmount(1e15, 1e15, 1e15)
    expect(result).toBe(3e15)
  })
})

// ============================================================
// calcLiabilityEndBalance — 负债类期末 = 期初 + 贷方 - 借方 (CP-K4-02)
// ⚠️ 负债类！与资产类（期初+借-贷）方向相反！
// ============================================================
describe('calcLiabilityEndBalance — 负债类方向 (CP-K4-02)', () => {
  it('all zero → 0', () => {
    expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
  })

  it('only credit (贷方增加负债) → end > begin', () => {
    expect(calcLiabilityEndBalance(1000, 500, 0)).toBe(1500)
  })

  it('only debit (借方减少负债) → end < begin', () => {
    expect(calcLiabilityEndBalance(1000, 0, 300)).toBe(700)
  })

  it('credit exceeds begin + no debit → 大额新增', () => {
    expect(calcLiabilityEndBalance(0, 1000000, 0)).toBe(1000000)
  })

  it('debit exceeds begin → negative balance (超额偿付)', () => {
    expect(calcLiabilityEndBalance(100, 0, 200)).toBe(-100)
  })

  it('equal credit and debit → end = begin', () => {
    expect(calcLiabilityEndBalance(5000, 2000, 2000)).toBe(5000)
  })

  it('large numbers (1e12)', () => {
    expect(calcLiabilityEndBalance(1e12, 5e11, 2e11)).toBe(1.3e12)
  })

  it('verify LIABILITY direction: NOT 期初+借-贷 (asset style)', () => {
    // 关键测试：负债类 ≠ 资产类
    // 负债类：期初 1000，贷方(增加) 500，借方(减少) 200 → 期末 = 1000 + 500 - 200 = 1300
    // 如果错误使用资产类公式：1000 + 200 - 500 = 700 ← 这是错误的！
    const begin = 1000
    const credit = 500  // 贷方（负债增加）
    const debit = 200   // 借方（负债减少）
    const result = calcLiabilityEndBalance(begin, credit, debit)
    expect(result).toBe(1300)    // 负债类正确答案
    expect(result).not.toBe(700) // 资产类错误答案
  })

  it('NaN inputs treated as 0', () => {
    expect(calcLiabilityEndBalance(NaN, 100, 50)).toBe(50)
    expect(calcLiabilityEndBalance(1000, NaN, NaN)).toBe(1000)
  })

  it('precision boundary (浮点精度)', () => {
    expect(calcLiabilityEndBalance(0.1, 0.2, 0.3)).toBeCloseTo(0, 10)
  })

  it('negative begin + credit → correct sum', () => {
    // 负余额+新增贷方（理论可行）
    expect(calcLiabilityEndBalance(-100, 300, 0)).toBe(200)
  })
})

// ============================================================
// calcTriangleReconciliation — 三角勾稽差额 (CP-K4-03)
// diff = begin + inc - dec - end，恒等时为0
// ============================================================
describe('calcTriangleReconciliation — edge cases (CP-K4-03)', () => {
  it('balanced case → 0 (完全勾稽平衡)', () => {
    // end = begin + inc - dec = 1000 + 500 - 200 = 1300
    expect(calcTriangleReconciliation(1000, 500, 200, 1300)).toBe(0)
  })

  it('imbalanced case → negative diff (期末偏高)', () => {
    // begin+inc-dec = 1300, end=1400 → diff = 1000+500-200-1400 = -100
    expect(calcTriangleReconciliation(1000, 500, 200, 1400)).toBe(-100)
  })

  it('imbalanced case → positive diff (期末偏低)', () => {
    // begin+inc-dec = 1300, end=1200 → diff = 1000+500-200-1200 = 100
    expect(calcTriangleReconciliation(1000, 500, 200, 1200)).toBe(100)
  })

  it('all zero → 0', () => {
    expect(calcTriangleReconciliation(0, 0, 0, 0)).toBe(0)
  })

  it('large values balanced → 0', () => {
    const begin = 1e12
    const inc = 5e11
    const dec = 2e11
    const end = begin + inc - dec // 1.3e12
    expect(calcTriangleReconciliation(begin, inc, dec, end)).toBeCloseTo(0, 4)
  })

  it('negative begin (罕见但不崩)', () => {
    // begin=-100, inc=50, dec=30, end=-80 → diff = -100+50-30-(-80) = 0
    expect(calcTriangleReconciliation(-100, 50, 30, -80)).toBe(0)
  })

  it('NaN inputs treated as 0', () => {
    // NaN in any position → that arg is 0
    expect(calcTriangleReconciliation(NaN, 100, 50, 50)).toBe(0) // 0+100-50-50=0
    expect(calcTriangleReconciliation(100, NaN, NaN, 100)).toBe(0) // 100+0-0-100=0
  })
})

// ============================================================
// calcSubtotal — 合计 = Σarr (CP-K4-04)
// 空数组→0
// ============================================================
describe('calcSubtotal — edge cases (CP-K4-04)', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('multiple elements', () => {
    expect(calcSubtotal([1000, 2000, 3000])).toBe(6000)
  })

  it('negative elements (红字)', () => {
    expect(calcSubtotal([-100, -200, -300])).toBe(-600)
  })

  it('mixed positive and negative', () => {
    expect(calcSubtotal([1000, -500, 200, -100])).toBe(600)
  })

  it('large numbers (1e12 万亿级)', () => {
    expect(calcSubtotal([1e12, 2e12, 3e12])).toBe(6e12)
  })

  it('all zeros', () => {
    expect(calcSubtotal([0, 0, 0, 0])).toBe(0)
  })

  it('many elements (模拟50+明细项目)', () => {
    const arr = Array.from({ length: 50 }, (_, i) => (i + 1) * 1000)
    const expected = (50 * 51 / 2) * 1000 // 1275000
    expect(calcSubtotal(arr)).toBe(expected)
  })

  it('NaN elements treated as 0', () => {
    expect(calcSubtotal([NaN, 5, NaN, 10])).toBe(15)
    expect(calcSubtotal([NaN, NaN])).toBe(0)
  })

  it('single NaN → 0', () => {
    expect(calcSubtotal([NaN])).toBe(0)
  })
})

// ============================================================
// calcChangeRate — 变动率 (CP-K4-05 related)
// prior=0∧current=0→null, prior=0∧current≠0→1, normal→(c-p)/p
// ============================================================
describe('calcChangeRate — edge cases', () => {
  it('prior=0 ∧ current=0 → null (无意义)', () => {
    expect(calcChangeRate(0, 0)).toBeNull()
  })

  it('prior=0 ∧ current≠0 → 1 (100%增长，从无到有)', () => {
    expect(calcChangeRate(1000, 0)).toBe(1)
  })

  it('prior=0 ∧ current negative → 1 (新增负余额也算100%)', () => {
    expect(calcChangeRate(-500, 0)).toBe(1)
  })

  it('normal growth: 1200/1000 → 0.2 (20%)', () => {
    expect(calcChangeRate(1200, 1000)).toBeCloseTo(0.2, 10)
  })

  it('negative growth: 800/1000 → -0.2 (20%下降)', () => {
    expect(calcChangeRate(800, 1000)).toBeCloseTo(-0.2, 10)
  })

  it('no change: 1000/1000 → 0', () => {
    expect(calcChangeRate(1000, 1000)).toBe(0)
  })

  it('doubling: 2000/1000 → 1.0 (100%增)', () => {
    expect(calcChangeRate(2000, 1000)).toBe(1.0)
  })

  it('current=0, prior=1000 → -1.0 (100%下降，全部清偿)', () => {
    expect(calcChangeRate(0, 1000)).toBe(-1.0)
  })

  it('large numbers precision', () => {
    expect(calcChangeRate(1.5e12, 1e12)).toBeCloseTo(0.5, 10)
  })

  it('negative prior (罕见)', () => {
    // current=100, prior=-200 → (100-(-200))/-200 = -1.5
    expect(calcChangeRate(100, -200)).toBeCloseTo(-1.5, 10)
  })

  it('NaN inputs treated as 0 → both zero → null', () => {
    expect(calcChangeRate(NaN, NaN)).toBeNull()
  })

  it('NaN current, valid prior → (0-prior)/prior = -1', () => {
    expect(calcChangeRate(NaN, 1000)).toBe(-1)
  })
})
