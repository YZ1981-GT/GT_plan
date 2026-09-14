/**
 * useF5QuantityRecon — F5-6 销售数量与结转成本数量核对 单元测试
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import {
  useF5QuantityRecon,
  migrateF5QuantityPlants,
  computeF5QtyProduct,
  computeF5QtyPlant,
  buildF5QtyGrandTotal,
  emptyF5QtyProduct,
  emptyF5QtyPlant,
  defaultF5QtyPlants,
} from '../useF5QuantityRecon'
import type { ChecklistResponse } from '../useF1FormData'

function mkResponses(seed?: Record<string, string>) {
  const map = ref(new Map<string, ChecklistResponse>())
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.value.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  return map
}

describe('compute / total / migrate', () => {
  it('产品：总计=Σ月；差异=销售−结转', () => {
    const prod = computeF5QtyProduct({
      ...emptyF5QtyProduct('A'),
      salesMonths: [1, 2, 3, 0, 0, 0, 0, 0, 0, 0, 0, 0],
      costMonths: [1, 1, 1, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    })
    expect(prod.sales.total).toBe(6)
    expect(prod.cost.total).toBe(3)
    expect(prod.diff.total).toBe(3)
    expect(prod.diff.months[1]).toBe(1)
  })

  it('分厂=Σ产品；总计=Σ分厂', () => {
    const plant = computeF5QtyPlant({
      id: 'p1',
      name: '分厂1',
      products: [
        { ...emptyF5QtyProduct('A'), salesMonths: [10, ...Array(11).fill(0)], costMonths: [8, ...Array(11).fill(0)] },
        { ...emptyF5QtyProduct('B'), salesMonths: [5, ...Array(11).fill(0)], costMonths: [5, ...Array(11).fill(0)] },
      ],
    })
    expect(plant.sales.months[0]).toBe(15)
    expect(plant.cost.months[0]).toBe(13)
    expect(plant.diff.months[0]).toBe(2)
    expect(plant.diff.total).toBe(2)

    const grand = buildF5QtyGrandTotal([plant, computeF5QtyPlant(emptyF5QtyPlant('分厂2', 1))])
    expect(grand.sales.months[0]).toBe(15)
  })

  it('扁平 sm/cm 与旧 salesQty 迁移', () => {
    const fromWide = migrateF5QuantityPlants(JSON.stringify([
      { plant: '分厂甲', product: 'P1', sm1: 10, cm1: 7 },
    ]))
    expect(fromWide[0].name).toBe('分厂甲')
    expect(fromWide[0].products[0].salesMonths[0]).toBe(10)
    expect(fromWide[0].products[0].costMonths[0]).toBe(7)

    const fromLegacy = migrateF5QuantityPlants(JSON.stringify([
      { product: '旧品', salesQty: 50, costQty: 40 },
    ]))
    expect(fromLegacy[0].products[0].salesMonths[11]).toBe(50)
    expect(fromLegacy[0].products[0].costMonths[11]).toBe(40)
  })
})

describe('useF5QuantityRecon', () => {
  beforeEach(() => { vi.useFakeTimers() })
  afterEach(() => { vi.useRealTimers() })

  it('默认2分厂×4产品；增删；更新月度后重算差异', () => {
    const allResponses = mkResponses()
    const recon = useF5QuantityRecon({ allResponses, isReadonly: ref(false) })
    expect(recon.plants.value).toHaveLength(defaultF5QtyPlants().length)
    expect(recon.plants.value[0].products).toHaveLength(4)

    recon.addPlant('新分厂')
    const plant = recon.plants.value.find((p) => p.name === '新分厂')!
    recon.addProduct(plant.id, '新品')
    const prod = plant.products.find((p) => p.name === '新品')
      ?? recon.plants.value.find((p) => p.id === plant.id)!.products.find((p) => p.name === '新品')!
    recon.updateMonth(plant.id, prod.id, 'sales', 0, 100)
    recon.updateMonth(plant.id, prod.id, 'cost', 0, 90)

    const updated = recon.plants.value.find((p) => p.id === plant.id)!
      .products.find((p) => p.id === prod.id)!
    expect(updated.diff.months[0]).toBe(10)
    expect(updated.diff.total).toBe(10)
    expect(recon.significantDiffs.value.some((d) => d.product === '新品')).toBe(true)
  })
})
