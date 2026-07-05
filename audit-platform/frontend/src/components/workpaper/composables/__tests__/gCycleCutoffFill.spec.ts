import { describe, it, expect } from 'vitest'
import {
  mapCutoffToG12Voucher,
  mapCutoffToG13Adjustment,
  mapCutoffToG14Adjustment,
  mapCutoffToG8Adjustment,
  mapCutoffToG9Adjustment,
  mergeByFillMode,
} from '../gCycleCutoffFill'
import type { ExtractedVoucher } from '../useCutoffAutoSampling'

const sample: ExtractedVoucher = {
  voucherNo: 'V-001',
  voucherDate: '2025-12-28',
  summary: '公允价值变动',
  debitAmount: '1000',
  creditAmount: '0',
  accountCode: '6101',
  accountName: '公允价值变动收益',
  counterpartAccount: '1101',
  voucherType: '记',
  cutoffStatus: '可能跨期',
  remark: '窗口样本',
  selected: true,
}

describe('gCycleCutoffFill', () => {
  it('mapCutoffToG12Voucher maps amounts and flags cross-period', () => {
    const row = mapCutoffToG12Voucher(sample, 1)
    expect(row.voucherNo).toBe('V-001')
    expect(row.debitAmount).toBe(1000)
    expect(row.isAbnormal).toBe(true)
  })

  it('mapCutoffToG13Adjustment uses 6101 defaults', () => {
    const row = mapCutoffToG13Adjustment(sample)
    expect(row.accountCode).toBe('6101')
    expect(row.debitAmount).toBe(1000)
    expect(row.summary).toBe('公允价值变动')
  })

  it('mergeByFillMode append adds rows', () => {
    const a = [{ id: '1' }]
    const b = [{ id: '2' }]
    expect(mergeByFillMode(a, b, 'append', (r) => r.id)).toHaveLength(2)
  })

  it('mergeByFillMode merge dedupes by key', () => {
    const a = [{ id: '1' }]
    const b = [{ id: '1' }, { id: '2' }]
    expect(mergeByFillMode(a, b, 'merge', (r) => r.id)).toHaveLength(2)
  })

  it('mapCutoffToG14Adjustment sets category 账项调整', () => {
    const row = mapCutoffToG14Adjustment({ ...sample, accountCode: '6702' })
    expect(row.category).toBe('账项调整')
    expect(row.indexRef).toBe('V-001')
  })

  it('mapCutoffToG8Adjustment uses account from sample', () => {
    const row = mapCutoffToG8Adjustment(sample, 1)
    expect(row.accountCode).toBe('6101')
    expect(row.accountName).toBe('公允价值变动收益')
    expect(row.summary).toBe('公允价值变动')
  })

  it('mapCutoffToG9Adjustment uses 1504 defaults', () => {
    const row = mapCutoffToG9Adjustment({ ...sample, accountCode: '1504', accountName: '' }, 1)
    expect(row.accountCode).toBe('1504')
    expect(row.accountName).toBe('其他非流动金融资产')
  })
})
