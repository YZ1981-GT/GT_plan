/**
 * Unit Tests — H5 油气资产公式引擎 + 折耗引擎（边界/边缘情况）
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/ Task 7.1
 * Requirements: P1-P10
 *
 * 与 h5FormulaEngine.pbt.spec.ts 互补：
 * - PBT 验证公式在随机输入下的数学正确性
 * - 本文件验证特定边界情况：零值/储量0/产量>储量/大数/NaN防护
 */
import { describe, it, expect } from 'vitest'
import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcTriangleReconciliation,
  calcNetValue,
  calcSubtotal,
  calcChangeRate,
  calcPriceDiffRate,
  calcLeaseReturnRate,
} from '../composables/useH5FormulaEngine'
import {
  calcUnitDepletion,
  calcDepletionRate,
  calcRemainingReserves,
  calcDepletionAfterImpairment,
  calcDepletionCapped,
} from '../composables/useH5DepletionEngine'

// ============================================================
// useH5FormulaEngine — 9 个纯函数
// ============================================================

// ── calcAuditedAmount ────────────────────────────────────────
describe('calcAuditedAmount — 审定数 = 未审 + AJE + RJE', () => {
  it('normal: 1000 + 200 + (-50) = 1150', () => {
    expect(calcAuditedAmount(1000, 200, -50)).toBe(1150)
  })

  it('all zero → 0', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('NaN inputs → treated as 0', () => {
    expect(calcAuditedAmount(NaN, 100, NaN)).toBe(100)
    expect(calcAuditedAmount(NaN, NaN, NaN)).toBe(0)
  })

  it('large numbers (亿级)', () => {
    expect(calcAuditedAmount(1e9, 5e8, -2e8)).toBe(1.3e9)
  })
})

// ── calcAssetEndBalance ──────────────────────────────────────
describe('calcAssetEndBalance — 资产类期末 = 期初 + 借 - 贷', () => {
  it('normal: 1000 + 300 - 100 = 1200', () => {
    expect(calcAssetEndBalance(1000, 300, 100)).toBe(1200)
  })

  it('negative result (贷方>期初+借方)', () => {
    expect(calcAssetEndBalance(100, 50, 200)).toBe(-50)
  })

  it('zero inputs', () => {
    expect(calcAssetEndBalance(0, 0, 0)).toBe(0)
  })

  it('NaN treated as 0', () => {
    expect(calcAssetEndBalance(NaN, 500, 100)).toBe(400)
  })
})

// ── calcContraEndBalance ─────────────────────────────────────
describe('calcContraEndBalance — 备抵类期末 = 期初 + 贷 - 借', () => {
  it('normal: 500 + 200 - 50 = 650', () => {
    expect(calcContraEndBalance(500, 50, 200)).toBe(650)
  })

  it('all zero → 0', () => {
    expect(calcContraEndBalance(0, 0, 0)).toBe(0)
  })

  it('NaN treated as 0', () => {
    expect(calcContraEndBalance(NaN, NaN, 300)).toBe(300)
  })
})

// ── calcTriangleReconciliation ───────────────────────────────
describe('calcTriangleReconciliation — 三角勾稽', () => {
  it('balanced: end = begin + inc - dec → 0', () => {
    // 1000 + 300 - 100 = 1200 → reconciliation = 0
    expect(calcTriangleReconciliation(1000, 300, 100, 1200)).toBe(0)
  })

  it('unbalanced: diff ≠ 0', () => {
    // expect 1200 but end=1300 → diff = 100
    expect(calcTriangleReconciliation(1000, 300, 100, 1300)).toBe(100)
  })

  it('negative diff', () => {
    expect(calcTriangleReconciliation(1000, 300, 100, 1100)).toBe(-100)
  })

  it('all zero → 0', () => {
    expect(calcTriangleReconciliation(0, 0, 0, 0)).toBe(0)
  })
})

// ── calcNetValue ─────────────────────────────────────────────
describe('calcNetValue — 净值 = 原值 - 累计折耗 - 减值', () => {
  it('normal: 10000 - 3000 - 500 = 6500', () => {
    expect(calcNetValue(10000, 3000, 500)).toBe(6500)
  })

  it('negative net value (fully depleted)', () => {
    expect(calcNetValue(1000, 800, 300)).toBe(-100)
  })

  it('zero cost → negative', () => {
    expect(calcNetValue(0, 100, 50)).toBe(-150)
  })

  it('NaN treated as 0', () => {
    expect(calcNetValue(NaN, 0, 0)).toBe(0)
  })
})

// ── calcSubtotal ─────────────────────────────────────────────
describe('calcSubtotal — 合计行', () => {
  it('normal array', () => {
    expect(calcSubtotal([100, 200, 300])).toBe(600)
  })

  it('empty array → 0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('single element', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('NaN in array → treated as 0', () => {
    expect(calcSubtotal([100, NaN, 200])).toBe(300)
  })

  it('negative values', () => {
    expect(calcSubtotal([100, -50, 200])).toBe(250)
  })
})

// ── calcChangeRate ───────────────────────────────────────────
describe('calcChangeRate — 变动率%', () => {
  it('normal increase: (1200-1000)/1000*100 = 20', () => {
    expect(calcChangeRate(1200, 1000)).toBe(20)
  })

  it('prior = 0 → returns 0 (no division by zero)', () => {
    expect(calcChangeRate(500, 0)).toBe(0)
  })

  it('decrease: (800-1000)/1000*100 = -20', () => {
    expect(calcChangeRate(800, 1000)).toBe(-20)
  })

  it('NaN prior → 0', () => {
    expect(calcChangeRate(100, NaN)).toBe(0)
  })
})

// ── calcPriceDiffRate ────────────────────────────────────────
describe('calcPriceDiffRate — 价差率%', () => {
  it('normal: (120-100)/100*100 = 20', () => {
    expect(calcPriceDiffRate(120, 100)).toBe(20)
  })

  it('marketPrice = 0 → returns 0', () => {
    expect(calcPriceDiffRate(100, 0)).toBe(0)
  })

  it('negative diff (below market)', () => {
    expect(calcPriceDiffRate(80, 100)).toBe(-20)
  })

  it('NaN inputs → 0', () => {
    expect(calcPriceDiffRate(NaN, NaN)).toBe(0)
  })
})

// ── calcLeaseReturnRate ──────────────────────────────────────
describe('calcLeaseReturnRate — 租赁收益率%', () => {
  it('normal: 50/500*100 = 10', () => {
    expect(calcLeaseReturnRate(50, 500)).toBe(10)
  })

  it('netValue = 0 → returns 0', () => {
    expect(calcLeaseReturnRate(100, 0)).toBe(0)
  })

  it('large rent vs small net value', () => {
    expect(calcLeaseReturnRate(1000, 100)).toBe(1000)
  })

  it('NaN inputs → 0', () => {
    expect(calcLeaseReturnRate(NaN, 100)).toBe(0)
  })
})

// ============================================================
// useH5DepletionEngine — 5 个纯函数
// ============================================================

// ── calcUnitDepletion ────────────────────────────────────────
describe('calcUnitDepletion — 单位产量法折耗', () => {
  it('normal: (10000-1000)*500/5000 = 900', () => {
    expect(calcUnitDepletion(10000, 1000, 500, 5000)).toBe(900)
  })

  it('reserves = 0 → returns 0 (no division by zero)', () => {
    expect(calcUnitDepletion(10000, 1000, 500, 0)).toBe(0)
  })

  it('large numbers (亿级储量)', () => {
    const result = calcUnitDepletion(1e9, 1e8, 1e6, 1e7)
    // (1e9 - 1e8) * 1e6 / 1e7 = 9e8 * 1e6 / 1e7 = 9e7
    expect(result).toBeCloseTo(9e7, 0)
  })

  it('production = 0 → 折耗 = 0', () => {
    expect(calcUnitDepletion(10000, 1000, 0, 5000)).toBe(0)
  })

  it('salvage > cost → negative depletion (合理:可折耗金额为负)', () => {
    // (1000-2000)*500/5000 = -1000*500/5000 = -100
    expect(calcUnitDepletion(1000, 2000, 500, 5000)).toBe(-100)
  })

  it('NaN inputs → treated as 0', () => {
    expect(calcUnitDepletion(NaN, 0, 500, 1000)).toBe(0)
  })
})

// ── calcDepletionRate ────────────────────────────────────────
describe('calcDepletionRate — 折耗率%', () => {
  it('normal: 3000/10000*100 = 30', () => {
    expect(calcDepletionRate(3000, 10000)).toBe(30)
  })

  it('cost = 0 → returns 0', () => {
    expect(calcDepletionRate(500, 0)).toBe(0)
  })

  it('NaN inputs → 0', () => {
    expect(calcDepletionRate(NaN, NaN)).toBe(0)
  })

  it('accDepletion > cost (已超额折耗)', () => {
    expect(calcDepletionRate(12000, 10000)).toBe(120)
  })
})

// ── calcRemainingReserves ────────────────────────────────────
describe('calcRemainingReserves — 剩余可采储量', () => {
  it('normal: 10000 - 3000 = 7000', () => {
    expect(calcRemainingReserves(10000, 3000)).toBe(7000)
  })

  it('accProduction > totalReserves → negative (已超采)', () => {
    expect(calcRemainingReserves(5000, 8000)).toBe(-3000)
  })

  it('zero total → negative when any production', () => {
    expect(calcRemainingReserves(0, 100)).toBe(-100)
  })

  it('NaN inputs → treated as 0', () => {
    expect(calcRemainingReserves(NaN, 500)).toBe(-500)
  })
})

// ── calcDepletionAfterImpairment ─────────────────────────────
describe('calcDepletionAfterImpairment — 含减值后折耗', () => {
  it('normal: (8000-1000)*500/5000 = 700', () => {
    expect(calcDepletionAfterImpairment(8000, 1000, 500, 5000)).toBe(700)
  })

  it('remainReserves = 0 → returns 0', () => {
    expect(calcDepletionAfterImpairment(8000, 1000, 500, 0)).toBe(0)
  })

  it('netValue < salvage → negative depletion', () => {
    expect(calcDepletionAfterImpairment(500, 1000, 100, 1000)).toBe(-50)
  })

  it('NaN inputs → 0', () => {
    expect(calcDepletionAfterImpairment(NaN, NaN, NaN, NaN)).toBe(0)
  })
})

// ── calcDepletionCapped ──────────────────────────────────────
describe('calcDepletionCapped — 折耗封顶（可折耗余额）', () => {
  it('normal: 10000 - 1000 - 5000 = 4000', () => {
    expect(calcDepletionCapped(10000, 1000, 5000)).toBe(4000)
  })

  it('fully depleted → 0', () => {
    expect(calcDepletionCapped(10000, 1000, 9000)).toBe(0)
  })

  it('over-depleted → negative (indicates over-depletion)', () => {
    expect(calcDepletionCapped(10000, 1000, 10000)).toBe(-1000)
  })

  it('NaN inputs → 0', () => {
    expect(calcDepletionCapped(NaN, NaN, NaN)).toBe(0)
  })

  it('large numbers', () => {
    expect(calcDepletionCapped(1e9, 1e8, 5e8)).toBe(4e8)
  })
})
