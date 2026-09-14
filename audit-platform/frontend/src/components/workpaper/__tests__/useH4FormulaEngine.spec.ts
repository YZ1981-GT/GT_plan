/**
 * useH4FormulaEngine PBT + 单元测试
 *
 * Property-Based Tests 使用 fast-check，numRuns: 100。
 * 单元测试覆盖边界：零值/负值/大数/NaN防护。
 * 覆盖 H4 工程物资公式引擎全部纯函数。
 */
import { describe, it, expect } from 'vitest'
import * as fc from 'fast-check'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcPriceDiffRate,
  calcDiffRate,
  calcRecoverableAmount,
  calcRequiredProvision,
  calcPeriodImpairmentAdjustment,
  calcUnitPrice,
  calcNetBookValue,
  calcAuditedEndBalance,
} from '../composables/useH4FormulaEngine'

// ─── Property-Based Tests ───────────────────────────────────────────────────

describe('useH4FormulaEngine — PBT', () => {
  /**
   * **Feature: h4-engineering-materials, Property P1: 审定数公式链正确性**
   *
   * For any 三元组 (未审数, AJE净额, RJE净额)，其中各值为有限数值，
   * calcAuditedAmount 的返回值应等于 未审数 + AJE + RJE。
   *
   * **Validates: Requirements 2.3**
   */
  describe('Property P1: 审定数公式链正确性', () => {
    it('calcAuditedAmount(u, a, r) === u + a + r', () => {
      fc.assert(
        fc.property(
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          fc.float({ min: -1e9, max: 1e9, noNaN: true }),
          (u, a, r) => {
            expect(calcAuditedAmount(u, a, r)).toBeCloseTo(u + a + r, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: h4-engineering-materials, Property P2: 资产类期末余额公式**
   *
   * For any 三元组 (期初, 借方发生, 贷方发生)，其中各值≥0，
   * calcAssetEndBalance 的返回值应等于 期初 + 借方发生 - 贷方发生。
   *
   * **Validates: Requirements 2.4**
   */
  describe('Property P2: 资产类期末余额公式', () => {
    it('calcAssetEndBalance(b, d, c) === b + d - c', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          (b, d, c) => {
            expect(calcAssetEndBalance(b, d, c)).toBeCloseTo(b + d - c, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: h4-engineering-materials, Property P3: 三角勾稽恒等**
   *
   * For any 三元组 (期初, 增加, 减少)，令 end = 期初 + 增加 - 减少，
   * calcTriangleReconciliation(begin, increase, decrease, end) 应恒等于 0。
   *
   * **Validates: Requirements 2.5**
   */
  describe('Property P3: 三角勾稽恒等', () => {
    it('calcTriangleReconciliation(b, i, d, b+i-d) === 0', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          fc.float({ min: 0, max: 1e9, noNaN: true }),
          (b, i, d) => {
            const end = b + i - d
            expect(calcTriangleReconciliation(b, i, d, end)).toBeCloseTo(0, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: h4-engineering-materials, Property P4: 合计行恒等**
   *
   * For any 数值数组（明细行金额列），calcSubtotal(arr) 应等于
   * arr.reduce((a, b) => a + b, 0)。
   *
   * **Validates: Requirements 2.4**
   */
  describe('Property P4: 合计行恒等', () => {
    it('calcSubtotal(arr) === arr.reduce((a,b)=>a+b, 0)', () => {
      fc.assert(
        fc.property(
          fc.array(fc.float({ min: -1e9, max: 1e9, noNaN: true }), { minLength: 1, maxLength: 50 }),
          (arr) => {
            const expected = arr.reduce((a, b) => a + b, 0)
            expect(calcSubtotal(arr)).toBeCloseTo(expected, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: h4-engineering-materials, Property P5: 关联价差率公式**
   *
   * For any (交易价格, 市场价格) 对，其中 marketPrice > 0，
   * calcPriceDiffRate(t, m) 应等于 (t - m) / m × 100。
   *
   * **Validates: Requirements 8.2**
   */
  describe('Property P5: 关联价差率公式', () => {
    it('calcPriceDiffRate(t, m) === (t-m)/m * 100', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 1, max: 1e9, noNaN: true }),
          fc.float({ min: 1, max: 1e9, noNaN: true }),
          (t, m) => {
            const expected = (t - m) / m * 100
            expect(calcPriceDiffRate(t, m)).toBeCloseTo(expected, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })

  /**
   * **Feature: h4-engineering-materials, Property P6: 差异率公式**
   *
   * For any (实际值, 预期值) 对，其中 expected > 0，
   * calcDiffRate(a, e) 应等于 (a - e) / e × 100。
   *
   * **Validates: Requirements 5.2**
   */
  describe('Property P6: 差异率公式', () => {
    it('calcDiffRate(a, e) === (a-e)/e * 100', () => {
      fc.assert(
        fc.property(
          fc.float({ min: 1, max: 1e9, noNaN: true }),
          fc.float({ min: 1, max: 1e9, noNaN: true }),
          (a, e) => {
            const expected = (a - e) / e * 100
            expect(calcDiffRate(a, e)).toBeCloseTo(expected, 5)
          }
        ),
        { numRuns: 100 }
      )
    })
  })
})


// ─── 单元测试（边界）──────────────────────────────────────────────────────────

describe('useH4FormulaEngine — 单元测试（边界）', () => {
  // ─── calcAuditedAmount ────────────────────────────────────────────────────

  describe('calcAuditedAmount 边界', () => {
    it('全零输入 → 0', () => {
      expect(calcAuditedAmount(0, 0, 0)).toBe(0)
    })

    it('负值输入正确计算', () => {
      expect(calcAuditedAmount(-100, -50, -30)).toBe(-180)
    })

    it('混合正负值', () => {
      expect(calcAuditedAmount(1000, -200, 50)).toBe(850)
    })

    it('大数（接近MAX_SAFE_INTEGER量级）', () => {
      const big = 1e15
      expect(calcAuditedAmount(big, big, big)).toBe(3e15)
    })

    it('极小浮点数精度', () => {
      expect(calcAuditedAmount(0.1, 0.2, 0.3)).toBeCloseTo(0.6, 10)
    })
  })

  // ─── calcAssetEndBalance ──────────────────────────────────────────────────

  describe('calcAssetEndBalance 边界', () => {
    it('全零输入 → 0', () => {
      expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
    })

    it('仅贷方发生 → 负值期末', () => {
      expect(calcAssetEndBalance(0, 0, 500)).toBe(-500)
    })

    it('仅借方发生 → 正值期末', () => {
      expect(calcAssetEndBalance(0, 1000, 0)).toBe(1000)
    })

    it('负期初（异常但不崩溃）', () => {
      expect(calcAssetEndBalance(-100, 200, 50)).toBe(50)
    })

    it('大数计算', () => {
      expect(calcAssetEndBalance(1e15, 1e14, 5e13)).toBe(1.05e15)
    })
  })

  // ─── calcTriangleReconciliation ───────────────────────────────────────────

  describe('calcTriangleReconciliation 边界', () => {
    it('全零 → 0', () => {
      expect(calcTriangleReconciliation(0, 0, 0, 0)).toBe(0)
    })

    it('平衡情况 → 0', () => {
      expect(calcTriangleReconciliation(100, 50, 30, 120)).toBe(0)
    })

    it('不平衡情况 → 差额', () => {
      expect(calcTriangleReconciliation(100, 50, 30, 130)).toBe(10)
    })

    it('负值全组合', () => {
      // end - (begin + increase - decrease)
      // -50 - (-100 + (-20) - (-30)) = -50 - (-90) = 40
      expect(calcTriangleReconciliation(-100, -20, -30, -50)).toBe(40)
    })
  })

  // ─── calcSubtotal ─────────────────────────────────────────────────────────

  describe('calcSubtotal 边界', () => {
    it('空数组 → 0', () => {
      expect(calcSubtotal([])).toBe(0)
    })

    it('单元素', () => {
      expect(calcSubtotal([42])).toBe(42)
    })

    it('含负值', () => {
      expect(calcSubtotal([100, -50, 30, -20])).toBe(60)
    })

    it('全零数组', () => {
      expect(calcSubtotal([0, 0, 0, 0, 0])).toBe(0)
    })

    it('大数组（50元素）', () => {
      const arr = Array.from({ length: 50 }, (_, i) => i + 1)
      expect(calcSubtotal(arr)).toBe(1275) // sum(1..50) = 50*51/2
    })
  })

  // ─── calcDiffRate ─────────────────────────────────────────────────────────

  describe('calcDiffRate 边界', () => {
    it('expected=0, actual=0 → 0', () => {
      expect(calcDiffRate(0, 0)).toBe(0)
    })

    it('expected=0, actual≠0 → 100（完全偏离）', () => {
      expect(calcDiffRate(500, 0)).toBe(100)
    })

    it('actual=expected → 0%', () => {
      expect(calcDiffRate(100, 100)).toBe(0)
    })

    it('actual > expected → 正差异率', () => {
      expect(calcDiffRate(120, 100)).toBeCloseTo(20, 5)
    })

    it('actual < expected → 负差异率', () => {
      expect(calcDiffRate(80, 100)).toBeCloseTo(-20, 5)
    })

    it('负值expected', () => {
      // (actual - expected) / expected * 100 = (-50 - (-100)) / (-100) * 100 = 50 / -100 * 100 = -50
      expect(calcDiffRate(-50, -100)).toBeCloseTo(-50, 5)
    })
  })

  // ─── calcPriceDiffRate ────────────────────────────────────────────────────

  describe('calcPriceDiffRate 边界', () => {
    it('marketPrice=0, transPrice=0 → 0', () => {
      expect(calcPriceDiffRate(0, 0)).toBe(0)
    })

    it('marketPrice=0, transPrice≠0 → 100（完全偏离）', () => {
      expect(calcPriceDiffRate(1000, 0)).toBe(100)
    })

    it('transPrice=marketPrice → 0%', () => {
      expect(calcPriceDiffRate(500, 500)).toBe(0)
    })

    it('transPrice > marketPrice → 正价差率（溢价）', () => {
      // (110 - 100) / 100 * 100 = 10%
      expect(calcPriceDiffRate(110, 100)).toBeCloseTo(10, 5)
    })

    it('transPrice < marketPrice → 负价差率（折价）', () => {
      // (90 - 100) / 100 * 100 = -10%
      expect(calcPriceDiffRate(90, 100)).toBeCloseTo(-10, 5)
    })

    it('极小市场价格', () => {
      // (100 - 0.01) / 0.01 * 100 = 999900%
      expect(calcPriceDiffRate(100, 0.01)).toBeCloseTo(999900, 0)
    })
  })

  // ─── H4-7 减值测算公式 ────────────────────────────────────────────────────

  describe('H4-7 减值测算公式', () => {
    it('calcRecoverableAmount = MAX(公允净额, 现值)', () => {
      expect(calcRecoverableAmount(80, 100)).toBe(100)
      expect(calcRecoverableAmount(120, 50)).toBe(120)
    })

    it('calcRequiredProvision = MAX(账面−可收回, 0)', () => {
      expect(calcRequiredProvision(200, 150)).toBe(50)
      expect(calcRequiredProvision(100, 150)).toBe(0)
    })

    it('calcPeriodImpairmentAdjustment = 应提 − 已提', () => {
      expect(calcPeriodImpairmentAdjustment(50, 20)).toBe(30)
      expect(calcPeriodImpairmentAdjustment(10, 40)).toBe(-30)
    })
  })

  // ─── H4-2 单价 / 净值 ─────────────────────────────────────────────────────

  describe('H4-2 单价与净值', () => {
    it('calcUnitPrice 数量为0返回 null', () => {
      expect(calcUnitPrice(100, 0)).toBeNull()
      expect(calcUnitPrice(100, 4)).toBe(25)
    })

    it('calcNetBookValue = 原值 − 跌价', () => {
      expect(calcNetBookValue(1000, 150)).toBe(850)
    })

    it('calcAuditedEndBalance = 审定期初 + 增 − 减', () => {
      expect(calcAuditedEndBalance(100, 50, 20)).toBe(130)
    })
  })
})
