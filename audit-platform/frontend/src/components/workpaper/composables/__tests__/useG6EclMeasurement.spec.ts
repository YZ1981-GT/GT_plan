/**
 * G6-13 ECL 计量公式 + 损失率回写 单元测试
 */
import { describe, it, expect } from 'vitest'
import {
  calcTermAdjustedPd,
  calcEclRateFromPdLgd,
  calcEclRateFromLossRate,
  calcImpairmentProvision,
  calcLossRateVariance,
} from '@/composables/useG6EclFormulaEngine'
import {
  collectEclRateUpdates,
  applyEclRateUpdatesToRows,
  createEmptyImpairmentRow,
} from '../useG6EclImpairmentCalc'

describe('G6-13 公式', () => {
  it('期限折算 PD', () => {
    expect(calcTermAdjustedPd(0.012, 12)).toBeCloseTo(0.012, 5)
    expect(calcTermAdjustedPd(0.012, 0)).toBe(0)
  })

  it('PD×LGD → ECL率', () => {
    expect(calcEclRateFromPdLgd(0.02, 0.45)).toBeCloseTo(0.009, 6)
  })

  it('损失率 + 前瞻调整', () => {
    expect(calcEclRateFromLossRate(0.01, 0.005)).toBeCloseTo(0.015, 6)
    expect(calcEclRateFromLossRate(0.9, 0.2)).toBe(1)
  })

  it('ECL金额 = 余额 × 率', () => {
    expect(calcImpairmentProvision(1_000_000, 0.01)).toBe(10_000)
  })

  it('与上期差异', () => {
    expect(calcLossRateVariance(0.05, 0.03)).toBeCloseTo(0.02, 6)
  })
})

describe('G6-13 → G6-12 损失率回写', () => {
  it('collectEclRateUpdates 按 prefer 覆盖同名', () => {
    const updates = collectEclRateUpdates(
      [{ projectName: '债A', eclRate: 0.01, stage: 'Stage1' }],
      [{ projectName: '债A', eclRate: 0.05, stage: 'Stage1' }],
      'lossRate',
    )
    expect(updates).toHaveLength(1)
    expect(updates[0].eclRate).toBe(0.05)
    expect(updates[0].method).toBe('lossRate')
  })

  it('applyEclRateUpdatesToRows 匹配并跳过 Stage3', () => {
    const base = [
      createEmptyImpairmentRow({
        id: '1', seq: 1, investProject: '债A', stage: 'Stage1', stageGroup: 'Stage1',
        amortizedCost: 1000, creditLossRate: 0.01,
      }),
      createEmptyImpairmentRow({
        id: '2', seq: 2, investProject: '债B', stage: 'Stage3', stageGroup: 'Stage3',
        amortizedCost: 2000, creditLossRate: 0.1,
      }),
    ]
    const result = applyEclRateUpdatesToRows(base, [
      { projectName: '债A', eclRate: 0.08, method: 'pdLgd' },
      { projectName: '债B', eclRate: 0.5, method: 'pdLgd' },
      { projectName: '债C', eclRate: 0.02, method: 'lossRate' },
    ])
    expect(result.count).toBe(1)
    expect(result.rows[0].creditLossRate).toBe(0.08)
    expect(result.skipped.some(s => s.reason === 'stage3')).toBe(true)
    expect(result.unmatched).toContain('债C')
  })
})
