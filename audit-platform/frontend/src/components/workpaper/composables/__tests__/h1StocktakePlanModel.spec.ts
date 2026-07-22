/**
 * H1-9 监盘计划 — 模型与逻辑单测
 */
import { describe, expect, it } from 'vitest'
import {
  buildSamplingMethodNarrative,
  calcCategoryScopeTotals,
  calcPlanLogicWarnings,
  createEmptyPlanForm,
  draftSampleQtyFromScopes,
  isPlannedRecountRatioValid,
  normalizePlanForm,
  recalcCategoryScopeRow,
  toLegacyPlanInfo,
} from '../h1StocktakePlanModel'

describe('h1StocktakePlanModel', () => {
  it('createEmptyPlanForm scaffolds sections', () => {
    const f = createEmptyPlanForm()
    expect(f.categoryScopes.length).toBeGreaterThanOrEqual(3)
    expect(f.method).toBe('抽样盘点')
    expect(f.sampleBookToFloorMethod).toContain('明细')
    expect(f.plannedRecountRatio).toBeNull()
  })

  it('recalcCategoryScopeRow computes net and coverage', () => {
    const row = recalcCategoryScopeRow({
      rowId: '1',
      seq: 1,
      category: '机器设备',
      endingBalance: 1000,
      impairment: 100,
      netBookValue: 0,
      unit: '台',
      quantity: 10,
      planQty: 3,
      planAmount: 450,
      coverageRate: 0,
    })
    expect(row.netBookValue).toBe(900)
    expect(row.coverageRate).toBe(50)
  })

  it('calcCategoryScopeTotals aggregates', () => {
    const t = calcCategoryScopeTotals([
      recalcCategoryScopeRow({
        rowId: 'a', seq: 1, category: 'A', endingBalance: 100, impairment: 0,
        netBookValue: 0, unit: '', quantity: 2, planQty: 1, planAmount: 40, coverageRate: 0,
      }),
      recalcCategoryScopeRow({
        rowId: 'b', seq: 2, category: 'B', endingBalance: 200, impairment: 0,
        netBookValue: 0, unit: '', quantity: 4, planQty: 2, planAmount: 60, coverageRate: 0,
      }),
    ])
    expect(t.endingBalance).toBe(300)
    expect(t.planAmount).toBe(100)
    expect(t.coverageRate).toBeCloseTo(33.3, 0)
  })

  it('isPlannedRecountRatioValid rejects Excel-like 23500%', () => {
    expect(isPlannedRecountRatioValid(null)).toBe(true)
    expect(isPlannedRecountRatioValid(10)).toBe(true)
    expect(isPlannedRecountRatioValid(100)).toBe(true)
    expect(isPlannedRecountRatioValid(23500)).toBe(false)
    expect(isPlannedRecountRatioValid(-1)).toBe(false)
  })

  it('normalizePlanForm clears bad recount ratio and merges legacy', () => {
    const f = normalizePlanForm(
      { plannedRecountRatio: 23500, plannedDate: '' },
      { stocktakeDate: '2025-12-31', method: '全面盘点', participants: '张三' },
    )
    expect(f.plannedRecountRatio).toBeNull()
    expect(f.plannedDate).toBe('2025-12-31')
    expect(f.method).toBe('全面盘点')
    expect(f.plannedLead).toBe('张三')
  })

  it('buildSamplingMethodNarrative includes bidirectional sample', () => {
    const f = createEmptyPlanForm()
    f.method = '抽样盘点'
    f.sampleBookToFloorQty = 20
    f.sampleFloorToBookQty = 5
    f.plannedRecountRatio = 10
    const n = buildSamplingMethodNarrative(f)
    expect(n).toContain('H1-9')
    expect(n).toContain('20')
    expect(n).toContain('复盘比例 10%')
  })

  it('draftSampleQtyFromScopes', () => {
    const d = draftSampleQtyFromScopes([
      { rowId: '1', seq: 1, category: 'A', endingBalance: 0, impairment: 0, netBookValue: 0, unit: '', quantity: 0, planQty: 10, planAmount: 0, coverageRate: 0 },
    ])
    expect(d.sampleBookToFloorQty).toBe(10)
    expect(d.sampleFloorToBookQty).toBe(3)
  })

  it('calcPlanLogicWarnings flags missing risk and bad coverage', () => {
    const f = createEmptyPlanForm()
    const w = calcPlanLogicWarnings(f)
    expect(w.some((x) => x.includes('存在性'))).toBe(true)
    expect(w.some((x) => x.includes('胜任'))).toBe(true)
  })

  it('toLegacyPlanInfo maps for H1-10/11 sync', () => {
    const f = createEmptyPlanForm()
    f.plannedDate = '2025-12-30'
    f.plannedLead = '李四'
    f.locationScopeNote = '一号厂房'
    f.method = '抽样盘点'
    const legacy = toLegacyPlanInfo(f)
    expect(legacy.stocktakeDate).toBe('2025-12-30')
    expect(legacy.participants).toContain('李四')
    expect(legacy.location).toBe('一号厂房')
  })
})
