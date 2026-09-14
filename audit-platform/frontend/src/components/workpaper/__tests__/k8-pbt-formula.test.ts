/**
 * K8 销售费用 — 公式引擎 Property-Based Tests (CP-K8-01, CP-K8-02)
 *
 * 覆盖 useK8FormulaEngine 核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：6601销售费用（损益类/借方科目，取发生额非余额）
 *
 * Spec: .kiro/specs/k8-selling-expenses/design.md → Correctness Properties CP-K8-01~02
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
} from '../composables/useK8FormulaEngine'

describe('useK8FormulaEngine PBT', () => {
  // 安全浮点生成器（避免 NaN/Infinity，32-bit bounds）
  const safeFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(-1e9),
    max: Math.fround(1e9),
  })

  // ═══ CP-K8-01: 审定数公式链 ═══
  // **Validates: Requirements 2.3**
  describe('Feature: k8-selling-expenses, Property CP-K8-01: 审定数公式链', () => {
    it('CP-K8-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat, safeFloat, safeFloat, (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
        }),
        { numRuns: 200 },
      )
    })
  })

  // ═══ CP-K8-02: 损益类发生额（借-贷） ═══
  // **Validates: Requirements 2.4**
  describe('Feature: k8-selling-expenses, Property CP-K8-02: 费用类发生额=借方发生-贷方发生', () => {
    // 发生额生成器：借方/贷方均≥0（费用类借方=支出增加，贷方=冲回/红冲）
    const nonNegFloat = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: 0,
      max: Math.fround(1e9),
    })

    it('CP-K8-02: calcIncomeStatementOccurrence(dr, cr) === dr - cr', () => {
      fc.assert(
        fc.property(nonNegFloat, nonNegFloat, (dr, cr) => {
          expect(calcIncomeStatementOccurrence(dr, cr)).toBeCloseTo(dr - cr, 5)
        }),
        { numRuns: 200 },
      )
    })
  })
})
