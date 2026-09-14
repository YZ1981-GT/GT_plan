import { describe, it, expect } from 'vitest'
import {
  defaultContractCostImpairmentSheet,
  enrichImpairmentProject,
  enrichImpairmentProjects,
  calcImpairmentTotals,
  calcImpairmentAmountTotal,
  migrateContractCostImpairmentSheet,
  emptyImpairmentProject,
  calcBookValue,
  calcNetRealizableValue,
  calcMeasuredProvision,
  isBlankImpairmentProject,
  pruneBlankImpairmentProjects,
} from '../useF2ContractCostImpairmentFormulas'

describe('useF2ContractCostImpairmentFormulas', () => {
  it('default sheet keeps one editable project row', () => {
    expect(defaultContractCostImpairmentSheet().projects).toHaveLength(1)
    expect(isBlankImpairmentProject(defaultContractCostImpairmentSheet().projects[0])).toBe(true)
  })

  it('prunes reserved blank rows but retains entered projects', () => {
    const entered = { ...emptyImpairmentProject(), projectName: '项目A', bookBalance: 100 }
    expect(pruneBlankImpairmentProjects([
      emptyImpairmentProject(),
      entered,
      emptyImpairmentProject(),
    ])).toEqual([entered])
  })

  it('keeps one blank row when all rows are empty', () => {
    const rows = pruneBlankImpairmentProjects([
      emptyImpairmentProject(),
      emptyImpairmentProject(),
    ])
    expect(rows).toHaveLength(1)
    expect(isBlankImpairmentProject(rows[0])).toBe(true)
  })

  it('calculates book value and NRV', () => {
    expect(calcBookValue(1000, 100)).toBe(900)
    expect(calcNetRealizableValue(800, 50)).toBe(750)
  })

  it('detects impairment and measures provision', () => {
    const row = {
      ...emptyImpairmentProject(),
      bookBalance: 1000,
      accumulatedProvision: 100,
      remainingConsideration: 800,
      estimatedFutureCosts: 50,
      companyRecordedProvision: 80,
    }
    const enriched = enrichImpairmentProject(row)
    expect(enriched.bookValue).toBe(900)
    expect(enriched.netRealizableValue).toBe(750)
    expect(enriched.isImpaired).toBe('是')
    expect(enriched.requiredProvision).toBe(250)
    expect(enriched.measuredProvision).toBe(150)
    expect(enriched.difference).toBe(70)
    expect(enriched.hasDifference).toBe(true)
  })

  it('handles reversal when NRV exceeds book value', () => {
    const row = {
      ...emptyImpairmentProject(),
      bookBalance: 1000,
      accumulatedProvision: 200,
      remainingConsideration: 950,
      estimatedFutureCosts: 50,
      companyRecordedProvision: 200,
    }
    const enriched = enrichImpairmentProject(row)
    expect(enriched.isImpaired).toBe('否')
    expect(calcMeasuredProvision(1000, 900, 200)).toBe(-100)
    expect(enriched.measuredProvision).toBe(-100)
  })

  it('column totals aggregate', () => {
    const rows = enrichImpairmentProjects([
      { ...emptyImpairmentProject(), bookBalance: 500, accumulatedProvision: 0 },
      { ...emptyImpairmentProject(), bookBalance: 300, accumulatedProvision: 0 },
    ])
    const totals = calcImpairmentTotals(rows)
    expect(totals.bookBalance).toBe(800)
    expect(totals.bookValue).toBe(800)
  })

  it('impairment amount total sums positive net impairment', () => {
    const rows = enrichImpairmentProjects([
      {
        ...emptyImpairmentProject(),
        bookBalance: 1000,
        accumulatedProvision: 0,
        remainingConsideration: 700,
        estimatedFutureCosts: 0,
      },
      {
        ...emptyImpairmentProject(),
        bookBalance: 500,
        accumulatedProvision: 0,
        remainingConsideration: 600,
        estimatedFutureCosts: 0,
      },
    ])
    expect(calcImpairmentAmountTotal(rows)).toBe(300)
  })

  it('migrates legacy revenue/cost rows', () => {
    const legacy = [{
      id: '1',
      projectName: '项目A',
      estimatedTotalRevenue: 1000,
      recognizedRevenue: 600,
      estimatedTotalCost: 800,
      incurredCost: 500,
      bookValue: 100,
      managementProvision: 20,
    }]
    const sheet = migrateContractCostImpairmentSheet(legacy)
    expect(sheet?.projects[0].projectName).toBe('项目A')
    expect(sheet?.projects[0].bookBalance).toBe(120)
    expect(sheet?.projects[0].remainingConsideration).toBe(400)
    expect(sheet?.projects[0].estimatedFutureCosts).toBe(300)
  })

  it('migrates new sheet JSON', () => {
    const legacy = {
      projects: [{ ...emptyImpairmentProject(), projectCode: 'P01' }],
    }
    const sheet = migrateContractCostImpairmentSheet(legacy)
    expect(sheet?.projects[0].projectCode).toBe('P01')
  })
})
