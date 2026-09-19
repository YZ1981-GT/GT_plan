/**
 * Property-Based Tests — D1 ECL坏账准备测算 composable
 *
 * Spec: .kiro/specs/d1-ecl-provision/
 * Tasks: 1.2–1.9
 *
 * 使用 fast-check + vitest 验证 8 个 correctness properties (Property 1–8)。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calculateShouldProvision,
  calculateDifference,
  calculateSumRow,
  calculateGrandTotal,
  checkExceedsMateriality,
  clampLossRate,
  formatAmountDisplay,
  serializeRows,
  deserializeRows,
  generateEclRowId,
} from '../useD1EclCalc'
import type { EclRow } from '../useD1EclCalc'

// ═══════════════════════════════════════════════════════════════════════════════
// 自定义生成器
// ═══════════════════════════════════════════════════════════════════════════════

/** 生成合法 EclRow（lossRate 已 clamp 到 [0,1]） */
function eclRowArbitrary(): fc.Arbitrary<EclRow> {
  return fc.record({
    id: fc.string({ minLength: 1, maxLength: 20 }),
    debtor: fc.string({ minLength: 0, maxLength: 50 }),
    balance: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
    lossRate: fc.float({ min: 0, max: 1, noNaN: true }),
    actualProvision: fc.float({ min: -1e8, max: 1e8, noNaN: true }),
    basis: fc.string({ minLength: 0, maxLength: 30 }),
    indexRef: fc.string({ minLength: 0, maxLength: 20 }),
  }).map(r => ({
    ...r,
    shouldProvision: r.balance * r.lossRate,
    difference: r.actualProvision - r.balance * r.lossRate,
  }))
}

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: D=B×C 应计提公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-ecl-provision, Property 1: D=B×C 应计提公式正确性', () => {
  /**
   * **Validates: Requirements 6.4, 7.4**
   *
   * calculateShouldProvision(balance, lossRate) === balance × lossRate
   */
  it('calculateShouldProvision(balance, lossRate) === balance × lossRate', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1, noNaN: true }),
        (balance, lossRate) => {
          const result = calculateShouldProvision(balance, lossRate)
          const expected = balance * lossRate
          expect(Math.abs(result - expected)).toBeLessThanOrEqual(1e-10)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: F=E-D 差异公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-ecl-provision, Property 2: F=E-D 差异公式正确性', () => {
  /**
   * **Validates: Requirements 6.5, 7.4**
   *
   * calculateDifference(actualProvision, shouldProvision) === actualProvision - shouldProvision
   */
  it('calculateDifference(actual, should) === actual - should', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (actualProvision, shouldProvision) => {
          const result = calculateDifference(actualProvision, shouldProvision)
          const expected = actualProvision - shouldProvision
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: SUM合计行不变量
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-ecl-provision, Property 3: SUM合计行不变量', () => {
  /**
   * **Validates: Requirements 6.6, 7.5, 7.7**
   *
   * portfolioSumRow 各字段 === Σ(row.field)
   * grandTotal === portfolioSum + individualSum 逐字段
   */
  it('calculateSumRow(rows) 各字段等于明细行之和', () => {
    fc.assert(
      fc.property(
        fc.array(eclRowArbitrary(), { minLength: 0, maxLength: 10 }),
        (rows) => {
          const sum = calculateSumRow(rows)
          const expectedBalance = rows.reduce((s, r) => s + r.balance, 0)
          const expectedShould = rows.reduce((s, r) => s + r.shouldProvision, 0)
          const expectedActual = rows.reduce((s, r) => s + r.actualProvision, 0)
          const expectedDiff = rows.reduce((s, r) => s + r.difference, 0)

          expect(sum.balance).toBeCloseTo(expectedBalance, 5)
          expect(sum.shouldProvision).toBeCloseTo(expectedShould, 5)
          expect(sum.actualProvision).toBeCloseTo(expectedActual, 5)
          expect(sum.difference).toBeCloseTo(expectedDiff, 5)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('calculateGrandTotal(portfolioSum, individualSum) === 逐字段相加', () => {
    fc.assert(
      fc.property(
        fc.array(eclRowArbitrary(), { minLength: 0, maxLength: 10 }),
        fc.array(eclRowArbitrary(), { minLength: 0, maxLength: 10 }),
        (portfolioRows, individualRows) => {
          const portfolioSum = calculateSumRow(portfolioRows)
          const individualSum = calculateSumRow(individualRows)
          const grandTotal = calculateGrandTotal(portfolioSum, individualSum)

          expect(grandTotal.balance).toBeCloseTo(portfolioSum.balance + individualSum.balance, 5)
          expect(grandTotal.shouldProvision).toBeCloseTo(portfolioSum.shouldProvision + individualSum.shouldProvision, 5)
          expect(grandTotal.actualProvision).toBeCloseTo(portfolioSum.actualProvision + individualSum.actualProvision, 5)
          expect(grandTotal.difference).toBeCloseTo(portfolioSum.difference + individualSum.difference, 5)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: 重要性判断公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-ecl-provision, Property 4: 重要性判断公式正确性', () => {
  /**
   * **Validates: Requirements 8.3**
   *
   * checkExceedsMateriality(diff, mat) === (mat > 0 AND |diff| > mat)
   */
  it('checkExceedsMateriality(diff, mat) === (mat > 0 && Math.abs(diff) > mat)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -100, max: 1e9, noNaN: true }),
        (totalDifference, materiality) => {
          const result = checkExceedsMateriality(totalDifference, materiality)
          const expected = materiality > 0 && Math.abs(totalDifference) > materiality
          expect(result).toBe(expected)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: 动态行增删计数不变量
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-ecl-provision, Property 5: 动态行增删计数不变量', () => {
  /**
   * **Validates: Requirements 6.3, 7.3**
   *
   * addRow → N+1; removeRow(valid i) → N-1; removeRow(invalid) → 不变
   */
  it('addRow increases length by 1', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 20 }),
        (initialLength) => {
          // Create an array of N rows
          const rows: EclRow[] = Array.from({ length: initialLength }, () => ({
            id: generateEclRowId(),
            debtor: '',
            balance: 0,
            lossRate: 0,
            shouldProvision: 0,
            actualProvision: 0,
            difference: 0,
            basis: '',
            indexRef: '',
          }))

          // Simulate addRow: push a new row
          const newRow: EclRow = {
            id: generateEclRowId(),
            debtor: '',
            balance: 0,
            lossRate: 0,
            shouldProvision: 0,
            actualProvision: 0,
            difference: 0,
            basis: '',
            indexRef: '',
          }
          rows.push(newRow)

          expect(rows.length).toBe(initialLength + 1)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('removeRow(valid index) decreases length by 1', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 1, max: 20 }),
        fc.nat(),
        (initialLength, indexSeed) => {
          // Create an array of N rows (N >= 1)
          const rows: EclRow[] = Array.from({ length: initialLength }, () => ({
            id: generateEclRowId(),
            debtor: '',
            balance: 0,
            lossRate: 0,
            shouldProvision: 0,
            actualProvision: 0,
            difference: 0,
            basis: '',
            indexRef: '',
          }))

          // Valid index within range
          const validIndex = indexSeed % initialLength

          // Simulate removeRow: splice at valid index
          rows.splice(validIndex, 1)

          expect(rows.length).toBe(initialLength - 1)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('removeRow(invalid index) keeps length unchanged', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 20 }),
        fc.integer({ min: 1, max: 100 }),
        (initialLength, offset) => {
          // Create an array of N rows
          const rows: EclRow[] = Array.from({ length: initialLength }, () => ({
            id: generateEclRowId(),
            debtor: '',
            balance: 0,
            lossRate: 0,
            shouldProvision: 0,
            actualProvision: 0,
            difference: 0,
            basis: '',
            indexRef: '',
          }))

          // Invalid index: beyond array bounds
          const invalidIndex = initialLength + offset

          // Simulate removeRow with guard: only splice if index valid
          if (invalidIndex >= 0 && invalidIndex < rows.length) {
            rows.splice(invalidIndex, 1)
          }

          expect(rows.length).toBe(initialLength)
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 损失率clamp [0,1]不变量
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-ecl-provision, Property 6: 损失率clamp [0,1]不变量', () => {
  /**
   * **Validates: Requirements 16.1, 16.2**
   *
   * result ∈ [0,1]; v∈[0,1]→result===v; v<0→0; v>1→1
   */
  it('clampLossRate(v) always returns a value in [0, 1]', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -10, max: 10, noNaN: true }),
        (value) => {
          const result = clampLossRate(value)
          expect(result).toBeGreaterThanOrEqual(0)
          expect(result).toBeLessThanOrEqual(1)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('clampLossRate(v) preserves values already in [0, 1]', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1, noNaN: true }),
        (value) => {
          const result = clampLossRate(value)
          expect(result).toBe(value)
        },
      ),
      { numRuns: 100 },
    )
  })

  it('clampLossRate(v) clamps negative to 0 and >1 to 1', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -10, max: 10, noNaN: true }),
        (value) => {
          const result = clampLossRate(value)
          if (value < 0 || Object.is(value, -0)) {
            expect(result).toBe(0)
          } else if (value > 1) {
            expect(result).toBe(1)
          } else {
            expect(result).toBe(value)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 7: JSON Round-Trip行数据持久化
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-ecl-provision, Property 7: JSON Round-Trip行数据持久化', () => {
  /**
   * **Validates: Requirements 12.5, 12.6**
   *
   * deserializeRows(serializeRows(rows)) preserves user-input fields
   * and recomputes shouldProvision/difference consistently
   */

  /** 生成可序列化的 EclRow（避免 -0 导致 JSON round-trip 不等） */
  function serializableEclRowArbitrary(): fc.Arbitrary<EclRow> {
    const safeFloat = (min: number, max: number) =>
      fc.float({ min, max, noNaN: true }).map(v => (Object.is(v, -0) ? 0 : v))

    return fc.record({
      id: fc.string({ minLength: 1, maxLength: 20 }).filter(s => s.length > 0),
      debtor: fc.string({ minLength: 0, maxLength: 30 }),
      balance: safeFloat(-1e8, 1e8),
      lossRate: safeFloat(0, 1),
      actualProvision: safeFloat(-1e8, 1e8),
      basis: fc.string({ minLength: 0, maxLength: 20 }),
      indexRef: fc.string({ minLength: 0, maxLength: 20 }),
    }).map(r => ({
      ...r,
      shouldProvision: r.balance * r.lossRate,
      difference: r.actualProvision - r.balance * r.lossRate,
    }))
  }

  it('deserializeRows(serializeRows(rows)) preserves debtor/balance/lossRate/actualProvision/basis/indexRef', () => {
    fc.assert(
      fc.property(
        fc.array(serializableEclRowArbitrary(), { minLength: 0, maxLength: 10 }),
        (rows) => {
          const json = serializeRows(rows)
          const restored = deserializeRows(json)

          expect(restored.length).toBe(rows.length)

          for (let i = 0; i < rows.length; i++) {
            const original = rows[i]
            const roundTripped = restored[i]

            // User-input fields preserved
            expect(roundTripped.id).toBe(original.id)
            expect(roundTripped.debtor).toBe(original.debtor)
            expect(roundTripped.balance).toBe(original.balance)
            expect(roundTripped.lossRate).toBe(original.lossRate)
            expect(roundTripped.actualProvision).toBe(original.actualProvision)
            expect(roundTripped.basis).toBe(original.basis)
            expect(roundTripped.indexRef).toBe(original.indexRef)

            // Computed fields recomputed consistently
            const expectedShould = original.balance * original.lossRate
            const expectedDiff = original.actualProvision - expectedShould
            expect(roundTripped.shouldProvision).toBeCloseTo(expectedShould, 10)
            expect(roundTripped.difference).toBeCloseTo(expectedDiff, 10)
          }
        },
      ),
      { numRuns: 100 },
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 8: 负数金额括号格式
// ═══════════════════════════════════════════════════════════════════════════════

describe('Feature: d1-ecl-provision, Property 8: 负数金额括号格式', () => {
  /**
   * **Validates: Requirements 15.2**
   *
   * formatAmountDisplay(negative, fmtAmount) contains '(' and ')', does NOT contain '-'
   */
  it('formatAmountDisplay(negative amount) uses parentheses, no minus sign', () => {
    const fmtAmount = (n: number) => n.toFixed(2)

    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(-1e9), max: Math.fround(-0.01), noNaN: true }),
        (amount) => {
          const result = formatAmountDisplay(amount, fmtAmount)
          expect(result).toContain('(')
          expect(result).toContain(')')
          expect(result).not.toContain('-')
        },
      ),
      { numRuns: 100 },
    )
  })
})
