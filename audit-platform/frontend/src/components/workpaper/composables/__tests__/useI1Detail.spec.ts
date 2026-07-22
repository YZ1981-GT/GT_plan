/**
 * useI1Detail — 对齐 Excel I1-2（原值/摊销/减值 → 审定 → 净值）
 */
import { describe, it, expect } from 'vitest'
import {
  recomputeI1DetailRow,
  normalizeI1DetailRow,
  emptyI1DetailRow,
  buildI1DetailCategorySummary,
  buildI1DetailConclusionDraft,
} from '../useI1Detail'

describe('recomputeI1DetailRow', () => {
  it('原值期末=期初+增加-减少；审定=未审+调整', () => {
    const row = recomputeI1DetailRow(emptyI1DetailRow({
      name: '专利A',
      costBegin: 1000,
      costIncrease: 200,
      costDecrease: 50,
      costBeginAdj: 10,
      costAdjInc: 5,
      costAdjDec: 2,
    }))
    expect(row.costEnd).toBe(1150)
    expect(row.auditedCostBegin).toBe(1010)
    expect(row.auditedCostIncrease).toBe(205)
    expect(row.auditedCostDecrease).toBe(52)
    expect(row.auditedCostEnd).toBe(1163)
  })

  it('摊销期末=期初+本期摊销+其他增加-处置-其他减少', () => {
    const row = recomputeI1DetailRow(emptyI1DetailRow({
      name: '软件B',
      costBegin: 1000,
      accAmortBegin: 100,
      amortProvision: 40,
      amortOtherIncrease: 10,
      amortDisposal: 20,
      amortOtherDecrease: 5,
    }))
    expect(row.accAmortEnd).toBe(125)
    expect(row.amortTransferOut).toBe(25) // 兼容旧字段=处置+其他减少
  })

  it('兼容旧 amortTransferOut / impairmentReversal', () => {
    const row = normalizeI1DetailRow({
      name: '旧数据',
      costBegin: 500,
      accAmortBegin: 50,
      amortProvision: 10,
      amortTransferOut: 30,
      impairmentBegin: 20,
      impairmentProvision: 5,
      impairmentReversal: 8,
    })
    expect(row.amortDisposal).toBe(30)
    expect(row.accAmortEnd).toBe(30) // 50+10-30
    expect(row.impairDisposal).toBe(8)
    expect(row.impairmentEnd).toBe(17) // 20+5-8
    expect(row.impairmentReversal).toBe(8) // 兼容写出=减少合计
  })

  it('净值=原值-摊销-减值（未审+审定）', () => {
    const row = recomputeI1DetailRow(emptyI1DetailRow({
      name: '商标C',
      costBegin: 1000,
      costIncrease: 0,
      costDecrease: 0,
      accAmortBegin: 200,
      amortProvision: 50,
      impairmentBegin: 30,
      impairmentProvision: 10,
    }))
    expect(row.costEnd).toBe(1000)
    expect(row.accAmortEnd).toBe(250)
    expect(row.impairmentEnd).toBe(40)
    expect(row.netBegin).toBe(770)
    expect(row.netValue).toBe(710)
    expect(row.auditedNetEnd).toBe(710)
  })

  it('寿命月数≤0 且有名称时默认寿命不确定=Y', () => {
    const row = recomputeI1DetailRow(emptyI1DetailRow({
      name: '商誉类',
      usefulLifeMonths: 0,
    }))
    expect(row.indefiniteLife).toBe('Y')
  })
})

describe('buildI1DetailCategorySummary', () => {
  it('按分类汇总', () => {
    const rows = [
      recomputeI1DetailRow(emptyI1DetailRow({ category: '软件', name: 'A', costBegin: 100 })),
      recomputeI1DetailRow(emptyI1DetailRow({ category: '软件', name: 'B', costBegin: 50 })),
      recomputeI1DetailRow(emptyI1DetailRow({ category: '专利权', name: 'C', costBegin: 200 })),
    ]
    const sum = buildI1DetailCategorySummary(rows)
    const soft = sum.find((s) => s.category === '软件')!
    expect(soft.count).toBe(2)
    expect(soft.costEnd).toBe(150)
    expect(sum.find((s) => s.category === '专利权')!.count).toBe(1)
  })
})

describe('buildI1DetailConclusionDraft', () => {
  it('勾稽一致时写未见异常', () => {
    const rows = [recomputeI1DetailRow(emptyI1DetailRow({
      name: '土地',
      category: '土地使用权',
      costBegin: 100,
      hasTitleEvidence: 'Y',
    }))]
    const summary = {
      costBegin: 100, costIncrease: 0, costDecrease: 0, costEnd: 100,
      auditedCostBegin: 100, auditedCostIncrease: 0, auditedCostDecrease: 0, auditedCostEnd: 100,
      accAmortBegin: 0, amortProvision: 0, amortOtherIncrease: 0, amortDisposal: 0, amortOtherDecrease: 0,
      accAmortEnd: 0, auditedAccAmortBegin: 0, auditedAmortIncrease: 0, auditedAmortDecrease: 0, auditedAccAmortEnd: 0,
      impairmentBegin: 0, impairmentProvision: 0, impairOtherIncrease: 0, impairDisposal: 0, impairOtherDecrease: 0,
      impairmentEnd: 0, auditedImpairmentBegin: 0, auditedImpairIncrease: 0, auditedImpairDecrease: 0, auditedImpairmentEnd: 0,
      netBegin: 100, netValue: 100, auditedNetBegin: 100, auditedNetEnd: 100,
    }
    const cross = {
      costDiff: 0, amortDiff: 0, impairDiff: 0,
      hasCostWarning: false, hasAmortWarning: false, hasImpairWarning: false, hasAnyWarning: false,
    }
    const text = buildI1DetailConclusionDraft(rows, summary, cross)
    expect(text).toContain('1 项')
    expect(text).toContain('勾稽一致')
  })
})
