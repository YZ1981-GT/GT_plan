/**
 * K6 持有待售 — Property-Based Tests (CP-K6-01~05)
 *
 * 覆盖 useK6FormulaEngine + useK6ClassificationEngine + useK6ImpairmentEngine 核心纯函数。
 * 使用 fast-check 验证数学正确性。
 * 科目：持有待售资产（借方/资产类）+ 持有待售负债（贷方/负债类）
 *
 * 核心公式：
 * - 审定数 = 未审 + AJE + RJE
 * - 账面价值 = 原值 - 累计折旧摊销 - 减值准备
 * - 分类判断：全True→classified；任一False→not_classified
 * - 公允价值净额 = 公允价值 - 预计出售费用
 * - 减值 = MAX(0, 账面价值 - 公允价值净额)，结果≥0
 *
 * Spec: .kiro/specs/k6-held-for-sale/design.md → Correctness Properties CP-K6-01~05
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import { calcAuditedAmount, calcBookValue, calcSubtotal } from '../composables/useK6FormulaEngine'
import { classifyHeldForSale } from '../composables/useK6ClassificationEngine'
import { calcFairValueNet, calcImpairment, calcAllocationRatio } from '../composables/useK6ImpairmentEngine'

fc.configureGlobal({ numRuns: 200 })

// 安全浮点生成器（金融范围，排除NaN和Infinity）
const safeFloat = (min = -1e12, max = 1e12) =>
  fc.double({ min, max, noNaN: true, noDefaultInfinity: true })

const EPSILON = 1e-4

describe('K6 Held-for-Sale Engines PBT', () => {
  // ═══ CP-K6-01: 审定数公式链 ═══
  // **Validates: Requirements 9.1**
  describe('Feature: k6-held-for-sale, Property CP-K6-01: 审定数公式链', () => {
    it('∀ (u,a,r) ∈ ℝ: calcAuditedAmount(u,a,r) === u + a + r', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (u, a, r) => {
          const result = calcAuditedAmount(u, a, r)
          const expected = u + a + r
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K6-02: 账面价值 ═══
  // **Validates: Requirements 9.2, 3.2**
  describe('Feature: k6-held-for-sale, Property CP-K6-02: 账面价值=原值-折旧摊销-减值', () => {
    it('∀ (cost,dep,imp) ∈ ℝ: calcBookValue(cost,dep,imp) === cost - dep - imp', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), safeFloat(), (cost, dep, imp) => {
          const result = calcBookValue(cost, dep, imp)
          const expected = cost - dep - imp
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K6-03: CAS42五条件分类判断确定性 ═══
  // **Validates: Requirements 4.2, 9.3**
  describe('Feature: k6-held-for-sale, Property CP-K6-03: CAS42五条件分类判断', () => {
    it('全True→classified', () => {
      fc.assert(
        fc.property(
          fc.array(fc.constant(true), { minLength: 5, maxLength: 5 }),
          (conditions) => {
            expect(classifyHeldForSale(conditions)).toBe('classified')
          },
        ),
      )
    })

    it('含任一False→not_classified', () => {
      // 生成5个布尔值，但至少有一个为false
      const genConditionsWithFalse = fc
        .array(fc.boolean(), { minLength: 5, maxLength: 5 })
        .filter((arr) => arr.some((v) => v === false))

      fc.assert(
        fc.property(genConditionsWithFalse, (conditions) => {
          expect(classifyHeldForSale(conditions)).toBe('not_classified')
        }),
      )
    })
  })

  // ═══ CP-K6-04: 公允价值净额 ═══
  // **Validates: Requirements 5.2, 9.4**
  describe('Feature: k6-held-for-sale, Property CP-K6-04: 公允价值净额=公允-出售费用', () => {
    it('∀ (fv,sc) ∈ ℝ: calcFairValueNet(fv,sc) === fv - sc', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), (fv, sc) => {
          const result = calcFairValueNet(fv, sc)
          const expected = fv - sc
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })
  })

  // ═══ CP-K6-05: 减值孰低且非负 ═══
  // **Validates: Requirements 5.3, 9.5**
  describe('Feature: k6-held-for-sale, Property CP-K6-05: 减值=MAX(0,账面-公允净额)非负', () => {
    it('∀ (bv,fvn) ∈ ℝ: calcImpairment(bv,fvn) === Math.max(0, bv - fvn)', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), (bv, fvn) => {
          const result = calcImpairment(bv, fvn)
          const expected = Math.max(0, bv - fvn)
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }),
      )
    })

    it('∀ (bv,fvn) ∈ ℝ: calcImpairment(bv,fvn) >= 0', () => {
      fc.assert(
        fc.property(safeFloat(), safeFloat(), (bv, fvn) => {
          const result = calcImpairment(bv, fvn)
          expect(result).toBeGreaterThanOrEqual(0)
        }),
      )
    })
  })
})


// ═══ CP-K6-06: 分摊比例=组内/组合计 ═══
// **Validates: Requirements 6.3, 9.6**
describe('Feature: k6-held-for-sale, Property CP-K6-06: 分摊比例=组内/组合计', () => {
  it('∀ itemBook ∈ ℝ, groupBook > 0: calcAllocationRatio(item, group) === item / group', () => {
    fc.assert(
      fc.property(
        safeFloat(),
        fc.double({ min: 0.01, max: 1e12, noNaN: true, noDefaultInfinity: true }),
        (itemBook, groupBook) => {
          const result = calcAllocationRatio(itemBook, groupBook)
          const expected = itemBook / groupBook
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }
      )
    )
  })

  it('groupBook === 0 → 0 (兜底)', () => {
    fc.assert(
      fc.property(safeFloat(), (itemBook) => {
        expect(calcAllocationRatio(itemBook, 0)).toBe(0)
      })
    )
  })
})

// ═══ CP-K6-07: 合计行恒等 ═══
// **Validates: Requirements 9.7**
describe('Feature: k6-held-for-sale, Property CP-K6-07: 合计行恒等', () => {
  it('∀ arr ∈ ℝ[]: calcSubtotal(arr) === Σarr', () => {
    fc.assert(
      fc.property(
        fc.array(safeFloat(), { minLength: 0, maxLength: 50 }),
        (arr) => {
          const result = calcSubtotal(arr)
          const expected = arr.reduce((s, v) => s + v, 0)
          expect(Math.abs(result - expected)).toBeLessThan(EPSILON)
        }
      )
    )
  })
})
