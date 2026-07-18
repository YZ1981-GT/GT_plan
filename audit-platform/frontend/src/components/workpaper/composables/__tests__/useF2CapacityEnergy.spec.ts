import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  ENERGY_ITEM_PRESETS,
  calcEnergyTotals,
  defaultCapacityEnergySheet,
  emptyCapacityRow,
  emptyStorageRow,
  enrichCapacityRow,
  enrichEnergyRow,
  enrichProductEnergyRow,
  groupStorageRows,
  isBlankCapacityRow,
  migrateCapacityEnergySheet,
  type CapacityEnergySheet,
} from '../useF2CapacityEnergyFormulas'
import { useF2CapacityEnergy } from '../useF2CapacityEnergy'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-63 公式层', () => {
  it('默认表：产能/库存/产品能耗各1空行，能源项目预置水电燃气蒸汽', () => {
    const sheet = defaultCapacityEnergySheet()
    expect(sheet.capacityRows).toHaveLength(1)
    expect(sheet.storageRows).toHaveLength(1)
    expect(sheet.productEnergyRows).toHaveLength(1)
    expect(sheet.energyRows.map((r) => r.itemName)).toEqual([...ENERGY_ITEM_PRESETS])
  })

  it('产能利用率 = 本年产量/全年产能，超100%标异常', () => {
    const ok = enrichCapacityRow({ ...emptyCapacityRow(), annualOutput: 80, annualCapacity: 100 })
    expect(ok.utilizationRate).toBeCloseTo(0.8)
    expect(ok.isAbnormal).toBe(false)

    const over = enrichCapacityRow({ ...emptyCapacityRow(), annualOutput: 120, annualCapacity: 100 })
    expect(over.isAbnormal).toBe(true)

    const zero = enrichCapacityRow({ ...emptyCapacityRow(), annualOutput: 120 })
    expect(zero.utilizationRate).toBeNull()
  })

  it('库存按仓库分组并小计，容量利用率=Σ库存/Σ容量', () => {
    const groups = groupStorageRows([
      { ...emptyStorageRow(), warehouseName: 'A仓', inventoryName: '甲', actualStock: 60, storageCapacity: 100, orderQty: 5 },
      { ...emptyStorageRow(), warehouseName: 'A仓', inventoryName: '乙', actualStock: 90, storageCapacity: 100, orderQty: 3 },
      { ...emptyStorageRow(), warehouseName: 'B仓', inventoryName: '丙', actualStock: 130, storageCapacity: 100 },
    ])
    expect(groups).toHaveLength(2)
    expect(groups[0].warehouseName).toBe('A仓')
    expect(groups[0].subtotal.actualStock).toBe(150)
    expect(groups[0].subtotal.utilizationRate).toBeCloseTo(0.75)
    expect(groups[0].subtotal.orderQty).toBe(8)
    expect(groups[1].rows[0].isAbnormal).toBe(true)
  })

  it('能源采购单价自动计算，本期较上期变动超±20%标异常', () => {
    const row = enrichEnergyRow({
      id: '1', itemName: '电',
      currentQty: 100, currentAmount: 130,
      priorQty: 100, priorAmount: 100,
    })
    expect(row.currentUnitPrice).toBeCloseTo(1.3)
    expect(row.priorUnitPrice).toBeCloseTo(1)
    expect(row.priceChangeRate).toBeCloseTo(0.3)
    expect(row.isAbnormal).toBe(true)

    expect(calcEnergyTotals([
      { id: '1', itemName: '水', currentQty: 0, currentAmount: 100, priorQty: 0, priorAmount: 80 },
      { id: '2', itemName: '电', currentQty: 0, currentAmount: 200, priorQty: 0, priorAmount: 150 },
    ])).toEqual({ currentAmount: 300, priorAmount: 230 })
  })

  it('产品单位能耗=(水+电+燃气)/产量，变动率超±20%标异常', () => {
    const row = enrichProductEnergyRow({
      id: '1', productName: '产品A', annualOutput: 100,
      waterUsage: 10, elecUsage: 60, gasUsage: 30,
      priorUnitEnergy: 0.7,
    })
    expect(row.totalEnergy).toBe(100)
    expect(row.unitEnergy).toBeCloseTo(1)
    expect(row.change).toBeCloseTo(0.3)
    expect(row.changeRate).toBeCloseTo(0.3 / 0.7)
    expect(row.isAbnormal).toBe(true)
  })

  it('迁移：旧扁平行拆入产能比较与产品能耗两区块', () => {
    const legacy = [
      {
        id: '1', productName: '产品A', productLine: '一线',
        designCapacity: 100, actualOutput: 90,
        elecTotal: 450, waterTotal: 50, gasTotal: 0,
        priorOutput: 80, priorElecTotal: 400,
        changeNote: '技改', auditFocus: '',
      },
    ]
    const sheet = migrateCapacityEnergySheet(legacy)
    expect(sheet.capacityRows).toHaveLength(1)
    expect(sheet.capacityRows[0].inventoryName).toBe('产品A / 一线')
    expect(sheet.capacityRows[0].annualOutput).toBe(90)
    expect(sheet.capacityRows[0].annualCapacity).toBe(100)
    expect(sheet.productEnergyRows[0].elecUsage).toBe(450)
    expect(sheet.productEnergyRows[0].priorUnitEnergy).toBeCloseTo(5)
    // 能源采购区回落为预置项目
    expect(sheet.energyRows.map((r) => r.itemName)).toEqual([...ENERGY_ITEM_PRESETS])
  })

  it('迁移：新结构裁剪空行且至少保留1行', () => {
    const sheet = migrateCapacityEnergySheet({
      capacityRows: [
        { id: '1', inventoryName: '甲', annualOutput: 10, annualCapacity: 20, remark: '' },
        { id: '2', inventoryName: '', annualOutput: 0, annualCapacity: 0, remark: '' },
      ],
      storageRows: [],
      energyRows: [],
      productEnergyRows: [],
    })
    expect(sheet.capacityRows).toHaveLength(1)
    expect(isBlankCapacityRow(sheet.capacityRows[0])).toBe(false)
    expect(sheet.storageRows).toHaveLength(1)
    expect(sheet.productEnergyRows).toHaveLength(1)
  })
})

describe('F2-63 composable', () => {
  function setup(initial?: unknown) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-63-rows', { item_id: 'F2-63-rows', conclusion: null, remark: JSON.stringify(initial) })
    }
    const allResponses = ref(map)
    const ce = useF2CapacityEnergy({ allResponses, isReadonly: ref(false) })
    return { ce, allResponses }
  }

  it('旧扁平数组自动升级为四区块结构并写回', () => {
    const { ce, allResponses } = setup([
      {
        id: '1', productName: '产品A', productLine: '',
        designCapacity: 100, actualOutput: 120,
        elecTotal: 100, waterTotal: 0, gasTotal: 0,
        priorOutput: 0, priorElecTotal: 0, changeNote: '', auditFocus: '',
      },
    ])
    expect(ce.capacityRows.value[0].isAbnormal).toBe(true)
    const saved = JSON.parse(allResponses.value.get('F2-63-rows')!.remark!) as CapacityEnergySheet
    expect(Array.isArray(saved)).toBe(false)
    expect(saved.capacityRows).toHaveLength(1)
  })

  it('新增空行不会被自回声裁剪吃掉', () => {
    const { ce } = setup()
    ce.addCapacityRow()
    expect(ce.sheet.value.capacityRows).toHaveLength(2)
    ce.addStorageRow('A仓')
    expect(ce.sheet.value.storageRows).toHaveLength(2)
    expect(ce.sheet.value.storageRows[1].warehouseName).toBe('A仓')
  })

  it('填写数据后利用率/小计/异常数实时联动', () => {
    const { ce } = setup()
    const capId = ce.sheet.value.capacityRows[0].id
    ce.updateCapacityRow(capId, { inventoryName: '甲', annualOutput: 150, annualCapacity: 100 })
    expect(ce.capacityRows.value[0].utilizationRate).toBeCloseTo(1.5)
    expect(ce.abnormalCount.value).toBe(1)

    const storId = ce.sheet.value.storageRows[0].id
    ce.updateStorageRow(storId, { warehouseName: 'A仓', actualStock: 50, storageCapacity: 200 })
    expect(ce.storageGroups.value[0].subtotal.utilizationRate).toBeCloseTo(0.25)

    const prodId = ce.sheet.value.productEnergyRows[0].id
    ce.updateProductEnergyRow(prodId, { productName: '甲', annualOutput: 10, elecUsage: 30 })
    expect(ce.productEnergyRows.value[0].unitEnergy).toBeCloseTo(3)
    expect(ce.filledCount.value).toBe(3)
  })
})
