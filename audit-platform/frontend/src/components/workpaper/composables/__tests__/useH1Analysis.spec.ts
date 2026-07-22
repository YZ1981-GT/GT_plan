/**
 * useH1Analysis / H1 公式 — 比率与年限计算单测
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  calcAvgUsefulLife,
  calcRemainingLife,
  calcRatioPct,
  calcRatioMultiple,
  calcNewRate,
  calcChangeRate,
} from '../useH1FormulaEngine'
import { useH1Analysis } from '../useH1Analysis'
import type { ChecklistItem } from '../useH1FormData'

function makeResponses(entries: Record<string, unknown>): Map<string, ChecklistItem> {
  const map = new Map<string, ChecklistItem>()
  for (const [k, v] of Object.entries(entries)) {
    map.set(k, {
      item_id: k,
      conclusion: null,
      remark: typeof v === 'string' ? v : JSON.stringify(v),
    })
  }
  return map
}

describe('H1-6 analysis formula helpers', () => {
  it('calcRatioPct returns percent and guards zero denom', () => {
    expect(calcRatioPct(25, 100)).toBeCloseTo(25)
    expect(calcRatioPct(10, 0)).toBeNull()
  })

  it('calcRatioMultiple returns multiple and guards zero denom', () => {
    expect(calcRatioMultiple(1000, 50)).toBeCloseTo(20)
    expect(calcRatioMultiple(100, 0)).toBeNull()
  })

  it('calcAvgUsefulLife / calcRemainingLife', () => {
    expect(calcAvgUsefulLife(1000, 100)).toBeCloseTo(10)
    expect(calcRemainingLife(400, 100)).toBeCloseTo(4)
    expect(calcAvgUsefulLife(1000, 0)).toBeNull()
    expect(calcRemainingLife(400, 0)).toBeNull()
  })

  it('newRate and changeRate align with analysis thresholds', () => {
    expect(calcNewRate(150, 1000)).toBeCloseTo(15) // <20% 成新率偏低
    expect(calcChangeRate(160, 100)).toBeCloseTo(60) // >50% 高变动
    expect(calcChangeRate(100, 0)).toBeNull()
  })
})

describe('H1-6 折旧合理性整体重算 (depreciationRecalc)', () => {
  const wpId = ref('wp-1')
  const projectId = ref('p-1')

  it('derives composite rate from prior-period depreciation and flags within threshold', () => {
    const allResponses = ref(makeResponses({
      'H1-2-rows': [
        { originalCostBegin: 1_000_000, originalCostEnd: 1_000_000, accDepProvision: 95_000 },
      ],
      'H1-6-ratio-inputs': { periodDepPrior: 100_000 },
    }))
    const { depreciationRecalc } = useH1Analysis(wpId, projectId, allResponses as any)
    const r = depreciationRecalc.value
    expect(r.avgCost).toBeCloseTo(1_000_000)
    expect(r.compositeRate).toBeCloseTo(10) // 100000/1000000
    expect(r.expectedDep).toBeCloseTo(100_000)
    expect(r.bookedDep).toBeCloseTo(95_000)
    expect(r.diff).toBeCloseTo(-5_000)
    expect(r.diffRate).toBeCloseTo(-5)
    expect(r.flagged).toBe(false) // |−5%| < 10%
    expect(r.hasBasis).toBe(true)
  })

  it('flags when booked depreciation deviates beyond threshold', () => {
    const allResponses = ref(makeResponses({
      'H1-2-rows': [
        { originalCostBegin: 1_000_000, originalCostEnd: 1_000_000, accDepProvision: 80_000 },
      ],
      'H1-6-ratio-inputs': { periodDepPrior: 100_000 },
    }))
    const { depreciationRecalc } = useH1Analysis(wpId, projectId, allResponses as any)
    const r = depreciationRecalc.value
    expect(r.diffRate).toBeCloseTo(-20)
    expect(r.flagged).toBe(true) // |−20%| > 10%
  })

  it('manual composite-rate override takes precedence over prior-period derivation', () => {
    const allResponses = ref(makeResponses({
      'H1-2-rows': [
        { originalCostBegin: 1_000_000, originalCostEnd: 1_000_000, accDepProvision: 80_000 },
      ],
      'H1-6-ratio-inputs': { periodDepPrior: 100_000 },
    }))
    const { depreciationRecalc, setDepRecalcRate } = useH1Analysis(wpId, projectId, allResponses as any)
    setDepRecalcRate(8) // 独立测算综合率 8%
    const r = depreciationRecalc.value
    expect(r.compositeRateSource).toContain('手工')
    expect(r.compositeRate).toBeCloseTo(8)
    expect(r.expectedDep).toBeCloseTo(80_000)
    expect(r.diff).toBeCloseTo(0)
    expect(r.flagged).toBe(false)
  })

  it('marks no basis when prior depreciation absent and no override', () => {
    const allResponses = ref(makeResponses({
      'H1-2-rows': [
        { originalCostBegin: 1_000_000, originalCostEnd: 1_000_000, accDepProvision: 80_000 },
      ],
    }))
    const { depreciationRecalc } = useH1Analysis(wpId, projectId, allResponses as any)
    const r = depreciationRecalc.value
    expect(r.hasBasis).toBe(false)
    expect(r.expectedDep).toBeNull()
    expect(r.diffRate).toBeNull()
    expect(r.flagged).toBe(false)
  })
})

describe('H1-6 折旧税会差异 → 递延所得税 (deferredTaxRecalc)', () => {
  const wpId = ref('wp-1')
  const projectId = ref('p-1')

  it('deductible temporary difference → deferred tax asset (N1)', () => {
    // 账面价值 = 1,000,000 − 400,000 − 100,000(减值) = 500,000
    // 计税基础 = 1,000,000 − 300,000(税法累计) = 700,000（税法不认减值+账面多提折旧）
    // 暂时性差异 = 500,000 − 700,000 = −200,000 → 可抵扣 → DTA = 200,000 × 25% = 50,000
    const allResponses = ref(makeResponses({
      'H1-2-rows': [
        { originalCostEnd: 1_000_000, accDepEnd: 400_000, impairmentEnd: 100_000, accDepProvision: 90_000 },
      ],
      'H1-6-tax-diff': { taxAccumDep: 300_000, taxPeriodDep: 80_000, taxRate: 25 },
    }))
    const { deferredTaxRecalc } = useH1Analysis(wpId, projectId, allResponses as any)
    const r = deferredTaxRecalc.value
    expect(r.bookCarrying).toBeCloseTo(500_000)
    expect(r.taxBase).toBeCloseTo(700_000)
    expect(r.temporaryDiff).toBeCloseTo(-200_000)
    expect(r.nature).toBe('deductible')
    expect(r.deductibleTD).toBeCloseTo(200_000)
    expect(r.deferredTaxAsset).toBeCloseTo(50_000)
    expect(r.deferredTaxLiability).toBe(0)
    expect(r.periodDepDiff).toBeCloseTo(10_000) // 90k账面 − 80k税法
  })

  it('taxable temporary difference → deferred tax liability (N3)', () => {
    // 账面价值 = 1,000,000 − 200,000 = 800,000；计税基础 = 1,000,000 − 500,000 = 500,000
    // 暂时性差异 = +300,000 → 应纳税 → DTL = 300,000 × 25% = 75,000（税法加速折旧）
    const allResponses = ref(makeResponses({
      'H1-2-rows': [
        { originalCostEnd: 1_000_000, accDepEnd: 200_000, impairmentEnd: 0 },
      ],
      'H1-6-tax-diff': { taxAccumDep: 500_000 },
    }))
    const { deferredTaxRecalc } = useH1Analysis(wpId, projectId, allResponses as any)
    const r = deferredTaxRecalc.value
    expect(r.temporaryDiff).toBeCloseTo(300_000)
    expect(r.nature).toBe('taxable')
    expect(r.deferredTaxLiability).toBeCloseTo(75_000) // 默认税率25%
    expect(r.deferredTaxAsset).toBe(0)
  })

  it('no tax base → hasBasis false, no deferred tax', () => {
    const allResponses = ref(makeResponses({
      'H1-2-rows': [{ originalCostEnd: 1_000_000, accDepEnd: 200_000 }],
    }))
    const { deferredTaxRecalc } = useH1Analysis(wpId, projectId, allResponses as any)
    const r = deferredTaxRecalc.value
    expect(r.hasBasis).toBe(false)
    expect(r.taxBase).toBeNull()
    expect(r.temporaryDiff).toBeNull()
    expect(r.nature).toBe('none')
    expect(r.deferredTaxAsset).toBe(0)
    expect(r.deferredTaxLiability).toBe(0)
  })
})
