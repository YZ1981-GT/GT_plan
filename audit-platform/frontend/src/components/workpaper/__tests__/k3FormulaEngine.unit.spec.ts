/**
 * Unit Tests — K3 其他应付款公式引擎 useK3FormulaEngine（边界/边缘情况）
 *
 * Spec: .kiro/specs/k3-other-payables/ Task 7.1
 * Requirements: CP-K3-01~06
 *
 * 与 k3FormulaEngine.pbt.spec.ts 互补：
 * - PBT 验证公式在随机输入下的数学正确性
 * - 本文件验证特定边界情况和边缘条件
 *
 * 科目：2241其他应付款（**贷方/负债类**）
 * ⚠️ 负债类！期末 = 期初 + 贷方 - 借方（与资产类方向相反！）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcTriangleReconciliation,
  calcProportion,
  calcSubtotal,
  calcChangeRate,
} from '../composables/useK3FormulaEngine'

// ============================================================
// calcAuditedAmount — 审定数 = 未审 + AJE + RJE (CP-K3-01)
// ============================================================
describe('calcAuditedAmount — edge cases (CP-K3-01)', () => {
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

  it('negative unadjusted (其他应付款负余额，少见情况)', () => {
    expect(calcAuditedAmount(-500, 100, 50)).toBe(-350)
  })
})

// ============================================================
// calcLiabilityEndBalance — 负债类期末 = 期初 + 贷方 - 借方 (CP-K3-02)
// ⚠️ 负债类！与资产类（期初+借-贷）方向相反！
// ============================================================
describe('calcLiabilityEndBalance — 负债类方向 (CP-K3-02)', () => {
  it('all zero → 0', () => {
    expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
  })

  it('only credit (贷方增加负债) → end > begin', () => {
    // 负债类：贷方增加负债
    expect(calcLiabilityEndBalance(1000, 500, 0)).toBe(1500)
  })

  it('only debit (借方减少负债) → end < begin', () => {
    // 负债类：借方减少负债（偿还）
    expect(calcLiabilityEndBalance(1000, 0, 300)).toBe(700)
  })

  it('credit exceeds begin + no debit → 大额新增负债', () => {
    expect(calcLiabilityEndBalance(0, 1000000, 0)).toBe(1000000)
  })

  it('debit exceeds begin → negative balance (超额偿付)', () => {
    // 偿付超过余额 → 负值（实务不常见但公式应正确计算）
    expect(calcLiabilityEndBalance(100, 0, 200)).toBe(-100)
  })

  it('equal credit and debit → end = begin', () => {
    expect(calcLiabilityEndBalance(5000, 2000, 2000)).toBe(5000)
  })

  it('large begin balance with zero movements', () => {
    expect(calcLiabilityEndBalance(999_999_999, 0, 0)).toBe(999_999_999)
  })

  it('large numbers (1e12)', () => {
    expect(calcLiabilityEndBalance(1e12, 5e11, 2e11)).toBe(1.3e12)
  })

  it('verify NEGATIVE direction: NOT 期初+借-贷 (asset style)', () => {
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

  it('zero credit, zero debit → end = begin (无变动)', () => {
    expect(calcLiabilityEndBalance(50000, 0, 0)).toBe(50000)
  })

  it('precision boundary (浮点精度)', () => {
    expect(calcLiabilityEndBalance(0.1, 0.2, 0.3)).toBeCloseTo(0, 10)
  })
})

// ============================================================
// calcTriangleReconciliation — 三角勾稽差额 (CP-K3-03)
// diff = end - (begin + inc - dec)，恒等时为0
// ============================================================
describe('calcTriangleReconciliation — edge cases (CP-K3-03)', () => {
  it('balanced case → 0 (完全勾稽平衡)', () => {
    // end = begin + inc - dec = 1000 + 500 - 200 = 1300
    expect(calcTriangleReconciliation(1000, 500, 200, 1300)).toBe(0)
  })

  it('imbalanced case → positive diff (期末偏高)', () => {
    // end=1400, expected=1300 → diff=100
    expect(calcTriangleReconciliation(1000, 500, 200, 1400)).toBe(100)
  })

  it('imbalanced case → negative diff (期末偏低，负债少计风险)', () => {
    // end=1200, expected=1300 → diff=-100
    expect(calcTriangleReconciliation(1000, 500, 200, 1200)).toBe(-100)
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

  it('large values imbalanced → diff', () => {
    const begin = 1e12
    const inc = 5e11
    const dec = 2e11
    const end = 1.5e12 // off by 0.2e12
    const expected = end - (begin + inc - dec)
    expect(calcTriangleReconciliation(begin, inc, dec, end)).toBeCloseTo(expected, 4)
  })

  it('negative begin (罕见但不应崩溃)', () => {
    // begin=-100, inc=50, dec=30 → expected=-80; end=-80 → diff=0
    expect(calcTriangleReconciliation(-100, 50, 30, -80)).toBe(0)
  })
})

// ============================================================
// calcProportion — 占比 = item / total (CP-K3-05)
// total=0 → null
// ============================================================
describe('calcProportion — edge cases (CP-K3-05)', () => {
  it('total=0 → null (避免除零)', () => {
    expect(calcProportion(500, 0)).toBeNull()
  })

  it('normal case: 500/1000 = 0.5', () => {
    expect(calcProportion(500, 1000)).toBe(0.5)
  })

  it('item=0 → 0 (零占比)', () => {
    expect(calcProportion(0, 1000)).toBe(0)
  })

  it('item > total → >1 (单项超合计，异常但不崩)', () => {
    expect(calcProportion(1500, 1000)).toBe(1.5)
  })

  it('negative item (红字冲回)', () => {
    expect(calcProportion(-200, 1000)).toBe(-0.2)
  })

  it('negative total → valid (不常见但公式接受)', () => {
    expect(calcProportion(100, -500)).toBe(-0.2)
  })

  it('both negative', () => {
    expect(calcProportion(-100, -500)).toBe(0.2)
  })

  it('large numbers precision', () => {
    const result = calcProportion(1e12, 3e12)
    expect(result).toBeCloseTo(1 / 3, 10)
  })

  it('very small item / large total → near zero', () => {
    expect(calcProportion(0.01, 1e9)).toBeCloseTo(1e-11, 15)
  })
})

// ============================================================
// calcSubtotal — 合计 = Σarr (CP-K3-04, CP-K3-06)
// 空数组→0
// ============================================================
describe('calcSubtotal — edge cases (CP-K3-04/06)', () => {
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

  it('single zero element', () => {
    expect(calcSubtotal([0])).toBe(0)
  })

  it('all zeros', () => {
    expect(calcSubtotal([0, 0, 0, 0])).toBe(0)
  })

  it('many elements (模拟50+往来对象)', () => {
    const arr = Array.from({ length: 50 }, (_, i) => (i + 1) * 1000) // 1000~50000
    const expected = (50 * 51 / 2) * 1000 // 1275000
    expect(calcSubtotal(arr)).toBe(expected)
  })

  it('accounts aging buckets (4区间模拟)', () => {
    // 1年内/1-2年/2-3年/3年以上
    const agingBuckets = [500000, 200000, 100000, 50000]
    expect(calcSubtotal(agingBuckets)).toBe(850000)
  })
})

// ============================================================
// calcChangeRate — 变动率 (CP-K3-06 related)
// prior=0∧current=0→0, prior=0∧current≠0→1, normal
// ============================================================
describe('calcChangeRate — edge cases', () => {
  it('prior=0 ∧ current=0 → 0 (无变动)', () => {
    expect(calcChangeRate(0, 0)).toBe(0)
  })

  it('prior=0 ∧ current≠0 → 1 (100%增长，从无到有)', () => {
    expect(calcChangeRate(1000, 0)).toBe(1)
  })

  it('prior=0 ∧ current negative → 1 (新增负余额也算100%)', () => {
    expect(calcChangeRate(-500, 0)).toBe(1)
  })

  it('normal growth: current=1200, prior=1000 → 0.2 (20%增长)', () => {
    expect(calcChangeRate(1200, 1000)).toBeCloseTo(0.2, 10)
  })

  it('negative growth: current=800, prior=1000 → -0.2 (20%下降)', () => {
    expect(calcChangeRate(800, 1000)).toBeCloseTo(-0.2, 10)
  })

  it('no change: current=1000, prior=1000 → 0', () => {
    expect(calcChangeRate(1000, 1000)).toBe(0)
  })

  it('doubling: current=2000, prior=1000 → 1.0 (100%)', () => {
    expect(calcChangeRate(2000, 1000)).toBe(1.0)
  })

  it('halving: current=500, prior=1000 → -0.5 (50%下降)', () => {
    expect(calcChangeRate(500, 1000)).toBe(-0.5)
  })

  it('current=0, prior=1000 → -1.0 (100%下降，全部清偿)', () => {
    expect(calcChangeRate(0, 1000)).toBe(-1.0)
  })

  it('large numbers', () => {
    // 从1e12增长到1.5e12 → 50%增长
    expect(calcChangeRate(1.5e12, 1e12)).toBeCloseTo(0.5, 10)
  })

  it('negative prior (罕见但不崩)', () => {
    // current=100, prior=-200 → (100-(-200))/-200 = -1.5
    expect(calcChangeRate(100, -200)).toBeCloseTo(-1.5, 10)
  })
})
