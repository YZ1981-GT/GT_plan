/**
 * 单元测试 — M2 实收资本（股本）公式引擎
 * (useM2FormulaEngine + useM2FxEngine + useM2VerifyEngine)
 *
 * Spec: .kiro/specs/m2-paid-in-capital/
 * Task: 7.1
 * Requirements: P1-P7
 *
 * 覆盖：
 * - useM2FormulaEngine: calcAuditedAmount, calcEquityEndBalance, calcSubtotal,
 *   calcVarianceAmount, calcVarianceRate, calcShareRatio
 * - useM2FxEngine: calcFxConverted, calcFxDiff
 * - useM2VerifyEngine: calcVerifyDiff, calcPaidInRate
 *
 * 科目：4001 实收资本/股本（**贷方/权益类！期末=期初+贷方-借方**）
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
  calcVarianceAmount,
  calcVarianceRate,
  calcShareRatio,
} from '../composables/useM2FormulaEngine'
import {
  calcFxConverted,
  calcFxDiff,
} from '../composables/useM2FxEngine'
import {
  calcVerifyDiff,
  calcPaidInRate,
} from '../composables/useM2VerifyEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// useM2FormulaEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── 1. calcAuditedAmount (P1) ──────────────────────────────────────────────

describe('calcAuditedAmount (P1: 审定数=未审+AJE+RJE)', () => {
  it('all zeros → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('negative AJE: 调减审定数', () => {
    // 未审50000 + AJE(-8000) + RJE(0) = 42000
    expect(calcAuditedAmount(50000, -8000, 0)).toBe(42000)
  })

  it('mixed values: positive unadj + negative AJE + positive RJE', () => {
    // 100000 + (-30000) + 5000 = 75000
    expect(calcAuditedAmount(100000, -30000, 5000)).toBe(75000)
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

// ─── 2. calcEquityEndBalance (P2: 权益类贷方！) ─────────────────────────────

describe('calcEquityEndBalance (P2: 权益类期末=期初+贷方-借方)', () => {
  it('basic: 期初1000 + 贷方(增资)500 - 借方(减资)200 = 1300', () => {
    expect(calcEquityEndBalance(1000, 500, 200)).toBe(1300)
  })

  it('zero debit (只有增资无减资): 期末=期初+贷方', () => {
    expect(calcEquityEndBalance(10000, 5000, 0)).toBe(15000)
  })

  it('zero credit (只有减资无增资): 期末=期初-借方', () => {
    expect(calcEquityEndBalance(10000, 0, 3000)).toBe(7000)
  })

  it('all zeros → 0', () => {
    expect(calcEquityEndBalance(0, 0, 0)).toBe(0)
  })

  it('debit exceeds begin+credit → negative (异常但公式正确)', () => {
    // 减资超出期初+增资
    expect(calcEquityEndBalance(10, 5, 20)).toBe(-5)
  })

  it('NaN/undefined handling', () => {
    expect(calcEquityEndBalance(NaN, 100, 50)).toBe(50)
    expect(calcEquityEndBalance(1000, undefined as any, null as any)).toBe(1000)
  })

  it('权益类方向对比资产类方向：增资在贷方增加(正向)', () => {
    // 权益类：期末=期初+贷方-借方 → 增资在贷方
    const equityEnd = calcEquityEndBalance(1000, 500, 0)
    expect(equityEnd).toBe(1500)
    // 对比：资产类期末=期初+借方-贷方 → 方向相反！
  })
})

// ─── 3. calcSubtotal (P7) ───────────────────────────────────────────────────

describe('calcSubtotal (P7: 分类小计求和)', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42000])).toBe(42000)
  })

  it('large array (8个出资人)', () => {
    expect(calcSubtotal([100, 200, 300, 400, 500, 600, 700, 800])).toBe(3600)
  })

  it('NaN in array treated as 0 (NaN protection)', () => {
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
  it('positive variance: 本期实收资本增加（增资）', () => {
    // 期末15000 - 期初10000 = +5000
    expect(calcVarianceAmount(15000, 10000)).toBe(5000)
  })

  it('negative variance: 本期实收资本减少（减资）', () => {
    // 期末8000 - 期初12000 = -4000
    expect(calcVarianceAmount(8000, 12000)).toBe(-4000)
  })

  it('zero variance: 无变动', () => {
    expect(calcVarianceAmount(10000, 10000)).toBe(0)
  })

  it('begin=0 special case: 新设企业首次出资', () => {
    expect(calcVarianceAmount(5000000, 0)).toBe(5000000)
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

  it('begin=0 & variance>0 → 1 (100%增长，新设企业)', () => {
    expect(calcVarianceRate(0, 500000)).toBe(1)
  })

  it('normal division: variance/begin', () => {
    // 变动额2000 / 期初10000 = 0.2 (增长20%)
    expect(calcVarianceRate(10000, 2000)).toBeCloseTo(0.2, 5)
  })

  it('begin=0 & variance<0 → 返回变动额本身(保护性，div by zero)', () => {
    expect(calcVarianceRate(0, -3000)).toBe(-3000)
  })

  it('negative variance with normal begin', () => {
    // 变动额-4000 / 期初20000 = -0.2
    expect(calcVarianceRate(20000, -4000)).toBeCloseTo(-0.2, 5)
  })

  it('NaN handling: safe(NaN)=0', () => {
    expect(calcVarianceRate(NaN, NaN)).toBe(0)
  })
})

// ─── 6. calcShareRatio ──────────────────────────────────────────────────────

describe('calcShareRatio (持股/出资比例)', () => {
  it('normal: 1000/10000 = 10%', () => {
    expect(calcShareRatio(1000, 10000)).toBeCloseTo(0.1, 5)
  })

  it('total=0 → returns 0 (避免除零)', () => {
    expect(calcShareRatio(5000, 0)).toBe(0)
  })

  it('individual=0 → 0%', () => {
    expect(calcShareRatio(0, 10000)).toBe(0)
  })

  it('equal → 100%', () => {
    expect(calcShareRatio(10000, 10000)).toBeCloseTo(1.0, 5)
  })

  it('NaN/undefined handling', () => {
    expect(calcShareRatio(NaN, 10000)).toBe(0)
    expect(calcShareRatio(5000, NaN)).toBe(0)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useM2FxEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── 7. calcFxConverted (P3) ────────────────────────────────────────────────

describe('calcFxConverted (P3: 折算本位币=原币×出资日汇率)', () => {
  it('USD 100万 × 6.5 → 650万', () => {
    expect(calcFxConverted(1000000, 6.5)).toBeCloseTo(6500000, 5)
  })

  it('zero amount → 0 (无外币出资)', () => {
    expect(calcFxConverted(0, 7.2)).toBe(0)
  })

  it('zero rate → 0 (异常汇率)', () => {
    expect(calcFxConverted(100000, 0)).toBe(0)
  })

  it('large values: 1亿USD × 7.1', () => {
    expect(calcFxConverted(100000000, 7.1)).toBeCloseTo(710000000, 0)
  })

  it('NaN/undefined handling', () => {
    expect(calcFxConverted(NaN, 7.0)).toBe(0)
    expect(calcFxConverted(100000, undefined as any)).toBe(0)
  })
})

// ─── 8. calcFxDiff (P4) ─────────────────────────────────────────────────────

describe('calcFxDiff (P4: 折算差异=折算本位币-账面本位币)', () => {
  it('positive diff: 折算>账面 → 计入M4资本公积贷方', () => {
    // 折算7500000 - 账面7200000 = +300000
    expect(calcFxDiff(7500000, 7200000)).toBe(300000)
  })

  it('negative diff: 折算<账面 → 计入M4资本公积借方', () => {
    // 折算6900000 - 账面7200000 = -300000
    expect(calcFxDiff(6900000, 7200000)).toBe(-300000)
  })

  it('equal → 0 (无折算差异)', () => {
    expect(calcFxDiff(7200000, 7200000)).toBe(0)
  })

  it('NaN handling', () => {
    expect(calcFxDiff(NaN, 100)).toBe(-100)
    expect(calcFxDiff(500, NaN)).toBe(500)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// useM2VerifyEngine
// ═══════════════════════════════════════════════════════════════════════════════

// ─── 9. calcVerifyDiff (P5) ─────────────────────────────────────────────────

describe('calcVerifyDiff (P5: 验资差异=实缴出资-验资金额)', () => {
  it('paid === verified → 0 (核对一致)', () => {
    expect(calcVerifyDiff(5000000, 5000000)).toBe(0)
  })

  it('positive diff: 实缴>验资 → 需查明(企业多记/验资少记)', () => {
    // 实缴5200000 - 验资5000000 = +200000
    expect(calcVerifyDiff(5200000, 5000000)).toBe(200000)
  })

  it('negative diff: 实缴<验资 → 需追补出资凭证', () => {
    // 实缴4800000 - 验资5000000 = -200000
    expect(calcVerifyDiff(4800000, 5000000)).toBe(-200000)
  })

  it('both zero → 0', () => {
    expect(calcVerifyDiff(0, 0)).toBe(0)
  })

  it('NaN handling', () => {
    expect(calcVerifyDiff(NaN, 1000)).toBe(-1000)
    expect(calcVerifyDiff(5000, NaN)).toBe(5000)
  })
})

// ─── 10. calcPaidInRate (P6) ────────────────────────────────────────────────

describe('calcPaidInRate (P6: 出资到位率=实缴/认缴)', () => {
  it('subscribed=0 → returns 0 (避免除零)', () => {
    expect(calcPaidInRate(5000000, 0)).toBe(0)
  })

  it('full payment: 实缴=认缴 → 1.0 (100%)', () => {
    expect(calcPaidInRate(10000000, 10000000)).toBeCloseTo(1.0, 5)
  })

  it('partial payment: 实缴<认缴 → <1.0', () => {
    // 实缴7500000 / 认缴10000000 = 0.75 (75%)
    expect(calcPaidInRate(7500000, 10000000)).toBeCloseTo(0.75, 5)
  })

  it('over payment: 实缴>认缴 → >1.0 (超额出资罕见)', () => {
    // 实缴12000000 / 认缴10000000 = 1.2 (120%)
    expect(calcPaidInRate(12000000, 10000000)).toBeCloseTo(1.2, 5)
  })

  it('zero paid → 0% (全未出资)', () => {
    expect(calcPaidInRate(0, 10000000)).toBe(0)
  })

  it('NaN handling: safe(NaN)=0, NaN subscribed → 0', () => {
    expect(calcPaidInRate(NaN, 10000000)).toBe(0)
    expect(calcPaidInRate(5000000, NaN)).toBe(0)
  })
})
