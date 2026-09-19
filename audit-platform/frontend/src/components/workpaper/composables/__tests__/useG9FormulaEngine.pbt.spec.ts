import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  parseNum,
  calcDebitBalance,
  calcAdjustedAmount,
  calcEndingBalance,
  calcL3Reconciliation,
  calcL3Variance,
  calcChangeRate,
  isDebitCreditBalanced,
} from '../useG9FormulaEngine'

const num = fc.float({ min: -1e6, max: 1e6, noNaN: true })

describe('G9 PBT — 公式引擎', () => {
  it('P1: calcDebitBalance === opening + debit - credit', () => {
    fc.assert(fc.property(num, num, num, (o, d, c) => {
      expect(calcDebitBalance(o, d, c)).toBeCloseTo(o + d - c, 4)
    }), { numRuns: 100 })
  })

  it('P2: calcAdjustedAmount === unadjusted + aje + rje', () => {
    fc.assert(fc.property(num, num, num, (u, a, r) => {
      expect(calcAdjustedAmount(u, a, r)).toBeCloseTo(u + a + r, 4)
    }), { numRuns: 100 })
  })

  it('P3: L3 调节表恒等', () => {
    fc.assert(fc.property(num, num, num, num, num, num, num, num, num, num,
      (o, p, d, ti, to, pl, oci, i, imp, other) => {
        const v = calcL3Reconciliation(o, p, d, ti, to, pl, oci, i, imp, other)
        expect(v).toBeCloseTo(o + p - d + ti - to + pl + oci + i - imp + other, 3)
      }), { numRuns: 50 })
  })

  it('P4: calcChangeRate 除零保护', () => {
    expect(calcChangeRate(0, 100)).toBeNull()
  })

  it('P5: 借贷平衡', () => {
    fc.assert(fc.property(
      fc.array(num, { minLength: 1, maxLength: 8 }),
      fc.array(num, { minLength: 1, maxLength: 8 }),
      (debits, credits) => {
        const d = debits.reduce((s, v) => s + v, 0)
        const c = credits.reduce((s, v) => s + v, 0)
        expect(isDebitCreditBalanced(debits, credits)).toBe(Math.abs(d - c) < 0.01)
      },
    ), { numRuns: 50 })
  })

  it('P6: parseNum 健壮性', () => {
    expect(parseNum(null)).toBe(0)
    expect(parseNum('  ')).toBe(0)
    expect(parseNum('abc')).toBe(0)
  })

  it('P7: calcEndingBalance 6 因子（OCI 默认 0）', () => {
    fc.assert(fc.property(num, num, num, num, num, num,
      (o, inc, dec, fv, int_, imp) => {
        expect(calcEndingBalance(o, inc, dec, fv, int_, imp))
          .toBeCloseTo(o + inc - dec + fv + int_ - imp, 3)
      }), { numRuns: 50 })
  })

  it('P7b: calcEndingBalance 含 OCI 变动', () => {
    fc.assert(fc.property(num, num, num, num, num, num, num,
      (o, inc, dec, fv, int_, imp, oci) => {
        expect(calcEndingBalance(o, inc, dec, fv, int_, imp, oci))
          .toBeCloseTo(o + inc - dec + fv + int_ - imp + oci, 3)
      }), { numRuns: 50 })
  })

  it('P8: L3 差异为零时平衡', () => {
    const closing = calcL3Reconciliation(500, 10, 5, 0, 0, 2, 1, 0, 0, 0)
    expect(calcL3Variance(closing, closing)).toBeCloseTo(0, 5)
  })
})
