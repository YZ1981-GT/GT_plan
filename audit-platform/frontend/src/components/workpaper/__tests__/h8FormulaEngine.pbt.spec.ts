/**
 * Property-Based Tests — H8 使用权资产公式引擎 + CAS21计量引擎
 *
 * Spec: .kiro/specs/h8-right-of-use-assets/ Tasks 2.3 ~ 2.7
 * Framework: fast-check (fc.assert + fc.property)
 * numRuns: 200
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcNetValue,
  calcSubtotal,
} from '../composables/useH8FormulaEngine'
import {
  calcInitialMeasurement,
  calcDepreciationPeriod,
  calcTerminationGainLoss,
  isShortTermLease,
  isLowValueLease,
} from '../composables/useH8CAS21Engine'

// ============================================================
// P1 (Task 2.3): 审定数公式链
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P1: 审定数公式链', () => {
  /**
   * **Validates: Requirements 2.3**
   * ∀ u,a,r ∈ ℝ: calcAuditedAmount(u, a, r) === u + a + r
   */
  it('∀ u,a,r: calcAuditedAmount(u,a,r) === u+a+r', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P2 (Task 2.4): 资产类期末余额
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P2: 资产类期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   * ∀ b,d,c ∈ ℝ: calcAssetEndBalance(b, d, c) === b + d - c
   */
  it('∀ b,d,c: calcAssetEndBalance(b,d,c) === b+d-c', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (b, d, c) => {
          expect(calcAssetEndBalance(b, d, c)).toBeCloseTo(b + d - c, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P3 (Task 2.5): 备抵类期末余额
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P3: 备抵类期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   * ∀ b,d,c ∈ ℝ: calcContraEndBalance(b, d, c) === b + c - d
   */
  it('∀ b,d,c: calcContraEndBalance(b,d,c) === b+c-d', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (b, d, c) => {
          expect(calcContraEndBalance(b, d, c)).toBeCloseTo(b + c - d, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P4 (Task 2.6): CAS21初始计量
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P4: CAS21初始计量公式', () => {
  /**
   * **Validates: Requirements 10.1**
   * ∀ ll,dc,inc ∈ ℝ: calcInitialMeasurement(ll, dc, inc) === ll + dc - inc
   */
  it('∀ ll,dc,inc: calcInitialMeasurement(ll,dc,inc) === ll+dc-inc', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (ll, dc, inc) => {
          expect(calcInitialMeasurement(ll, dc, inc)).toBeCloseTo(ll + dc - inc, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P5 (Task 2.7): 折旧期=min(租赁期,寿命)
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P5: 折旧期min公式', () => {
  /**
   * **Validates: Requirements 10.2**
   * ∀ lt,ul ∈ ℤ⁺ (1..600 months): calcDepreciationPeriod(lt, ul) === Math.min(lt, ul)
   */
  it('∀ lt,ul (positive integers): calcDepreciationPeriod(lt,ul) === Math.min(lt,ul)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 600 }),
        fc.integer({ min: 1, max: 600 }),
        (lt, ul) => {
          expect(calcDepreciationPeriod(lt, ul)).toBe(Math.min(lt, ul))
        },
      ),
      { numRuns: 200 },
    )
  })
})


// ============================================================
// P6 (Task 2.8): 终止损益
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P6: 终止损益', () => {
  /**
   * **Validates: Requirements 10.3**
   * ∀ lb,nv ∈ ℝ: calcTerminationGainLoss(lb, nv) === lb - nv
   */
  it('∀ lb,nv: calcTerminationGainLoss(lb,nv) === lb-nv', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (lb, nv) => {
          expect(calcTerminationGainLoss(lb, nv)).toBeCloseTo(lb - nv, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P7 (Task 2.9): 短期租赁判断
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P7: 短期租赁判断', () => {
  /**
   * **Validates: Requirements 8.2**
   * ∀ m ∈ [1,36]: isShortTermLease(m) === (m <= 12)
   */
  it('∀ m ∈ [1,36]: isShortTermLease(m) === (m <= 12)', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 36 }),
        (m) => {
          expect(isShortTermLease(m)).toBe(m <= 12)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P8 (Task 2.10): 低价值租赁判断
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P8: 低价值租赁判断', () => {
  /**
   * **Validates: Requirements 8.3**
   * ∀ v ∈ [1,100000]: isLowValueLease(v) === (v <= 40000)
   */
  it('∀ v ∈ [1,100000]: isLowValueLease(v) === (v <= 40000)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 1, max: 100000, noNaN: true }),
        (v) => {
          expect(isLowValueLease(v)).toBe(v <= 40000)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P9 (Task 2.11): 合计行恒等
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P9: 合计行恒等', () => {
  /**
   * **Validates: Requirements 2.4**
   * ∀ arr ∈ number[]: calcSubtotal(arr) ≈ arr.reduce((s,x)=>s+x, 0)
   */
  it('∀ arr: calcSubtotal(arr) ≈ Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 0, maxLength: 20 }),
        (arr) => {
          const expected = arr.reduce((s, x) => s + x, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P10 (Task 2.12): 净值公式
// ============================================================
describe('Feature: h8-right-of-use-assets, Property P10: 净值公式', () => {
  /**
   * **Validates: Requirements 2.3**
   * ∀ c,d,i ∈ ℝ⁺: calcNetValue(c, d, i) === c - d - i
   */
  it('∀ c,d,i: calcNetValue(c,d,i) === c-d-i', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (c, d, i) => {
          expect(calcNetValue(c, d, i)).toBeCloseTo(c - d - i, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})
