import { describe, expect, it } from 'vitest'
import { materializeLedgerWindow } from '@/utils/ledgerDisplay'
import type { LedgerWindowResponse } from '@/services/ledgerWindowApi'

function wire(pageIndex = 0): LedgerWindowResponse {
  const month = {
    month: '2025-01', label: '2025-01 本月合计', row_count: 2,
    debit_total: '12.00', credit_total: '3.00', closing_balance: '109.00',
    closing_balance_signed: '109.00', closing_direction: 'debit' as const,
  }
  return {
    kind: 'ledger', dataset_id: 'd1', query_fingerprint: 'q1',
    entries: [
      { id: 'r1', voucher_date: '2025-01-01', voucher_no: '001', debit_amount: '5.00',
        credit_amount: null, running_balance: '105.00', running_balance_signed: '105.00', running_balance_direction: 'debit' },
      { id: 'r2', voucher_date: '2025-01-02', voucher_no: '002', debit_amount: '7.00',
        credit_amount: '3.00', running_balance: '109.00', running_balance_signed: '109.00', running_balance_direction: 'debit' },
    ],
    summary: {
      total: 2, annual_opening: '100.00', annual_opening_signed: '100.00', annual_opening_direction: 'debit',
      range_opening: '100.00', range_opening_signed: '100.00', range_opening_direction: 'debit',
      debit_total: '12.00', credit_total: '3.00', undated_count: 0, months: [month], warnings: [],
    },
    page: { limit: 2, page_index: pageIndex, start: 1, end: 2, has_more: false, next_cursor: null },
    extra_columns: [], subtotals: [{ after_entry_id: 'r2', month }],
  }
}

describe('materializeLedgerWindow', () => {
  it('直接采用服务端运行余额和月合计，不从当前窗口重新累计', () => {
    const rows = materializeLedgerWindow(wire())
    expect(rows.map((row) => row._type)).toEqual(['opening', 'normal', 'normal', 'subtotal'])
    expect(rows.map((row) => row.balance)).toEqual([100, 105, 109, 109])
    expect(rows.at(-1)?.debit_amount).toBe(12)
  })

  it('后续窗可省略重复的范围期初行', () => {
    const rows = materializeLedgerWindow(wire(1), { includeOpening: false })
    expect(rows[0]._type).toBe('normal')
    expect(rows).toHaveLength(3)
  })
})


  it('贷方余额保留带符号数，避免窗口化后把原有负数显示成正数', () => {
    const response = wire()
    response.summary.range_opening_signed = '-100.00'
    response.summary.range_opening = '100.00'
    response.summary.range_opening_direction = 'credit'
    response.entries[0].running_balance_signed = '-105.00'
    response.entries[0].running_balance = '105.00'
    response.entries[0].running_balance_direction = 'credit'
    response.entries[1].running_balance_signed = '-109.00'
    response.entries[1].running_balance = '109.00'
    response.entries[1].running_balance_direction = 'credit'
    response.subtotals[0].month.closing_balance_signed = '-109.00'
    response.subtotals[0].month.closing_balance = '109.00'
    response.subtotals[0].month.closing_direction = 'credit'
    expect(materializeLedgerWindow(response).map((row) => row.balance)).toEqual([-100, -105, -109, -109])
  })
