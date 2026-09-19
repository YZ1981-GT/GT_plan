/**
 * i2AnalysisModel — I2-5 实质性分析公式/异常/结论 单测
 */
import { describe, it, expect } from 'vitest'
import {
  safeRatio,
  recomputeCompositionRow,
  emptyCompositionRow,
  recomputeAllComposition,
  compositionTotals,
  recomputePerCapitaYoY,
  emptyPerCapitaYoY,
  syncDerivedFromComposition,
  createDefaultBundle,
  createDefaultCompositionMeta,
  normalizeBundle,
  summarizeAnalysisAnomalies,
  buildAnalysisConclusionDraft,
  seedCompositionFromI6Detail,
  I2_ANALYSIS_GROWTH_THRESHOLD,
  I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
} from '../i2AnalysisModel'

describe('safeRatio / composition formulas', () => {
  it('safeRatio returns null when denominator is 0', () => {
    expect(safeRatio(100, 0)).toBeNull()
    expect(safeRatio(50, 200)).toBe(0.25)
  })

  it('recomputeCompositionRow computes structure, rev ratio, growth', () => {
    const row = recomputeCompositionRow(
      emptyCompositionRow({ itemName: '人工费', currentAmount: 120, priorAmount: 100 }),
      200, // total current
      200, // total prior
      1000, // revenue current
      800, // revenue prior
    )
    expect(row.currentStructure).toBeCloseTo(0.6)
    expect(row.priorStructure).toBeCloseTo(0.5)
    expect(row.currentRevRatio).toBeCloseTo(0.12)
    expect(row.priorRevRatio).toBeCloseTo(0.125)
    expect(row.growthRate).toBeCloseTo(0.2)
    expect(row.revRatioChange).toBeCloseTo(-0.005)
  })

  it('growthRate null when prior is 0 (no #DIV/0!)', () => {
    const row = recomputeCompositionRow(
      emptyCompositionRow({ currentAmount: 100, priorAmount: 0 }),
      100, 0, 500, 0,
    )
    expect(row.growthRate).toBeNull()
    expect(row.priorRevRatio).toBeNull()
  })

  it('compositionTotals and anomaly when growth > 30%', () => {
    const rows = recomputeAllComposition([
      emptyCompositionRow({ itemName: '人工费', currentAmount: 200, priorAmount: 100 }),
      emptyCompositionRow({ itemName: '材料费', currentAmount: 50, priorAmount: 50 }),
    ], { revenueCurrent: 1000, revenuePrior: 1000 })
    expect(rows[0].isAnomaly).toBe(true) // +100%
    expect(rows[1].isAnomaly).toBe(false)
    const t = compositionTotals(rows, { revenueCurrent: 1000, revenuePrior: 1000 })
    expect(t.totalCurrent).toBe(250)
    expect(t.rdToRevenueCurrent).toBeCloseTo(0.25)
  })
})

describe('per capita / sync / normalize', () => {
  it('recomputePerCapitaYoY', () => {
    const p = recomputePerCapitaYoY(emptyPerCapitaYoY({
      staffCostCurrent: 1000,
      headcountCurrent: 10,
      rdExpenseCurrent: 2000,
      materialCurrent: 400,
      staffCostPrior: 800,
      headcountPrior: 8,
      rdExpensePrior: 1600,
      materialPrior: 320,
    }))
    expect(p.avgSalaryCurrent).toBe(100)
    expect(p.avgRdCurrent).toBe(200)
    expect(p.avgMaterialCurrent).toBe(40)
    expect(p.avgSalaryGrowth).toBe(0) // 100 vs 100
  })

  it('syncDerivedFromComposition fills peer current and self peer row', () => {
    const b = createDefaultBundle()
    b.compositionRows = [
      emptyCompositionRow({ itemName: '人工费', currentAmount: 300, priorAmount: 200 }),
      emptyCompositionRow({ itemName: '材料费', currentAmount: 100, priorAmount: 100 }),
    ]
    b.compositionMeta = { revenueCurrent: 2000, revenuePrior: 2000 }
    b.perCapitaYoY.headcountCurrent = 10
    b.perCapitaYoY.headcountPrior = 10
    const synced = syncDerivedFromComposition(b)
    expect(synced.peerIndicators[0].current).toBeCloseTo(0.2) // 400/2000
    expect(synced.perCapitaYoY.avgSalaryCurrent).toBe(30)
    const self = synced.perCapitaPeers.find((r) => r.isSelf)
    expect(self?.avgRdExpense).toBe(40)
  })

  it('normalizeBundle accepts legacy array', () => {
    const b = normalizeBundle([{ projectName: 'P1', beginAmount: 1 }])
    expect(b.compositionRows.length).toBeGreaterThan(0)
    expect(b.projectFluctuationRows?.[0].projectName).toBe('P1')
  })

  it('seedCompositionFromI6Detail aggregates by category', () => {
    const rows = seedCompositionFromI6Detail([
      { category: '人工费', auditedAmount: 100, priorAudited: 80 },
      { category: '人工费-社保', auditedAmount: 20, priorAudited: 10 },
      { category: '材料费', auditedAmount: 50, priorAudited: 40 },
    ])
    const labor = rows.find((r) => r.itemName === '人工费')
    expect(labor?.currentAmount).toBe(100) // first match on 人工费 exact-ish
    expect(rows.some((r) => r.itemName === '材料费' && r.currentAmount === 50)).toBe(true)
  })

  it('buildAnalysisConclusionDraft mentions totals', () => {
    const b = createDefaultBundle()
    b.compositionRows = [
      emptyCompositionRow({ itemName: '人工费', currentAmount: 100, priorAmount: 100 }),
    ]
    b.compositionMeta = { ...createDefaultCompositionMeta(), revenueCurrent: 1000, revenuePrior: 1000 }
    const synced = syncDerivedFromComposition(b)
    const draft = buildAnalysisConclusionDraft(synced)
    expect(draft).toContain('100')
    expect(draft).toContain('10.00%')
    const anom = summarizeAnalysisAnomalies(synced)
    expect(anom.missingRevenue).toBe(false)
  })
})

describe('configurable thresholds', () => {
  it('createDefaultCompositionMeta uses default thresholds', () => {
    const meta = createDefaultCompositionMeta()
    expect(meta.growthThreshold).toBe(I2_ANALYSIS_GROWTH_THRESHOLD)
    expect(meta.revRatioDeltaThreshold).toBe(I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD)
  })

  it('recomputeAllComposition respects custom growthThreshold from meta', () => {
    const meta = { ...createDefaultCompositionMeta(), revenueCurrent: 0, revenuePrior: 0, growthThreshold: 0.5 }
    // +40% growth: anomaly under default 30% threshold, but NOT under custom 50% threshold
    const rows = recomputeAllComposition([
      emptyCompositionRow({ itemName: '人工费', currentAmount: 140, priorAmount: 100 }),
    ], meta)
    expect(rows[0].isAnomaly).toBe(false)

    const strictMeta = { ...meta, growthThreshold: 0.3 }
    const strictRows = recomputeAllComposition([
      emptyCompositionRow({ itemName: '人工费', currentAmount: 140, priorAmount: 100 }),
    ], strictMeta)
    expect(strictRows[0].isAnomaly).toBe(true)
  })

  it('normalizeBundle falls back to default thresholds when missing', () => {
    const b = normalizeBundle({ compositionMeta: { revenueCurrent: 100, revenuePrior: 100 } })
    expect(b.compositionMeta.growthThreshold).toBe(I2_ANALYSIS_GROWTH_THRESHOLD)
    expect(b.compositionMeta.revRatioDeltaThreshold).toBe(I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD)
  })

  it('normalizeBundle preserves persisted custom thresholds', () => {
    const b = normalizeBundle({
      compositionMeta: { revenueCurrent: 100, revenuePrior: 100, growthThreshold: 0.5, revRatioDeltaThreshold: 0.05 },
    })
    expect(b.compositionMeta.growthThreshold).toBe(0.5)
    expect(b.compositionMeta.revRatioDeltaThreshold).toBe(0.05)
  })
})

describe('budget variance', () => {
  it('computes budgetVariance/budgetVarianceRate when budgetAmount > 0', () => {
    const row = recomputeCompositionRow(
      emptyCompositionRow({ itemName: '人工费', currentAmount: 130, priorAmount: 100, budgetAmount: 100 }),
      130, 100, 0, 0,
    )
    expect(row.budgetVariance).toBe(30)
    expect(row.budgetVarianceRate).toBeCloseTo(0.3)
  })

  it('budgetVariance is null when budgetAmount is 0 (not applicable)', () => {
    const row = recomputeCompositionRow(
      emptyCompositionRow({ itemName: '人工费', currentAmount: 130, priorAmount: 100, budgetAmount: 0 }),
      130, 100, 0, 0,
    )
    expect(row.budgetVariance).toBeNull()
    expect(row.budgetVarianceRate).toBeNull()
  })

  it('flags isAnomaly when |budgetVarianceRate| > growthThreshold and budget > 0', () => {
    const rows = recomputeAllComposition([
      // within growth threshold (0 growth vs prior) but budget variance rate 40% > 30% default → anomaly
      emptyCompositionRow({ itemName: '人工费', currentAmount: 140, priorAmount: 140, budgetAmount: 100 }),
    ], { ...createDefaultCompositionMeta(), revenueCurrent: 0, revenuePrior: 0 })
    expect(rows[0].isAnomaly).toBe(true)
  })

  it('does not flag budget anomaly when variance rate within threshold', () => {
    const rows = recomputeAllComposition([
      emptyCompositionRow({ itemName: '人工费', currentAmount: 110, priorAmount: 110, budgetAmount: 100 }),
    ], { ...createDefaultCompositionMeta(), revenueCurrent: 0, revenuePrior: 0 })
    expect(rows[0].isAnomaly).toBe(false)
  })

  it('compositionTotals sums budget and computes total variance', () => {
    const rows = recomputeAllComposition([
      emptyCompositionRow({ itemName: '人工费', currentAmount: 120, priorAmount: 100, budgetAmount: 100 }),
      emptyCompositionRow({ itemName: '材料费', currentAmount: 60, priorAmount: 50, budgetAmount: 50 }),
    ], createDefaultCompositionMeta())
    const t = compositionTotals(rows, createDefaultCompositionMeta())
    expect(t.totalBudget).toBe(150)
    expect(t.budgetVariance).toBe(30)
    expect(t.budgetVarianceRate).toBeCloseTo(0.2)
  })
})

describe('I6 category alias mapping', () => {
  it('seedCompositionFromI6Detail matches aliases (职工薪酬→人工费, 折旧→制造费用分摊, 摊销→无形资产摊销)', () => {
    const rows = seedCompositionFromI6Detail([
      { category: '职工薪酬', auditedAmount: 200, priorAudited: 150 },
      { category: '领料', auditedAmount: 80, priorAudited: 60 },
      { category: '折旧', auditedAmount: 30, priorAudited: 20 },
      { category: '无形资产摊销费用', auditedAmount: 15, priorAudited: 10 },
    ])
    const labor = rows.find((r) => r.itemName === '人工费')
    const material = rows.find((r) => r.itemName === '材料费')
    const mfg = rows.find((r) => r.itemName === '制造费用分摊')
    const amort = rows.find((r) => r.itemName === '无形资产摊销')
    expect(labor?.currentAmount).toBe(200)
    expect(material?.currentAmount).toBe(80)
    expect(mfg?.currentAmount).toBe(30)
    expect(amort?.currentAmount).toBe(15)
  })
})
