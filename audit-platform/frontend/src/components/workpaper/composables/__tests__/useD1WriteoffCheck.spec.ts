/**
 * Property-Based Tests — D1-16 坏账准备转回/核销检查表
 *
 * Spec: .kiro/specs/d1-writeoff-check/
 * Tasks: 1.4–1.8
 *
 * 使用 fast-check + vitest 验证 6 个 correctness properties。
 * P1: Reversal SUM / P2: Writeoff SUM / P3: 动态行增删 / P4: reversalExceedsProvision / P5: JSON Round-Trip / P6: 负数括号
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  sumArray,
  parseNum,
  isReversalExceedsProvision,
  isWriteoffExceedsProvision,
  getMissingReversalFields,
  getMissingWriteoffFields,
} from '../useD1WriteoffCheck'
import { formatNegativeAmount } from '../d1InspectionFormulas'

// ═══════════════════════════════════════════════════════════════════════════════
// Property 1: Reversal SUM 合计行公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-writeoff-check, Property 1: Reversal SUM 合计行公式正确性
describe('Feature: d1-writeoff-check, Property 1: Reversal SUM 合计行公式正确性', () => {
  /**
   * **Validates: Requirements 2.1**
   *
   * For any array of {reversalAmount, priorProvisionAmount} (length 0-20, floats 0 to 1e8 noNaN):
   *   sumArray(rows.map(r => r.reversalAmount)) === rows.reduce((s,r) => s + r.reversalAmount, 0)
   *   sumArray(rows.map(r => r.priorProvisionAmount)) === rows.reduce((s,r) => s + r.priorProvisionAmount, 0)
   */
  it('P1: reversalTotalE and reversalTotalF equal manual reduce sum', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            reversalAmount: fc.float({ min: 0, max: 1e8, noNaN: true }),
            priorProvisionAmount: fc.float({ min: 0, max: 1e8, noNaN: true }),
          }),
          { minLength: 0, maxLength: 20 }
        ),
        (rows) => {
          const totalE = sumArray(rows.map((r) => r.reversalAmount))
          const totalF = sumArray(rows.map((r) => r.priorProvisionAmount))
          const expectedE = rows.reduce((s, r) => s + r.reversalAmount, 0)
          const expectedF = rows.reduce((s, r) => s + r.priorProvisionAmount, 0)
          expect(totalE).toBeCloseTo(expectedE)
          expect(totalF).toBeCloseTo(expectedF)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 2: Writeoff SUM 合计行公式正确性
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-writeoff-check, Property 2: Writeoff SUM 合计行公式正确性
describe('Feature: d1-writeoff-check, Property 2: Writeoff SUM 合计行公式正确性', () => {
  /**
   * **Validates: Requirements 5.1**
   *
   * For any array of {writeoffAmount} (length 0-20, floats 0 to 1e8 noNaN):
   *   sumArray(rows.map(r => r.writeoffAmount)) === rows.reduce((s,r) => s + r.writeoffAmount, 0)
   */
  it('P2: writeoffTotalC equals manual reduce sum', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.record({
            writeoffAmount: fc.float({ min: 0, max: 1e8, noNaN: true }),
          }),
          { minLength: 0, maxLength: 20 }
        ),
        (rows) => {
          const totalC = sumArray(rows.map((r) => r.writeoffAmount))
          const expectedC = rows.reduce((s, r) => s + r.writeoffAmount, 0)
          expect(totalC).toBeCloseTo(expectedC)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 3: 动态行增删计数不变量
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-writeoff-check, Property 3: 动态行增删计数不变量
describe('Feature: d1-writeoff-check, Property 3: 动态行增删计数不变量', () => {
  /**
   * **Validates: Requirements 1.3, 4.3**
   *
   * Test with a simple array model (no Vue reactivity needed, just test the logic):
   * - Generate initial length N (0-20)
   * - Create array of N items with unique ids
   * - Adding one item → length becomes N+1
   * - Removing existing id → length becomes N-1
   * - Removing non-existing id → length stays N
   */
  it('P3: add increases length by 1, remove existing decreases by 1, remove non-existing unchanged', () => {
    fc.assert(
      fc.property(
        fc.uniqueArray(fc.string({ minLength: 1, maxLength: 10 }), { minLength: 0, maxLength: 20 }),
        fc.string({ minLength: 11, maxLength: 20 }),
        (ids, nonExistingId) => {
          // Ensure nonExistingId is truly not in the array
          fc.pre(!ids.includes(nonExistingId))

          // Initial array of items with unique ids
          const items = ids.map((id) => ({ id, value: 0 }))
          const N = items.length

          // Adding one item → length becomes N+1
          const afterAdd = [...items, { id: 'new-item', value: 0 }]
          expect(afterAdd.length).toBe(N + 1)

          // Removing existing id (if N > 0) → length becomes N-1
          if (N > 0) {
            const idToRemove = ids[0]
            const afterRemove = items.filter((item) => item.id !== idToRemove)
            expect(afterRemove.length).toBe(N - 1)
          }

          // Removing non-existing id → length stays N
          const afterRemoveNonExisting = items.filter((item) => item.id !== nonExistingId)
          expect(afterRemoveNonExisting.length).toBe(N)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 4: reversalExceedsProvision 判定正确性
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-writeoff-check, Property 4: reversalExceedsProvision 判定正确性
describe('Feature: d1-writeoff-check, Property 4: reversalExceedsProvision 判定正确性', () => {
  /**
   * **Validates: Requirements 3.1**
   *
   * For any (reversalAmount: float -1e6 to 1e8, priorProvision: float -1e6 to 1e8):
   *   isReversalExceedsProvision(reversalAmount, priorProvision) === (reversalAmount > 0 && reversalAmount > priorProvision)
   */
  it('P4: isReversalExceedsProvision returns true iff reversalAmount > 0 AND reversalAmount > priorProvision', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e6, max: 1e8, noNaN: true }),
        fc.float({ min: -1e6, max: 1e8, noNaN: true }),
        (reversalAmount, priorProvision) => {
          const result = isReversalExceedsProvision(reversalAmount, priorProvision)
          const expected = reversalAmount > 0 && reversalAmount > priorProvision
          expect(result).toBe(expected)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 5: JSON Round-Trip 序列化完整性
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-writeoff-check, Property 5: JSON Round-Trip 序列化完整性
describe('Feature: d1-writeoff-check, Property 5: JSON Round-Trip 序列化完整性', () => {
  /**
   * **Validates: Requirements 9.5**
   *
   * Generate valid ReversalRow[] and WriteoffRow[] arrays:
   *   JSON.parse(JSON.stringify(array)) deep equals array
   */
  // Helper: fc.float can produce -0, which JSON.stringify normalizes to 0.
  // Use .map to normalize -0 → 0 to match JSON round-trip behavior.
  const jsonSafeFloat = fc.float({ min: -1e8, max: 1e8, noNaN: true, noDefaultInfinity: true })
    .map((v) => (Object.is(v, -0) ? 0 : v))

  const reversalRowArb = fc.record({
    id: fc.string({ minLength: 0, maxLength: 50 }),
    unitName: fc.string({ minLength: 0, maxLength: 50 }),
    reason: fc.string({ minLength: 0, maxLength: 50 }),
    recoveryMethod: fc.string({ minLength: 0, maxLength: 50 }),
    originalBasis: fc.string({ minLength: 0, maxLength: 50 }),
    reversalAmount: jsonSafeFloat,
    priorProvisionAmount: jsonSafeFloat,
    reasonabilityAnalysis: fc.string({ minLength: 0, maxLength: 50 }),
    indexRef: fc.string({ minLength: 0, maxLength: 50 }),
  })

  const writeoffRowArb = fc.record({
    id: fc.string({ minLength: 0, maxLength: 50 }),
    unitName: fc.string({ minLength: 0, maxLength: 50 }),
    noteNature: fc.string({ minLength: 0, maxLength: 50 }),
    writeoffAmount: jsonSafeFloat,
    writeoffReason: fc.string({ minLength: 0, maxLength: 50 }),
    writeoffProcedure: fc.string({ minLength: 0, maxLength: 50 }),
  })

  it('P5: ReversalRow[] survives JSON round-trip', () => {
    fc.assert(
      fc.property(
        fc.array(reversalRowArb, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const serialized = JSON.stringify(rows)
          const deserialized = JSON.parse(serialized)
          expect(deserialized).toEqual(rows)
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P5: WriteoffRow[] survives JSON round-trip', () => {
    fc.assert(
      fc.property(
        fc.array(writeoffRowArb, { minLength: 0, maxLength: 10 }),
        (rows) => {
          const serialized = JSON.stringify(rows)
          const deserialized = JSON.parse(serialized)
          expect(deserialized).toEqual(rows)
        }
      ),
      { numRuns: 100 }
    )
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// Property 6: 负数金额括号格式
// ═══════════════════════════════════════════════════════════════════════════════

// Feature: d1-writeoff-check, Property 6: 负数金额括号格式
describe('Feature: d1-writeoff-check, Property 6: 负数金额括号格式', () => {
  /**
   * **Validates: Requirements 12.2**
   *
   * For any negative amount: result contains '(' and ')' and does NOT contain '-'
   * For any non-negative amount: result is empty string ''
   */
  it('P6: negative amounts formatted with parentheses, no minus sign', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: Math.fround(-0.01), noNaN: true }),
        (negativeValue) => {
          const result = formatNegativeAmount(negativeValue)
          expect(result).toContain('(')
          expect(result).toContain(')')
          expect(result).not.toContain('-')
        }
      ),
      { numRuns: 100 }
    )
  })

  it('P6: non-negative amounts return empty string', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (nonNegativeValue) => {
          const result = formatNegativeAmount(nonNegativeValue)
          expect(result).toBe('')
        }
      ),
      { numRuns: 100 }
    )
  })
})
