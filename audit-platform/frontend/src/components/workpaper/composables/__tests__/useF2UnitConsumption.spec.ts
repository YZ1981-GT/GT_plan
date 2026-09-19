import { describe, expect, it } from 'vitest'
import { ref } from 'vue'
import {
  defaultUnitConsumptionSheet,
  enrichCostFlowRow,
  enrichCostStructureRow,
  enrichMaterialConsumptionRow,
  enrichUnitCostRow,
  migrateUnitConsumptionSheet,
} from '../useF2UnitConsumptionFormulas'
import { useF2UnitConsumption } from '../useF2UnitConsumption'
import type { ChecklistResponse } from '../useF2SpecialFormData'

describe('F2-64 公式层', () => {
  it('默认生成四区块各本年/上年12个月，不预留额外空行', () => {
    const sheet = defaultUnitConsumptionSheet()
    expect(sheet.costStructureRows).toHaveLength(24)
    expect(sheet.costFlowRows).toHaveLength(24)
    expect(sheet.unitCostRows).toHaveLength(24)
    expect(sheet.materialConsumptionRows).toHaveLength(24)
    expect(sheet.peerRows).toHaveLength(4)
  })

  it('成本构成小计与占比自动计算', () => {
    const base = defaultUnitConsumptionSheet().costStructureRows[0]
    const row = enrichCostStructureRow({
      ...base, material1: 50, material2: 10, material3: 10,
      otherMaterial: 5, directLabor: 15, manufacturing: 10,
    })
    expect(row.total).toBe(100)
    expect(row.rates.material1).toBeCloseTo(0.5)
    expect(row.rates.directLabor).toBeCloseTo(0.15)
  })

  it('成本衔接：生产成本=期初+投入-期末，单位成本=生产成本/产量', () => {
    const base = defaultUnitConsumptionSheet().costFlowRows[0]
    const row = enrichCostFlowRow({
      ...base, openingWip: 20, materialInput: 100, laborInput: 30,
      manufacturingInput: 10, endingWip: 40, outputQty: 20,
    })
    expect(row.productionCost).toBe(120)
    expect(row.unitCost).toBe(6)
  })

  it('产品单位成本按材料/人工/制造费用及产量自动计算', () => {
    const base = defaultUnitConsumptionSheet().unitCostRows[0]
    const row = enrichUnitCostRow({
      ...base, openingFinished: 10, directMaterial: 60, directLabor: 20,
      manufacturing: 10, endingFinished: 20, outputQty: 10,
    })
    expect(row.costTotal).toBe(80)
    expect(row.unitMaterial).toBe(6)
    expect(row.unitLabor).toBe(2)
    expect(row.unitCost).toBe(8)
  })

  it('材料耗用自动测算单位产量耗用和单位成本', () => {
    const base = defaultUnitConsumptionSheet().materialConsumptionRows[0]
    const row = enrichMaterialConsumptionRow({
      ...base,
      outputQty: 100,
      material1: { inputQty: 250, unit: 'kg', inputAmount: 500 },
    })
    expect(row.material1.unitOutput).toBe(2.5)
    expect(row.material1.unitCost).toBe(5)
  })

  it('旧扁平材料行迁入第4部分且保留产品名', () => {
    const migrated = migrateUnitConsumptionSheet([
      { productName: '产品A', materialName: '钢材', unit: 'kg', inputQty: 200, outputQty: 100, materialUnitPrice: 3 },
    ])
    expect(migrated.productName).toBe('产品A')
    expect(migrated.consumptionMaterialNames[0]).toBe('钢材')
    expect(migrated.materialConsumptionRows[0].material1.inputAmount).toBe(600)
  })
})

describe('F2-64 composable', () => {
  function setup(initial?: unknown) {
    const map = new Map<string, ChecklistResponse>()
    if (initial !== undefined) {
      map.set('F2-64-rows', { item_id: 'F2-64-rows', conclusion: null, remark: JSON.stringify(initial) })
    }
    const allResponses = ref(map)
    return { uc: useF2UnitConsumption({ allResponses, isReadonly: ref(false) }), allResponses }
  }

  it('旧数据自动迁移并写回对象结构', () => {
    const { uc, allResponses } = setup([
      { productName: '产品A', materialName: '钢材', inputQty: 100, outputQty: 50, materialUnitPrice: 2 },
    ])
    expect(uc.sheet.value.productName).toBe('产品A')
    expect(Array.isArray(JSON.parse(allResponses.value.get('F2-64-rows')!.remark!))).toBe(false)
  })

  it('月度输入后四个区块实时联动', () => {
    const { uc } = setup()
    const structure = uc.sheet.value.costStructureRows[0]
    uc.updateCostStructure(structure.id, { material1: 80, directLabor: 20 })
    expect(uc.costStructureRows.value[0].total).toBe(100)

    const flow = uc.sheet.value.costFlowRows[0]
    uc.updateCostFlow(flow.id, { materialInput: 100, outputQty: 20 })
    expect(uc.costFlowRows.value[0].unitCost).toBe(5)

    const material = uc.sheet.value.materialConsumptionRows[0]
    uc.updateMaterialConsumption(material.id, { outputQty: 10 })
    uc.updateMaterialCell(material.id, 'material1', { inputQty: 30, inputAmount: 60 })
    expect(uc.materialConsumptionRows.value[0].material1.unitOutput).toBe(3)
    expect(uc.materialConsumptionRows.value[0].material1.unitCost).toBe(6)
  })
})
