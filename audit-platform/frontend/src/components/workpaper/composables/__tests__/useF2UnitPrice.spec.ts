import { describe, expect, it, vi } from 'vitest'
import { nextTick, ref } from 'vue'
import {
  calcChangeRate,
  calcUnitPrice,
  defaultUnitPriceSheet,
  emptyMonthlyGroup,
  emptyMonthlyItem,
  emptySpecGroup,
  emptySpecItem,
  enrichMonthlyGroup,
  enrichSpecGroup,
  isBlankMonthlyGroup,
  isBlankSpecGroup,
  migrateUnitPriceSheet,
  pruneMonthlyGroups,
  pruneSpecGroups,
} from '../useF2UnitPriceFormulas'
import { useF2UnitPrice } from '../useF2UnitPrice'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-62 formulas', () => {
  it('默认每个分析层次仅保留一个可编辑组和一个项目', () => {
    const sheet = defaultUnitPriceSheet()
    expect(sheet.supplierGroups).toHaveLength(1)
    expect(sheet.materialGroups).toHaveLength(1)
    expect(sheet.specGroups).toHaveLength(1)
    expect(sheet.supplierGroups[0].items).toHaveLength(1)
    expect(isBlankMonthlyGroup(sheet.supplierGroups[0])).toBe(true)
    expect(isBlankSpecGroup(sheet.specGroups[0])).toBe(true)
  })

  it('采购单价=金额÷数量，数量为0时为空', () => {
    expect(calcUnitPrice(1200, 100)).toBe(12)
    expect(calcUnitPrice(1200, 0)).toBeNull()
  })

  it('变动率=(本期-上期)÷上期', () => {
    expect(calcChangeRate(120, 100)).toBeCloseTo(0.2, 6)
    expect(calcChangeRate(120, 0)).toBeNull()
  })

  it('月度组计算各项目平均价和组内偏离', () => {
    const group = emptyMonthlyGroup()
    group.name = '供应商A'
    const a = emptyMonthlyItem()
    a.name = '钢材'
    a.months[0] = { amount: 1000, qty: 100 } // 10
    const b = emptyMonthlyItem()
    b.name = '铜材'
    b.months[0] = { amount: 3000, qty: 100 } // 30
    group.items = [a, b]

    const enriched = enrichMonthlyGroup(group)
    expect(enriched.totalAmount).toBe(4000)
    expect(enriched.totalQty).toBe(200)
    expect(enriched.avgPrice).toBe(20)
    expect(enriched.items[0].groupDeviation).toBeCloseTo(-0.5, 6)
    expect(enriched.items[0].isAbnormal).toBe(true)
    expect(enriched.abnormalCount).toBe(2)
  })

  it('规格跨年度变动超过20%自动标识', () => {
    const group = emptySpecGroup()
    group.categoryName = '钢材'
    const item = emptySpecItem()
    item.spec = 'Q235'
    item.periods[0] = { label: '本期', amount: 1300, qty: 10 }
    item.periods[1] = { label: '上期', amount: 1000, qty: 10 }
    group.items = [item]
    const enriched = enrichSpecGroup(group)
    expect(enriched.items[0].periods[0].unitPrice).toBe(130)
    expect(enriched.items[0].latestChangeRate).toBeCloseTo(0.3, 6)
    expect(enriched.items[0].isAbnormal).toBe(true)
  })

  it('裁剪空组和空项目，但全部为空时保留一个输入壳', () => {
    const filledGroup = emptyMonthlyGroup()
    filledGroup.name = '供应商A'
    filledGroup.items = [
      emptyMonthlyItem(),
      { ...emptyMonthlyItem(), name: '钢材' },
    ]
    const monthly = pruneMonthlyGroups([emptyMonthlyGroup(), filledGroup])
    expect(monthly).toHaveLength(1)
    expect(monthly[0].items).toHaveLength(1)
    expect(monthly[0].items[0].name).toBe('钢材')

    const spec = pruneSpecGroups([emptySpecGroup(), emptySpecGroup()])
    expect(spec).toHaveLength(1)
    expect(spec[0].items).toHaveLength(1)
  })

  it('旧版 T/T-1/T-2 行迁入第三层规格跨年度分析', () => {
    const migrated = migrateUnitPriceSheet([{
      id: 'old-1',
      materialName: '铜材',
      spec: 'T2',
      qtyT: 10,
      qtyT1: 20,
      qtyT2: 25,
      priceT: 100,
      priceT1: 90,
      priceT2: 80,
    }])
    expect(migrated.specGroups[0].categoryName).toBe('铜材')
    expect(migrated.specGroups[0].items[0].spec).toBe('T2')
    expect(migrated.specGroups[0].items[0].periods[0]).toMatchObject({
      qty: 10,
      amount: 1000,
    })
  })
})

function responses(raw?: unknown) {
  const map = new Map<string, ChecklistResponse>()
  if (raw !== undefined) {
    map.set('F2-62-rows', {
      item_id: 'F2-62-rows',
      conclusion: null,
      remark: JSON.stringify(raw),
    })
  }
  return ref(map)
}

describe('useF2UnitPrice composable', () => {
  it('新增分析组不会被 persist/load 回环裁剪', async () => {
    vi.useFakeTimers()
    const allResponses = responses()
    const up = useF2UnitPrice({ allResponses })
    up.addMonthlyGroup('supplierGroups')
    await nextTick()
    expect(up.sheet.value.supplierGroups).toHaveLength(2)
    vi.runAllTimers()
    await nextTick()
    expect(up.sheet.value.supplierGroups).toHaveLength(2)
    vi.useRealTimers()
  })

  it('更新月度金额数量后单价实时联动', () => {
    const up = useF2UnitPrice({ allResponses: responses() })
    const group = up.sheet.value.supplierGroups[0]
    const item = group.items[0]
    up.updateMonth('supplierGroups', group.id, item.id, 0, { amount: 1500, qty: 100 })
    expect(up.supplierGroups.value[0].items[0].enrichedMonths[0].unitPrice).toBe(15)
  })
})
