/**
 * K11 资产减值损失 — 公式引擎 + 减值汇总引擎 Property-Based Tests (CP-K11-01~05)
 *
 * 覆盖 useK11FormulaEngine + useK11ImpairmentSummaryEngine 全部核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：6701资产减值损失（**损益类/借方科目**，取发生额非余额）
 *
 * Spec: .kiro/specs/k11-asset-impairment-loss/design.md → Correctness Properties CP-K11-01~05
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSourceVariance,
  calcSubtotal,
} from '../composables/useK11FormulaEngine'
import { calcImpairmentSummary } from '../composables/useK11ImpairmentSummaryEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器（避免NaN/Infinity）
const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K11 PBT — 公式引擎正确性', () => {
  // ═══ CP-K11-01: 审定数公式链 ═══
  // **Validates: Requirements 2.3**
  describe('Feature: k11-asset-impairment-loss, Property CP-K11-01: 审定数公式链', () => {
    it('CP-K11-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K11-02: 损益类减值损失发生额=借方发生-贷方发生 ═══
  // **Validates: Requirements 2.4**
  describe('Feature: k11-asset-impairment-loss, Property CP-K11-02: 减值损失发生额=借方发生-贷方发生', () => {
    it('CP-K11-02: calcIncomeStatementOccurrence(dr, cr) === dr - cr (debitOcc≥0, creditOcc≥0)', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
          (dr, cr) => {
            const result = calcIncomeStatementOccurrence(dr, cr)
            const expected = dr - cr
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ CP-K11-03: 减值汇总=Σ各来源 ═══
  // **Validates: Requirements 4.1**
  describe('Feature: k11-asset-impairment-loss, Property CP-K11-03: 减值汇总=Σ各来源', () => {
    it('CP-K11-03: calcImpairmentSummary(sources) === sum of sources', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e6, 1e6), { minLength: 1, maxLength: 20 }),
          (sources) => {
            const result = calcImpairmentSummary(sources)
            const expected = sources.reduce((s, x) => s + x, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K11-03b: calcImpairmentSummary([]) === 0 (空数组)', () => {
      expect(calcImpairmentSummary([])).toBe(0)
    })
  })

  // ═══ CP-K11-04: 源底稿核对差异=K11-源底稿 ═══
  // **Validates: Requirements 3.2**
  describe('Feature: k11-asset-impairment-loss, Property CP-K11-04: 源底稿核对差异', () => {
    it('CP-K11-04: calcSourceVariance(k11, src) === k11 - src', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), (k11, src) => {
          const result = calcSourceVariance(k11, src)
          const expected = k11 - src
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K11-05: 合计行恒等 ═══
  // **Validates: Requirements 6.7**
  describe('Feature: k11-asset-impairment-loss, Property CP-K11-05: 合计行恒等', () => {
    it('CP-K11-05: calcSubtotal(arr) === sum of arr', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e6, 1e6), { minLength: 1, maxLength: 30 }),
          (arr) => {
            const result = calcSubtotal(arr)
            const expected = arr.reduce((s, x) => s + x, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K11-05b: calcSubtotal([]) === 0 (空数组)', () => {
      expect(calcSubtotal([])).toBe(0)
    })
  })
})
