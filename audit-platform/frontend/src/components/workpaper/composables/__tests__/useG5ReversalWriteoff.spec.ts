import { describe, expect, it } from 'vitest'
import {
  emptyReversalRow,
  emptyWriteoffRow,
  inferApprovalComplete,
  summarizeChecks,
  useG5ReversalWriteoff,
} from '../useG5ReversalWriteoff'

describe('useG5ReversalWriteoff', () => {
  it('转回金额超过累计计提 → isValid=false', () => {
    const row = emptyReversalRow({ reversalAmount: 100, accumulatedProvision: 50 })
    expect(row.isValid).toBe(false)
  })

  it('转回金额不超过累计计提 → isValid=true', () => {
    const row = emptyReversalRow({ reversalAmount: 50, accumulatedProvision: 100 })
    expect(row.isValid).toBe(true)
  })

  it('核销审批完整可从程序文案推断', () => {
    const row = emptyWriteoffRow({ procedures: '董事会已批准核销' })
    expect(inferApprovalComplete(row)).toBe(true)
  })

  it('检查项 w1=是 → 审批完整', () => {
    const row = emptyWriteoffRow()
    row.checks.find(c => c.id === 'w1')!.result = '是'
    expect(inferApprovalComplete(row)).toBe(true)
  })

  it('summarizeChecks 生成合理性分析文本', () => {
    const row = emptyReversalRow()
    row.checks[0].result = '是'
    row.checks[0].note = '回单已核对'
    expect(summarizeChecks(row.checks)).toContain('是')
    expect(summarizeChecks(row.checks)).toContain('回单已核对')
  })

  it('loadRows 兼容旧格式并统计异常', () => {
    const rw = useG5ReversalWriteoff()
    rw.loadReversalRows([
      { debtor: '甲', reversalAmount: 20, accumulatedProvision: 10, reason: '', indexRef: '', isRelatedParty: true } as any,
    ])
    rw.loadWriteoffRows([
      { debtor: '乙', writeoffAmount: 5, approvalStatus: '', reason: '', indexRef: '', isRelatedParty: false } as any,
    ])
    expect(rw.invalidReversals.value).toHaveLength(1)
    expect(rw.incompleteWriteoffs.value).toHaveLength(1)
    expect(rw.totals.value.reversalAmount).toBe(20)
    expect(rw.relatedReversals.value).toHaveLength(1)
  })

  it('upsert 后合计正确', () => {
    const rw = useG5ReversalWriteoff()
    const a = emptyReversalRow({ debtor: 'A', reversalAmount: 10, accumulatedProvision: 30 })
    const b = emptyWriteoffRow({ debtor: 'B', writeoffAmount: 7, procedures: '已审批通过' })
    rw.upsertReversal(a)
    rw.upsertWriteoff(b)
    expect(rw.totals.value.reversalAmount).toBe(10)
    expect(rw.totals.value.writeoffAmount).toBe(7)
    expect(rw.incompleteWriteoffs.value).toHaveLength(0)
  })
})
