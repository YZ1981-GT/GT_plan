/**
 * H7 生产性生物资产 — Property-Based Tests (P1~P12)
 *
 * Spec: .kiro/specs/h7-biological-assets/ Tasks 2.4~2.15
 * Feature: h7-biological-assets
 *
 * 使用 fast-check 对纯函数公式引擎进行属性验证。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'

import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcFairEndBalance,
  calcNetValue,
  calcSubtotal,
  calcChangeRate,
  calcFairValueDiffRate,
} from '../useH7FormulaEngine'

import {
  calcStraightLine,
  calcMonthlyDep,
  calcDepAfterImpairment,
} from '../useH7DepreciationEngine'

import { calcTransferDiff } from '../useH7TransferEngine'

// ─── P1: 审定数公式链 ───────────────────────────────────────────────────────

describe('Property P1: 审定数公式链', () => {
  it('calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (u, a, r) => {
          expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P2: 资产类期末余额 ─────────────────────────────────────────────────────

describe('Property P2: 资产类期末余额', () => {
  it('calcAssetEndBalance(b, d, c) === b + d - c', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, d, c) => {
          expect(calcAssetEndBalance(b, d, c)).toBeCloseTo(b + d - c, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P3: 备抵类期末余额 ─────────────────────────────────────────────────────

describe('Property P3: 备抵类期末余额', () => {
  it('calcContraEndBalance(b, d, c) === b + c - d', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (b, d, c) => {
          expect(calcContraEndBalance(b, d, c)).toBeCloseTo(b + c - d, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P4: 公允价值模式期末 ───────────────────────────────────────────────────

describe('Property P4: 公允模式期末', () => {
  it('calcFairEndBalance(b, i, d, fc) === b + i - d + fc', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        fc.float({ min: -1e9, max: 1e9, noNaN: true }),
        (b, i, d, fairChange) => {
          expect(calcFairEndBalance(b, i, d, fairChange)).toBeCloseTo(b + i - d + fairChange, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P5: 直线法折旧 ─────────────────────────────────────────────────────────

describe('Property P5: 直线法折旧', () => {
  it('calcStraightLine(cost, rate, life) === cost×(1-rate)/life', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(1), max: Math.fround(1e9), noNaN: true }),
        fc.float({ min: Math.fround(0), max: Math.fround(0.99), noNaN: true }),
        fc.float({ min: Math.fround(1), max: Math.fround(100), noNaN: true }),
        (cost, rate, life) => {
          const expected = (cost * (1 - rate)) / life
          expect(calcStraightLine(cost, rate, life)).toBeCloseTo(expected, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P6: 月折旧 ─────────────────────────────────────────────────────────────

describe('Property P6: 月折旧', () => {
  it('calcMonthlyDep(annual) === annual / 12', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        (annual) => {
          expect(calcMonthlyDep(annual)).toBeCloseTo(annual / 12, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P7: 互转差额 ───────────────────────────────────────────────────────────

describe('Property P7: 互转差额', () => {
  it('calcTransferDiff(out, in) === out - in', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (out, inp) => {
          expect(calcTransferDiff(out, inp)).toBeCloseTo(out - inp, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P8: 合计行恒等 ─────────────────────────────────────────────────────────

describe('Property P8: 合计行恒等', () => {
  it('calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: -1e6, max: 1e6, noNaN: true }), { minLength: 1, maxLength: 50 }),
        (arr) => {
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 3)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P9: 净值公式 ───────────────────────────────────────────────────────────

describe('Property P9: 净值公式', () => {
  it('calcNetValue(c, d, i) === c - d - i', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (c, d, i) => {
          expect(calcNetValue(c, d, i)).toBeCloseTo(c - d - i, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P10: 变动率公式 ────────────────────────────────────────────────────────

describe('Property P10: 变动率公式', () => {
  it('calcChangeRate(c, p) === (c-p)/p × 100 when p > 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(0), max: Math.fround(1e9), noNaN: true }),
        fc.float({ min: Math.fround(1), max: Math.fround(1e9), noNaN: true }),
        (current, prior) => {
          const expected = ((current - prior) / prior) * 100
          expect(calcChangeRate(current, prior)).toBeCloseTo(expected, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P11: 公允价值差异率 ────────────────────────────────────────────────────

describe('Property P11: 公允价值差异率', () => {
  it('calcFairValueDiffRate(a, b) === (a-b)/b × 100 when b > 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(1), max: Math.fround(1e9), noNaN: true }),
        fc.float({ min: Math.fround(1), max: Math.fround(1e9), noNaN: true }),
        (assessed, book) => {
          const expected = ((assessed - book) / book) * 100
          expect(calcFairValueDiffRate(assessed, book)).toBeCloseTo(expected, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})

// ─── P12: 减值后折旧 ────────────────────────────────────────────────────────

describe('Property P12: 减值后折旧', () => {
  it('calcDepAfterImpairment(nv, rate, life) === nv×(1-rate)/life', () => {
    fc.assert(
      fc.property(
        fc.float({ min: Math.fround(1), max: Math.fround(1e9), noNaN: true }),
        fc.float({ min: Math.fround(0), max: Math.fround(0.99), noNaN: true }),
        fc.float({ min: Math.fround(1), max: Math.fround(100), noNaN: true }),
        (nv, rate, life) => {
          const expected = (nv * (1 - rate)) / life
          expect(calcDepAfterImpairment(nv, rate, life)).toBeCloseTo(expected, 2)
        },
      ),
      { numRuns: 200 },
    )
  })
})
