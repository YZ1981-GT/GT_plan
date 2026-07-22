/**
 * H1-9 监盘计划增强 — 单测
 */
import { describe, expect, it } from 'vitest'
import { createEmptyPlanForm } from '../h1StocktakePlanModel'
import {
  aggregateH12ToCategoryScopes,
  applyRiskSuggestions,
  calcPlanVsCheckWarnings,
  draftIdleNoteFromH4,
  draftPlanConclusion,
  extractPriorYearPlanHints,
  getPlanGateBlockers,
  isCoverageAdequateForRisk,
  isPlanReadyForCheck,
  suggestCoverageByRisk,
} from '../h1StocktakePlanEnhance'

describe('h1StocktakePlanEnhance', () => {
  it('aggregateH12ToCategoryScopes groups by category', () => {
    const rows = aggregateH12ToCategoryScopes([
      { category: '机器设备', originalCostEnd: 100, impairmentEnd: 10, netValue: 70, quantity: 2 },
      { category: '机器设备', originalCostEnd: 50, impairmentEnd: 0, netValue: 40, quantity: 1 },
      { category: '运输设备', originalCostEnd: 80, impairmentEnd: 0, netValue: 60, quantity: 3 },
    ])
    expect(rows).toHaveLength(2)
    const m = rows.find((r) => r.category === '机器设备')!
    expect(m.endingBalance).toBe(150)
    expect(m.impairment).toBe(10)
    expect(m.netBookValue).toBe(110)
    expect(m.quantity).toBe(3)
  })

  it('draftIdleNoteFromH4 summarizes', () => {
    const note = draftIdleNoteFromH4([
      { name: '旧车床', netValue: 1000, originalCost: 5000, idleReason: '产能过剩' },
    ])
    expect(note).toContain('1 项')
    expect(note).toContain('旧车床')
  })

  it('suggestCoverageByRisk scales with risk', () => {
    expect(suggestCoverageByRisk('高').minCoverageRate).toBe(70)
    expect(suggestCoverageByRisk('中').minCoverageRate).toBe(50)
    expect(suggestCoverageByRisk('低').minCoverageRate).toBe(30)
  })

  it('applyRiskSuggestions fills plan amounts', () => {
    const f = createEmptyPlanForm()
    f.existenceRiskLevel = '高'
    f.categoryScopes = [{
      rowId: '1', seq: 1, category: '机器设备', endingBalance: 1000, impairment: 0,
      netBookValue: 1000, unit: '台', quantity: 10, planQty: 0, planAmount: 0, coverageRate: 0,
    }]
    const next = applyRiskSuggestions(f)
    expect(next.categoryScopes[0].planAmount).toBe(700)
    expect(next.plannedRecountRatio).toBe(20)
    expect(next.sampleBookToFloorQty).toBeGreaterThan(0)
  })

  it('getPlanGateBlockers and isPlanReadyForCheck', () => {
    const f = createEmptyPlanForm()
    expect(isPlanReadyForCheck(f)).toBe(false)
    expect(getPlanGateBlockers(f).length).toBeGreaterThan(0)
    f.existenceRiskLevel = '低'
    f.plannedDate = '2025-12-31'
    f.plannedLead = '张三'
    f.categoryScopes[0].netBookValue = 100
    f.categoryScopes[0].planAmount = 40
    f.categoryScopes[0].planQty = 1
    f.plannedRecountRatio = 5
    // recalc coverage
    f.categoryScopes[0].coverageRate = 40
    expect(isCoverageAdequateForRisk(f)).toBe(true)
    expect(getPlanGateBlockers(f).length).toBe(0)
  })

  it('calcPlanVsCheckWarnings flags shortfall', () => {
    const f = createEmptyPlanForm()
    f.sampleBookToFloorQty = 10
    f.sampleFloorToBookQty = 5
    const w = calcPlanVsCheckWarnings(f, { bookToFloorCount: 3, floorToBookCount: 1, checkedAmount: 0 })
    expect(w.some((x) => x.includes('账面→实物'))).toBe(true)
    expect(w.some((x) => x.includes('实物→账面'))).toBe(true)
  })

  it('draftPlanConclusion mentions risk and method', () => {
    const f = createEmptyPlanForm()
    f.existenceRiskLevel = '中'
    f.method = '抽样盘点'
    f.plannedDate = '2025-12-30'
    const c = draftPlanConclusion(f)
    expect(c).toContain('中')
    expect(c).toContain('抽样盘点')
    expect(c).toContain('H1-10')
  })

  it('extractPriorYearPlanHints', () => {
    const h = extractPriorYearPlanHints({
      plannedDate: '2024-12-28',
      plannedLead: '李四',
      plannedRecountRatio: 8,
      planConclusion: '上年结论',
    })
    expect(h.priorYearDate).toBe('2024-12-28')
    expect(h.priorYearStaff).toBe('李四')
    expect(h.priorYearSampleRate).toBe('8%')
    expect(h.priorYearIssues).toBe('上年结论')
  })
})
