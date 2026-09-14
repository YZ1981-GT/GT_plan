import { describe, it, expect } from 'vitest'
import {
  normalizeI2ProjectDetailRow,
  recalcI2ProjectDetailRow,
  calcEndingBlock,
  calcAuditedBlock,
  hasTreatmentMismatch,
  summarizeI2ProjectDetail,
  serializeI2ProjectDetailRow,
  emptyCostBlock,
  emptyI2ProjectDetailRow,
  extractMaterialIncreaseTotal,
} from '../i2ProjectDetailModel'
import { extractI27MaterialTotal } from '../i2MaterialCheckModel'

describe('i2ProjectDetailModel', () => {
  it('期末 = 期初 + 增加 − 减少', () => {
    const ending = calcEndingBlock(
      emptyCostBlock({ material: 100, capitalized: 100 }),
      emptyCostBlock({ material: 50, capitalized: 50 }),
      emptyCostBlock({ material: 20, capitalized: 20 }),
    )
    expect(ending.material).toBe(130)
    expect(ending.capitalized).toBe(130)
  })

  it('审定 = 期末 + 调整', () => {
    const audited = calcAuditedBlock(
      emptyCostBlock({ material: 130, capitalized: 130 }),
      emptyCostBlock({ material: -10, capitalized: -10 }),
    )
    expect(audited.material).toBe(120)
    expect(audited.capitalized).toBe(120)
  })

  it('费用性质合计与资本化+费用化勾稽', () => {
    const ok = emptyCostBlock({
      material: 60, labor: 40, capitalized: 70, expensed: 30,
    })
    expect(hasTreatmentMismatch(ok)).toBe(false)

    const bad = emptyCostBlock({
      material: 60, labor: 40, capitalized: 50, expensed: 30,
    })
    expect(hasTreatmentMismatch(bad)).toBe(true)
  })

  it('兼容旧版扁平字段迁移到本期增加', () => {
    const row = normalizeI2ProjectDetailRow({
      projectName: '项目甲',
      materialDirect: 100,
      materialAux: 20,
      laborSalary: 80,
      depEquipment: 30,
      otherDesign: 10,
    })
    expect(row.increase.material).toBe(120)
    expect(row.increase.labor).toBe(80)
    expect(row.increase.depreciation).toBe(30)
    expect(row.increase.other).toBe(10)
    expect(row.increase.capitalized).toBe(240)
    expect(row.materialSubtotal).toBe(120)
  })

  it('serialize 保留 materialSubtotal 供 I2-8 取数', () => {
    const row = emptyI2ProjectDetailRow({
      projectName: 'P1',
      increase: emptyCostBlock({ material: 55, capitalized: 55 }),
    })
    recalcI2ProjectDetailRow(row)
    const ser = serializeI2ProjectDetailRow(row)
    expect(ser.materialSubtotal).toBe(55)
    expect(extractI27MaterialTotal([ser])).toBe(55)
    expect(extractMaterialIncreaseTotal([ser])).toBe(55)
  })

  it('汇总统计资本化/费用化与材料增加', () => {
    const rows = [
      emptyI2ProjectDetailRow({
        increase: emptyCostBlock({ material: 100, labor: 50, capitalized: 120, expensed: 30 }),
      }),
      emptyI2ProjectDetailRow({
        increase: emptyCostBlock({ material: 40, capitalized: 40 }),
      }),
    ]
    rows.forEach(recalcI2ProjectDetailRow)
    const s = summarizeI2ProjectDetail(rows)
    expect(s.materialIncreaseTotal).toBe(140)
    expect(s.increaseCapitalized).toBe(160)
    expect(s.increaseExpensed).toBe(30)
  })
})
