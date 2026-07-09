/**
 * Unit Tests — M6 未分配利润公式引擎 + 分配结转引擎
 *
 * Spec: .kiro/specs/m6-retained-earnings/
 * Task: 7.1 单元测试：useM6FormulaEngine + useM6DistributionEngine
 *
 * 覆盖：
 * - Edge cases: zero values, negative values, very large numbers
 * - Boundary: precision (floating point rounding)
 * - Direction: verify equity credit direction explicitly (different from M3 debit/counter)
 * - Safe handling: null/undefined/NaN inputs → 0
 * - Integration: calcRetainedEnd consistency with calcDistributable
 *
 * Requirements: P1-P7
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcEquityEndBalance,
  calcSubtotal,
} from '../composables/useM6FormulaEngine'
import {
  calcRetainedEnd,
  calcDistributable,
  calcLinkageDiff,
} from '../composables/useM6DistributionEngine'

// ─── safe() 行为验证 ─────────────────────────────────────────────────────────

describe('safe() behavior (internal helper, tested through public API)', () => {
  it('null → 0', () => {
    // calcAuditedAmount passes through safe() for each arg
    expect(calcAuditedAmount(null as any, 0, 0)).toBe(0)
    expect(calcAuditedAmount(0, null as any, 0)).toBe(0)
    expect(calcAuditedAmount(0, 0, null as any)).toBe(0)
  })

  it('undefined → 0', () => {
    expect(calcAuditedAmount(undefined as any, 0, 0)).toBe(0)
    expect(calcEquityEndBalance(undefined as any, 100, 50)).toBe(50)
  })

  it('NaN → 0', () => {
    expect(calcAuditedAmount(NaN, 100, 200)).toBe(300)
    expect(calcEquityEndBalance(NaN, NaN, NaN)).toBe(0)
  })

  it('Infinity → 0', () => {
    expect(calcAuditedAmount(Infinity, 100, 0)).toBe(100)
    expect(calcAuditedAmount(-Infinity, 100, 0)).toBe(100)
  })

  it('"abc" (non-numeric string) → 0', () => {
    expect(calcAuditedAmount('abc' as any, 50, 50)).toBe(100)
    expect(calcRetainedEnd('abc' as any, 100, 0, 0)).toBe(100)
  })
})

// ─── calcAuditedAmount ───────────────────────────────────────────────────────

describe('calcAuditedAmount', () => {
  it('zero values: 0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('positive values: 1000 + 200 + 50 = 1250', () => {
    expect(calcAuditedAmount(1000, 200, 50)).toBe(1250)
  })

  it('negative AJE: 1000 + (-300) + 0 = 700', () => {
    expect(calcAuditedAmount(1000, -300, 0)).toBe(700)
  })

  it('negative RJE: 1000 + 0 + (-500) = 500', () => {
    expect(calcAuditedAmount(1000, 0, -500)).toBe(500)
  })

  it('mixed signs: (-500) + 200 + (-100) = -400', () => {
    expect(calcAuditedAmount(-500, 200, -100)).toBe(-400)
  })

  it('all negative: (-100) + (-200) + (-300) = -600', () => {
    expect(calcAuditedAmount(-100, -200, -300)).toBe(-600)
  })

  it('large numbers: 1e12 + 1e12 + 1e12 = 3e12', () => {
    expect(calcAuditedAmount(1e12, 1e12, 1e12)).toBe(3e12)
  })
})

// ─── calcEquityEndBalance (权益类贷方方向！) ─────────────────────────────────

describe('calcEquityEndBalance (credit direction - 权益类)', () => {
  it('期末=期初+贷方-借方: 1000 + 500 - 200 = 1300', () => {
    expect(calcEquityEndBalance(1000, 500, 200)).toBe(1300)
  })

  it('credit direction: begin+credit-debit (NOT begin+debit-credit like M3)', () => {
    // M6 权益类贷方：增加在贷方 → 期末=begin+credit-debit
    // M3 库存股备抵借方：增加在借方 → 期末=begin+debit-credit
    const begin = 5000
    const credit = 2000 // 本年净利润转入
    const debit = 800   // 分配(盈余公积+股利)
    // M6: 5000 + 2000 - 800 = 6200
    expect(calcEquityEndBalance(begin, credit, debit)).toBe(6200)
    // 如果用了M3的公式(借方方向)会得到不同结果: 5000 + 800 - 2000 = 3800
    expect(calcEquityEndBalance(begin, credit, debit)).not.toBe(begin + debit - credit)
  })

  it('negative result allowed (累计亏损): 100 + 0 - 500 = -400', () => {
    // 未分配利润可以为负（累计亏损）
    expect(calcEquityEndBalance(100, 0, 500)).toBe(-400)
  })

  it('zero begin, pure credit: 0 + 3000 - 0 = 3000', () => {
    expect(calcEquityEndBalance(0, 3000, 0)).toBe(3000)
  })

  it('zero begin, pure debit: 0 + 0 - 1000 = -1000', () => {
    expect(calcEquityEndBalance(0, 0, 1000)).toBe(-1000)
  })

  it('all zero: 0 + 0 - 0 = 0', () => {
    expect(calcEquityEndBalance(0, 0, 0)).toBe(0)
  })

  it('large numbers precision: 9999999999.99 + 0.01 - 0 ≈ 10000000000', () => {
    expect(calcEquityEndBalance(9999999999.99, 0.01, 0)).toBeCloseTo(10000000000, 5)
  })
})

// ─── calcSubtotal ────────────────────────────────────────────────────────────

describe('calcSubtotal', () => {
  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element: [42] → 42', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('multiple positive: [100, 200, 300] → 600', () => {
    expect(calcSubtotal([100, 200, 300])).toBe(600)
  })

  it('mixed: [100, -50, 200, -75] → 175', () => {
    expect(calcSubtotal([100, -50, 200, -75])).toBe(175)
  })

  it('array with NaN → treated as 0', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
  })

  it('array with null → treated as 0', () => {
    expect(calcSubtotal([100, null as any, 200])).toBe(300)
  })

  it('array with undefined → treated as 0', () => {
    expect(calcSubtotal([undefined as any, 50])).toBe(50)
  })

  it('non-array input → 0', () => {
    expect(calcSubtotal(null as any)).toBe(0)
    expect(calcSubtotal(undefined as any)).toBe(0)
  })

  it('all zeros: [0, 0, 0, 0] → 0', () => {
    expect(calcSubtotal([0, 0, 0, 0])).toBe(0)
  })
})

// ─── calcRetainedEnd (利润分配结转核心！) ─────────────────────────────────────

describe('calcRetainedEnd', () => {
  it('all zero → 0', () => {
    expect(calcRetainedEnd(0, 0, 0, 0)).toBe(0)
  })

  it('basic: 5000 + 2000 - 200 - 100 = 6700', () => {
    expect(calcRetainedEnd(5000, 2000, 200, 100)).toBe(6700)
  })

  it('large numbers: 1e12 + 5e11 - 5e10 - 5e10 = 1.4e12', () => {
    expect(calcRetainedEnd(1e12, 5e11, 5e10, 5e10)).toBe(1.4e12)
  })

  it('negative net profit (亏损): 5000 + (-3000) - 0 - 0 = 2000', () => {
    expect(calcRetainedEnd(5000, -3000, 0, 0)).toBe(2000)
  })

  it('negative begin (累计亏损): (-2000) + 5000 - 300 - 200 = 2500', () => {
    expect(calcRetainedEnd(-2000, 5000, 300, 200)).toBe(2500)
  })

  it('result can be negative: 1000 + 500 - 2000 - 1000 = -1500', () => {
    expect(calcRetainedEnd(1000, 500, 2000, 1000)).toBe(-1500)
  })

  it('only surplus accrual: 10000 + 0 - 1000 - 0 = 9000', () => {
    expect(calcRetainedEnd(10000, 0, 1000, 0)).toBe(9000)
  })

  it('only dividend: 10000 + 0 - 0 - 500 = 9500', () => {
    expect(calcRetainedEnd(10000, 0, 0, 500)).toBe(9500)
  })

  it('precision: 0.1 + 0.2 - 0.05 - 0.05 = 0.2', () => {
    expect(calcRetainedEnd(0.1, 0.2, 0.05, 0.05)).toBeCloseTo(0.2, 10)
  })
})

// ─── calcDistributable ───────────────────────────────────────────────────────

describe('calcDistributable', () => {
  it('basic: 5000 + 2000 = 7000', () => {
    expect(calcDistributable(5000, 2000)).toBe(7000)
  })

  it('negative begin: (-1000) + 3000 = 2000', () => {
    expect(calcDistributable(-1000, 3000)).toBe(2000)
  })

  it('negative net profit: 5000 + (-2000) = 3000', () => {
    expect(calcDistributable(5000, -2000)).toBe(3000)
  })

  it('both negative: (-500) + (-1000) = -1500', () => {
    expect(calcDistributable(-500, -1000)).toBe(-1500)
  })

  it('zero + zero = 0', () => {
    expect(calcDistributable(0, 0)).toBe(0)
  })

  it('large: 9.99e14 + 1e12 = 1.00e15 (approximately)', () => {
    expect(calcDistributable(9.99e14, 1e12)).toBeCloseTo(1.0e15, -9)
  })
})

// ─── calcLinkageDiff ─────────────────────────────────────────────────────────

describe('calcLinkageDiff', () => {
  it('zero diff (一致): 500 - 500 = 0', () => {
    expect(calcLinkageDiff(500, 500)).toBe(0)
  })

  it('positive diff (M6 > source): 600 - 500 = 100', () => {
    expect(calcLinkageDiff(600, 500)).toBe(100)
  })

  it('negative diff (M6 < source): 400 - 500 = -100', () => {
    expect(calcLinkageDiff(400, 500)).toBe(-100)
  })

  it('both zero: 0 - 0 = 0', () => {
    expect(calcLinkageDiff(0, 0)).toBe(0)
  })

  it('negative values: (-100) - (-100) = 0', () => {
    expect(calcLinkageDiff(-100, -100)).toBe(0)
  })

  it('mixed: (-50) - 50 = -100', () => {
    expect(calcLinkageDiff(-50, 50)).toBe(-100)
  })
})

// ─── Integration: calcRetainedEnd 与 calcDistributable 一致性 ────────────────

describe('Integration: calcRetainedEnd ↔ calcDistributable consistency', () => {
  it('calcRetainedEnd(b,np,sa,d) = calcDistributable(b,np) - sa - d', () => {
    const b = 10000, np = 5000, sa = 500, d = 300
    const retained = calcRetainedEnd(b, np, sa, d)
    const distributable = calcDistributable(b, np)
    expect(retained).toBe(distributable - sa - d)
  })

  it('consistency with all negative inputs', () => {
    const b = -2000, np = -1000, sa = 100, d = 50
    const retained = calcRetainedEnd(b, np, sa, d)
    const distributable = calcDistributable(b, np)
    expect(retained).toBe(distributable - sa - d)
  })

  it('consistency with zeros', () => {
    const retained = calcRetainedEnd(0, 0, 0, 0)
    const distributable = calcDistributable(0, 0)
    expect(retained).toBe(distributable - 0 - 0)
    expect(retained).toBe(0)
  })

  it('consistency with large numbers', () => {
    const b = 1e12, np = 5e11, sa = 5e10, d = 2e10
    const retained = calcRetainedEnd(b, np, sa, d)
    const distributable = calcDistributable(b, np)
    expect(retained).toBe(distributable - sa - d)
  })
})
