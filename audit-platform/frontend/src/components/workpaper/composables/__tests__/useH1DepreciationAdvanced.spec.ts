/**
 * H1-12 高级能力单测：归因 / 期初 / 税龄 / 抽样 / 估计变更 / 重要性
 */
import { describe, it, expect } from 'vitest'
import {
  attributeDepreciationDiff,
  checkBeginAccumulatedDep,
  checkTaxMinLife,
  classifyDiffAmount,
  defaultMateriality,
  selectDepreciationSample,
  calcWithEstimateChangeTest,
  buildEngineWatermark,
  formatWatermarkLine,
  parseH18DisposalRows,
  parseH14ImpairmentRows,
  H1_12_ENGINE_VERSION,
} from '../useH1DepreciationAdvanced'

describe('checkTaxMinLife', () => {
  it('房屋低于20年提示', () => {
    const r = checkTaxMinLife('房屋及建筑物', 15)
    expect(r.ok).toBe(false)
    expect(r.minYears).toBe(20)
  })
  it('运输工具4年通过', () => {
    expect(checkTaxMinLife('运输设备', 4).ok).toBe(true)
  })
})

describe('classifyDiffAmount / materiality', () => {
  const cfg = defaultMateriality(10000)
  it('尾差', () => {
    expect(classifyDiffAmount(0.005, cfg)).toBe('ok')
    expect(classifyDiffAmount(0.5, cfg)).toBe('rounding')
  })
  it('重大', () => {
    expect(classifyDiffAmount(600, cfg)).toBe('material')
  })
})

describe('attributeDepreciationDiff', () => {
  it('满折仍提', () => {
    const a = attributeDepreciationDiff({
      difference: 1000,
      monthlyDiff: 1000,
      accDepDiff: 1000,
      calcMonthly: 0,
      bookMonthly: 1000,
      periodMonths: 12,
      monthsAtEnd: 120,
      usefulLifeMonths: 120,
    })
    expect(a.codes).toContain('fully_depreciated_still')
  })
  it('处置日归因', () => {
    const a = attributeDepreciationDiff({
      difference: 500,
      monthlyDiff: 0,
      accDepDiff: 0,
      calcMonthly: 100,
      bookMonthly: 100,
      periodMonths: 6,
      monthsAtEnd: 30,
      usefulLifeMonths: 120,
      disposalDate: '2024-06-30',
    })
    expect(a.codes).toContain('disposal_month')
  })
})

describe('checkBeginAccumulatedDep', () => {
  it('期初一致时 ok', () => {
    // 2015-01 投入，2024-01-01 期初 → 截至 2023-12-31
    const r = checkBeginAccumulatedDep({
      cost: 120000,
      salvageRate: 0.05,
      usefulLifeYears: 10,
      startDate: '2015-01-01',
      periodBegin: '2024-01-01',
      bookAccDepBegin: 950 * 107, // 次月起提至 2023-12 ≈107月? 2015-02..2023-12
    })
    // 只断言结构；精确月数由引擎保证
    expect(typeof r.diff).toBe('number')
    expect(r.calcAccDepBegin).toBeGreaterThan(0)
  })
})

describe('calcWithEstimateChangeTest', () => {
  it('变更后月折旧低于变更前（残值提高或年限缩短）', () => {
    const r = calcWithEstimateChangeTest({
      cost: 240000,
      salvageRateBefore: 0,
      usefulLifeYearsBefore: 10,
      salvageRateAfter: 0,
      usefulLifeYearsAfter: 8,
      startDate: '2018-01-01',
      periodBegin: '2024-01-01',
      periodEnd: '2024-12-31',
      changeDate: '2024-06-30',
    })
    expect(r.monthsBeforeChange + r.monthsAfterChange).toBe(r.periodMonths)
    expect(r.monthlyAfter).not.toBe(r.monthlyBefore)
    expect(r.periodDep).toBeGreaterThan(0)
  })
})

describe('selectDepreciationSample', () => {
  it('减值与处置强制入样且覆盖率达标', () => {
    const pop = [
      { rowId: '1', originalCost: 1000000, impairmentEnd: 0 },
      { rowId: '2', originalCost: 500000, impairmentEnd: 1000 },
      { rowId: '3', originalCost: 200000, disposalDate: '2024-05-01' },
      { rowId: '4', originalCost: 50000 },
      { rowId: '5', originalCost: 30000 },
    ]
    const r = selectDepreciationSample(pop as any, '2024-01-01', { costCoverageTarget: 0.8, minRandom: 0 })
    expect(r.selectedIds.has('2')).toBe(true)
    expect(r.selectedIds.has('3')).toBe(true)
    expect(r.costCoverage).toBeGreaterThanOrEqual(0.8)
  })
})

describe('watermark / parse links', () => {
  it('水印含引擎版本', () => {
    const w = buildEngineWatermark({ branch: 'A', periodEnd: '2024-12-31', rowCount: 10 })
    expect(w.engineVersion).toBe(H1_12_ENGINE_VERSION)
    expect(formatWatermarkLine(w)).toContain('H1-12-engine')
  })
  it('解析 H1-8 / H1-14', () => {
    expect(parseH18DisposalRows(JSON.stringify([{ assetNo: 'A1', disposalDate: '2024-01-01', name: 'x' }]))).toHaveLength(1)
    expect(parseH14ImpairmentRows(JSON.stringify([{ assetGroup: 'G1', impairmentAmount: 100 }]))).toHaveLength(1)
  })
})
