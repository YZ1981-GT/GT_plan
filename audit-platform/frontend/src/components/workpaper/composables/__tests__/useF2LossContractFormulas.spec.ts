import { describe, it, expect } from 'vitest'
import {
  defaultLossContractSheet,
  enrichLossContractProject,
  enrichLossContractProjects,
  calcLossContractTotals,
  migrateLossContractSheet,
  emptyLossContractProject,
  calcContractEstimatedLoss,
  resolveCompletionRate,
  isBlankLossContractProject,
  pruneBlankLossContractProjects,
} from '../useF2LossContractFormulas'

describe('useF2LossContractFormulas', () => {
  it('default sheet keeps one editable project row', () => {
    const projects = defaultLossContractSheet().projects
    expect(projects).toHaveLength(1)
    expect(isBlankLossContractProject(projects[0])).toBe(true)
  })

  it('prunes reserved blank rows but retains entered projects', () => {
    const entered = {
      ...emptyLossContractProject(),
      projectName: '项目A',
      estimatedTotalRevenue: 100,
    }
    expect(pruneBlankLossContractProjects([
      emptyLossContractProject(),
      entered,
      emptyLossContractProject(),
    ])).toEqual([entered])
  })

  it('keeps one blank row when all rows are empty', () => {
    const projects = pruneBlankLossContractProjects([
      emptyLossContractProject(),
      emptyLossContractProject(),
    ])
    expect(projects).toHaveLength(1)
    expect(isBlankLossContractProject(projects[0])).toBe(true)
  })

  it('calculates contract estimated loss ④=③−②', () => {
    expect(calcContractEstimatedLoss(1000, 1200)).toBe(200)
    expect(calcContractEstimatedLoss(1200, 1000)).toBe(0)
  })

  it('derives completion rate from recognized revenue', () => {
    const row = {
      ...emptyLossContractProject(),
      recognizedRevenue: 600,
      estimatedTotalRevenue: 1000,
      completionRate: 0.2,
    }
    expect(resolveCompletionRate(row)).toBeCloseTo(0.6, 5)
  })

  it('calculates loss chain for onerous contract', () => {
    const row = {
      ...emptyLossContractProject(),
      completionRate: 0.5,
      estimatedTotalRevenue: 1000,
      estimatedTotalCost: 1300,
      priorRecognizedLoss: 0,
      bookRecognizedLoss: 100,
    }
    const enriched = enrichLossContractProject(row)
    expect(enriched.isLoss).toBe('是')
    expect(enriched.contractEstimatedLoss).toBe(300)
    expect(enriched.recognizedLossInPl).toBe(150)
    expect(enriched.currentPeriodLoss).toBe(150)
    expect(enriched.difference).toBe(50)
    expect(enriched.hasDifference).toBe(true)
  })

  it('uses manual prior recognized loss when provided', () => {
    const row = {
      ...emptyLossContractProject(),
      completionRate: 0.5,
      estimatedTotalRevenue: 1000,
      estimatedTotalCost: 1300,
      priorRecognizedLoss: 200,
      bookRecognizedLoss: 0,
    }
    const enriched = enrichLossContractProject(row)
    expect(enriched.recognizedLossInPl).toBe(200)
    expect(enriched.currentPeriodLoss).toBe(100)
  })

  it('column totals aggregate', () => {
    const rows = enrichLossContractProjects([
      { ...emptyLossContractProject(), estimatedTotalRevenue: 500, estimatedTotalCost: 800 },
      { ...emptyLossContractProject(), estimatedTotalRevenue: 300, estimatedTotalCost: 400 },
    ])
    const totals = calcLossContractTotals(rows)
    expect(totals.estimatedTotalRevenue).toBe(800)
    expect(totals.estimatedTotalCost).toBe(1200)
    expect(totals.contractEstimatedLoss).toBe(400)
  })

  it('migrates legacy flat array rows', () => {
    const legacy = [{
      id: '1',
      projectName: '项目A',
      estimatedTotalRevenue: 1000,
      estimatedTotalCost: 1200,
      recognizedRevenue: 400,
      priorRecognizedLoss: 50,
      managementProvision: 80,
    }]
    const sheet = migrateLossContractSheet(legacy)
    expect(sheet?.projects[0].projectName).toBe('项目A')
    expect(sheet?.projects[0].bookRecognizedLoss).toBe(80)
    expect(sheet?.projects[0].priorRecognizedLoss).toBe(50)
  })

  it('migrates new sheet JSON', () => {
    const legacy = {
      projects: [{ ...emptyLossContractProject(), projectCode: 'P01' }],
    }
    const sheet = migrateLossContractSheet(legacy)
    expect(sheet?.projects[0].projectCode).toBe('P01')
  })
})
