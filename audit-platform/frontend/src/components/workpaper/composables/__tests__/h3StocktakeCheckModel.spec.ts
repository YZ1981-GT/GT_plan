/**
 * H3-9 盘点检查表 — 模型单测（双向抽盘）
 */
import { describe, it, expect } from 'vitest'
import {
  applyQtySideEffects,
  calcDirectionCoverage,
  calcRowDiffs,
  calcStocktakeStats,
  createEmptyCheckRow,
  draftCheckSheetConclusion,
  mapH32RowsToCheckRows,
  normalizeCheckRow,
  normalizeDirection,
  sumH32BookAmount,
} from '../h3StocktakeCheckModel'

describe('h3StocktakeCheckModel', () => {
  it('normalizes legacy H3-9 rows and defaults direction to bookToFloor', () => {
    const row = normalizeCheckRow({
      assetName: '写字楼A',
      location: '浦东',
      titleCertNo: '沪(2024)不动产权第001号',
      area: 1200,
      purpose: '出租',
      tenant: '某公司',
      leaseStatus: '已出租',
      physicalStatus: '正常',
      bookValue: 5000000,
      conclusion: '相符',
    }, 0)
    expect(row.assetName).toBe('写字楼A')
    expect(row.bookAmount).toBe(5000000)
    expect(row.bookQty).toBe(1)
    expect(row.result).toBe('账实相符')
    expect(row.direction).toBe('bookToFloor')
    expect(row.titleCertNo).toBe('沪(2024)不动产权第001号')
  })

  it('normalizeDirection accepts Chinese completeness labels', () => {
    expect(normalizeDirection('实物→账面')).toBe('floorToBook')
    expect(normalizeDirection('完整性')).toBe('floorToBook')
    expect(normalizeDirection('')).toBe('bookToFloor')
  })

  it('calcRowDiffs and applyQtySideEffects', () => {
    const row = createEmptyCheckRow('bookToFloor', 1, '测试物业')
    row.bookQty = 1
    row.sampleQty = 1
    row.clientCountQty = 1
    row.bookAmount = 2000000
    row.unitPrice = 2000000
    applyQtySideEffects(row)
    expect(row.result).toBe('账实相符')
    expect(calcRowDiffs(row).hasVariance).toBe(false)

    row.sampleQty = 0
    applyQtySideEffects(row)
    expect(row.result).toBe('盘亏')
    expect(row.diffAmount).toBe(-2000000)
  })

  it('calcDirectionCoverage avoids div-by-zero', () => {
    const rows = [createEmptyCheckRow('bookToFloor', 1, 'A')]
    rows[0].bookAmount = 100
    const cov = calcDirectionCoverage(rows as any, null)
    expect(cov.ratioPct).toBeNull()
    const cov2 = calcDirectionCoverage(rows as any, 1000)
    expect(cov2.ratioPct).toBe(10)
  })

  it('mapH32RowsToCheckRows supports both directions', () => {
    const b2f = mapH32RowsToCheckRows([
      { assetName: '小', originalCostEnd: 100 },
      { assetName: '大', originalCostEnd: 9000 },
    ], { maxRows: 1, direction: 'bookToFloor' })
    expect(b2f).toHaveLength(1)
    expect(b2f[0].assetName).toBe('大')
    expect(b2f[0].direction).toBe('bookToFloor')

    const f2b = mapH32RowsToCheckRows(
      [{ assetName: '现场物业', originalCostEnd: 1000 }],
      { direction: 'floorToBook' },
    )
    expect(f2b[0].direction).toBe('floorToBook')
  })

  it('sumH32BookAmount aggregates cost and fair value', () => {
    expect(sumH32BookAmount([{ originalCostEnd: 100 }, { costEnd: 200 }], 'cost')).toBe(300)
    expect(sumH32BookAmount([{ fairValueEnd: 500 }], 'fair_value')).toBe(500)
  })

  it('calcStocktakeStats tracks bidirectional counts and vacancy', () => {
    const r1 = createEmptyCheckRow('bookToFloor', 1, 'A')
    r1.leaseStatus = '空置'
    r1.result = '账实相符'
    const r2 = createEmptyCheckRow('floorToBook', 1, 'B')
    r2.leaseStatus = '已出租'
    r2.sampleQty = 0
    r2.bookQty = 1
    applyQtySideEffects(r2)
    const stats = calcStocktakeStats([r1, r2])
    expect(stats.bookToFloorCount).toBe(1)
    expect(stats.floorToBookCount).toBe(1)
    expect(stats.vacantCount).toBe(1)
    expect(stats.vacantRate).toBe(50)
    expect(stats.deficitCount).toBe(1)
  })

  it('draftCheckSheetConclusion flags missing completeness test', () => {
    const onlyExist = [createEmptyCheckRow('bookToFloor', 1, 'A')]
    onlyExist[0].result = '账实相符'
    const text = draftCheckSheetConclusion({
      stats: calcStocktakeStats(onlyExist),
      bookToFloorCoverage: calcDirectionCoverage(onlyExist as any, 1000),
      floorToBookCoverage: calcDirectionCoverage([], 1000),
      meta: {
        testPopulation: '', specificSample: '', samplingPopulation: '',
        samplingMethod: '', samplingProcess: '', location: '园区',
        clientStaff: '', auditors: '', countTime: '2025-12-31', totalBookCost: 1000,
      },
    })
    expect(text).toContain('完整性')
  })
})
