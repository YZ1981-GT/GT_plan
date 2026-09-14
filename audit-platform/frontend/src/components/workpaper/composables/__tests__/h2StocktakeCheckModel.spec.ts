/**
 * H2-13 盘点检查表 — 模型单测
 */
import { describe, it, expect } from 'vitest'
import {
  applyQtySideEffects,
  calcDirectionCoverage,
  calcRowDiffs,
  createEmptyCheckRow,
  deriveConstructionStatus,
  draftCheckSheetConclusion,
  isStoppedCheckRow,
  mapDetailRowsToCheckRows,
  normalizeCheckRow,
  sumDetailCipCost,
} from '../h2StocktakeCheckModel'

describe('h2StocktakeCheckModel', () => {
  it('normalizes legacy site-visit rows', () => {
    const row = normalizeCheckRow({
      name: '厂房扩建',
      siteLocation: 'A区',
      visibleProgress: 60,
      constructionStatus: '停工',
      progressDifference: '落后账面10%',
      photos: 'att-1',
    }, 0)
    expect(row.name).toBe('厂房扩建')
    expect(row.location).toBe('A区')
    expect(row.progressDesc).toContain('落后账面')
    expect(row.photoUrl).toBe('att-1')
    expect(isStoppedCheckRow(row)).toBe(true)
  })

  it('treats stopDuration/stopReason as stopped', () => {
    const row = normalizeCheckRow({
      name: '管廊',
      stopDuration: '8个月',
      stopReason: '资金链断裂',
    }, 0)
    expect(row.constructionStatus).toBe('停工')
    expect(isStoppedCheckRow(row)).toBe(true)
  })

  it('derives ready-for-use as 完工 when no stop', () => {
    expect(deriveConstructionStatus({
      constructionStatus: '',
      stopDuration: '',
      stopReason: '',
      readyForUse: '是',
    })).toBe('完工')
  })

  it('calcRowDiffs and applyQtySideEffects', () => {
    const row = createEmptyCheckRow('bookToFloor', 1, '测试')
    row.bookQty = 1
    row.sampleQty = 1
    row.clientCountQty = 1
    row.bookAmount = 1000
    row.unitPrice = 1000
    applyQtySideEffects(row)
    expect(row.result).toBe('账实相符')
    expect(calcRowDiffs(row).hasVariance).toBe(false)

    row.sampleQty = 0
    applyQtySideEffects(row)
    expect(row.result).toBe('盘亏')
    expect(row.diffAmount).toBe(-1000)
  })

  it('mapDetailRowsToCheckRows prefers large cipEnd', () => {
    const rows = mapDetailRowsToCheckRows([
      { name: '小', cipEnd: 100 },
      { name: '大', cipEnd: 9000 },
      { name: '中', cipEnd: 500 },
    ], { maxRows: 2 })
    expect(rows.map((r) => r.name)).toEqual(['大', '中'])
    expect(rows[0].bookAmount).toBe(9000)
    expect(rows[0].remark).toContain('H2-2')
  })

  it('coverage avoids divide by zero', () => {
    const rows = [createEmptyCheckRow('bookToFloor', 1, 'A')]
    rows[0].bookAmount = 100
    const cov = calcDirectionCoverage(rows, null)
    expect(cov.ratioPct).toBeNull()
    expect(sumDetailCipCost([{ cipEnd: 10 }, { endAudited: 20 }])).toBe(30)
  })

  it('draft conclusion mentions stop and ready-for-use', () => {
    const text = draftCheckSheetConclusion({
      total: 3,
      matchCount: 2,
      matchRate: 66.7,
      surplusCount: 0,
      deficitCount: 1,
      stoppedCount: 1,
      readyForUseCount: 1,
      bookToFloorCount: 2,
      floorToBookCount: 1,
      coveragePct: 12.5,
      location: '工地',
      countTime: '2025-12-31',
    })
    expect(text).toContain('停工')
    expect(text).toContain('可使用状态')
    expect(text).toContain('12.50%')
  })
})
