/**
 * Property-Based Tests — E1-5 调整分录借贷平衡校验
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 6.2
 *
 * Property 12: isBalanced(rows, debitField, creditField) correctly identifies when Σ借方 === Σ贷方
 *
 * **Validates: Requirements 5.2**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import { isBalanced } from '../useE1FormulaEngine'

// ─── Property 12: 借贷平衡校验 ──────────────────────────────────────────────

describe('Feature: e1-monetary-fund-refactor, Property 12: 借贷平衡校验', () => {
  /**
   * **Validates: Requirements 5.2**
   *
   * For any array of rows where debit fields sum equals credit fields sum → isBalanced returns true
   */
  it('isBalanced returns true when Σ借方 === Σ贷方', () => {
    // Generate rows where we force debit sum === credit sum by splitting a total evenly
    const rowCountArb = fc.integer({ min: 1, max: 20 })
    const amountArb = fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(
        fc.array(amountArb, { minLength: 1, maxLength: 20 }),
        (amounts) => {
          // Create balanced rows: each row has same value in debit and credit
          // This guarantees Σdebit === Σcredit
          const rows = amounts.map(amt => ({
            debit: amt,
            credit: amt,
          }))

          const result = isBalanced(rows, 'debit', 'credit')
          expect(result).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })

  /**
   * **Validates: Requirements 5.2**
   *
   * For any array of rows where debit fields sum !== credit fields sum → isBalanced returns false
   */
  it('isBalanced returns false when Σ借方 !== Σ贷方', () => {
    // Generate rows with a guaranteed imbalance (diff >= 0.01 to exceed 0.001 tolerance)
    const amountArb = fc.double({ min: 0, max: 1e6, noNaN: true, noDefaultInfinity: true })
    const diffArb = fc.double({ min: 0.01, max: 1e6, noNaN: true, noDefaultInfinity: true })

    fc.assert(
      fc.property(
        fc.array(amountArb, { minLength: 1, maxLength: 20 }),
        diffArb,
        fc.boolean(),
        (amounts, diff, addToDebit) => {
          // Create rows that are balanced
          const rows = amounts.map(amt => ({
            debit: amt,
            credit: amt,
          }))

          // Then add imbalance to the first row (diff >= 0.01 > 0.001 tolerance)
          if (addToDebit) {
            rows[0] = { ...rows[0], debit: rows[0].debit + diff }
          } else {
            rows[0] = { ...rows[0], credit: rows[0].credit + diff }
          }

          const result = isBalanced(rows, 'debit', 'credit')
          expect(result).toBe(false)
        },
      ),
      { numRuns: 100 },
    )
  })

  /**
   * **Validates: Requirements 5.2**
   *
   * Edge case: empty array → isBalanced returns true (0 === 0)
   */
  it('isBalanced returns true for empty array (0 === 0)', () => {
    fc.assert(
      fc.property(
        fc.constant([]),
        (rows) => {
          const result = isBalanced(rows, 'debit', 'credit')
          expect(result).toBe(true)
        },
      ),
      { numRuns: 100 },
    )
  })
})
