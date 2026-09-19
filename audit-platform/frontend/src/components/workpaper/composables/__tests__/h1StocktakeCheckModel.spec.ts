/**
 * H1-10 盘点检查表 — 模型单测
 */
import { describe, expect, it } from 'vitest'
import {
  applyQtySideEffects,
  calcDirectionCoverage,
  calcRowDiffs,
  createEmptyCheckMeta,
  createEmptyCheckRow,
  deriveResultFromQty,
  draftCheckSheetConclusion,
  draftMetaFromPlan,
  mapDetailRowsToCheckRows,
  normalizeCheckMeta,
  normalizeCheckRow,
  sumDetailOriginalCost,
} from '../h1StocktakeCheckModel'

describe('h1StocktakeCheckModel', () => {
  it('normalizeCheckRow defaults direction to bookToFloor and maps bookCost', () => {
    const r = normalizeCheckRow({ name: '机床', bookCost: 10000, bookQty: 1 }, 0)
    expect(r.direction).toBe('bookToFloor')
    expect(r.bookAmount).toBe(10000)
    expect(r.bookCost).toBe(10000)
    expect(r.name).toBe('机床')
  })

  it('normalizeCheckRow keeps floorToBook', () => {
    const r = normalizeCheckRow({ direction: 'floorToBook', name: '叉车' }, 1)
    expect(r.direction).toBe('floorToBook')
    expect(r.seq).toBe(2)
  })

  it('deriveResultFromQty', () => {
    expect(deriveResultFromQty(1, 1)).toBe('账实相符')
    expect(deriveResultFromQty(2, 1)).toBe('盘盈')
    expect(deriveResultFromQty(0, 1)).toBe('盘亏')
  })

  it('calcRowDiffs flags variance', () => {
    const d = calcRowDiffs({ sampleQty: 2, bookQty: 1, clientCountQty: 1 })
    expect(d.sampleVsBook).toBe(1)
    expect(d.sampleVsClient).toBe(1)
    expect(d.clientVsBook).toBe(0)
    expect(d.hasVariance).toBe(true)
  })

  it('applyQtySideEffects syncs result and diffAmount', () => {
    const row = createEmptyCheckRow('bookToFloor', 1, '泵')
    row.bookQty = 2
    row.sampleQty = 1
    row.unitPrice = 5000
    applyQtySideEffects(row)
    expect(row.result).toBe('盘亏')
    expect(row.diffAmount).toBe(-5000)
    expect(row.quantityCheck).toBe('不一致')
  })

  it('calcDirectionCoverage avoids DIV/0 when total missing', () => {
    const rows = [
      createEmptyCheckRow('bookToFloor', 1),
      createEmptyCheckRow('bookToFloor', 2),
    ]
    rows[0].bookAmount = 100
    rows[1].bookAmount = 200
    const empty = calcDirectionCoverage(rows, null)
    expect(empty.ratioPct).toBeNull()
    expect(empty.sampleAmount).toBe(300)
    const ok = calcDirectionCoverage(rows, 1000)
    expect(ok.ratioPct).toBe(30)
  })

  it('draftMetaFromPlan fills blanks only', () => {
    const meta = createEmptyCheckMeta()
    meta.location = '已有地点'
    const drafted = draftMetaFromPlan(meta, {
      location: '计划地点',
      stocktakeDate: '2025-12-31',
      participants: '张三',
      method: '全面盘点',
      scope: '全部设备',
    })
    expect(drafted.location).toBe('已有地点')
    expect(drafted.countTime).toBe('2025-12-31')
    expect(drafted.auditors).toBe('张三')
    expect(drafted.samplingMethod).toBe('全面盘点')
    expect(drafted.testPopulation).toBe('全部设备')
  })

  it('normalizeCheckRow maps legacy import aliases', () => {
    const r = normalizeCheckRow({
      assetName: '旧名',
      assetCode: 'A-1',
      bookCost: 900,
      stocktakeResult: '盘亏',
      direction: '实物→账面',
      inspector: '李四',
    }, 0)
    expect(r.name).toBe('旧名')
    expect(r.assetNo).toBe('A-1')
    expect(r.bookAmount).toBe(900)
    expect(r.result).toBe('盘亏')
    expect(r.direction).toBe('floorToBook')
    expect(r.checker).toBe('李四')
  })

  it('mapDetailRowsToCheckRows prefers large amounts', () => {
    const rows = mapDetailRowsToCheckRows([
      { name: '小', originalCostEnd: 100 },
      { name: '大', originalCostEnd: 9000 },
    ], { maxRows: 10 })
    expect(rows[0].name).toBe('大')
    expect(rows[0].bookAmount).toBe(9000)
    expect(rows[0].direction).toBe('bookToFloor')
  })

  it('sumDetailOriginalCost and draftCheckSheetConclusion', () => {
    expect(sumDetailOriginalCost([{ originalCostEnd: 10 }, { costClosing: 20 }])).toBe(30)
    const text = draftCheckSheetConclusion({
      total: 2,
      matchCount: 2,
      matchRate: 100,
      surplusCount: 0,
      deficitCount: 0,
      surplusAmount: 0,
      deficitAmount: 0,
      bookToFloorCount: 1,
      floorToBookCount: 1,
      coveragePct: 12.5,
      location: '车间',
      countTime: '2025-12-31',
    })
    expect(text).toContain('相符率 100')
    expect(text).toContain('12.50%')
  })
})
