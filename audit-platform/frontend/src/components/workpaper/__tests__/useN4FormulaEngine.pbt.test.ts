/**
 * N4 税金及附加 — 公式引擎 + 多税种测算引擎 Property-Based Tests (CP-N4-P1~P6)
 *
 * 覆盖 useN4FormulaEngine + useN4MultiTaxEngine 全部核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：6403税金及附加（**损益类/借方科目**，取发生额非余额）
 *
 * Spec: .kiro/specs/n4-taxes-and-surcharges/design.md → Correctness Properties P1~P6
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcPeriodAmount,
  calcSubtotal,
} from '../composables/useN4FormulaEngine'
import {
  calcSurtax,
  calcPropertyTaxByValue,
  calcStampTax,
} from '../composables/useN4MultiTaxEngine'

fc.configureGlobal({ numRuns: 200 })

const EPSILON = 1e-6

// 安全浮点生成器（避免NaN/Infinity）
const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

describe('N4 PBT — 公式引擎 + 多税种测算引擎正确性', () => {
  // ═══ P1: 审定数公式链 ═══
  // **Validates: Requirements 2.3**
  describe('Feature: n4-taxes-and-surcharges, Property P1: 审定数公式链', () => {
    it('P1: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ P2: 损益类本期发生额 ═══
  // **Validates: Requirements 2.4**
  describe('Feature: n4-taxes-and-surcharges, Property P2: 损益类本期发生额', () => {
    it('P2: calcPeriodAmount(d, c) === d - c', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
          (d, c) => {
            const result = calcPeriodAmount(d, c)
            const expected = d - c
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ P3: 合计行恒等 ═══
  // **Validates: Requirements 7.4**
  describe('Feature: n4-taxes-and-surcharges, Property P3: 合计行恒等', () => {
    it('P3: calcSubtotal(arr) === Σarr', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e6, 1e6), { minLength: 1, maxLength: 50 }),
          (arr) => {
            const result = calcSubtotal(arr)
            const expected = arr.reduce((s, v) => s + v, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('P3b: calcSubtotal([]) === 0 (空数组)', () => {
      expect(calcSubtotal([])).toBe(0)
    })
  })

  // ═══ P4: 城建税及附加 ═══
  // **Validates: Requirements 4.1**
  describe('Feature: n4-taxes-and-surcharges, Property P4: 城建税及附加', () => {
    it('P4: calcSurtax(vat, ct, rate) === (vat + ct) × rate', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
          fc.constantFrom(0.07, 0.05, 0.01, 0.03, 0.02),
          (vat, ct, rate) => {
            const result = calcSurtax(vat, ct, rate)
            const expected = (vat + ct) * rate
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ P5: 房产税从价 ═══
  // **Validates: Requirements 4.2**
  describe('Feature: n4-taxes-and-surcharges, Property P5: 房产税从价', () => {
    it('P5: calcPropertyTaxByValue(ov, dr) === ov × (1 - dr) × 0.012', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: Math.fround(1e12), noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: Math.fround(0.3), noNaN: true, noDefaultInfinity: true }),
          (ov, dr) => {
            const result = calcPropertyTaxByValue(ov, dr)
            const expected = ov * (1 - dr) * 0.012
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ P6: 印花税 ═══
  // **Validates: Requirements 4.3**
  describe('Feature: n4-taxes-and-surcharges, Property P6: 印花税', () => {
    it('P6: calcStampTax(amt, rate) === amt × rate', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: Math.fround(1e12), noNaN: true, noDefaultInfinity: true }),
          fc.float({ min: 0, max: Math.fround(0.001), noNaN: true, noDefaultInfinity: true }),
          (amt, rate) => {
            const result = calcStampTax(amt, rate)
            const expected = amt * rate
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })
})
