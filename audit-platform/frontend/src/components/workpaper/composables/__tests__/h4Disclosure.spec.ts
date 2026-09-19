/**
 * H4 附注披露：上市分类表 / 国企汇总表 公式与取数
 */
import { describe, expect, it } from 'vitest'
import {
  buildH4ListedMaterialsDisplay,
  createDefaultH4ListedMaterials,
  h4ListedMaterialsGross,
  h4ListedMaterialsNet,
  mapCategoryToH4ListedKey,
  seedH4ListedMaterialsFromDetail,
} from '../h4ListedDisclosureModel'
import {
  buildH4SoeSummaryDisplay,
  createDefaultH4SoeSummary,
  h4SoeSummaryTotal,
  seedH4SoeMaterialsFromAdjudication,
  soeCarrying,
} from '../h4SoeDisclosureModel'
import { summarizeH41Sections } from '../useH4Disclosure'

describe('h4ListedDisclosureModel', () => {
  it('分类映射：专用材料/设备/工器具', () => {
    expect(mapCategoryToH4ListedKey('专用材料')).toBe('specialMaterial')
    expect(mapCategoryToH4ListedKey('设备')).toBe('specialEquipment')
    expect(mapCategoryToH4ListedKey('专用设备')).toBe('specialEquipment')
    expect(mapCategoryToH4ListedKey('工器具')).toBe('tools')
    expect(mapCategoryToH4ListedKey('其他')).toBe('specialMaterial')
  })

  it('小计与合计：合计 = 三项原值 − 减值', () => {
    const rows = createDefaultH4ListedMaterials()
    rows[0].endBalance = 100
    rows[1].endBalance = 50
    rows[2].endBalance = 30
    rows[3].endBalance = 20
    expect(h4ListedMaterialsGross(rows).endBalance).toBe(180)
    expect(h4ListedMaterialsNet(rows).endBalance).toBe(160)
  })

  it('展示行含空白小计、减值括号行、合计', () => {
    const rows = createDefaultH4ListedMaterials()
    rows[0].endBalance = 10
    rows[0].priorBalance = 8
    rows[3].endBalance = 2
    rows[3].priorBalance = 1
    const display = buildH4ListedMaterialsDisplay(rows)
    expect(display.map((r) => r.key)).toEqual([
      'specialMaterial',
      'specialEquipment',
      'tools',
      '__gross__',
      'impairment',
      '__total__',
    ])
    expect(display.find((r) => r.key === '__gross__')!.endBalance).toBe(10)
    expect(display.find((r) => r.key === '__total__')!.endBalance).toBe(8)
    expect(display.find((r) => r.key === 'impairment')!.isDeduction).toBe(true)
  })

  it('从明细分类种子并优先 H4-7 减值', () => {
    const seeded = seedH4ListedMaterialsFromDetail(
      [
        { category: '专用材料', beginAmount: 40, endAmount: 60, auditedEnd: 55 },
        { category: '设备', beginAmount: 10, endAmount: 20 },
        { category: '工器具', beginAmount: 5, endAmount: 8, impairEnd: 3 },
      ],
      { impairmentEnd: 12, impairmentPrior: 4 },
    )
    expect(seeded.find((r) => r.key === 'specialMaterial')!.endBalance).toBe(55)
    expect(seeded.find((r) => r.key === 'specialEquipment')!.endBalance).toBe(20)
    expect(seeded.find((r) => r.key === 'tools')!.priorBalance).toBe(5)
    expect(seeded.find((r) => r.key === 'impairment')!.endBalance).toBe(12)
    expect(seeded.find((r) => r.key === 'impairment')!.priorBalance).toBe(4)
  })
})

describe('h4SoeDisclosureModel', () => {
  it('账面价值 = 账面余额 − 减值；合计自动汇总', () => {
    expect(soeCarrying(100, 15)).toBe(85)
    const rows = createDefaultH4SoeSummary()
    rows[0].endBook = 200
    rows[0].endImpairment = 20
    rows[1].endBook = 80
    rows[1].endImpairment = 5
    rows[1].beginBook = 70
    rows[1].beginImpairment = 3
    const tot = h4SoeSummaryTotal(rows)
    expect(tot.endBook).toBe(280)
    expect(tot.endImpairment).toBe(25)
    expect(tot.endCarrying).toBe(255)
    expect(tot.beginCarrying).toBe(67)
  })

  it('展示含合计行且账面价值自动计算', () => {
    const rows = createDefaultH4SoeSummary()
    rows[1].endBook = 100
    rows[1].endImpairment = 10
    const display = buildH4SoeSummaryDisplay(rows)
    expect(display).toHaveLength(3)
    expect(display[1].endCarrying).toBe(90)
    expect(display[2].label).toContain('合')
    expect(display[2].editable).toBe(false)
  })

  it('工程物资行自审定分段种子', () => {
    const mat = seedH4SoeMaterialsFromAdjudication({
      endBook: 120,
      endImpairment: 15,
      beginBook: 100,
      beginImpairment: 10,
    })
    expect(mat.key).toBe('materials')
    expect(soeCarrying(mat.endBook, mat.endImpairment)).toBe(105)
  })
})

describe('summarizeH41Sections', () => {
  it('从 H4-1-rows 原值/减值段汇总', () => {
    const map = new Map<string, any>()
    map.set('H4-1-rows', {
      remark: JSON.stringify([
        { section: 'original', beginBalance: 100, endBalance: 150, audited: 148 },
        { section: 'impairment', beginBalance: 10, endBalance: 12, audited: 12 },
        { section: 'net', isTotal: true, audited: 136 },
      ]),
    })
    map.set('H4-1-adjudicated-total', { remark: '136' })
    const s = summarizeH41Sections(map)
    expect(s.originalEnd).toBe(148)
    expect(s.impairEnd).toBe(12)
    expect(s.originalBegin).toBe(100)
    expect(s.netAudited).toBe(136)
  })

  it('无明细行时净值汇总键加回减值还原账面余额', () => {
    const map = new Map<string, any>()
    map.set('H4-1-adjudicated-total', { remark: '90' })
    map.set('H4-1-begin-total', { remark: '80' })
    map.set('H4-7-provision-balance', { remark: '10' })
    const s = summarizeH41Sections(map)
    expect(s.impairEnd).toBe(10)
    expect(s.originalEnd).toBe(100)
    expect(s.originalBegin).toBe(80)
    expect(s.netAudited).toBe(90)
  })
})
