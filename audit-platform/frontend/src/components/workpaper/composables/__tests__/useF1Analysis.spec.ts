/**
 * useF1Analysis 纯函数单测 — F1-4 实质性分析
 */
import { describe, it, expect } from 'vitest'
import {
  recalcSupplierRow,
  withPeriodMetrics,
  aggregateDetailByAnalysisNature,
  computeTop5,
  createEmptySupplierRow,
  NATURE_TO_ANALYSIS,
} from '../useF1Analysis'

describe('useF1Analysis pure helpers', () => {
  it('recalcSupplierRow: 期末=期初+借−贷，账面价值=期末−坏账', () => {
    const row = recalcSupplierRow({
      ...createEmptySupplierRow(),
      priorBalance: 100,
      debit: 50,
      credit: 30,
      badDebt: 10,
    })
    expect(row.endBalance).toBe(120)
    expect(row.bookValue).toBe(110)
  })

  it('withPeriodMetrics: 变动额与变动率', () => {
    const m = withPeriodMetrics({ current: 130, prior: 100 })
    expect(m.changeAmount).toBe(30)
    expect(m.changeRate).toBeCloseTo(0.3, 6)
  })

  it('withPeriodMetrics: 上期为 0 返回 N/A', () => {
    expect(withPeriodMetrics({ current: 10, prior: 0 }).changeRate).toBe('N/A')
  })

  it('aggregateDetailByAnalysisNature maps F1-2 nature to analysis buckets', () => {
    const rows = [
      { nature: '货款', endAudited: 100, priorAudited: 80, debit: 40 },
      { nature: '工程款', endAudited: 50, priorAudited: 20, debit: 10 },
      { nature: '服务费', endAudited: 30, priorAudited: 10, debit: 5 },
      { nature: '其他', endAudited: 20, priorAudited: 5, debit: 2 },
    ]
    const bal = aggregateDetailByAnalysisNature(rows, 'balance')
    expect(bal.inventory.current).toBe(100)
    expect(bal.construction.current).toBe(50)
    expect(bal.expense.current).toBe(30)
    expect(bal.other.current).toBe(20)
    expect(bal.inventory.prior).toBe(80)

    const deb = aggregateDetailByAnalysisNature(rows, 'debit')
    expect(deb.inventory.current).toBe(40)
    expect(deb.construction.current).toBe(10)
  })

  it('NATURE_TO_ANALYSIS covers F1 payment natures', () => {
    expect(NATURE_TO_ANALYSIS['货款']).toBe('inventory')
    expect(NATURE_TO_ANALYSIS['设备款']).toBe('construction')
  })

  it('computeTop5 sorts by endAudited and warns when concentration > 50%', () => {
    const rows = [
      { customerName: 'A', endAudited: 600, priorAudited: 500 },
      { customerName: 'B', endAudited: 200, priorAudited: 100 },
      { customerName: 'C', endAudited: 100, priorAudited: 100 },
      { customerName: 'D', endAudited: 50, priorAudited: 50 },
      { customerName: 'E', endAudited: 30, priorAudited: 30 },
      { customerName: 'F', endAudited: 20, priorAudited: 20 },
    ]
    const { top5, concentrationWarning, majorCandidates } = computeTop5(rows, 5)
    expect(top5).toHaveLength(5)
    expect(top5[0].customerName).toBe('A')
    expect(concentrationWarning).toMatch(/集中度/)
    expect(majorCandidates[0].supplierName).toBe('A')
    expect(majorCandidates[0].endBalance).toBe(600)
  })

  it('computeTop5 returns empty for empty input', () => {
    const r = computeTop5([])
    expect(r.top5).toEqual([])
    expect(r.concentrationWarning).toBeNull()
  })

  it('buildCrossCycleHints warns when purchase missing / turnover high / payable compare', async () => {
    const { buildCrossCycleHints } = await import('../useF1Analysis')
    expect(
      buildCrossCycleHints({
        prepaidEndCurrent: 100,
        prepaidEndPrior: 80,
        inventoryRelatedDebit: 50,
        inventoryPurchaseCurrent: 0,
        inventoryBalanceCurrent: 0,
        payableBalanceCurrent: 0,
      }).some(h => h.includes('存货采购金额')),
    ).toBe(true)

    const turnoverHints = buildCrossCycleHints({
      prepaidEndCurrent: 500,
      prepaidEndPrior: 500,
      inventoryRelatedDebit: 10,
      inventoryPurchaseCurrent: 200,
      inventoryBalanceCurrent: 100,
      payableBalanceCurrent: 50,
    })
    expect(turnoverHints.some(h => h.includes('周转'))).toBe(true)
    expect(turnoverHints.some(h => h.includes('应付'))).toBe(true)
  })
})
