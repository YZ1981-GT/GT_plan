/**
 * K9 管理费用 — 公式引擎/分析引擎/截止引擎 Property-Based Tests (CP-K9-01~07)
 *
 * 覆盖 useK9FormulaEngine + useK9AnalysisEngine + useK9CutoffEngine 全部核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：6602管理费用（**损益类/借方科目**，取发生额非余额）
 *
 * Spec: .kiro/specs/k9-admin-expenses/design.md → Correctness Properties CP-K9-01~07
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcIncomeStatementOccurrence,
  calcSubtotal,
} from '../composables/useK9FormulaEngine'
import {
  calcYoYChange,
  calcRatioToRevenue,
  isAbnormalFluctuation,
} from '../composables/useK9AnalysisEngine'
import { isCrossPeriod } from '../composables/useK9CutoffEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器（避免NaN/Infinity）
const safeFloat = (min = -1e9, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const positiveFloat = (min = 0.01, max = 1e9) =>
  fc.float({ min: Math.fround(min), max: Math.fround(max), noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K9 FormulaEngine + AnalysisEngine + CutoffEngine PBT', () => {
  // ═══ CP-K9-01: 审定数公式链 ═══
  // **Validates: Requirements 2.3**
  describe('Feature: k9-admin-expenses, Property CP-K9-01: 审定数公式链', () => {
    it('CP-K9-01: calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K9-02: 损益类费用发生额=借方发生-贷方发生 ═══
  // **Validates: Requirements 2.4**
  describe('Feature: k9-admin-expenses, Property CP-K9-02: 费用类发生额=借方发生-贷方发生', () => {
    it('CP-K9-02: calcIncomeStatementOccurrence(dr, cr) === dr - cr (debitOcc≥0, creditOcc≥0)', () => {
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

  // ═══ CP-K9-03: 同比变动率=(本期-上期)/|上期| ═══
  // **Validates: Requirements 4.2**
  describe('Feature: k9-admin-expenses, Property CP-K9-03: 同比变动率=(本期-上期)/上期', () => {
    it('CP-K9-03: calcYoYChange(cur, prior) === (cur - prior)/|prior| (prior≠0)', () => {
      fc.assert(
        fc.property(
          safeFloat(),
          safeFloat().filter((v) => Math.abs(v) > 0.001),
          (cur, prior) => {
            const result = calcYoYChange(cur, prior)
            expect(result).not.toBeNull()
            const expected = (cur - prior) / Math.abs(prior)
            expect(Math.abs(result! - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K9-03b: calcYoYChange(cur, 0) === null (除零返回null)', () => {
      fc.assert(
        fc.property(safeFloat(), (cur) => {
          expect(calcYoYChange(cur, 0)).toBeNull()
        }),
      )
    })
  })

  // ═══ CP-K9-04: 占营业收入比=费用/营业收入 ═══
  // **Validates: Requirements 4.3**
  describe('Feature: k9-admin-expenses, Property CP-K9-04: 占收入比=费用/营业收入', () => {
    it('CP-K9-04: calcRatioToRevenue(exp, rev) === exp/rev (rev>0)', () => {
      fc.assert(
        fc.property(
          safeFloat(),
          positiveFloat(0.01, 1e9),
          (exp, rev) => {
            const result = calcRatioToRevenue(exp, rev)
            expect(result).not.toBeNull()
            const expected = exp / rev
            expect(Math.abs(result! - expected)).toBeLessThan(EPSILON)
          },
        ),
      )
    })

    it('CP-K9-04b: calcRatioToRevenue(exp, 0) === null (营收为0返回null)', () => {
      fc.assert(
        fc.property(safeFloat(), (exp) => {
          expect(calcRatioToRevenue(exp, 0)).toBeNull()
        }),
      )
    })
  })

  // ═══ CP-K9-05: 异常波动判断=|变动率|>阈值 ═══
  // **Validates: Requirements 4.4**
  describe('Feature: k9-admin-expenses, Property CP-K9-05: 异常判断=|变动率|>阈值', () => {
    it('CP-K9-05: isAbnormalFluctuation(rate, th) === (Math.abs(rate) > th)', () => {
      fc.assert(
        fc.property(
          safeFloat(-10, 10),
          positiveFloat(0.01, 5),
          (rate, th) => {
            const result = isAbnormalFluctuation(rate, th)
            const expected = Math.abs(rate) > th
            expect(result).toBe(expected)
          },
        ),
      )
    })
  })

  // ═══ CP-K9-06: 合计行恒等 ═══
  // **Validates: Requirements 9.6**
  describe('Feature: k9-admin-expenses, Property CP-K9-06: 合计行恒等', () => {
    it('CP-K9-06: calcSubtotal(arr) === arr.reduce((s,x)=>s+x, 0)', () => {
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

    it('CP-K9-06b: calcSubtotal([]) === 0 (空数组)', () => {
      expect(calcSubtotal([])).toBe(0)
    })
  })

  // ═══ CP-K9-07: 跨期判断确定性 ═══
  // **Validates: Requirements 5.4**
  describe('Feature: k9-admin-expenses, Property CP-K9-07: 跨期判断确定性', () => {
    it('CP-K9-07a: 不同月份的两个日期 → isCrossPeriod=true', () => {
      // 生成两个日期保证分属不同月份
      fc.assert(
        fc.property(
          fc.integer({ min: 2020, max: 2030 }),
          fc.integer({ min: 1, max: 12 }),
          fc.integer({ min: 1, max: 28 }),
          fc.integer({ min: 1, max: 28 }),
          (year, month1, day1, day2) => {
            // 确保第二个月与第一个不同
            const month2 = (month1 % 12) + 1
            const srcDate = `${year}-${String(month1).padStart(2, '0')}-${String(day1).padStart(2, '0')}`
            const bookDate = `${year}-${String(month2).padStart(2, '0')}-${String(day2).padStart(2, '0')}`
            const result = isCrossPeriod(srcDate, bookDate, `${year}-12-31`)
            expect(result).toBe(true)
          },
        ),
      )
    })

    it('CP-K9-07b: 同年同月的两个日期 → isCrossPeriod=false', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 2020, max: 2030 }),
          fc.integer({ min: 1, max: 12 }),
          fc.integer({ min: 1, max: 28 }),
          fc.integer({ min: 1, max: 28 }),
          (year, month, day1, day2) => {
            const srcDate = `${year}-${String(month).padStart(2, '0')}-${String(day1).padStart(2, '0')}`
            const bookDate = `${year}-${String(month).padStart(2, '0')}-${String(day2).padStart(2, '0')}`
            const result = isCrossPeriod(srcDate, bookDate, `${year}-12-31`)
            expect(result).toBe(false)
          },
        ),
      )
    })

    it('CP-K9-07c: 不同年份 → isCrossPeriod=true', () => {
      fc.assert(
        fc.property(
          fc.integer({ min: 2020, max: 2028 }),
          fc.integer({ min: 1, max: 12 }),
          fc.integer({ min: 1, max: 28 }),
          fc.integer({ min: 1, max: 12 }),
          fc.integer({ min: 1, max: 28 }),
          (year, month1, day1, month2, day2) => {
            const srcDate = `${year}-${String(month1).padStart(2, '0')}-${String(day1).padStart(2, '0')}`
            const bookDate = `${year + 1}-${String(month2).padStart(2, '0')}-${String(day2).padStart(2, '0')}`
            const result = isCrossPeriod(srcDate, bookDate, `${year}-12-31`)
            expect(result).toBe(true)
          },
        ),
      )
    })
  })
})
