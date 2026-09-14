/**
 * H1-11 监盘小结 — 模型与统计逻辑单测
 */
import { describe, expect, it } from 'vitest'
import {
  calcRecountRates,
  createEmptySummaryForm,
  draftLocationsFromCheckRows,
  draftRecountFromCheckRows,
  isTimeRangeValid,
  normalizeSummaryForm,
} from '../h1StocktakeSummaryModel'

describe('h1StocktakeSummaryModel', () => {
  it('createEmptySummaryForm has fixed section scaffolding', () => {
    const f = createEmptySummaryForm()
    expect(f.mgmtItems).toHaveLength(7)
    expect(f.precheckItems).toHaveLength(4)
    expect(f.categoryNotes).toHaveLength(4)
    expect(f.groups).toHaveLength(3)
    expect(f.recountIndex).toBe('H1-10')
  })

  it('normalizeSummaryForm merges legacy conclusion and fills missing defs', () => {
    const f = normalizeSummaryForm(
      { conclusion: '', mgmtItems: [{ id: 'dept', answer: '设备部' }], locations: [{ assetName: '厂房' }] },
      '旧结论',
    )
    expect(f.conclusion).toBe('旧结论')
    expect(f.mgmtItems.find((m) => m.id === 'dept')?.answer).toBe('设备部')
    expect(f.mgmtItems).toHaveLength(7)
    expect(f.locations[0].assetName).toBe('厂房')
    expect(f.locations[0].rowId).toBeTruthy()
  })

  it('calcRecountRates computes coverage and accuracy', () => {
    const f = createEmptySummaryForm()
    f.recountTotalUnits = 100
    f.recountSampleUnits = 20
    f.recountCorrectUnits = 19
    f.recountTotalAmount = 1000
    f.recountSampleAmount = 200
    f.recountCorrectAmount = 200
    const r = calcRecountRates(f)
    expect(r.unitCoverage).toBe(20)
    expect(r.unitAccuracy).toBe(95)
    expect(r.amountCoverage).toBe(20)
    expect(r.amountAccuracy).toBe(100)
  })

  it('isTimeRangeValid', () => {
    expect(isTimeRangeValid('09:00', '17:00')).toBe(true)
    expect(isTimeRangeValid('17:00', '09:00')).toBe(false)
    expect(isTimeRangeValid('', '09:00')).toBe(true)
  })

  it('draftRecountFromCheckRows aggregates H1-10', () => {
    const d = draftRecountFromCheckRows([
      { result: '账实相符', bookNetValue: 100, bookCost: 200 },
      { result: '盘亏', bookNetValue: 50, bookCost: 80 },
      { result: '账实相符', bookNetValue: 30, bookCost: 40 },
    ])
    expect(d.recountTotalUnits).toBe(3)
    expect(d.recountCorrectUnits).toBe(2)
    expect(d.recountCorrectAmount).toBe(130)
  })

  it('draftLocationsFromCheckRows dedupes by location', () => {
    const locs = draftLocationsFromCheckRows([
      { name: 'A', location: '一楼' },
      { name: 'B', location: '一楼' },
      { name: 'C', location: '二楼' },
    ])
    expect(locs).toHaveLength(2)
    expect(locs.map((l) => l.storageLocation).sort()).toEqual(['一楼', '二楼'])
  })
})
