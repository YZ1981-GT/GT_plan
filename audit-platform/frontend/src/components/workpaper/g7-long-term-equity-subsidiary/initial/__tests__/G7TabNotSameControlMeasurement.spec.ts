/**
 * G7TabNotSameControlMeasurement (G7-9) 单元测试
 *
 * 公式层已迁移至 g7NotSameControlModel；本文件保留商誉显示与名称唯一性逻辑校验。
 */
import { describe, it, expect } from 'vitest'
import { calcGoodwill, calcNotSameControlCost } from '../../../composables/useG7SubFormulaEngine'
import { describeGoodwill, recalcNotSameControlMergerRow, createNotSameControlMergerRow } from '../g7NotSameControlModel'

describe('G7-9 兼容公式引擎', () => {
  it('calcNotSameControlCost 默认可只传对价（费用=0）', () => {
    expect(calcNotSameControlCost(10000)).toBe(10000)
    expect(calcNotSameControlCost(10000, 0)).toBe(10000)
    expect(calcNotSameControlCost(10000, 500)).toBe(10000)
  })

  it('calcGoodwill 正负符号', () => {
    expect(calcGoodwill(15000, 10000)).toBe(5000)
    expect(calcGoodwill(8000, 12000)).toBe(-4000)
  })
})

describe('G7-9 商誉显示逻辑', () => {
  function getGoodwillDisplay(goodwill: number): { label: string } | null {
    if (goodwill > 0.005) return { label: '商誉' }
    if (goodwill < -0.005) return { label: '廉价购买利得' }
    return null
  }

  it('成本>份额 → 商誉', () => {
    const g = calcGoodwill(15000, 10000)
    expect(getGoodwillDisplay(g)!.label).toBe('商誉')
    expect(describeGoodwill(g)).toContain('商誉')
  })

  it('成本<份额 → 廉价购买利得', () => {
    const g = calcGoodwill(8000, 12000)
    expect(getGoodwillDisplay(g)!.label).toBe('廉价购买利得')
  })

  it('新模型：费用不进入初始成本', () => {
    const row = createNotSameControlMergerRow(1, 'X')
    row.cashConsideration = 100
    row.acquisitionCostsExpensed = 20
    row.acquireeIdentifiableNetAssetsFV = 100
    row.ownershipRatio = 1
    recalcNotSameControlMergerRow(row)
    expect(row.initialInvestmentCost).toBe(100)
    expect(row.goodwill).toBe(0)
  })
})

describe('G7-9 名称唯一性', () => {
  function validateInvesteeName(rows: { investeeName: string }[], name: string | null | undefined): true | string {
    if (!name?.trim()) return '名称不能为空'
    if (rows.some(r => r.investeeName === name.trim())) return '该被投资单位已存在'
    return true
  }

  it('空/重复拒绝，新名称通过', () => {
    expect(validateInvesteeName([], '')).toBe('名称不能为空')
    expect(validateInvesteeName([{ investeeName: 'A' }], 'A')).toBe('该被投资单位已存在')
    expect(validateInvesteeName([{ investeeName: 'A' }], 'B')).toBe(true)
  })
})
