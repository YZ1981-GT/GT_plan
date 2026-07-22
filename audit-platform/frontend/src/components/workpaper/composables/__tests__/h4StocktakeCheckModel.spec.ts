/**
 * H4-6 盘点检查表 — 模型单测（双向抽盘 + 三数量 + 旧行兼容）
 */
import { describe, it, expect } from 'vitest'
import {
  applyQtySideEffects,
  calcDirectionCoverage,
  calcRowDiffs,
  calcStocktakeStats,
  collectStocktakeImpairmentConcerns,
  createEmptyCheckRow,
  draftCheckSheetConclusion,
  mapH42RowsToCheckRows,
  normalizeCheckRow,
  normalizeDirection,
  sumH42EndAmount,
} from '../h4StocktakeCheckModel'

describe('h4StocktakeCheckModel', () => {
  it('normalizes legacy H4-6 rows (bookAmt/countQty)', () => {
    const row = normalizeCheckRow({
      name: '钢筋',
      spec: 'HRB400',
      bookQty: 100,
      bookAmt: 50000,
      countQty: 98,
      countAmt: 49000,
      location: '一号库',
      remark: '旧数据',
    }, 0)
    expect(row.name).toBe('钢筋')
    expect(row.bookAmount).toBe(50000)
    expect(row.sampleQty).toBe(98)
    expect(row.clientCountQty).toBe(98)
    expect(row.direction).toBe('bookToFloor')
    expect(row.result).toBe('盘亏')
  })

  it('normalizeDirection accepts Chinese completeness labels', () => {
    expect(normalizeDirection('实物→账面')).toBe('floorToBook')
    expect(normalizeDirection('完整性')).toBe('floorToBook')
    expect(normalizeDirection('')).toBe('bookToFloor')
  })

  it('calcRowDiffs and applyQtySideEffects', () => {
    const row = createEmptyCheckRow('bookToFloor', 1, '水泥')
    row.bookQty = 10
    row.sampleQty = 10
    row.clientCountQty = 10
    row.bookAmount = 2000
    row.unitPrice = 200
    applyQtySideEffects(row)
    expect(row.result).toBe('账实相符')
    expect(calcRowDiffs(row).hasVariance).toBe(false)

    row.sampleQty = 8
    applyQtySideEffects(row)
    expect(row.result).toBe('盘亏')
    expect(row.diffAmount).toBe(-400)
  })

  it('calcDirectionCoverage avoids div-by-zero', () => {
    const rows = [createEmptyCheckRow('bookToFloor', 1, 'A')]
    rows[0].bookAmount = 100
    const cov = calcDirectionCoverage(rows as any, null)
    expect(cov.ratioPct).toBeNull()
    const cov2 = calcDirectionCoverage(rows as any, 1000)
    expect(cov2.ratioPct).toBe(10)
  })

  it('mapH42RowsToCheckRows prefers large amounts', () => {
    const mapped = mapH42RowsToCheckRows([
      { name: '小件', endAmount: 100, quantity: 1 },
      { name: '大件', category: '设备', endAmount: 9000, quantity: 2, unit: '台' },
    ], { maxRows: 1, direction: 'bookToFloor' })
    expect(mapped).toHaveLength(1)
    expect(mapped[0].name).toContain('大件')
    expect(mapped[0].direction).toBe('bookToFloor')
    expect(mapped[0].bookQty).toBe(2)
  })

  it('collectStocktakeImpairmentConcerns picks idle/damage/deficit', () => {
    const idle = createEmptyCheckRow('bookToFloor', 1, '闲置管材')
    idle.qualityStatus = '闲置'
    idle.bookAmount = 1000
    const ok = createEmptyCheckRow('bookToFloor', 2, '正常')
    ok.qualityStatus = '正常'
    ok.result = '账实相符'
    const deficit = createEmptyCheckRow('bookToFloor', 3, '盘亏件')
    deficit.result = '盘亏'
    deficit.bookAmount = 500
    const concerns = collectStocktakeImpairmentConcerns([idle, ok, deficit])
    expect(concerns).toHaveLength(2)
    expect(concerns.map((c) => c.name).sort()).toEqual(['闲置管材', '盘亏件'].sort())
  })

  it('calcStocktakeStats and draft conclusion', () => {
    const a = createEmptyCheckRow('bookToFloor', 1, 'A')
    a.bookQty = 1
    a.sampleQty = 1
    a.clientCountQty = 1
    a.result = '账实相符'
    const b = createEmptyCheckRow('floorToBook', 1, 'B')
    b.bookQty = 1
    b.sampleQty = 0
    b.clientCountQty = 1
    applyQtySideEffects(b)
    const stats = calcStocktakeStats([a, b])
    expect(stats.bookToFloorCount).toBe(1)
    expect(stats.floorToBookCount).toBe(1)
    expect(stats.deficitCount).toBe(1)

    const text = draftCheckSheetConclusion({
      stats,
      bookToFloorCoverage: { sampleAmount: 100, totalBookCost: 1000, ratioPct: 10, rowCount: 1, varianceCount: 0 },
      floorToBookCoverage: { sampleAmount: 50, totalBookCost: 1000, ratioPct: 5, rowCount: 1, varianceCount: 1 },
      meta: {
        testPopulation: '',
        specificSample: '',
        samplingPopulation: '',
        samplingMethod: '随机选样',
        samplingProcess: '',
        location: '工地',
        clientStaff: '',
        auditors: '',
        countTime: '2026-03-01',
        totalBookCost: 1000,
      },
    })
    expect(text).toContain('工地')
    expect(text).toContain('10.00%')
  })

  it('sumH42EndAmount', () => {
    expect(sumH42EndAmount([
      { endAmount: 100 },
      { bookAmt: 50 },
    ])).toBe(150)
  })
})
