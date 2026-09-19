/**
 * Property-Based Tests — H5 油气资产公式引擎 + 折耗引擎
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Tasks 2.3 ~ 2.12
 * Framework: fast-check (fc.assert + fc.property)
 * numRuns: 200
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcSubtotal,
  calcNetValue,
  calcTriangleReconciliation,
  calcLeaseReturnRate,
} from '../composables/useH5FormulaEngine'
import {
  calcUnitDepletion,
  calcDepletionCapped,
} from '../composables/useH5DepletionEngine'

// ============================================================
// P1 (Task 2.3): 审定数公式链
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P1: 审定数公式链正确性', () => {
  /**
   * **Validates: Requirements 2.3**
   * ∀ unadj, aje, rje ∈ ℝ: calcAuditedAmount(u, a, r) === u + a + r
   */
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P2 (Task 2.4): 资产类期末余额
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P2: 资产类期末余额', () => {
  /**
   * **Validates: Requirements 2.4**
   * ∀ begin, debit, credit ∈ ℝ≥0: calcAssetEndBalance(b, d, c) === b + d - c
   */
  it('calcAssetEndBalance(b, d, c) === b + d - c', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (b, d, c) => {
          const result = calcAssetEndBalance(b, d, c)
          const expected = b + d - c
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P3 (Task 2.5): 备抵类期末余额
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P3: 备抵类期末余额', () => {
  /**
   * **Validates: Requirements 2.5**
   * ∀ begin, debit, credit ∈ ℝ≥0: calcContraEndBalance(b, d, c) === b + c - d
   */
  it('calcContraEndBalance(b, d, c) === b + c - d', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (b, d, c) => {
          const result = calcContraEndBalance(b, d, c)
          const expected = b + c - d
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P4 (Task 2.6): 单位产量法折耗（正常情况）
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P4: 单位产量法折耗', () => {
  /**
   * **Validates: Requirements 7.4, 9.1**
   * ∀ cost>0, salvage<cost, production>0, reserves>production:
   * calcUnitDepletion(cost, salvage, prod, res) === (cost - salvage) * prod / res
   */
  it('calcUnitDepletion(cost, salvage, prod, res) === (cost-salvage)*prod/res', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 1, max: 1e6, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
        (cost, salvageRatio, production, reserveExtra) => {
          // Derive salvage < cost, reserves > production
          const salvage = cost * salvageRatio * 0.99 // ensure salvage < cost
          const reserves = production * (1 + reserveExtra + 0.01) // ensure reserves > production
          const result = calcUnitDepletion(cost, salvage, production, reserves)
          const expected = (cost - salvage) * production / reserves
          expect(Math.abs(result - expected)).toBeLessThan(1e-4)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P5 (Task 2.7): 储量为0时折耗=0
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P5: 储量为零不除零', () => {
  /**
   * **Validates: Requirements 9.1**
   * ∀ cost, salvage, production: calcUnitDepletion(cost, salvage, prod, 0) === 0
   */
  it('calcUnitDepletion(cost, salvage, prod, 0) === 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 1, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (cost, salvage, production) => {
          const result = calcUnitDepletion(cost, salvage, production, 0)
          expect(result).toBe(0)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P6 (Task 2.8): 折耗封顶
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P6: 折耗封顶', () => {
  /**
   * **Validates: Requirements 9.5**
   * ∀ cost, salvage(<cost), accDepletion(<cost-salvage):
   * calcDepletionCapped(cost, salvage, accDepl) === cost - salvage - accDepl
   */
  it('calcDepletionCapped(cost, salvage, accDepl) === cost - salvage - accDepl', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 100, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1, noNaN: true, noDefaultInfinity: true }),
        (cost, salvageRatio, deplRatio) => {
          const salvage = cost * salvageRatio * 0.99
          const depletable = cost - salvage
          const accDepletion = depletable * deplRatio * 0.99
          const result = calcDepletionCapped(cost, salvage, accDepletion)
          const expected = cost - salvage - accDepletion
          expect(Math.abs(result - expected)).toBeLessThan(1e-4)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P7 (Task 2.9): 合计行恒等
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P7: 合计行恒等', () => {
  /**
   * **Validates: Requirements 2.6**
   * ∀ arr (non-empty): calcSubtotal(arr) === Σarr
   */
  it('calcSubtotal(arr) === arr.reduce((s,v)=>s+v, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(fc.double({ noNaN: true, noDefaultInfinity: true, min: -1e9, max: 1e9 }), { minLength: 1, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(Math.abs(result - expected)).toBeLessThan(1e-4)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P8 (Task 2.10): 净值公式
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P8: 净值公式', () => {
  /**
   * **Validates: Requirements 8.4**
   * ∀ cost, accDepletion, impairment ∈ ℝ≥0: calcNetValue(c, d, i) === c - d - i
   */
  it('calcNetValue(c, d, i) === c - d - i', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (c, d, i) => {
          const result = calcNetValue(c, d, i)
          const expected = c - d - i
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P9 (Task 2.11): 三角勾稽恒等
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P9: 三角勾稽恒等', () => {
  /**
   * **Validates: Requirements 2.6**
   * ∀ begin, increase, decrease ∈ ℝ≥0, end = begin + increase - decrease:
   * calcTriangleReconciliation(b, i, d, b+i-d) === 0
   */
  it('calcTriangleReconciliation(b, i, d, b+i-d) === 0', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true }),
        (begin, increase, decrease) => {
          const end = begin + increase - decrease
          const result = calcTriangleReconciliation(begin, increase, decrease, end)
          expect(Math.abs(result)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ============================================================
// P10 (Task 2.12): 租赁收益率
// ============================================================
describe('Feature: h5-oil-gas-assets, Property P10: 租赁收益率公式', () => {
  /**
   * **Validates: Requirements 11.1**
   * ∀ annualRent, netValue ∈ (0, 1e8]:
   * calcLeaseReturnRate(r, nv) === r / nv * 100
   */
  it('calcLeaseReturnRate(r, nv) === r/nv * 100', () => {
    fc.assert(
      fc.property(
        fc.double({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        fc.double({ min: 1, max: 1e8, noNaN: true, noDefaultInfinity: true }),
        (rent, netValue) => {
          const result = calcLeaseReturnRate(rent, netValue)
          const expected = (rent / netValue) * 100
          expect(Math.abs(result - expected)).toBeLessThan(1e-6)
        },
      ),
      { numRuns: 200 },
    )
  })
})
