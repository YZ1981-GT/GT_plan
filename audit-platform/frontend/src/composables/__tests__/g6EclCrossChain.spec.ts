/**
 * G6 ECL 跨表链路回归：G6-11 阶段 → G6-12 行；G6-13 损失率 → G6-12；G6-12 → G6-14
 */
import { describe, it, expect } from 'vitest'
import {
  applyStageUpdatesToRows,
  applyEclRateUpdatesToRows,
  collectEclRateUpdates,
  createEmptyImpairmentRow,
} from '@/components/workpaper/composables/useG6EclImpairmentCalc'
import {
  calcTermAdjustedPd,
  effectivePdHorizonMonths,
} from '@/composables/useG6EclFormulaEngine'
import {
  G6_11_ROWS_KEY,
  G6_12_DATA_KEY,
  G6_14_DATA_KEY,
  G6_14_ROWS_KEY,
  G6_STAGE_UPDATED_EVENT,
  G6_ECL_RATE_UPDATED_EVENT,
} from '@/components/workpaper/composables/g6CrossHelpers'
import { useG6EclReversalWriteOff } from '@/components/workpaper/composables/useG6EclReversalWriteOff'

describe('g6EclCrossChain', () => {
  it('事件常量集中定义', () => {
    expect(G6_11_ROWS_KEY).toBe('G6-11-rows')
    expect(G6_12_DATA_KEY).toBe('G6-12-impairment-calc-data')
    expect(G6_14_DATA_KEY).toBe('G6-14-reversal-writeoff-data')
    expect(G6_14_ROWS_KEY).toBe('G6-14-rows')
    expect(G6_STAGE_UPDATED_EVENT).toBe('g6-stage-updated')
    expect(G6_ECL_RATE_UPDATED_EVENT).toBe('g6:ecl-rate-updated')
  })

  it('G6-11→G6-12 阶段同步保留已有行并新建缺失项', () => {
    const existing = [
      createEmptyImpairmentRow({
        id: '1',
        seq: 1,
        investProject: '债A',
        stage: 'Stage1',
        amortizedCost: 100,
      }),
    ]
    const { rows, created, updated } = applyStageUpdatesToRows(existing, [
      { investProject: '债A', auditStage: 'Stage2', bookBalance: 100 },
      { investProject: '债B', auditStage: 'Stage3', bookBalance: 200 },
    ])
    expect(updated).toBe(1)
    expect(created).toBe(1)
    expect(rows.find(r => r.investProject === '债A')?.stage).toBe('Stage2')
    expect(rows.find(r => r.investProject === '债B')?.stage).toBe('Stage3')
  })

  it('G6-13→G6-12 损失率回写跳过 Stage3，并报告匹配', () => {
    const base = [
      createEmptyImpairmentRow({ id: '1', seq: 1, investProject: '债A', stage: 'Stage1' }),
      createEmptyImpairmentRow({ id: '2', seq: 2, investProject: '债B', stage: 'Stage3' }),
    ]
    const updates = collectEclRateUpdates(
      [
        { projectName: '债A', stage: 'Stage1', eclRate: 0.02 },
        { projectName: '债B', stage: 'Stage3', eclRate: 0.5 },
        { projectName: '债C', stage: 'Stage1', eclRate: 0.01 },
      ],
      [],
      'pdLgd',
    )
    const result = applyEclRateUpdatesToRows(base, updates)
    expect(result.count).toBe(1)
    expect(result.rows[0].creditLossRate).toBe(0.02)
    expect(result.skipped.some(s => s.reason === 'stage3')).toBe(true)
    expect(result.unmatched).toContain('债C')
    expect(result.matchReport.byName).toContain('债A')
  })

  it('优先按 crossSheetInvestmentId 匹配损失率（改名仍命中）', () => {
    const base = [
      createEmptyImpairmentRow({
        id: 'stable-1',
        seq: 1,
        investProject: '旧名称',
        crossSheetInvestmentId: 'inv-stable-1',
        stage: 'Stage1',
      }),
    ]
    const updates = collectEclRateUpdates(
      [{
        projectName: '新名称',
        crossSheetInvestmentId: 'inv-stable-1',
        eclRate: 0.08,
        stage: 'Stage1',
      }],
      [],
      'pdLgd',
    )
    expect(updates[0].crossSheetInvestmentId).toBe('inv-stable-1')
    const result = applyEclRateUpdatesToRows(base, updates)
    expect(result.count).toBe(1)
    expect(result.matchReport.byId).toEqual(['旧名称'])
    expect(result.rows[0].creditLossRate).toBe(0.08)
  })

  it('Stage1 PD 展望期不超过 12 个月', () => {
    expect(effectivePdHorizonMonths('Stage1', 48)).toBe(12)
    expect(calcTermAdjustedPd(0.05, 48, 'Stage1')).toBe(calcTermAdjustedPd(0.05, 12))
    expect(calcTermAdjustedPd(0.05, 48, 'Stage2')).toBeGreaterThan(
      calcTermAdjustedPd(0.05, 48, 'Stage1'),
    )
  })

  it('G6-12→G6-14：聚合转回后勾稽闸门可通过', () => {
    const { importFromImpairmentRows, gate, setG12ReversalTotal, reversals } = useG6EclReversalWriteOff()
    const g12Rows = [
      createEmptyImpairmentRow({
        id: 'a',
        seq: 1,
        investProject: '债A',
        crossSheetInvestmentId: 'inv-a',
        currentReversal: 40,
        priorImpairment: 100,
      }),
      createEmptyImpairmentRow({
        id: 'a2',
        seq: 2,
        investProject: '债A',
        crossSheetInvestmentId: 'inv-a',
        currentReversal: 60,
        priorImpairment: 100,
      }),
    ]
    const result = importFromImpairmentRows(g12Rows)
    expect(result.added).toBe(1)
    expect(reversals.value[0].reversalAmount).toBe(100)
    expect(reversals.value[0].crossSheetInvestmentId).toBe('inv-a')
    reversals.value[0].isReasonable = '合理'
    reversals.value[0].reversalReason = '信用风险好转'
    reversals.value[0].originalBasis = '原减值依据'
    reversals.value[0].reasonAnalysis = '已核实'
    setG12ReversalTotal(100)
    expect(gate.value.g12ReversalGap).toBe(0)
    expect(gate.value.ready).toBe(true)
  })
})
