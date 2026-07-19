import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcDebitBalance,
  calcFairValue,
  calcUnrealizedGain,
  calcRealizedGain,
  calcLevel1Diff,
  calcCountDiff,
  calcReconciliation,
  calcClosingQuantity,
  isDebitCreditBalanced,
  calcNetGain,
  calcFairValueChange,
  calcAdjustedAmount,
} from './useG1TraFinFormulaEngine'

// 浮点容差：加/减/乘法在 double 下的舍入误差远小于 0.01，统一用 0.01 容差避免假失败。
const TOL = 1e-2
const approxEqual = (a: number, b: number, tol = TOL) => Math.abs(a - b) <= tol

describe('useG1TraFinFormulaEngine (PBT)', () => {
  // --- 2.2 Property 1: 借方余额 = 期初 + 借方 - 贷方 ---
  // Validates: Requirements 13.1, 3.4
  it('Property 1: calcDebitBalance(opening, debit, credit) ≈ opening + debit - credit', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (opening, debit, credit) => {
          expect(approxEqual(calcDebitBalance(opening, debit, credit), opening + debit - credit)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.3 Property 2: 公允价值 = 数量 × 单位公允值（数量 ≥ 0）---
  // Validates: Requirements 13.3, 5.3, 9.3
  it('Property 2: calcFairValue(quantity, unitFV) ≈ quantity × unitFV (quantity ≥ 0)', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 1_000_000 }),
        fc.float({ min: 0, max: 1e4, noNaN: true }),
        (quantity, unitFV) => {
          // quantity ≥ 0，不触发 quantity<0→0 的钳制
          expect(approxEqual(calcFairValue(quantity, unitFV), quantity * unitFV)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.4 Property 3: 未实现损益 = 公允价值 - 成本 ---
  // Validates: Requirements 13.4, 7.4
  it('Property 3: calcUnrealizedGain(fairValue, cost) ≈ fairValue - cost', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (fairValue, cost) => {
          expect(approxEqual(calcUnrealizedGain(fairValue, cost), fairValue - cost)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.5 Property 4: 已实现损益 = 处置收入 - 成本 ---
  // Validates: Requirements 13.5, 5.5, 8.3
  it('Property 4: calcRealizedGain(proceeds, cost) ≈ proceeds - cost', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e8, noNaN: true }),
        (proceeds, cost) => {
          expect(approxEqual(calcRealizedGain(proceeds, cost), proceeds - cost)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.6 Property 5: Level1差异 = 持仓 × 报价 - 账面值 ---
  // Validates: Requirements 13.7, 9.2
  it('Property 5: calcLevel1Diff(qty, quote, bookValue) ≈ qty × quote - bookValue', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 1_000_000 }),
        fc.float({ min: 0, max: 1e4, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (qty, quote, bookValue) => {
          // qty ≥ 0，calcLevel1Diff 内部走 calcFairValue，不触发钳制
          expect(approxEqual(calcLevel1Diff(qty, quote, bookValue), qty * quote - bookValue)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.7 Property 6: 盘点差异 = 盘点数量 - 账面数量（整数）---
  // Validates: Requirements 13.8, 12.2
  it('Property 6: calcCountDiff(counted, booked) === counted - booked', () => {
    fc.assert(
      fc.property(
        fc.integer({ min: 0, max: 1_000_000 }),
        fc.integer({ min: 0, max: 1_000_000 }),
        (counted, booked) => {
          // 整数运算无浮点误差，严格相等
          expect(calcCountDiff(counted, booked)).toBe(counted - booked)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.8 Property 7: 报表日 = 盘点日 − 增加 + 减少（资产负债表日→盘点日口径）---
  // Validates: Requirements 13.9, 12.5
  it('Property 7: calcReconciliation(countDay, increase, decrease) ≈ countDay - increase + decrease', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (countDay, increase, decrease) => {
          expect(approxEqual(calcReconciliation(countDay, increase, decrease), countDay - increase + decrease)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.9 Property 8: 期末数量 = 期初 + 买入 - 卖出（约束 sold ≤ opening + bought，不触发 <0→0 钳制）---
  // Validates: Requirements 13.10, 5.2, 7.2
  it('Property 8: calcClosingQuantity(opening, bought, sold) === opening + bought - sold (sold ≤ opening + bought)', () => {
    fc.assert(
      fc.property(
        fc.nat({ max: 1_000_000 }),
        fc.nat({ max: 1_000_000 }),
        fc.float({ min: 0, max: 1, noNaN: true }),
        (opening, bought, ratio) => {
          // 约束 sold ≤ opening + bought，保证结果 ≥ 0，避免触发钳制
          const sold = Math.floor((opening + bought) * ratio)
          expect(calcClosingQuantity(opening, bought, sold)).toBe(opening + bought - sold)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.10 Property 9: 借贷平衡 ↔ |SUM(debits) - SUM(credits)| < 0.01（数组）---
  // Validates: Requirements 13.11, 6.2
  it('Property 9: isDebitCreditBalanced(debits, credits) ↔ |SUM(debits) - SUM(credits)| < 0.01', () => {
    fc.assert(
      fc.property(
        fc.array(fc.float({ min: 0, max: 1e6, noNaN: true }), { minLength: 1, maxLength: 20 }),
        fc.array(fc.float({ min: 0, max: 1e6, noNaN: true }), { minLength: 1, maxLength: 20 }),
        (debits, credits) => {
          const d = debits.reduce((s, v) => s + v, 0)
          const c = credits.reduce((s, v) => s + v, 0)
          expect(isDebitCreditBalanced(debits, credits)).toBe(Math.abs(d - c) < 0.01)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.11 Property 10: 净损益 = 已实现损益 - 手续费（fee ≥ 0，不触发 fee<0→0 钳制）---
  // Validates: Requirements 13.6, 8.4
  it('Property 10: calcNetGain(realizedGain, fee) ≈ realizedGain - fee (fee ≥ 0)', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: 0, max: 1e6, noNaN: true }),
        (realizedGain, fee) => {
          // fee ≥ 0，Math.max(fee, 0) === fee，不触发钳制
          expect(approxEqual(calcNetGain(realizedGain, fee), realizedGain - fee)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.12 Property 11: 公允价值变动方向性（期末 > 期初 → 变动 > 0）---
  // Validates: Requirements 13.12
  it('Property 11: calcFairValueChange(endFV, startFV) > 0 when endFV > startFV', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        fc.float({ min: 1, max: 1e6, noNaN: true }),
        (startFV, delta) => {
          // endFV = startFV + delta，delta ≥ 1 保证 endFV 严格大于 startFV
          const endFV = startFV + delta
          expect(calcFairValueChange(endFV, startFV)).toBeGreaterThan(0)
        },
      ),
      { numRuns: 200 },
    )
  })

  // --- 2.13 Property 12: 审定数 = 未审 + AJE + RJE ---
  // Validates: Requirements 13.2, 3.5, 5.8
  it('Property 12: calcAdjustedAmount(unadjusted, aje, rje) ≈ unadjusted + aje + rje', () => {
    fc.assert(
      fc.property(
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        fc.float({ min: -1e8, max: 1e8, noNaN: true }),
        (unadjusted, aje, rje) => {
          expect(approxEqual(calcAdjustedAmount(unadjusted, aje, rje), unadjusted + aje + rje)).toBe(true)
        },
      ),
      { numRuns: 200 },
    )
  })
})
