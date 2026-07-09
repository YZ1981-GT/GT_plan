/**
 * 单元测试 — M1 应付股利公式引擎 (useM1FormulaEngine + useM1FxEngine + useM1DividendEngine)
 *
 * Spec: .kiro/specs/m1-dividends-payable/
 * Task: 7.1
 * Requirements: P1-P6
 *
 * 覆盖：
 * - useM1FormulaEngine: calcAuditedAmount, calcLiabilityEndBalance, calcSubtotal, calcVarianceAmount, calcVarianceRate
 * - useM1FxEngine: calcFxConverted, calcFxDiff
 * - useM1DividendEngine: calcDeclaredDividend, calcDeclareDiff
 *
 * 科目：2232 应付股利（贷方/负债类！期末=期初+贷方-借方）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
  calcVarianceAmount,
  calcVarianceRate,
} from '../composables/useM1FormulaEngine'
import {
  calcFxConverted,
  calcFxDiff,
} from '../composables/useM1FxEngine'
import {
  calcDeclaredDividend,
  calcDeclareDiff,
} from '../composables/useM1DividendEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// useM1FormulaEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── 1. calcAuditedAmount (P1) ──────────────────────────────────────────────

describe('calcAuditedAmount (P1: 审定数=未审+AJE+RJE)', () => {
  it('all zeros → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('negative AJE: 调减审定数', () => {
    // 未审5000 + AJE(-800) + RJE(0) = 4200
    expect(calcAuditedAmount(5000, -800, 0)).toBe(4200)
  })

  it('mixed values: positive unadj + negative AJE + positive RJE', () => {
    // 10000 + (-3000) + 500 = 7500
    expect(calcAuditedAmount(10000, -3000, 500)).toBe(7500)
  })

  it('NaN treated as 0 via safe()', () => {
    expect(calcAuditedAmount(NaN, 100, 50)).toBe(150)
    expect(calcAuditedAmount(1000, NaN, NaN)).toBe(1000)
  })

  it('undefined/null treated as 0 via safe()', () => {
    expect(calcAuditedAmount(undefined as any, 200, 100)).toBe(300)
    expect(calcAuditedAmount(500, null as any, undefined as any)).toBe(500)
  })
})

// ─── 2. calcLiabilityEndBalance (P2) ────────────────────────────────────────

describe('calcLiabilityEndBalance (P2: 负债类期末=期初+贷方-借方)', () => {
  it('basic: 期初100 + 贷方(宣告)50 - 借方(支付)20 = 130', () => {
    expect(calcLiabilityEndBalance(100, 50, 20)).toBe(130)
  })

  it('zero debit (只有宣告无支付): 期末=期初+贷方', () => {
    expect(calcLiabilityEndBalance(1000, 500, 0)).toBe(1500)
  })

  it('zero credit (只有支付无宣告): 期末=期初-借方', () => {
    expect(calcLiabilityEndBalance(1000, 0, 300)).toBe(700)
  })

  it('all zeros → 0', () => {
    expect(calcLiabilityEndBalance(0, 0, 0)).toBe(0)
  })

  it('debit exceeds begin+credit → negative (异常但公式正确)', () => {
    expect(calcLiabilityEndBalance(10, 5, 20)).toBe(-5)
  })

  it('NaN/undefined handling', () => {
    expect(calcLiabilityEndBalance(NaN, 100, 50)).toBe(50)
    expect(calcLiabilityEndBalance(1000, undefined as any, null as any)).toBe(1000)
  })
})

// ─── 3. calcSubtotal (P6) ───────────────────────────────────────────────────

describe('calcSubtotal (P6: 数组求和)', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('large array (8个股东)', () => {
    expect(calcSubtotal([100, 200, 300, 400, 500, 600, 700, 800])).toBe(3600)
  })

  it('NaN in array treated as 0', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
  })

  it('undefined/null in array treated as 0', () => {
    expect(calcSubtotal([100, undefined as any, null as any, 200])).toBe(300)
  })

  it('non-array input → 0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })
})

// ─── 4. calcVarianceAmount ──────────────────────────────────────────────────

describe('calcVarianceAmount (变动额=期末审定-期初审定)', () => {
  it('positive variance: 本期应付股利增加', () => {
    // 期末1500 - 期初1000 = +500
    expect(calcVarianceAmount(1500, 1000)).toBe(500)
  })

  it('negative variance: 本期应付股利减少', () => {
    // 期末800 - 期初1200 = -400
    expect(calcVarianceAmount(800, 1200)).toBe(-400)
  })

  it('zero variance: 无变动', () => {
    expect(calcVarianceAmount(1000, 1000)).toBe(0)
  })

  it('NaN handling', () => {
    expect(calcVarianceAmount(NaN, 100)).toBe(-100)
    expect(calcVarianceAmount(500, NaN)).toBe(500)
  })
})

// ─── 5. calcVarianceRate ────────────────────────────────────────────────────

describe('calcVarianceRate (xlsx: IF(AND(E=0,J=0),0,IF(AND(E=0,J>0),1,J/E)))', () => {
  it('both zero → 0 (无变动)', () => {
    expect(calcVarianceRate(0, 0)).toBe(0)
  })

  it('begin=0 & variance>0 → 1 (100%增长)', () => {
    expect(calcVarianceRate(0, 500)).toBe(1)
  })

  it('normal division: variance/begin', () => {
    // 变动额200 / 期初1000 = 0.2 (增长20%)
    expect(calcVarianceRate(1000, 200)).toBeCloseTo(0.2, 5)
  })

  it('begin=0 & variance<0 → 返回变动额本身(保护性)', () => {
    // 期初=0且变动<0 → 返回v (避免除零)
    expect(calcVarianceRate(0, -300)).toBe(-300)
  })

  it('negative variance with normal begin', () => {
    // 变动额-400 / 期初2000 = -0.2
    expect(calcVarianceRate(2000, -400)).toBeCloseTo(-0.2, 5)
  })

  it('NaN handling: safe(NaN)=0', () => {
    // begin=NaN → safe=0, variance=NaN → safe=0 → both zero → 0
    expect(calcVarianceRate(NaN, NaN)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useM1FxEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── 6. calcFxConverted (P3) ────────────────────────────────────────────────

describe('calcFxConverted (P3: 折算本位币=原币×汇率)', () => {
  it('USD 100 × 7.2 → 720', () => {
    expect(calcFxConverted(100, 7.2)).toBeCloseTo(720, 5)
  })

  it('zero amount → 0', () => {
    expect(calcFxConverted(0, 7.2)).toBe(0)
  })

  it('zero rate → 0', () => {
    expect(calcFxConverted(100, 0)).toBe(0)
  })

  it('NaN/undefined handling', () => {
    expect(calcFxConverted(NaN, 7.0)).toBe(0)
    expect(calcFxConverted(100, undefined as any)).toBe(0)
  })
})

// ─── 7. calcFxDiff (P4) ─────────────────────────────────────────────────────

describe('calcFxDiff (P4: 汇兑差异=折算-账面)', () => {
  it('positive diff: 汇率上升导致外币负债增加', () => {
    // 折算750 - 账面720 = +30
    expect(calcFxDiff(750, 720)).toBe(30)
  })

  it('negative diff: 汇率下降导致外币负债减少', () => {
    // 折算690 - 账面720 = -30
    expect(calcFxDiff(690, 720)).toBe(-30)
  })

  it('zero diff: 无汇兑差异', () => {
    expect(calcFxDiff(720, 720)).toBe(0)
  })

  it('NaN handling', () => {
    expect(calcFxDiff(NaN, 100)).toBe(-100)
    expect(calcFxDiff(500, NaN)).toBe(500)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useM1DividendEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── 8. calcDeclaredDividend (P5) ───────────────────────────────────────────

describe('calcDeclaredDividend (P5: 应宣告股利=利润×比例)', () => {
  it('profit 1,000,000 × 30% → 300,000', () => {
    expect(calcDeclaredDividend(1_000_000, 0.3)).toBeCloseTo(300_000, 5)
  })

  it('zero ratio → 0 (不分配)', () => {
    expect(calcDeclaredDividend(1_000_000, 0)).toBe(0)
  })

  it('zero profit → 0 (无利润可分)', () => {
    expect(calcDeclaredDividend(0, 0.5)).toBe(0)
  })

  it('NaN/undefined handling', () => {
    expect(calcDeclaredDividend(NaN, 0.3)).toBe(0)
    expect(calcDeclaredDividend(1_000_000, undefined as any)).toBe(0)
  })
})

// ─── 9. calcDeclareDiff ─────────────────────────────────────────────────────

describe('calcDeclareDiff (宣告差异=测算-账面)', () => {
  it('positive: 少分配（应宣告>实际宣告）', () => {
    // 测算300,000 - 账面250,000 = +50,000
    expect(calcDeclareDiff(300_000, 250_000)).toBe(50_000)
  })

  it('negative: 多分配（应宣告<实际宣告）', () => {
    // 测算200,000 - 账面250,000 = -50,000
    expect(calcDeclareDiff(200_000, 250_000)).toBe(-50_000)
  })

  it('zero: 完全匹配', () => {
    expect(calcDeclareDiff(300_000, 300_000)).toBe(0)
  })

  it('NaN handling', () => {
    expect(calcDeclareDiff(NaN, 100)).toBe(-100)
    expect(calcDeclareDiff(500, NaN)).toBe(500)
  })
})
