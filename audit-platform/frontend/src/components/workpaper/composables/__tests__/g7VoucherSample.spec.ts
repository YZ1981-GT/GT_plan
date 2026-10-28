import { describe, it, expect } from 'vitest'
import {
  createG7VoucherSampleRow,
  parseG7VoucherSampleRows,
} from '../g7VoucherSample'
// 抽凭回填（原 mergeVoucherSamples 按凭证号去重）改经共享回填函数，见 g7VoucherFill.spec
// （spec voucher-identity-writeback-and-audit-phase 任务 11）

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

