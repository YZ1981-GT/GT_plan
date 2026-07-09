/**
 * K12 营业外收入 — CP-K12-05 Property-Based Test
 *
 * 合计行恒等：calcSubtotal(arr) === Σarr
 * 适用：审定表合计行、明细表分类小计
 *
 * Generator: arr from fc.array(fc.float({noNaN:true, noDefaultInfinity:true}), {minLength:0, maxLength:50})
 * Property: calcSubtotal(arr) must always equal arr.reduce((sum, x) => sum + x, 0)
 * Tolerance: relative 1e-10 (floating point approximate equality)
 *
 * Spec: .kiro/specs/k12-non-operating-income/design.md → Correctness Properties CP-K12-05
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcSubtotal } from '../composables/useK12FormulaEngine'

fc.configureGlobal({ numRuns: 100 })

/** Approximate equality with relative tolerance for floating point comparison */
function approxEqual(a: number, b: number, relTol = 1e-10): boolean {
  if (a === b) return true
  const denom = Math.max(Math.abs(a), Math.abs(b), 1)
  return Math.abs(a - b) / denom <= relTol
}

describe('K12 PBT — CP-K12-05 合计行恒等', () => {
  // ═══ CP-K12-05: 合计行恒等 ═══
  // **Validates: Requirements 6.7**
  describe('Feature: k12-non-operating-income, Property CP-K12-05: 合计行恒等', () => {
    it('CP-K12-05: calcSubtotal(arr) === Σarr (arr∈float[], 0≤len≤50)', () => {
      fc.assert(
        fc.property(
          fc.array(
            fc.float({ noNaN: true, noDefaultInfinity: true }),
            { minLength: 0, maxLength: 50 },
          ),
          (arr) => {
            const result = calcSubtotal(arr)
            const expected = arr.reduce((sum, x) => sum + x, 0)
            expect(approxEqual(result, expected)).toBe(true)
          },
        ),
      )
    })
  })
})
