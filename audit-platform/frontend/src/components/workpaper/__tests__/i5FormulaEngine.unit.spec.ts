/**
 * I5 其他非流动资产 — 公式引擎确定性边界测试
 * 覆盖 useI5FormulaEngine 全部5个纯函数
 * Spec: .kiro/specs/i5-other-noncurrent-assets/ Task 7.1
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcTriangleReconciliation,
  calcSubtotal,
  calcChangeRate,
} from '../composables/useI5FormulaEngine'

// ═══════════════════════════════════════════════════════════════════════════════
// calcAuditedAmount: 审定数 = 未审数 + AJE + RJE
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAuditedAmount', () => {
  it('正常值：100 + 20 + (-5) = 115', () => {
    expect(calcAuditedAmount(100, 20, -5)).toBe(115)
  })

  it('全零：0 + 0 + 0 = 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('负数 AJE/RJE：500 + (-100) + (-50) = 350', () => {
    expect(calcAuditedAmount(500, -100, -50)).toBe(350)
  })

  it('全负值：(-200) + (-30) + (-20) = -250', () => {
    expect(calcAuditedAmount(-200, -30, -20)).toBe(-250)
  })

  it('大数值：1000000 + 500000 + 250000 = 1750000', () => {
    expect(calcAuditedAmount(1000000, 500000, 250000)).toBe(1750000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcAssetEndBalance: 期末 = 期初 + 增加 - 减少
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcAssetEndBalance', () => {
  it('基本用例：1000 + 500 - 200 = 1300', () => {
    expect(calcAssetEndBalance(1000, 500, 200)).toBe(1300)
  })

  it('全零：0 + 0 - 0 = 0', () => {
    expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
  })

  it('无增减：800 + 0 - 0 = 800', () => {
    expect(calcAssetEndBalance(800, 0, 0)).toBe(800)
  })

  it('仅增加：0 + 300 - 0 = 300', () => {
    expect(calcAssetEndBalance(0, 300, 0)).toBe(300)
  })

  it('减少超期初（负余额）：100 + 0 - 500 = -400', () => {
    expect(calcAssetEndBalance(100, 0, 500)).toBe(-400)
  })

  it('大数值：9999999 + 1 - 0 = 10000000', () => {
    expect(calcAssetEndBalance(9999999, 1, 0)).toBe(10000000)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcTriangleReconciliation: 差额 = (期初+增加-减少) - 期末
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcTriangleReconciliation', () => {
  it('平衡（差额=0）：(1000+500-200) - 1300 = 0', () => {
    expect(calcTriangleReconciliation(1000, 500, 200, 1300)).toBe(0)
  })

  it('不平衡（正差额）：(1000+500-200) - 1200 = 100', () => {
    expect(calcTriangleReconciliation(1000, 500, 200, 1200)).toBe(100)
  })

  it('不平衡（负差额）：(1000+500-200) - 1400 = -100', () => {
    expect(calcTriangleReconciliation(1000, 500, 200, 1400)).toBe(-100)
  })

  it('全零平衡：(0+0-0) - 0 = 0', () => {
    expect(calcTriangleReconciliation(0, 0, 0, 0)).toBe(0)
  })

  it('期末为负时：(100+0-0) - (-50) = 150', () => {
    expect(calcTriangleReconciliation(100, 0, 0, -50)).toBe(150)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcSubtotal: SUM(数组)，空数组返回0
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcSubtotal', () => {
  it('多元素：[1,2,3] = 6', () => {
    expect(calcSubtotal([1, 2, 3])).toBe(6)
  })

  it('空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('含负值：[10, -3, 5, -2] = 10', () => {
    expect(calcSubtotal([10, -3, 5, -2])).toBe(10)
  })

  it('单元素：[42] = 42', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('全负值：[-1, -2, -3] = -6', () => {
    expect(calcSubtotal([-1, -2, -3])).toBe(-6)
  })

  it('大数组：100个1 = 100', () => {
    expect(calcSubtotal(Array(100).fill(1))).toBe(100)
  })
})

// ═══════════════════════════════════════════════════════════════════════════════
// calcChangeRate: 变动率 = (当期 - 前期) / 前期
// ═══════════════════════════════════════════════════════════════════════════════

describe('calcChangeRate', () => {
  it('翻倍：200/100 → (200-100)/100 = 1.0', () => {
    expect(calcChangeRate(200, 100)).toBeCloseTo(1.0)
  })

  it('前期为0返回null', () => {
    expect(calcChangeRate(100, 0)).toBeNull()
  })

  it('当期=前期 → 变动率=0', () => {
    expect(calcChangeRate(500, 500)).toBeCloseTo(0)
  })

  it('减少50%：(50-100)/100 = -0.5', () => {
    expect(calcChangeRate(50, 100)).toBeCloseTo(-0.5)
  })

  it('当期为0：(0-200)/200 = -1.0', () => {
    expect(calcChangeRate(0, 200)).toBeCloseTo(-1.0)
  })

  it('负前期：(100-(-50))/(-50) = -3.0', () => {
    expect(calcChangeRate(100, -50)).toBeCloseTo(-3.0)
  })
})
