import { describe, expect, it } from 'vitest'
import {
  evaluateG12CoreWorkflowReadiness,
  g12AdjustmentNeedsSync,
  resolveG12WorkflowActiveIndex,
} from '../g12CoreWorkflowReadiness'

function mapOf(entries: Record<string, { remark?: string; conclusion?: string }>) {
  return new Map(Object.entries(entries))
}

describe('evaluateG12CoreWorkflowReadiness', () => {
  it('空底稿时仅少数步通过', () => {
    const r = evaluateG12CoreWorkflowReadiness(new Map())
    expect(r.doneCount).toBeLessThan(3)
    expect(r.allOk).toBe(false)
  })

  it('G12-2 + 同步后的 G12-3 + TB 无差异', () => {
    const m = mapOf({
      'G12-hedge-detail-rows': {
        remark: JSON.stringify([{
          rowKind: 'fv_allocation',
          instrumentFvCumulative: 100,
          salesPortion: 100,
          purchasePortion: 0,
        }]),
      },
      'G12-aje-rows': {
        remark: JSON.stringify([{
          rowId: '1', seq: 1, adjustmentDesc: 'test', category: 'account',
          accountCode: '6103', debitAmount: 0, creditAmount: 10,
        }, {
          rowId: '2', seq: 2, adjustmentDesc: 'test', category: 'account',
          accountCode: '6101', debitAmount: 10, creditAmount: 0,
        }]),
      },
      'G12-aje-adj-overlay': { remark: JSON.stringify({ net_hedge: -10 }) },
      'G12-adj-tb': { remark: '90' },
    })
    const r = evaluateG12CoreWorkflowReadiness(m)
    expect(r.items[0].ok).toBe(true)
    expect(r.items[1].ok).toBe(true)
    expect(r.items[2].ok).toBe(true)
    expect(r.items[3].ok).toBe(true)
  })
})

describe('g12AdjustmentNeedsSync', () => {
  it('平衡但未写 overlay 时需要同步', () => {
    const m = mapOf({
      'G12-aje-rows': {
        remark: JSON.stringify([{
          rowId: '1', seq: 1, adjustmentDesc: 'x', category: 'account',
          accountCode: '6103', debitAmount: 0, creditAmount: 5,
        }, {
          rowId: '2', seq: 2, adjustmentDesc: 'x', category: 'account',
          accountCode: '6101', debitAmount: 5, creditAmount: 0,
        }]),
      },
    })
    expect(g12AdjustmentNeedsSync(m)).toBe(true)
  })
})

describe('resolveG12WorkflowActiveIndex', () => {
  it('G12-1 页在未取 TB 时高亮步骤 2', () => {
    const r = evaluateG12CoreWorkflowReadiness(mapOf({
      'G12-hedge-detail-rows': {
        remark: JSON.stringify([{ rowKind: 'fv_allocation', instrumentFvCumulative: 1, salesPortion: 1, purchasePortion: 0 }]),
      },
    }))
    expect(resolveG12WorkflowActiveIndex('G12-1', r)).toBe(2)
  })
})
