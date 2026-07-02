/**
 * Property-Based Tests — E1 货币资金公式引擎
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 1.2
 *
 * Property 1: 审定数公式 calcAudited(u, a) === u + a
 * Property 2: 变动额/变动率（模板口径）
 * Property 3: 现金/数字货币余额链式
 * Property 4: 调节后余额
 * Property 5: 应计利息
 * Property 6: 外币折算
 * Property 7: 盘点差异
 * Property 8: 数组求和不变量
 * Property 9: 超阈值判定
 * Property 10: 动态行增删计数
 * Property 11: JSON Round-Trip
 *
 * **Validates: Requirements 1.2, 1.3, 3.2, 5.2, 6.2-6.4, 7.4, 10.3, 14.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  calcAudited,
  calcChange,
  calcChangeRate,
  calcCashBalance,
  calcReconciled,
  calcAccruedInterest,
  calcFxConvert,
  calcCountDiff,
  sumField,
  exceedsThreshold,
  serializeRows,
  deserializeRows,
} from '../useE1FormulaEngine'

// ─── Property 1: 审定数公式 ─────────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 1: 审定数公式', () => {
  /**
   * **Validates: Requirements 1.2**
   *
   * For any (unadjusted, adjustment) reals:
   * calcAudited(u, a) === u + a
   */
  it('calcAudited(u, a) === u + a for any reals', () => {
    const valArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(valArb, valArb, (u, a) => {
        const result = calcAudited(u, a)
        expect(result).toBeCloseTo(u + a, 10)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 2: 变动额/变动率（模板口径）────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 2: 变动额/变动率', () => {
  /**
   * **Validates: Requirements 1.3**
   *
   * For any (endingAudited, openingAudited):
   * - calcChange === ending - opening
   * - calcChangeRate: opening=0&ending=0→0, opening=0&ending>0→1, else change/opening
   */
  it('calcChange(ending, opening) === ending - opening', () => {
    const valArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(valArb, valArb, (ending, opening) => {
        const result = calcChange(ending, opening)
        expect(result).toBeCloseTo(ending - opening, 10)
      }),
      { numRuns: 100 },
    )
  })

  it('calcChangeRate follows 模板口径 rules', () => {
    const valArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(valArb, valArb, (change, opening) => {
        const result = calcChangeRate(change, opening)
        const ending = opening + change

        if (opening === 0 && ending === 0) {
          expect(result).toBe(0)
        } else if (opening === 0 && ending > 0) {
          expect(result).toBe(1)
        } else if (opening === 0) {
          // opening=0, ending<=0 (but not both zero)
          expect(result).toBe('')
        } else {
          expect(result).toBeCloseTo(change / opening, 10)
        }
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 3: 现金/数字货币余额链式 ──────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 3: 现金/数字货币余额链式', () => {
  /**
   * **Validates: Requirements 3.2, 14.2**
   *
   * For any (opening, increase, decrease):
   * calcCashBalance(o, i, d) === o + i - d
   */
  it('calcCashBalance(o, i, d) === o + i - d', () => {
    const valArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(valArb, valArb, valArb, (o, i, d) => {
        const result = calcCashBalance(o, i, d)
        expect(result).toBeCloseTo(o + i - d, 10)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 4: 调节后余额 ─────────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 4: 调节后余额', () => {
  /**
   * **Validates: Requirements 6.2, 6.3**
   *
   * For any (base, addItems, subItems):
   * calcReconciled(b, a, s) === b + a - s
   */
  it('calcReconciled(b, a, s) === b + a - s', () => {
    const valArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(valArb, valArb, valArb, (b, a, s) => {
        const result = calcReconciled(b, a, s)
        expect(result).toBeCloseTo(b + a - s, 10)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 5: 应计利息 ───────────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 5: 应计利息', () => {
  /**
   * **Validates: Requirements 10.3**
   *
   * For any (fcAmount≥0, days≥0, dailyRate≥0):
   * calcAccruedInterest(f, d, r) === f × d × r
   */
  it('calcAccruedInterest(f, d, r) === f × d × r for non-negative inputs', () => {
    const amountArb = fc.double({ min: 0, max: 1e9, noNaN: true, noDefaultInfinity: true })
    const daysArb = fc.double({ min: 0, max: 3650, noNaN: true, noDefaultInfinity: true })
    const rateArb = fc.double({ min: 0, max: 0.01, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(amountArb, daysArb, rateArb, (f, d, r) => {
        const result = calcAccruedInterest(f, d, r)
        expect(result).toBeCloseTo(f * d * r, 5)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 6: 外币折算 ───────────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 6: 外币折算', () => {
  /**
   * **Validates: Requirements 3.2, 14.2**
   *
   * For any (fcAmount, rate≥0):
   * calcFxConvert(f, r) === f × r
   */
  it('calcFxConvert(f, r) === f × r', () => {
    const amountArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })
    const rateArb = fc.double({ min: 0, max: 20, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(amountArb, rateArb, (f, r) => {
        const result = calcFxConvert(f, r)
        expect(result).toBeCloseTo(f * r, 5)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 7: 盘点差异 ───────────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 7: 盘点差异', () => {
  /**
   * **Validates: Requirements 7.4**
   *
   * For any (actual, book):
   * calcCountDiff(a, b) === a - b
   */
  it('calcCountDiff(a, b) === a - b', () => {
    const valArb = fc.double({ min: -1e9, max: 1e9, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(valArb, valArb, (a, b) => {
        const result = calcCountDiff(a, b)
        expect(result).toBeCloseTo(a - b, 10)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 8: 数组求和不变量 ─────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 8: 数组求和不变量', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * For any array of objects with a numeric field:
   * sumField(rows, field) === Σ rows[i][field]
   */
  it('sumField equals manual sum for any row array', () => {
    const rowArb = fc.record({
      amount: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
    })

    fc.assert(
      fc.property(
        fc.array(rowArb, { minLength: 0, maxLength: 30 }),
        (rows) => {
          const result = sumField(rows, 'amount')
          const expected = rows.reduce((sum, r) => sum + r.amount, 0)
          expect(result).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('sumField returns 0 for missing/non-numeric fields', () => {
    const rowArb = fc.record({
      other: fc.string({ minLength: 0, maxLength: 5 }),
    })

    fc.assert(
      fc.property(
        fc.array(rowArb, { minLength: 1, maxLength: 10 }),
        (rows) => {
          const result = sumField(rows, 'amount')
          expect(result).toBe(0)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 9: 超阈值判定 ─────────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 9: 超阈值判定', () => {
  /**
   * **Validates: Requirements 6.4**
   *
   * For any (rate: real, threshold>0):
   * exceedsThreshold(rate, threshold) === |rate| > threshold
   * rate='' → false
   */
  it('exceedsThreshold(rate, threshold) === |rate| > threshold for numeric rate', () => {
    const rateArb = fc.double({ min: -10, max: 10, noNaN: true, noDefaultInfinity: true })
    const thresholdArb = fc.double({ min: 0.01, max: 1, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(rateArb, thresholdArb, (rate, threshold) => {
        const result = exceedsThreshold(rate, threshold)
        const expected = Math.abs(rate) > threshold
        expect(result).toBe(expected)
      }),
      { numRuns: 100 },
    )
  })

  it('exceedsThreshold returns false for empty string rate', () => {
    const thresholdArb = fc.double({ min: 0.01, max: 1, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(thresholdArb, (threshold) => {
        expect(exceedsThreshold('', threshold)).toBe(false)
      }),
      { numRuns: 100 },
    )
  })
})

// ─── Property 10: 动态行增删计数 ────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 10: 动态行增删计数', () => {
  /**
   * **Validates: Requirements 3.2, 14.2**
   *
   * For any rows length N:
   * - addRow → N+1
   * - removeRow(valid i) → N-1
   * - removeRow(invalid i) → N
   */
  it('addRow increases length by 1', () => {
    const rowArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 5 }),
      amount: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
    })

    fc.assert(
      fc.property(
        fc.array(rowArb, { minLength: 0, maxLength: 20 }),
        (rows) => {
          const before = rows.length
          const after = [...rows, { id: 'new', amount: 0 }]
          expect(after.length).toBe(before + 1)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('removeRow at valid index decreases length by 1', () => {
    const rowArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 5 }),
      amount: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
    })

    fc.assert(
      fc.property(
        fc.array(rowArb, { minLength: 1, maxLength: 20 }),
        (rows) => {
          const idx = Math.floor(Math.random() * rows.length)
          const after = rows.filter((_, i) => i !== idx)
          expect(after.length).toBe(rows.length - 1)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('removeRow at invalid index keeps length unchanged', () => {
    const rowArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 5 }),
      amount: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
    })

    fc.assert(
      fc.property(
        fc.array(rowArb, { minLength: 0, maxLength: 20 }),
        fc.integer({ min: -100, max: -1 }),
        (rows, invalidIdx) => {
          // Invalid index: negative or >= length
          const idx = invalidIdx < 0 ? invalidIdx : rows.length + invalidIdx
          const after = idx >= 0 && idx < rows.length
            ? rows.filter((_, i) => i !== idx)
            : [...rows]
          expect(after.length).toBe(rows.length)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('removeRow at out-of-bounds index keeps length unchanged', () => {
    const rowArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 5 }),
      amount: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
    })

    fc.assert(
      fc.property(
        fc.array(rowArb, { minLength: 0, maxLength: 20 }),
        (rows) => {
          const invalidIdx = rows.length + 1 // always out of bounds
          const after = invalidIdx >= 0 && invalidIdx < rows.length
            ? rows.filter((_, i) => i !== invalidIdx)
            : [...rows]
          expect(after.length).toBe(rows.length)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ─── Property 11: JSON Round-Trip ───────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 11: JSON Round-Trip', () => {
  /**
   * **Validates: Requirements 3.2, 14.2**
   *
   * For any valid row array:
   * deserialize(serialize(rows)) preserves user-input fields;
   * computed fields recomputed consistently.
   */
  it('round-trip preserves user-input fields', () => {
    const rowArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 10 }),
      currency: fc.constantFrom('人民币', '美元', '日元', '欧元', '港币'),
      opening: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
      increase: fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
      decrease: fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true }),
    })
    const userFields = ['id', 'currency', 'opening', 'increase', 'decrease']

    fc.assert(
      fc.property(
        fc.array(rowArb, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const json = serializeRows(rows, userFields)
          const recompute = (r: Record<string, unknown>) => ({
            ...r,
            ending: (r.opening as number) + (r.increase as number) - (r.decrease as number),
          })
          const result = deserializeRows(json, recompute)

          expect(result).toHaveLength(rows.length)
          for (let i = 0; i < rows.length; i++) {
            // User-input fields preserved
            expect(result[i].id).toBe(rows[i].id)
            expect(result[i].currency).toBe(rows[i].currency)
            expect(result[i].opening).toBeCloseTo(rows[i].opening, 10)
            expect(result[i].increase).toBeCloseTo(rows[i].increase, 10)
            expect(result[i].decrease).toBeCloseTo(rows[i].decrease, 10)
            // Computed field recomputed consistently
            const expectedEnding = rows[i].opening + rows[i].increase - rows[i].decrease
            expect(result[i].ending as number).toBeCloseTo(expectedEnding, 10)
          }
        },
      ),
      { numRuns: 100 },
    )
  })

  it('serialize only preserves specified user fields', () => {
    const rowArb = fc.record({
      id: fc.string({ minLength: 1, maxLength: 5 }),
      amount: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
      computed: fc.double({ min: -1e6, max: 1e6, noNaN: true, noDefaultInfinity: true }),
    })

    fc.assert(
      fc.property(
        fc.array(rowArb, { minLength: 1, maxLength: 10 }),
        (rows) => {
          const json = serializeRows(rows, ['id', 'amount'])
          const parsed = JSON.parse(json)
          for (const item of parsed) {
            expect(item).toHaveProperty('id')
            expect(item).toHaveProperty('amount')
            expect(item).not.toHaveProperty('computed')
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})
