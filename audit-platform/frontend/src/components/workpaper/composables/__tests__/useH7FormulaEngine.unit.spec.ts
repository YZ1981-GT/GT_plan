/**
 * H7 生产性生物资产 — 单元测试：引擎边界场景
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 7.1
 * Requirements: P1-P12
 *
 * 测试边界：零值/大数/NaN/公允模式切换
 */
import { describe, it, expect } from 'vitest'

import {
  calcAuditedAmount,
  calcAssetEndBalance,
  calcContraEndBalance,
  calcFairEndBalance,
  calcNetValue,
  calcSubtotal,
  calcChangeRate,
  calcPriceDiffRate,
  calcFairValueDiffRate,
} from '../useH7FormulaEngine'

import {
  calcStraightLine,
  calcMonthlyDep,
  calcDepAfterImpairment,
  calcAccDep,
} from '../useH7DepreciationEngine'

import {
  calcProdToConsumable,
  calcProdToPublic,
  calcTransferDiff,
} from '../useH7TransferEngine'

// ─── useH7FormulaEngine 边界测试 ────────────────────────────────────────────

describe('useH7FormulaEngine - 边界场景', () => {
  it('审定数：全零', () => {
    expect(calcAuditedAmount(0, 0, 0)).toBe(0)
  })

  it('审定数：大数', () => {
    expect(calcAuditedAmount(1e12, -5e11, 2e11)).toBeCloseTo(7e11)
  })

  it('资产期末余额：借方贷方都为0', () => {
    expect(calcAssetEndBalance(100, 0, 0)).toBe(100)
  })

  it('备抵类期末余额：期初+贷方-借方', () => {
    expect(calcContraEndBalance(1000, 200, 500)).toBe(1300)
  })

  it('公允模式期末：含负变动', () => {
    expect(calcFairEndBalance(1000, 200, 100, -50)).toBe(1050)
  })

  it('净值：全零', () => {
    expect(calcNetValue(0, 0, 0)).toBe(0)
  })

  it('净值：常规场景', () => {
    expect(calcNetValue(10000, 3000, 500)).toBe(6500)
  })

  it('合计：空数组返回0', () => {
    expect(calcSubtotal([])).toBe(0)
  })

  it('合计：单元素', () => {
    expect(calcSubtotal([42])).toBe(42)
  })

  it('变动率：prior为0返回0', () => {
    expect(calcChangeRate(100, 0)).toBe(0)
  })

  it('变动率：正常计算', () => {
    expect(calcChangeRate(120, 100)).toBeCloseTo(20)
  })

  it('价差率：marketPrice为0返回0', () => {
    expect(calcPriceDiffRate(100, 0)).toBe(0)
  })

  it('公允差异率：bookValue为0返回0', () => {
    expect(calcFairValueDiffRate(100, 0)).toBe(0)
  })

  it('公允差异率：正常计算', () => {
    expect(calcFairValueDiffRate(110, 100)).toBeCloseTo(10)
  })
})

// ─── useH7DepreciationEngine 边界测试 ───────────────────────────────────────

describe('useH7DepreciationEngine - 边界场景', () => {
  it('直线法：usefulLife <= 0返回0', () => {
    expect(calcStraightLine(10000, 0.05, 0)).toBe(0)
    expect(calcStraightLine(10000, 0.05, -1)).toBe(0)
  })

  it('直线法：常规 10年5%残值', () => {
    expect(calcStraightLine(10000, 0.05, 10)).toBeCloseTo(950)
  })

  it('月折旧：年折旧12000→月1000', () => {
    expect(calcMonthlyDep(12000)).toBeCloseTo(1000)
  })

  it('月折旧：零值', () => {
    expect(calcMonthlyDep(0)).toBe(0)
  })

  it('减值后折旧：remainLife <= 0返回0', () => {
    expect(calcDepAfterImpairment(5000, 0.05, 0)).toBe(0)
  })

  it('减值后折旧：常规', () => {
    // 净值5000, 残值率5%, 剩余5年 → 5000×0.95/5 = 950
    expect(calcDepAfterImpairment(5000, 0.05, 5)).toBeCloseTo(950)
  })

  it('累计折旧：月折旧×月数', () => {
    expect(calcAccDep(1000, 36)).toBe(36000)
  })

  it('累计折旧：0个月', () => {
    expect(calcAccDep(1000, 0)).toBe(0)
  })
})

// ─── useH7TransferEngine 边界测试 ───────────────────────────────────────────

describe('useH7TransferEngine - 边界场景', () => {
  it('生产→消耗：转出=转入', () => {
    const r = calcProdToConsumable(5000)
    expect(r.transferOut).toBe(5000)
    expect(r.transferIn).toBe(5000)
  })

  it('生产→公益：转出=转入', () => {
    const r = calcProdToPublic(3000)
    expect(r.transferOut).toBe(3000)
    expect(r.transferIn).toBe(3000)
  })

  it('互转差额：相等为0', () => {
    expect(calcTransferDiff(5000, 5000)).toBe(0)
  })

  it('互转差额：不等时正确计算', () => {
    expect(calcTransferDiff(5000, 4800)).toBe(200)
  })

  it('互转差额：零值', () => {
    expect(calcTransferDiff(0, 0)).toBe(0)
  })
})
