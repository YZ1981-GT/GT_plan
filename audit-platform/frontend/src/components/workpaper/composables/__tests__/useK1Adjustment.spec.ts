import { describe, it, expect } from 'vitest'
import {
  normalizeK1AdjustmentRow,
  categoryFromLegacy,
  entryTypeFromCategory,
} from '../useK1Adjustment'
import { injectK1Adjustments } from '../k1AdjustmentInject'
import { K1_VOUCHER_PUSH_MARK } from '../useK1VoucherCheck'

describe('useK1Adjustment', () => {
  it('migrates legacy journal-entry shape to Excel columns', () => {
    const row = normalizeK1AdjustmentRow(
      {
        id: 'entry-1',
        entryType: 'AJE',
        accountCode: '1221',
        summary: '补记关联方其他应收',
        debitAmount: 10000,
        creditAmount: 0,
        preparedBy: '张三',
      },
      0,
    )
    expect(row.description).toBe('补记关联方其他应收')
    expect(row.category).toBe('账项调整')
    expect(row.entryType).toBe('AJE')
    expect(row.reportItem).toBe('其他应收款')
    expect(row.accountName).toBe('其他应收款')
    expect(row.debitAmount).toBe(10000)
  })

  it('maps RJE legacy entryType to 报表调整', () => {
    expect(categoryFromLegacy({ entryType: 'RJE' })).toBe('报表调整')
    expect(entryTypeFromCategory('报表调整')).toBe('RJE')
    expect(entryTypeFromCategory('账项调整')).toBe('AJE')
  })

  it('sets bad debt report/note items for 1231', () => {
    const row = normalizeK1AdjustmentRow(
      { accountCode: '1231', debitAmount: 500, creditAmount: 0 },
      0,
    )
    expect(row.reportItem).toBe('坏账准备')
    expect(row.noteItem).toBe('坏账准备')
    expect(row.accountName).toBe('坏账准备')
  })
})

describe('k1AdjustmentInject', () => {
  it('replaces same sourceKind rows idempotently', () => {
    const map = new Map<string, any>()
    map.set('K1-4-adj-entries', {
      item_id: 'K1-4-adj-entries',
      remark: JSON.stringify([
        { rowId: 'old', sourceKind: 'k1-12-voucher', description: 'old draft' },
        { rowId: 'keep', description: 'manual row' },
      ]),
    })

    const added = injectK1Adjustments(
      map,
      [
        {
          summary: `${K1_VOUCHER_PUSH_MARK}凭证异常：V001`,
          accountCode: '1221',
          accountName: '其他应收款',
          debitAmount: 0,
          creditAmount: 0,
          indexRef: 'K1-12',
          remark: '金额待补',
        },
      ],
      'k1-12-voucher',
    )

    expect(added).toHaveLength(1)
    const rows = JSON.parse(map.get('K1-4-adj-entries')!.remark)
    expect(rows).toHaveLength(2)
    expect(rows.some((r: any) => r.description === 'old draft')).toBe(false)
    expect(rows.some((r: any) => r.description === 'manual row')).toBe(true)
    expect(rows.some((r: any) => r.description.includes(K1_VOUCHER_PUSH_MARK))).toBe(true)
  })
})
