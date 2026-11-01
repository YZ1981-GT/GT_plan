import { describe, expect, it } from 'vitest'

import {
  calculateTbSummaryAudited,
  recalcTbSummaryRow,
  recalcTbSummaryRows,
} from '../tbSummaryRecalc'

describe('试算汇总审定数增量重算', () => {
  it('保持原有借贷加减、空值和分币舍入口径', () => {
    expect(calculateTbSummaryAudited({
      unadjusted: '100.005',
      aje_dr: 20,
      aje_cr: '3',
      rcl_dr: null,
      rcl_cr: 2,
    })).toBe(115.01)
    expect(calculateTbSummaryAudited({ unadjusted: 'bad' })).toBeNull()
    expect(calculateTbSummaryAudited({ unadjusted: 5, aje_cr: 5 })).toBeNull()
  })

  it('只改目标行且相同结果不制造响应式写入', () => {
    const edited = { unadjusted: 100, rcl_dr: 4, audited: 100 }
    const untouched = { unadjusted: 9, audited: 9 }

    expect(recalcTbSummaryRow(edited)).toBe(true)
    expect(edited.audited).toBe(104)
    expect(untouched.audited).toBe(9)
    expect(recalcTbSummaryRow(edited)).toBe(false)
  })

  it('批量边界显式重算全部行并返回真实变化数', () => {
    const rows = [
      { unadjusted: 1, audited: null },
      { unadjusted: 0, audited: null },
      { unadjusted: 3, aje_dr: 2, audited: 5 },
    ]
    expect(recalcTbSummaryRows(rows)).toBe(1)
    expect(rows.map((row) => row.audited)).toEqual([1, null, 5])
  })
})
