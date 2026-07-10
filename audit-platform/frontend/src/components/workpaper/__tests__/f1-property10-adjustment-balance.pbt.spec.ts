/**
 * F1 Property 10 PBT: 调整分录借贷平衡检查
 *
 * 验证调整分录F1-3的借贷平衡纯函数 checkBalance：
 * - 借方合计 === SUM(所有行.debitAmount)
 * - 贷方合计 === SUM(所有行.creditAmount)
 * - isBalanced === (debitTotal === creditTotal)
 * - balanceDiff === debitTotal - creditTotal
 *
 * **Validates: Requirements 6.5**
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcSubtotal } from '../composables/useF1FormulaEngine'
import { checkBalance } from '../composables/useF1Adjustment'

// ─── Generators ──────────────────────────────────────────────────────────────

/** 调整分录行生成器（只需借贷金额） */
const adjustmentRowArb = fc.record({
  debitAmount: fc.float({ min: 0, max: 1e9, noNaN: true }),
  creditAmount: fc.float({ min: 0, max: 1e9, noNaN: true }),
})

/** 多行调整分录 */
const adjustmentRowsArb = fc.array(adjustmentRowArb, { minLength: 1, maxLength: 10 })

/** 平衡分录生成器：借方总额 === 贷方总额 */
const balancedRowsArb = fc.nat({ max: 5 }).chain(count => {
  const n = count + 1
  return fc.array(
    fc.float({ min: 1, max: 1e8, noNaN: true }),
    { minLength: n, maxLength: n },
  ).map(amounts => {
    // 前 n-1 行有借方，最后一行平衡贷方
    const totalDebit = amounts.reduce((a, b) => a + b, 0)
    const rows = amounts.map(amt => ({ debitAmount: amt, creditAmount: 0 }))
    // 最后加一行贷方等于全部借方之和
    rows.push({ debitAmount: 0, creditAmount: totalDebit })
    return rows
  })
})

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('F1 Property 10: 调整分录借贷平衡检查', () => {
  /**
   * **Property 10a: 借方合计 === SUM(行.debitAmount)**
   *
   * checkBalance 计算的 debitTotal 应精确等于所有行的 debitAmount 之和。
   *
   * **Validates: Requirements 6.5**
   */
  it('checkBalance.debitTotal === SUM(rows.debitAmount)', () => {
    fc.assert(
      fc.property(adjustmentRowsArb, (rows) => {
        const result = checkBalance(rows)
        const expected = calcSubtotal(rows.map(r => r.debitAmount))
        return Math.abs(result.debitTotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 10b: 贷方合计 === SUM(行.creditAmount)**
   *
   * **Validates: Requirements 6.5**
   */
  it('checkBalance.creditTotal === SUM(rows.creditAmount)', () => {
    fc.assert(
      fc.property(adjustmentRowsArb, (rows) => {
        const result = checkBalance(rows)
        const expected = calcSubtotal(rows.map(r => r.creditAmount))
        return Math.abs(result.creditTotal - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 10c: isBalanced === (debitTotal === creditTotal)**
   *
   * **Validates: Requirements 6.5**
   */
  it('checkBalance.isBalanced 等价于 debitTotal === creditTotal', () => {
    fc.assert(
      fc.property(adjustmentRowsArb, (rows) => {
        const result = checkBalance(rows)
        const expectedBalanced = result.debitTotal === result.creditTotal
        return result.isBalanced === expectedBalanced
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 10d: balanceDiff === debitTotal - creditTotal**
   *
   * **Validates: Requirements 6.5**
   */
  it('checkBalance.balanceDiff === debitTotal - creditTotal', () => {
    fc.assert(
      fc.property(adjustmentRowsArb, (rows) => {
        const result = checkBalance(rows)
        const expected = result.debitTotal - result.creditTotal
        return Math.abs(result.balanceDiff - expected) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 10e: 已知平衡分录必然 isBalanced === true**
   *
   * 构造借方总额===贷方总额的分录，checkBalance.isBalanced 必须为 true。
   *
   * **Validates: Requirements 6.5**
   */
  it('构造平衡分录时 isBalanced 必为 true', () => {
    fc.assert(
      fc.property(balancedRowsArb, (rows) => {
        const result = checkBalance(rows)
        // 由于浮点精度，使用容差判断
        return Math.abs(result.balanceDiff) < 1e-6
      }),
      { numRuns: 100 },
    )
  })

  /**
   * **Property 10f: 单行行且借=贷时必然平衡**
   */
  it('单行借===贷时 isBalanced === true', () => {
    fc.assert(
      fc.property(
        fc.float({ min: 0, max: 1e9, noNaN: true }),
        (amount) => {
          const rows = [{ debitAmount: amount, creditAmount: amount }]
          const result = checkBalance(rows)
          return result.isBalanced === true && result.balanceDiff === 0
        },
      ),
      { numRuns: 100 },
    )
  })

  /**
   * 单元测试：空数组时全零且平衡
   */
  it('空数组 checkBalance 返回全零且平衡', () => {
    const result = checkBalance([])
    expect(result.debitTotal).toBe(0)
    expect(result.creditTotal).toBe(0)
    expect(result.isBalanced).toBe(true)
    expect(result.balanceDiff).toBe(0)
  })
})
