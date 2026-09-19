import { describe, it, expect } from 'vitest'
import {
  buildG5AdjudicationRows,
  G5_CHANGE_RATE_THRESHOLD,
} from '../useG5Adjudication'
import type { G5AdjRowStore } from '../g5AdjudicationItems'

describe('buildG5AdjudicationRows (G5-1 Excel 对齐)', () => {
  it('审定=未审+账项+重分类；小计汇总；一年以上=小计-一年内；净额勾稽', () => {
    const store: G5AdjRowStore = {
      'gross-individual': { closingUnadjusted: 100, closingAJE: 10, closingRJE: 0 },
      'gross-collective-business': { closingUnadjusted: 200, closingAJE: 0, closingRJE: 5 },
      'gross-collective-customer': { closingUnadjusted: 50 },
      'gross-one-year': { closingUnadjusted: 40 },
      'provision-individual': { closingUnadjusted: 8 },
      'provision-collective-business': { closingUnadjusted: 12 },
      'provision-collective-customer': { closingUnadjusted: 2 },
      'provision-one-year': { closingUnadjusted: 3 },
    }
    const rows = buildG5AdjudicationRows(store, 300)
    const by = Object.fromEntries(rows.map((r) => [r.rowKey, r]))

    // 单项审定 100+10+0
    expect(by['gross-individual'].closingAdjusted).toBe(110)
    // 业务类型 200+0+5
    expect(by['gross-collective-business'].closingAdjusted).toBe(205)
    // 小计 = 110+205+50
    expect(by['gross__subtotal'].closingAdjusted).toBe(365)
    // 一年以上 = 365-40
    expect(by['gross-reportable'].closingAdjusted).toBe(325)
    // 坏账小计 8+12+2=22；一年以上坏账=22-3=19
    expect(by['provision__subtotal'].closingAdjusted).toBe(22)
    expect(by['provision-reportable'].closingAdjusted).toBe(19)
    // 净额 = 325-19
    expect(by['net__row'].closingAdjusted).toBe(306)
    // 差异 = 306-300
    expect(by['tb-diff'].closingAdjusted).toBe(6)
  })

  it('变动率阈值 30%', () => {
    expect(G5_CHANGE_RATE_THRESHOLD).toBe(0.3)
  })
})
