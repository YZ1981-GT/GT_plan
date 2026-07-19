import { describe, expect, it } from 'vitest'
import {
  buildG410ImpairmentDrafts,
  buildG413AbnormalMemos,
  buildG48VarianceMemos,
  buildG44InterestVarianceDraft,
} from '../g4ExceptionRouting'

describe('g4ExceptionRouting', () => {
  it('builds positive impairment as Dr 6702 / Cr 1502', () => {
    const drafts = buildG410ImpairmentDrafts([
      { id: 'positive', investProject: '债券A', impairmentAdjustment: 125 },
    ])

    expect(drafts).toHaveLength(2)
    expect(drafts[0]).toMatchObject({
      accountCode: '6702',
      debitAmount: 125,
      creditAmount: 0,
    })
    expect(drafts[1]).toMatchObject({
      accountCode: '1502',
      debitAmount: 0,
      creditAmount: 125,
    })
  })

  it('reverses the impairment entry for a negative adjustment', () => {
    const drafts = buildG410ImpairmentDrafts([
      { id: 'negative', investProject: '债券B', impairmentAdjustment: -80 },
    ])

    expect(drafts).toHaveLength(2)
    expect(drafts[0]).toMatchObject({
      accountCode: '1502',
      debitAmount: 80,
      creditAmount: 0,
    })
    expect(drafts[1]).toMatchObject({
      accountCode: '6702',
      debitAmount: 0,
      creditAmount: 80,
    })
  })

  it('keeps G4-8 and G4-13 exception memos at zero', () => {
    const inventory = buildG48VarianceMemos([
      { id: 'inventory-1', securitiesName: '债券C', variance: 10, remark: '' },
    ])
    const vouchers = buildG413AbnormalMemos([
      {
        id: 'voucher-1',
        voucherNo: '记-001',
        isAbnormal: true,
        debitAmount: 999,
        creditAmount: 999,
        abnormalNote: '支持文件缺失',
      },
    ])

    expect(inventory[0]).toMatchObject({
      sourceKey: 'G4-8:item:inventory-1:inventory-difference',
      category: '其他',
      debitAmount: 0,
      creditAmount: 0,
    })
    expect(vouchers[0]).toMatchObject({
      category: '其他',
      debitAmount: 0,
      creditAmount: 0,
    })
  })

  it('routes only the G4-4 variance as a balanced draft', () => {
    expect(buildG44InterestVarianceDraft(0.009)).toEqual([])
    const drafts = buildG44InterestVarianceDraft(25)
    expect(drafts).toHaveLength(2)
    expect(drafts[0]).toMatchObject({
      accountCode: '150102',
      debitAmount: 25,
      sourceKind: 'interest-variance',
    })
    expect(drafts[1]).toMatchObject({
      accountCode: '6011',
      creditAmount: 25,
    })
  })
})
