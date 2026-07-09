/**
 * K12 营业外收入 — Property CP-K12-01: 审定数公式链
 *
 * 断言：calcAuditedAmount(u, a, r) === u + a + r
 * 科目：6301营业外收入（损益类/贷方科目，取发生额非余额）
 *
 * Spec: .kiro/specs/k12-non-operating-income/design.md → Correctness Properties CP-K12-01
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcAuditedAmount } from '../composables/useK12FormulaEngine'

// 安全浮点生成器（避免NaN/Infinity）
const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K12 PBT — CP-K12-01: 审定数公式链', () => {
  // ═══ CP-K12-01: 审定数 = 未审数 + AJE + RJE ═══
  // Feature: k12-non-operating-income, Property CP-K12-01: 审定数公式链
  // **Validates: Requirements 2.3, 6.3**
  it('CP-K12-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
        const result = calcAuditedAmount(u, a, r)
        const expected = u + a + r
        expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
      }),
      { numRuns: 100 },
    )
  })
})
