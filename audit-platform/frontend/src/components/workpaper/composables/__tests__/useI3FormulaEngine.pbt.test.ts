/**
 * I3 商誉 — Property-Based Testing (P1~P8)
 *
 * 覆盖 useI3FormulaEngine + useI3DcfEngine 全部纯函数。
 * 使用 fast-check 验证数学正确性。
 *
 * Spec: .kiro/specs/i3-goodwill/design.md → Correctness Properties CP-I3-01~08
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcGoodwillEndBalance,
  calcInitialGoodwill,
  calcSubtotal,
  calcImpairmentAllocation,
} from '../useI3FormulaEngine'
import {
  calcDcfPresentValue,
  calcRecoverableAmount,
} from '../useI3DcfEngine'

describe('useI3FormulaEngine+DcfEngine PBT', () => {
  // 安全浮点生成器（32-bit bounds required by fast-check）
  const safeFloat = fc.float({
    noNaN: true,
    noDefaultInfinity: true,
    min: Math.fround(-1e9),
    max: Math.fround(1e9),
  })

  // ═══ P1: 审定数公式链 ═══
  // **Validates: Requirements 2.2**
  it('Property P1: calcAuditedAmount(u, a, r) === u + a + r', () => {
    fc.assert(
      fc.property(safeFloat, safeFloat, safeFloat, (u, a, r) => {
        expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
      }),
      { numRuns: 200 },
    )
  })

  // ═══ P2: 商誉期末余额（不摊销！） ═══
  // **Validates: Requirements 2.3**
  it('Property P2: calcGoodwillEndBalance(b, n, i) === b + n - i', () => {
    const posFloat = fc.float({
      noNaN: true,
      noDefaultInfinity: true,
      min: 0,
      max: Math.fround(1e8),
    })

    fc.assert(
      fc.property(posFloat, posFloat, posFloat, (begin, newAcq, imp) => {
        // impairment ∈ [0, begin + newAcq]
        const maxImp = begin + newAcq
        const impairment = maxImp > 0 ? imp * (maxImp / Math.fround(1e8)) : 0
        expect(calcGoodwillEndBalance(begin, newAcq, impairment))
          .toBeCloseTo(begin + newAcq - impairment, 4)
      }),
      { numRuns: 200 },
    )
  })

  // ═══ P3: 初始商誉=合并成本-可辨认净资产公允 ═══
  // **Validates: Requirements 4.2**
  it('Property P3: calcInitialGoodwill(mc, nafv) === mc - nafv', () => {
    fc.assert(
      fc.property(
        fc.float({ noNaN: true, noDefaultInfinity: true, min: 0, max: Math.fround(1e9) }),
        fc.float({ noNaN: true, noDefaultInfinity: true, min: 0, max: Math.fround(1e9) }),
        (mc, nafv) => {
          fc.pre(mc >= nafv)
          expect(calcInitialGoodwill(mc, nafv)).toBeCloseTo(mc - nafv, 5)
        },
      ),
      { numRuns: 200 },
    )
  })

  // ═══ P4: 减值先冲商誉再按比例分摊 ═══
  // **Validates: Requirements 5.2, 5.3, 5.4**
  it('Property P4: 减值先冲商誉 → goodwillImpairment === MIN(total, goodwill)', () => {
    const assetArb = fc.record({
      name: fc.string({ minLength: 1, maxLength: 5 }),
      bookValue: fc.float({ noNaN: true, noDefaultInfinity: true, min: Math.fround(0.01), max: Math.fround(1e6) }),
    })

    fc.assert(
      fc.property(
        fc.float({ noNaN: true, noDefaultInfinity: true, min: Math.fround(0.01), max: Math.fround(1e8) }),
        fc.float({ noNaN: true, noDefaultInfinity: true, min: Math.fround(0.01), max: Math.fround(1e8) }),
        fc.array(assetArb, { minLength: 1, maxLength: 5 }),
        (totalImpairment, goodwillAmount, otherAssets) => {
          const result = calcImpairmentAllocation(totalImpairment, goodwillAmount, otherAssets)

          // P4a: goodwillImpairment === MIN(totalImpairment, goodwillAmount)
          expect(result.goodwillImpairment).toBeCloseTo(
            Math.min(totalImpairment, goodwillAmount), 4,
          )

          // P4b: 总分摊守恒 — 仅当其他资产总额≥剩余减值时成立
          const remaining = totalImpairment - result.goodwillImpairment
          const totalOtherBook = otherAssets.reduce((s, a) => s + a.bookValue, 0)
          const totalAllocated = result.goodwillImpairment
            + result.otherAllocations.reduce((s, a) => s + a.amount, 0)
          if (totalOtherBook >= remaining) {
            expect(totalAllocated).toBeCloseTo(totalImpairment, 3)
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  // ═══ P5: DCF现值计算 ═══
  // **Validates: Requirements 6.2**
  it('Property P5: calcDcfPresentValue(cfs, r) === Σ(cf/(1+r)^(i+1))', () => {
    fc.assert(
      fc.property(
        fc.array(
          fc.float({ noNaN: true, noDefaultInfinity: true, min: Math.fround(-1e6), max: Math.fround(1e6) }),
          { minLength: 1, maxLength: 20 },
        ),
        fc.float({ noNaN: true, noDefaultInfinity: true, min: Math.fround(0.001), max: Math.fround(0.99) }),
        (cfs, r) => {
          const actual = calcDcfPresentValue(cfs, r)
          let expected = 0
          for (let i = 0; i < cfs.length; i++) {
            expected += cfs[i] / Math.pow(1 + r, i + 1)
          }
          // Relative tolerance for floating point accumulation
          if (Math.abs(expected) < 1e-6) {
            expect(actual).toBeCloseTo(expected, 4)
          } else {
            expect(Math.abs(actual - expected) / Math.abs(expected)).toBeLessThan(1e-6)
          }
        },
      ),
      { numRuns: 200 },
    )
  })

  // ═══ P6: 可收回金额=MAX(公允-处置费, DCF) ═══
  // **Validates: Requirements 6.4**
  it('Property P6: calcRecoverableAmount(fv, dcf) === Math.max(fv, dcf)', () => {
    fc.assert(
      fc.property(safeFloat, safeFloat, (fv, dcf) => {
        expect(calcRecoverableAmount(fv, dcf)).toBe(Math.max(fv, dcf))
      }),
      { numRuns: 200 },
    )
  })

  // ═══ P7: 减值金额非负且≤资产组账面 ═══
  // **Validates: Requirements 5.2, 5.3**
  it('Property P7: impairment ∈ [0, cguBookValue]', () => {
    const assetArb = fc.record({
      name: fc.string({ minLength: 1, maxLength: 5 }),
      bookValue: fc.float({ noNaN: true, noDefaultInfinity: true, min: 0, max: Math.fround(1e6) }),
    })

    fc.assert(
      fc.property(
        fc.float({ noNaN: true, noDefaultInfinity: true, min: 0, max: Math.fround(1e8) }),
        fc.float({ noNaN: true, noDefaultInfinity: true, min: 0, max: Math.fround(1e8) }),
        fc.array(assetArb, { minLength: 1, maxLength: 5 }),
        (totalImpairment, goodwillAmount, otherAssets) => {
          const result = calcImpairmentAllocation(totalImpairment, goodwillAmount, otherAssets)

          // 商誉减值非负且≤商誉账面
          expect(result.goodwillImpairment).toBeGreaterThanOrEqual(0)
          expect(result.goodwillImpairment).toBeLessThanOrEqual(goodwillAmount + 1e-6)

          // 各其他资产分摊非负且≤其账面
          result.otherAllocations.forEach((alloc, idx) => {
            expect(alloc.amount).toBeGreaterThanOrEqual(-1e-9)
            expect(alloc.amount).toBeLessThanOrEqual(otherAssets[idx].bookValue + 1e-6)
          })
        },
      ),
      { numRuns: 200 },
    )
  })

  // ═══ P8: 合计行恒等 ═══
  // **Validates: Requirements 2.7**
  it('Property P8: calcSubtotal(arr) === arr.reduce((a,b) => a+b, 0)', () => {
    fc.assert(
      fc.property(
        fc.array(safeFloat, { minLength: 0, maxLength: 50 }),
        (arr) => {
          const expected = arr.reduce((a, b) => a + b, 0)
          expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
        },
      ),
      { numRuns: 200 },
    )
  })
})
