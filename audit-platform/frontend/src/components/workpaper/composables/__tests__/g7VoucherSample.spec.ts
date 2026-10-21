import { describe, it, expect } from 'vitest'
import {
  createG7VoucherSampleRow,
  parseG7VoucherSampleRows,
  mergeVoucherSamples,
  type G7VoucherSample,
} from '../g7VoucherSample'

describe('createG7VoucherSampleRow', () => {
  it('creates a zeroed row with seq', () => {
    const row = createG7VoucherSampleRow(3)
    expect(row.seq).toBe(3)
    expect(row.debitAmount).toBe(0)
    expect(row.creditAmount).toBe(0)
    expect(row.voucherNo).toBe('')
  })
})

describe('parseG7VoucherSampleRows', () => {
  it('parses array payload and re-sequences', () => {
    const rows = parseG7VoucherSampleRows([
      { voucherNo: 'V1', debitAmount: '100' },
      { voucherNo: 'V2', creditAmount: 50 },
    ])
    expect(rows).toHaveLength(2)
    expect(rows[0].debitAmount).toBe(100)
    expect(rows[1].creditAmount).toBe(50)
    expect(rows.map(r => r.seq)).toEqual([1, 2])
  })

  it('accepts {rows:[...]} wrapper and returns [] for junk', () => {
    expect(parseG7VoucherSampleRows({ rows: [{ voucherNo: 'A' }] })).toHaveLength(1)
    expect(parseG7VoucherSampleRows(null)).toEqual([])
    expect(parseG7VoucherSampleRows('x')).toEqual([])
  })
})

describe('mergeVoucherSamples (Property 14: voucherNo 去重)', () => {
  const samples: G7VoucherSample[] = [
    { voucherNo: 'PZ-001', voucherDate: '2025-03-01', summary: '处置甲公司', counterAccount: '1002', debitAmount: 500 },
    { voucherNo: 'PZ-002', voucherDate: '2025-03-05', summary: '收款', creditAmount: 300 },
  ]

  it('maps samples into rows (debit / credit split)', () => {
    const { rows, added, skipped } = mergeVoucherSamples([], samples)
    expect(added).toBe(2)
    expect(skipped).toBe(0)
    expect(rows).toHaveLength(2)
    expect(rows[0]).toMatchObject({ voucherNo: 'PZ-001', businessContent: '处置甲公司', counterAccount: '1002', debitAmount: 500, creditAmount: 0, source: '抽凭' })
    expect(rows[1]).toMatchObject({ voucherNo: 'PZ-002', creditAmount: 300 })
  })

  it('dedups by voucherNo against existing rows', () => {
    const existing = mergeVoucherSamples([], samples).rows
    const { rows, added, skipped } = mergeVoucherSamples(existing, samples)
    expect(added).toBe(0)
    expect(skipped).toBe(2)
    expect(rows).toHaveLength(2)
  })

  it('dedups within the same batch (only one row per voucherNo)', () => {
    const dup: G7VoucherSample[] = [
      { voucherNo: 'X', debitAmount: 10 },
      { voucherNo: 'X', debitAmount: 999 },
    ]
    const { rows, added, skipped } = mergeVoucherSamples([], dup)
    expect(added).toBe(1)
    expect(skipped).toBe(1)
    expect(rows).toHaveLength(1)
    expect(rows[0].debitAmount).toBe(10)
  })

  it('appends samples with empty voucherNo without dedup', () => {
    const noVoucher: G7VoucherSample[] = [
      { debitAmount: 1 },
      { debitAmount: 2 },
    ]
    const { rows, added, skipped } = mergeVoucherSamples([], noVoucher)
    expect(added).toBe(2)
    expect(skipped).toBe(0)
    expect(rows).toHaveLength(2)
  })

  it('prefers debitAmount ?? amount for debit side', () => {
    const { rows } = mergeVoucherSamples([], [{ voucherNo: 'A', amount: 77 }])
    expect(rows[0].debitAmount).toBe(77)
  })

  it('多科目凭证按对方分录展开为多行，且同一张凭证的展开行不互相去重', () => {
    const multi: G7VoucherSample[] = [{
      voucherNo: 'M-1',
      voucherDate: '2025-05-01',
      summary: '处置收款',
      debitAmount: 1000,
      counterpartAccount: '多科目',
      voucherEntries: [
        { account_code: '1511', account_name: '长期股权投资', debit_amount: null, credit_amount: '800', summary: '转出成本' },
        { account_code: '6111', account_name: '投资收益', debit_amount: null, credit_amount: '200', summary: '处置收益' },
        { account_code: '1002', account_name: '银行存款', debit_amount: '1000', credit_amount: null, summary: '收款' },
      ],
    }]
    const { rows, added, skipped } = mergeVoucherSamples([], multi)
    expect(added).toBe(2)
    expect(skipped).toBe(0)
    expect(rows.map(r => [r.voucherNo, r.counterAccount, r.creditAmount])).toEqual([
      ['M-1', '1511', 800],
      ['M-1', '6111', 200],
    ])

    // 同一张凭证再次回填：按样本去重，整张跳过（skipped 按样本计 1）
    const again = mergeVoucherSamples(rows, multi)
    expect(again.added).toBe(0)
    expect(again.skipped).toBe(1)
    expect(again.rows).toHaveLength(2)
  })

  it('does not mutate the passed-in existing array', () => {
    const existing = createG7VoucherSampleRow(1)
    existing.voucherNo = 'KEEP'
    const arr = [existing]
    mergeVoucherSamples(arr, samples)
    expect(arr).toHaveLength(1) // 原数组不被追加
  })
})
