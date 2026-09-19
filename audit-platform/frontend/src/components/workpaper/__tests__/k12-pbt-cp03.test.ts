/**
 * K12 营业外收入 — Property CP-K12-03: 同比变动率=(本期-上期)/上期
 *
 * 科目：6301营业外收入（损益类/贷方科目，取发生额非余额）
 * 公式：calcYoYChange(current, prior) === (current - prior) / prior
 * 约束：prior≠0（prior===0时函数返回null，除零保护）
 *
 * Spec: .kiro/specs/k12-non-operating-income/design.md → CP-K12-03
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcYoYChange } from '../composables/useK12FormulaEngine'

describe('K12 PBT — CP-K12-03: 同比变动率=(本期-上期)/上期', () => {
  // **Validates: Requirements 6.5**
  describe('Feature: k12-non-operating-income, Property CP-K12-03: 同比变动率=(本期-上期)/上期', () => {
    it('CP-K12-03: calcYoYChange(cur, prior) === (cur - prior) / prior when prior≠0', () => {
      fc.assert(
        fc.property(
          fc.float({ noNaN: true, noDefaultInfinity: true }),
          fc.float({ noNaN: true, noDefaultInfinity: true }).filter(x => x !== 0),
          (cur, prior) => {
            const result = calcYoYChange(cur, prior)
            // prior≠0 so result should not be null
            expect(result).not.toBeNull()
            const expected = (cur - prior) / prior
            // Use relative tolerance for floating point comparison
            if (Math.abs(expected) < 1e-10) {
              expect(Math.abs(result!)).toBeLessThan(1e-10)
            } else {
              const relError = Math.abs((result! - expected) / expected)
              expect(relError).toBeLessThan(1e-10)
            }
          },
        ),
        { numRuns: 100 },
      )
    })

    it('CP-K12-03b: calcYoYChange(cur, 0) === null (除零保护)', () => {
      fc.assert(
        fc.property(
          fc.float({ noNaN: true, noDefaultInfinity: true }),
          (cur) => {
            const result = calcYoYChange(cur, 0)
            expect(result).toBeNull()
          },
        ),
        { numRuns: 100 },
      )
    })
  })
})
