/**
 * K12 营业外收入 — Property CP-K12-04: 占比=单项/合计
 *
 * 验证 calcProportion(item, total) 在 total>0 时恒等于 item/total。
 * 科目：6301营业外收入（损益类/贷方科目）
 *
 * Spec: .kiro/specs/k12-non-operating-income/design.md → Correctness Properties CP-K12-04
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcProportion } from '../composables/useK12FormulaEngine'

fc.configureGlobal({ numRuns: 100 })

const EPSILON = 1e-6

describe('K12 PBT — CP-K12-04 占比公式', () => {
  /**
   * **Validates: Requirements 6.6**
   *
   * Property: calcProportion(item, total) === item / total (when total > 0)
   * Generator: item from fc.float (any finite), total from fc.float with min 0.01 to ensure total > 0
   */
  describe('Feature: k12-non-operating-income, Property CP-K12-04: 占比=单项/合计', () => {
    it('CP-K12-04: calcProportion(item, total) === item / total (total > 0)', () => {
      fc.assert(
        fc.property(
          fc.float({ noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: Math.fround(0.01), noNaN: true, noDefaultInfinity: true }),
          (item, total) => {
            const result = calcProportion(item, total)
            const expected = item / total
            // result should not be null since total > 0
            expect(result).not.toBeNull()
            expect(Math.abs(result! - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })
})
