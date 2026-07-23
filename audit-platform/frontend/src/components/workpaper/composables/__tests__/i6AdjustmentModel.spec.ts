import { describe, it, expect } from 'vitest'
import { applyAjeFromI63, applyAjeToI62Detail, categoryFromLegacy, aggregateI63Nets, buildI63DraftsFromDetail } from '../i6AdjustmentModel'
import type { I6AdjudicationRow } from '../useI6Adjudication'

function adjRow(partial: Record<string, unknown>) {
  return {
    rowId: 'r1',
    description: '测试',
    category: '账项调整',
    entryType: 'AJE',
    accountCode: '6602',
    accountName: '研发费用',
    noteItem: '人工费',
    debitAmount: 100,
    creditAmount: 0,
    ...partial,
  }
}

function adjRows(): I6AdjudicationRow[] {
  return [
    { rowId: 'a1', 类别: '人员人工费用', 上期未审: 0, 上期AJE: 0, 上期RJE: 0, 上期审定: 0, 本期未审: 1000, 本期AJE: 0, 本期RJE: 0, 本期审定: 1000, 变动额: 1000, 变动率: 1, 备注: '', changeRateHighlight: false },
    { rowId: 'a2', 类别: '直接投入费用', 上期未审: 0, 上期AJE: 0, 上期RJE: 0, 上期审定: 0, 本期未审: 500, 本期AJE: 0, 本期RJE: 0, 本期审定: 500, 变动额: 500, 变动率: 1, 备注: '', changeRateHighlight: false },
  ]
}

describe('i6AdjustmentModel', () => {
  it('categoryFromLegacy 兼容旧 AJE/RJE', () => {
    expect(categoryFromLegacy({ category: 'AJE' })).toBe('账项调整')
    expect(categoryFromLegacy({ category: 'RJE' })).toBe('报表调整')
    expect(categoryFromLegacy({ category: '账项调整' })).toBe('账项调整')
  })

  it('applyAjeFromI63 按附注项目精确匹配', () => {
    const result = applyAjeFromI63(adjRows(), [adjRow({ noteItem: '人工费', debitAmount: 200 })])
    const labor = result.rows.find((r) => r.类别 === '人员人工费用')
    expect(labor?.本期AJE).toBe(200)
    expect(result.totalAje).toBe(200)
    expect(result.approx).toBe(false)
  })

  it('applyAjeFromI63 未匹配时按未审占比分摊', () => {
    const result = applyAjeFromI63(adjRows(), [adjRow({ noteItem: '', debitAmount: 300 })])
    expect(result.totalAje).toBe(300)
    expect(result.approx).toBe(true)
    const sum = result.rows.reduce((s, r) => s + r.本期AJE, 0)
    expect(sum).toBeCloseTo(300, 1)
  })

  it('applyAjeToI62Detail 按费用性质同步至 I6-2', () => {
    const detail = [
      { id: 'd1', category: '项目A', expenseNature: '人工费', aje: 0, rje: 0 },
      { id: 'd2', category: '项目B', expenseNature: '材料费', aje: 0, rje: 0 },
    ]
    const result = applyAjeToI62Detail(detail, [
      adjRow({ noteItem: '人工费', debitAmount: 150 }),
      adjRow({ noteItem: '材料费', debitAmount: 50, category: '账项调整' }),
    ])
    expect(result.rows.find((r) => r.expenseNature === '人工费')?.aje).toBe(150)
    expect(result.rows.find((r) => r.expenseNature === '材料费')?.aje).toBe(50)
    expect(result.totalAje).toBe(200)
  })

  it('aggregateI63Nets 汇总 6602 净额', () => {
    const nets = aggregateI63Nets([
      adjRow({ debitAmount: 100 }),
      { ...adjRow({ debitAmount: 0, creditAmount: 20 }), category: '报表调整' },
    ])
    expect(nets.ajeNet).toBe(100)
    expect(nets.rjeNet).toBe(-20)
  })

  it('buildI63DraftsFromDetail 生成借贷平衡分录对', () => {
    const lines = buildI63DraftsFromDetail([
      { category: '人工费', expenseNature: '人工费', aje: 100, rje: 0 },
      { category: '材料费', expenseNature: '材料费', aje: 0, rje: 50 },
    ])
    expect(lines).toHaveLength(4)
    const ajeDebit = lines.find((l) => l.noteItem === '人工费' && l.accountCode === '6602')
    const ajeCredit = lines.find((l) => l.noteItem === '人工费' && l.accountCode === '2241')
    expect(ajeDebit?.debitAmount).toBe(100)
    expect(ajeCredit?.creditAmount).toBe(100)
    const rjeDebit = lines.find((l) => l.noteItem === '材料费' && l.accountCode === '6602')
    expect(rjeDebit?.debitAmount).toBe(50)
    expect(rjeDebit?.category).toBe('报表调整')
  })
})
