import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcQuantityDiff,
  calcFairValueDiff,
  calcMarketValueDiff,
  calcDisposalGain,
  calcDividendDiff,
  hasDifference,
} from './useG0FormulaEngine'

// 浮点容差：公式引擎对部分函数做了 2 位小数四舍五入（误差 ≤ 0.005），
// 加/减法在 double 下的舍入误差远小于此，统一用 0.01 容差避免假失败。
const TOL = 1e-2
const approxEqual = (a: number, b: number, tol = TOL) => Math.abs(a - b) <= tol

describe('useG0FormulaEngine (PBT)', () => {
  // --- 2.2 Property 1: 数量差异 = 回函持仓 - 账面持仓 ---
  // Validates: Requirements 2.5, 7.1
  it('Property 1: calcQuantityDiff(confirmed, booked) === confirmed - booked', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: -1_000_000, max: 1_000_000 }),
        fc.integer({ min: -1_000_000, max: 1_000_000 }),
        (confirmed, booked) => {
          // 整数运算无浮点误差，严格相等
          expect(calcQuantityDiff(confirmed, booked)).toBe(confirmed - booked)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.3 Property 2: 公允价值差异 = 回函 - 账面 ---
  // Validates: Requirements 2.6, 7.2
  it('Property 2: calcFairValueDiff(confirmedFV, bookedFV) ≈ confirmedFV - bookedFV', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (confirmedFV, bookedFV) => {
          expect(approxEqual(calcFairValueDiff(confirmedFV, bookedFV), confirmedFV - bookedFV)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.4 Property 3: 市值差异 = 回函市值 - 账面市值 ---
  // Validates: Requirements 2.7, 7.3
  it('Property 3: calcMarketValueDiff(confirmedMV, bookedMV) ≈ confirmedMV - bookedMV', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (confirmedMV, bookedMV) => {
          expect(approxEqual(calcMarketValueDiff(confirmedMV, bookedMV), confirmedMV - bookedMV)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.5 Property 4: 处置损益 = 成交 - 成本 - 手续费 ---
  // Validates: Requirements 3.13, 7.4
  it('Property 4: calcDisposalGain(proceeds, cost, fee) ≈ proceeds - cost - fee', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        (proceeds, cost, fee) => {
          // fee ≥ 0，不触发 fee<0→0 的钳制；引擎做 2 位四舍五入，用容差比较
          expect(approxEqual(calcDisposalGain(proceeds, cost, fee), proceeds - cost - fee)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.6 Property 5: 股利差异 = 应收 - 实收 - 税 ---
  // Validates: Requirements 7.5
  it('Property 5: calcDividendDiff(declared, received, tax) ≈ declared - received - tax', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e7, noNaN: true }),
        fc.float({ min: 0, max: 1e7, noNaN: true }),
        fc.float({ min: 0, max: 1e7, noNaN: true }),
        (declared, received, tax) => {
          expect(approxEqual(calcDividendDiff(declared, received, tax), declared - received - tax)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.7 Property 6: 差异判定定义一致性 ---
  // hasDifference 两参数语义不同（数量差异 vs 公允价值差异），阈值非对称
  // （|qty|>0 OR |fv|>0.01），故验证其与真实定义式一致，而非对称性。
  // Validates: Requirements 7.6
  it('Property 6: hasDifference(qtyDiff, fvDiff) === (|qtyDiff|>0 || |fvDiff|>0.01)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (qtyDiff, fvDiff) => {
          expect(hasDifference(qtyDiff, fvDiff)).toBe(
            Math.abs(qtyDiff) > 0 || Math.abs(fvDiff) > 0.01,
          )
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.8 Property 7: 零差异恒等（自身与自身差异 = 0）---
  // Validates: Requirements 7.1~7.3
  it('Property 7: calcQuantityDiff(v,v)=0 ∧ calcFairValueDiff(v,v)=0 ∧ calcMarketValueDiff(v,v)=0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (v) => {
          expect(calcQuantityDiff(v, v)).toBe(0)
          expect(calcFairValueDiff(v, v)).toBe(0)
          expect(calcMarketValueDiff(v, v)).toBe(0)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.9 Property 8: 处置损益与手续费反比（手续费越高 → 处置损益越低）---
  // Validates: Requirements 7.4
  it('Property 8: calcDisposalGain(p, c, fee1) < calcDisposalGain(p, c, fee2) when fee1 > fee2 >= 0', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 1, max: 1e6, noNaN: true }),
        (proceeds, cost, fee2, delta) => {
          // fee1 = fee2 + delta，delta ≥ 1 保证四舍五入后严格更高的手续费产出更低的损益
          const fee1 = fee2 + delta
          expect(calcDisposalGain(proceeds, cost, fee1)).toBeLessThan(
            calcDisposalGain(proceeds, cost, fee2),
          )
        },
      ),
      { numRuns: 200 },
    )
  })
})
