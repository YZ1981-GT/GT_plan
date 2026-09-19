import { describe, expect, it } from 'vitest'
import {
  computeOverdueRow,
  emptyOverdueRow,
  isBlankOverdueRow,
  safeParseOverdueRows,
} from '../useF3OverdueCheck'

describe('F3-5 逾期未付票据公式与风险', () => {
  it('计算期限、逾期天数、尚未支付金额与风险提示', () => {
    const row = computeOverdueRow({
      ...emptyOverdueRow(1),
      ticketNo: 'HP-001',
      drawer: '甲公司',
      acceptor: '乙银行',
      payee: '丙公司',
      issueDate: '2025-01-01',
      dueDate: '2025-07-01',
      faceValue: 1_000_000,
      postPaymentAmount: 600_000,
      isAdjusted: '否',
    }, new Date('2025-10-15T00:00:00'))

    expect(row.termDays).toBe(181)
    expect(row.overdueDays).toBe(105)
    expect(row.unpaidAmount).toBe(400_000)
    expect(row.riskFlags).toContain('逾期超过90天')
    expect(row.riskFlags).toContain('期后尚未付清')
    expect(row.riskFlags).toContain('调整处理待确认')
  })

  it('期后支付超过票面金额时尚未支付金额不为负数', () => {
    const row = computeOverdueRow({
      ...emptyOverdueRow(1),
      faceValue: 100,
      postPaymentAmount: 120,
    }, new Date('2025-01-01T00:00:00'))
    expect(row.unpaidAmount).toBe(0)
  })

  it('空行判定忽略公式与附件槽位', () => {
    expect(isBlankOverdueRow(emptyOverdueRow(1, 99))).toBe(true)
    expect(computeOverdueRow(emptyOverdueRow(1, 99)).riskFlags).toEqual([])
    expect(isBlankOverdueRow({ ...emptyOverdueRow(1), ticketNo: 'HP-002' })).toBe(false)
  })
})

describe('F3-5 旧数据迁移', () => {
  it('把旧逾期说明、催收和建议合并到借款条件，并迁移调整状态', () => {
    const rows = safeParseOverdueRows(JSON.stringify([{
      rowId: 'old-1',
      drawer: '出票公司',
      acceptor: '承兑银行',
      noteType: '银行承兑',
      faceValue: 500_000,
      issueDate: '2025-01-01',
      dueDate: '2025-06-30',
      overdueReason: '资金紧张',
      collectionStatus: '已发催款函',
      auditAdvice: '关注诉讼',
      transferredToAp: '是',
    }]))

    expect(rows).toHaveLength(1)
    expect(rows[0].loanConditions).toContain('资金紧张')
    expect(rows[0].loanConditions).toContain('已发催款函')
    expect(rows[0].loanConditions).toContain('关注诉讼')
    expect(rows[0].isAdjusted).toBe('是')
  })

  it('修剪多余空行并保留一行空白录入行', () => {
    const mixed = safeParseOverdueRows(JSON.stringify([
      { rowId: 'empty-1' },
      { rowId: 'filled', ticketNo: 'HP-003' },
      { rowId: 'empty-2' },
    ]))
    expect(mixed).toHaveLength(1)
    expect(mixed[0].ticketNo).toBe('HP-003')
    expect(mixed[0].seq).toBe(1)

    expect(safeParseOverdueRows(JSON.stringify([{ rowId: 'empty' }]))).toHaveLength(1)
  })
})
