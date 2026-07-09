/**
 * I6 研发费用 — 公式引擎 Property-Based Tests (P1~P8)
 *
 * 覆盖 useI6FormulaEngine 全部纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：6602研发费用（损益类/借方科目，取发生额非余额）
 *
 * Spec: .kiro/specs/i6-research-development-expense/design.md → Correctness Properties CP-I6-01~08
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcIncomeStatementNet,
  calcMonthlyTotal,
  validateVRI601,
  calcSubtotal,
  calcDebitCreditBalance,
  isCutoffCrossover,
  calcChangeRate,
} from '../composables/useI6FormulaEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器
const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const positiveFloat = (min = 0, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('useI6FormulaEngine PBT', () => {
  // ═══ P1: 审定数公式链 ═══
  // **Validates: Requirements 2.2**
  describe('Feature: i6-research-development-expense, Property P1: 审定数公式链', () => {
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

  // ═══ P2: 损益类净发生额（借-贷） ═══
  // **Validates: Requirements 2.3**
  describe('Feature: i6-research-development-expense, Property P2: 损益净发生额=借方-贷方', () => {
    it('P2: calcIncomeStatementNet(dr, cr) === dr - cr', () => {
      fc.assert(
        fc.property(positiveFloat(0, 1e9), positiveFloat(0, 1e9), (debit, credit) => {
          const result = calcIncomeStatementNet(debit, credit)
          const expected = debit - credit
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ P3: 月度合计=SUM(12月) ═══
  // **Validates: Requirements 2.4**
  describe('Feature: i6-research-development-expense, Property P3: 月度合计=SUM(1月~12月)', () => {
    it('P3: calcMonthlyTotal(months) === months.reduce((a,b)=>a+b,0)', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e6, 1e6), { minLength: 12, maxLength: 12 }),
          (months) => {
            const result = calcMonthlyTotal(months)
            const expected = months.reduce((a, b) => a + b, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ P4: VR-I6-01校验 ═══
  // **Validates: Requirements 4.4, 10.1**
  describe('Feature: i6-research-development-expense, Property P4: VR-I6-01费用化+资本化=总额', () => {
    it('P4a: validateVRI601(e, c, e+c).isValid === true', () => {
      fc.assert(
        fc.property(positiveFloat(0, 1e9), positiveFloat(0, 1e9), (expense, capitalized) => {
          const total = expense + capitalized
          const result = validateVRI601(expense, capitalized, total)
          expect(result.isValid).toBe(true)
        }),
      )
    })

    it('P4b: validateVRI601(e, c, e+c+100).isValid === false', () => {
      fc.assert(
        fc.property(positiveFloat(0, 1e9), positiveFloat(0, 1e9), (expense, capitalized) => {
          const wrongTotal = expense + capitalized + 100
          const result = validateVRI601(expense, capitalized, wrongTotal)
          expect(result.isValid).toBe(false)
        }),
      )
    })
  })

  // ═══ P5: 合计行恒等 ═══
  // **Validates: Requirements 2.5**
  describe('Feature: i6-research-development-expense, Property P5: 合计行恒等', () => {
    it('P5: calcSubtotal(arr) === arr.reduce((a,b)=>a+b,0)', () => {
      fc.assert(
        fc.property(
          fc.array(safeFloat(-1e6, 1e6), { minLength: 1, maxLength: 50 }),
          (arr) => {
            const result = calcSubtotal(arr)
            const expected = arr.reduce((a, b) => a + b, 0)
            expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })
  })

  // ═══ P6: 借贷平衡 ═══
  // **Validates: Requirements 2.6**
  describe('Feature: i6-research-development-expense, Property P6: 借贷平衡', () => {
    it('P6: if Σdebits === Σcredits then isBalanced === true', () => {
      fc.assert(
        fc.property(
          fc.array(positiveFloat(0, 1e6), { minLength: 1, maxLength: 20 }),
          (amounts) => {
            // 构造平衡分录：借方=贷方（使用同一组金额）
            const result = calcDebitCreditBalance(amounts, amounts)
            expect(result.isBalanced).toBe(true)
          },
        ),
      )
    })

    it('P6b: 不平衡分录 isBalanced === false', () => {
      fc.assert(
        fc.property(
          fc.array(positiveFloat(0.01, 1e6), { minLength: 1, maxLength: 20 }),
          positiveFloat(1, 1e6),
          (debits, extra) => {
            // 贷方加extra破坏平衡
            const credits = [...debits, extra]
            const result = calcDebitCreditBalance(debits, credits)
            expect(result.isBalanced).toBe(false)
          },
        ),
      )
    })
  })

  // ═══ P7: 截止测试日期差 ═══
  // **Validates: Requirements 2.7**
  describe('Feature: i6-research-development-expense, Property P7: 截止测试日期差判断', () => {
    it('P7: |bookingDate - documentDate| ≤ 5天 → isCutoffCrossover returns false', () => {
      fc.assert(
        fc.property(
          fc.date({ min: new Date('2020-01-01'), max: new Date('2030-12-31') }),
          fc.integer({ min: 0, max: 5 }),
          fc.boolean(),
          (baseDate, daysDiff, addOrSubtract) => {
            const offsetMs = daysDiff * 24 * 60 * 60 * 1000
            const otherDate = new Date(
              addOrSubtract ? baseDate.getTime() + offsetMs : baseDate.getTime() - offsetMs,
            )
            // |diff| ≤ 5 days → should NOT be crossover
            const result = isCutoffCrossover(baseDate, otherDate, 5)
            expect(result).toBe(false)
          },
        ),
      )
    })

    it('P7b: |bookingDate - documentDate| > 5天 → isCutoffCrossover returns true', () => {
      fc.assert(
        fc.property(
          fc.date({ min: new Date('2020-01-01'), max: new Date('2030-12-31') }),
          fc.integer({ min: 6, max: 365 }),
          fc.boolean(),
          (baseDate, daysDiff, addOrSubtract) => {
            const offsetMs = daysDiff * 24 * 60 * 60 * 1000
            const otherDate = new Date(
              addOrSubtract ? baseDate.getTime() + offsetMs : baseDate.getTime() - offsetMs,
            )
            // |diff| > 5 days → should BE crossover
            const result = isCutoffCrossover(baseDate, otherDate, 5)
            expect(result).toBe(true)
          },
        ),
      )
    })
  })

  // ═══ P8: 变动率计算 ═══
  // **Validates: Requirements 2.8**
  describe('Feature: i6-research-development-expense, Property P8: 变动率公式正确性', () => {
    it('P8: calcChangeRate(c, p) === (c-p)/|p| × 100 (prior≠0)', () => {
      fc.assert(
        fc.property(
          safeFloat(-1e9, 1e9),
          fc.oneof(
            fc.float({ min: Math.fround(0.01), max: Math.fround(1e9), noNaN: true, noDefaultInfinity: true }),
            fc.float({ min: Math.fround(-1e9), max: Math.fround(-0.01), noNaN: true, noDefaultInfinity: true }),
          ),
          (current, prior) => {
            const result = calcChangeRate(current, prior)
            const expected = ((current - prior) / Math.abs(prior)) * 100
            expect(result).not.toBeNull()
            expect(Math.abs(result! - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('P8b: calcChangeRate(c, 0) === null (prior=0时无法计算)', () => {
      fc.assert(
        fc.property(safeFloat(), (current) => {
          expect(calcChangeRate(current, 0)).toBeNull()
        }),
      )
    })
  })
})
