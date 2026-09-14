/**
 * H4-6A/B 监盘计划与小结 — 模型单测
 */
import { describe, it, expect } from 'vitest'
import {
  createEmptyPlanForm,
  draftPlanConclusion,
  draftSummaryFromCheck,
  normalizePlanForm,
  planGateBlockers,
  suggestedCoverage,
} from '../h4StocktakePlanModel'

describe('h4StocktakePlanModel', () => {
  it('suggestedCoverage by risk', () => {
    expect(suggestedCoverage('高')).toBe(50)
    expect(suggestedCoverage('中')).toBe(30)
    expect(suggestedCoverage('低')).toBe(15)
  })

  it('planGateBlockers lists missing fields', () => {
    const form = createEmptyPlanForm()
    expect(planGateBlockers(form).length).toBeGreaterThan(0)
    form.existenceRiskLevel = '中'
    form.stocktakeDate = '2026-03-01'
    form.scope = '期末工程物资'
    form.method = '抽盘'
    form.bidirectionalNote = '双向'
    expect(planGateBlockers(form)).toEqual([])
  })

  it('normalizePlanForm and draftPlanConclusion', () => {
    const form = normalizePlanForm({
      existenceRiskLevel: '高',
      stocktakeDate: '2026-03-01',
      method: '抽盘',
      scope: '仓库A',
      plannedCoveragePct: 40,
    })
    expect(form.existenceRiskLevel).toBe('高')
    const text = draftPlanConclusion(form)
    expect(text).toContain('高')
    expect(text).toContain('40%')
    expect(text).toContain('H4-6')
  })

  it('draftSummaryFromCheck fills dashboard fields', () => {
    const s = draftSummaryFromCheck({
      location: '一号库',
      countTime: '2026-03-01',
      clientStaff: '仓管张三',
      auditors: '审计李四',
      total: 10,
      matchCount: 8,
      surplusCount: 1,
      deficitCount: 1,
      varianceCount: 2,
      concernCount: 1,
      matchRate: 80,
      coveragePct: 25.5,
      auditNote: '有差异',
      auditConclusion: '',
    })
    expect(s.staffAndTime).toContain('一号库')
    expect(s.walkthroughNote).toContain('10')
    expect(s.overallReconcile).toContain('25.50%')
    expect(s.abnormalNote).toBe('有差异')
    expect(s.lastAutoSyncAt).toBeTruthy()
  })
})
