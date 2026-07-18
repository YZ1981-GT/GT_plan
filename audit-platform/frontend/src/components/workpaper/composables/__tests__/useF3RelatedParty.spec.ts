import { describe, expect, it } from 'vitest'
import {
  computeRelatedPartyRow,
  emptyRelatedPartyRow,
  isBlankRelatedPartyRow,
  safeParseRelatedPartyRows,
} from '../useF3RelatedParty'

describe('F3-6 关联方票据余额与风险公式', () => {
  it('期末余额 = 期初 + 贷方发生 - 借方发生', () => {
    const row = computeRelatedPartyRow({
      ...emptyRelatedPartyRow(1),
      partyName: '甲关联方',
      relationship: '控股股东',
      noteType: '银行承兑汇票',
      openingBalance: 1_000_000,
      debitMovement: 300_000,
      creditMovement: 500_000,
      pricingPolicy: '市场定价',
      transactionReason: '采购材料',
      subsequentPaymentAmount: 200_000,
    }, 2_400_000)

    expect(row.closingBalance).toBe(1_200_000)
    expect(row.concentration).toBe(50)
    expect(row.riskFlags).toContain('关联方余额集中度较高')
  })

  it('识别关系、定价、款项性质和期后付款缺失风险', () => {
    const row = computeRelatedPartyRow({
      ...emptyRelatedPartyRow(1),
      partyName: '待核实方',
      creditMovement: 100_000,
    }, 100_000)

    expect(row.riskFlags).toContain('关联关系待核实')
    expect(row.riskFlags).toContain('定价政策未说明')
    expect(row.riskFlags).toContain('款项性质未说明')
    expect(row.riskFlags).toContain('无期后付款记录')
  })

  it('空白录入行不生成风险提示', () => {
    const row = computeRelatedPartyRow(emptyRelatedPartyRow(1))
    expect(isBlankRelatedPartyRow(row)).toBe(true)
    expect(row.riskFlags).toEqual([])
  })
})

describe('F3-6 旧数据迁移与空行修剪', () => {
  it('旧面值迁移为贷方发生并保持期末金额，旧用途迁移为款项性质', () => {
    const rows = safeParseRelatedPartyRows(JSON.stringify([{
      rowId: 'old-1',
      partyName: '乙关联方',
      relationship: '联营企业',
      noteType: '商业承兑',
      faceValue: 800_000,
      purpose: '采购设备',
      fairness: '公允',
      settlementMethod: '票据结算',
      auditEvaluation: '未见异常',
    }]))

    expect(rows).toHaveLength(1)
    expect(rows[0].creditMovement).toBe(800_000)
    expect(rows[0].closingBalance).toBe(800_000)
    expect(rows[0].transactionReason).toBe('采购设备')
    expect(rows[0].pricingPolicy).toBe('公允')
    expect(rows[0].remark).toContain('票据结算')
    expect(rows[0].remark).toContain('未见异常')
  })

  it('修剪多余空行并重排序号，全部为空时保留一行', () => {
    const rows = safeParseRelatedPartyRows(JSON.stringify([
      { rowId: 'blank-1' },
      { rowId: 'filled', partyName: '丙关联方', creditMovement: 10_000 },
      { rowId: 'blank-2' },
    ]))
    expect(rows).toHaveLength(1)
    expect(rows[0].partyName).toBe('丙关联方')
    expect(rows[0].seq).toBe(1)

    expect(safeParseRelatedPartyRows(JSON.stringify([{ rowId: 'blank' }]))).toHaveLength(1)
  })
})
