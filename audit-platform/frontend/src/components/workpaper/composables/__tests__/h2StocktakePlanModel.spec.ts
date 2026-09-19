/**
 * H2-12 监盘计划 — 模型与增强单测
 */
import { describe, expect, it } from 'vitest'
import {
  calcCategoryScopeTotals,
  calcPlanLogicWarnings,
  createEmptyPlanForm,
  isPlannedRecountRatioValid,
  normalizePlanForm,
  recalcCategoryScopeRow,
  toLegacyPlan,
} from '../h2StocktakePlanModel'
import {
  aggregateH22ToCategoryScopes,
  applyRiskSuggestions,
  draftMajorProjectsFromH22,
  draftPlanConclusion,
  getPlanGateBlockers,
  isPlanReadyForCheck,
  suggestCoverageByRisk,
} from '../h2StocktakePlanEnhance'

describe('h2StocktakePlanModel', () => {
  it('recalcCategoryScopeRow computes net and coverage', () => {
    const row = recalcCategoryScopeRow({
      rowId: '1',
      seq: 1,
      category: '自营工程',
      endingBalance: 1000,
      impairment: 100,
      netBookValue: 0,
      unit: '项',
      quantity: 2,
      planQty: 1,
      planAmount: 450,
      coverageRate: 0,
    })
    expect(row.netBookValue).toBe(900)
    expect(row.coverageRate).toBe(50)
  })

  it('normalizePlanForm upgrades legacy five-field plan', () => {
    const form = normalizePlanForm({
      inspectionDate: '2025-12-31',
      location: '厂区A',
      participants: '张三',
      scope: '重大工程',
      schedule: '上午踏勘',
      selectedProjects: [{ rowId: 'a', name: '一期车间', reason: '金额重大', plannedContent: '进度' }],
    })
    expect(form.plannedDate).toBe('2025-12-31')
    expect(form.locationScopeNote).toBe('厂区A')
    expect(form.plannedLead).toBe('张三')
    expect(form.selectedProjects).toHaveLength(1)
    expect(form.selectedProjects[0].name).toBe('一期车间')
  })

  it('toLegacyPlan maps for H2-13 compatibility', () => {
    const form = createEmptyPlanForm()
    form.plannedDate = '2026-01-15'
    form.plannedLead = '李四'
    form.locationScopeNote = '工地B'
    form.selectedProjects = [{ rowId: 'x', name: '二期', reason: '随机选取', plannedContent: '' }]
    form.categoryScopes = [
      recalcCategoryScopeRow({
        rowId: 'c1',
        seq: 1,
        category: '出包工程',
        endingBalance: 200,
        impairment: 0,
        netBookValue: 200,
        unit: '项',
        quantity: 1,
        planQty: 1,
        planAmount: 100,
        coverageRate: 0,
      }),
    ]
    const legacy = toLegacyPlan(form)
    expect(legacy.inspectionDate).toBe('2026-01-15')
    expect(legacy.location).toBe('工地B')
    expect(legacy.participants).toContain('李四')
    expect(legacy.selectedProjects).toHaveLength(1)
    expect(legacy.scope).toContain('覆盖率')
  })

  it('rejects abnormal recount ratio', () => {
    expect(isPlannedRecountRatioValid(23500)).toBe(false)
    expect(isPlannedRecountRatioValid(10)).toBe(true)
    expect(isPlannedRecountRatioValid(null)).toBe(true)
  })
})

describe('h2StocktakePlanEnhance', () => {
  it('aggregates H2-2 by category', () => {
    const rows = aggregateH22ToCategoryScopes([
      { name: 'A', category: '自营工程', cipEnd: 100, impairmentEnd: 0, netValue: 100 },
      { name: 'B', category: '自营工程', cipEnd: 50, impairmentEnd: 0, netValue: 50 },
      { name: 'C', category: '出包工程', cipEnd: 80, impairmentEnd: 10, netValue: 70 },
    ])
    expect(rows).toHaveLength(2)
    const zy = rows.find((r) => r.category === '自营工程')!
    expect(zy.endingBalance).toBe(150)
    expect(zy.quantity).toBe(2)
  })

  it('drafts major projects sorted by net', () => {
    const majors = draftMajorProjectsFromH22([
      { name: '小', cipEnd: 10, netValue: 10 },
      { name: '大', cipEnd: 90, netValue: 90 },
    ])
    expect(majors[0].name).toBe('大')
    expect(majors[0].netBookValue).toBe(90)
  })

  it('risk suggestion and gate', () => {
    const sug = suggestCoverageByRisk('高')
    expect(sug.minCoverageRate).toBe(70)

    const form = createEmptyPlanForm()
    form.existenceRiskLevel = '高'
    form.plannedDate = '2026-01-01'
    form.plannedLead = '王五'
    form.selectedProjects = [{ rowId: '1', name: '工程X', reason: '金额重大', plannedContent: '' }]
    form.categoryScopes = [
      recalcCategoryScopeRow({
        rowId: 'c',
        seq: 1,
        category: '自营工程',
        endingBalance: 1000,
        impairment: 0,
        netBookValue: 1000,
        unit: '项',
        quantity: 10,
        planQty: 4,
        planAmount: 700,
        coverageRate: 0,
      }),
    ]
    form.plannedRecountRatio = 20
    expect(calcCategoryScopeTotals(form.categoryScopes).coverageRate).toBe(70)
    expect(getPlanGateBlockers(form)).toHaveLength(0)
    expect(isPlanReadyForCheck(form)).toBe(true)

    const applied = applyRiskSuggestions(createEmptyPlanForm())
    expect(applied.existenceRiskLevel).toBe('')
  })

  it('draftPlanConclusion mentions CIP and H2-13', () => {
    const form = createEmptyPlanForm()
    form.existenceRiskLevel = '中'
    form.plannedDate = '2026-02-01'
    form.plannedLead = '赵六'
    const text = draftPlanConclusion(form)
    expect(text).toContain('在建工程')
    expect(text).toContain('H2-13')
  })

  it('logic warnings when empty', () => {
    const warnings = calcPlanLogicWarnings(createEmptyPlanForm())
    expect(warnings.length).toBeGreaterThan(3)
  })
})
