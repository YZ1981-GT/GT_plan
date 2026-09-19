/**
 * useA38Goodwill — 公式引擎单元测试
 * Spec: .kiro/specs/a3-8-goodwill-impairment/ Task 8
 */
import { describe, it, expect } from 'vitest'
import {
  calcTotal, calcDiff, calcImpairment, calcWacc, calcKe,
  discountFactor, calcDcfPv, calcTerminalPv, calcFairValueNet,
  calcRecoverableAmount, allocateImpairment,
  type A38ImpairmentRow, type A38RecoverableData, type A38AllocationRow,
} from '../useA38Goodwill'

const row = (a: number | null, b1: number | null, b2: number | null, rec: number | null): A38ImpairmentRow =>
  ({ id: 'r', name: '', carrying_a: a, goodwill_b1: b1, minority_b2: b2, recoverable: rec, reason: '', remark: '' })

describe('useA38Goodwill — 减值主表公式', () => {
  it('合计 = A+B1+B2', () => {
    expect(calcTotal(row(100, 20, 5, null))).toBe(125)
  })
  it('null 视为 0', () => {
    expect(calcTotal(row(100, null, null, null))).toBe(100)
  })
  it('差额 = 合计 - 可收回', () => {
    expect(calcDiff(row(100, 20, 0, 90))).toBe(30)
  })
  it('减值准备 = max(差额,0)；差额≤0→0', () => {
    expect(calcImpairment(row(100, 0, 0, 90))).toBe(10)
    expect(calcImpairment(row(100, 0, 0, 120))).toBe(0)
  })
})

describe('useA38Goodwill — WACC/CAPM', () => {
  it('Ke = Rf + β(Rm-Rf)', () => {
    expect(calcKe({ tax_rate: null, debt_d: null, equity_e: null, cost_debt_kd: null, rf: 0.03, beta: 1.2, rm: 0.08 }))
      .toBeCloseTo(0.03 + 1.2 * 0.05, 6)
  })
  it('WACC 税后加权', () => {
    const w: A38RecoverableData['wacc'] = { tax_rate: 0.25, debt_d: 400, equity_e: 600, cost_debt_kd: 0.05, rf: 0.03, beta: 1, rm: 0.08 }
    const ke = 0.03 + 1 * 0.05 // 0.08
    const expected = (600 / 1000) * ke + (400 / 1000) * 0.05 * 0.75
    expect(calcWacc(w)).toBeCloseTo(expected, 6)
  })
  it('D+E=0 → null', () => {
    expect(calcWacc({ tax_rate: 0.25, debt_d: 0, equity_e: 0, cost_debt_kd: 0.05, rf: 0.03, beta: 1, rm: 0.08 })).toBeNull()
  })
})

describe('useA38Goodwill — DCF', () => {
  it('折现系数 1/(1+r)^n', () => {
    expect(discountFactor(0.1, 1)).toBeCloseTo(1 / 1.1, 6)
    expect(discountFactor(0.1, 2)).toBeCloseTo(1 / 1.21, 6)
  })
  it('预测期现值合计', () => {
    const dcf = { cash_flows: [110, 121], base_cash_flow: null, perpetual_growth: null, discount_rate: 0.1 }
    // 110/1.1 + 121/1.21 = 100 + 100 = 200
    expect(calcDcfPv(dcf)).toBeCloseTo(200, 6)
  })
  it('终值 r<=g → null', () => {
    expect(calcTerminalPv({ cash_flows: [100], base_cash_flow: 100, perpetual_growth: 0.1, discount_rate: 0.05 })).toBeNull()
  })
  it('终值 = base(1+g)/(r-g) 折现到末年', () => {
    const dcf = { cash_flows: [100], base_cash_flow: 100, perpetual_growth: 0.02, discount_rate: 0.1 }
    const terminal = (100 * 1.02) / (0.1 - 0.02)
    expect(calcTerminalPv(dcf)).toBeCloseTo(terminal / 1.1, 6)
  })
})

describe('useA38Goodwill — 可收回金额孰高', () => {
  it('取公允价值净额与 DCF 现值孰高', () => {
    const rec: A38RecoverableData = {
      fair_value_rows: [{ id: 'fv-1', name: '', fair_value: 300, disposal_cost: 50 }], // net=250
      dcf: { cash_flows: [220], base_cash_flow: null, perpetual_growth: null, discount_rate: 0.1 }, // pv=200
      wacc: { tax_rate: null, debt_d: null, equity_e: null, cost_debt_kd: null, rf: null, beta: null, rm: null },
    }
    expect(calcFairValueNet(rec.fair_value_rows)).toBe(250)
    const r = calcRecoverableAmount(rec)
    expect(r.value).toBeCloseTo(250, 4)
    expect(r.path).toBe('fair_value')
  })
})

describe('useA38Goodwill — 减值损失分摊', () => {
  const rows: A38AllocationRow[] = [
    { id: 'al-0', asset_type: '流动资产', carrying: 100, minority: null, recoverable: null },
    { id: 'al-1', asset_type: '固定资产', carrying: 300, minority: null, recoverable: null },
    { id: 'al-2', asset_type: '商誉', carrying: 50, minority: null, recoverable: null },
  ]
  it('先全额冲商誉，剩余按其他资产账面比例分摊', () => {
    const result = allocateImpairment(rows, 130)
    const gw = result.find((x) => x.id === 'al-2')!
    expect(gw.alloc_first).toBe(50) // 全冲商誉
    // 剩余 80 按 100:300 分摊 → 20 : 60
    expect(result.find((x) => x.id === 'al-0')!.alloc_second).toBeCloseTo(20, 4)
    expect(result.find((x) => x.id === 'al-1')!.alloc_second).toBeCloseTo(60, 4)
  })
  it('总和守恒', () => {
    const result = allocateImpairment(rows, 130)
    const sum = result.reduce((s, x) => s + x.alloc_first + x.alloc_second, 0)
    expect(sum).toBeCloseTo(130, 4)
  })
})
