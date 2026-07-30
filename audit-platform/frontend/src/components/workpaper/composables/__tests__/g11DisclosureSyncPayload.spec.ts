import { describe, expect, it } from 'vitest'
import {
  buildG11ListedSyncPayloads,
  buildG11SoeSyncPayloads,
  G11_LISTED_TRADING_SUBTABLE,
  G11_MAIN_SUBTABLE,
} from '../g11DisclosureSyncPayload'
import { defaultG11DiscStore } from '../g11DisclosureFromAdj'
import { G11_DISCLOSURE_SHEET_NAME, G11_NOTE_SECTION } from '../g11NoteSectionMap'

describe('g11DisclosureSyncPayload', () => {
  it('buildG11ListedSyncPayloads 对齐五、69', () => {
    const store = defaultG11DiscStore('listed')
    store.rows = store.rows.map((r) =>
      r.rowKey === 'equity_method' ? { ...r, currentAmount: 100, priorAmount: 80 } : r,
    )
    store.tradingDispose = {
      equity_stock: { currentAmount: 30, priorAmount: 0 },
      debt_bond: { currentAmount: 0, priorAmount: 0 },
      derivative_non_hedge: { currentAmount: 0, priorAmount: 0 },
      derivative_hedge: { currentAmount: 0, priorAmount: 0 },
      other: { currentAmount: 0, priorAmount: 0 },
    }
    const payloads = buildG11ListedSyncPayloads('wp-g11', [], {
      store,
      noteText: '附注说明',
      auditNote: '审计说明',
      auditConclusion: '结论',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(G11_NOTE_SECTION.listed)
    // sheet_name = 源 xlsx 真实 tab 名（非 `附注上市` 短名）
    expect(payloads[0].sheet_name).toBe(G11_DISCLOSURE_SHEET_NAME.listed)
    const main = payloads[0].sub_table_data[G11_MAIN_SUBTABLE]
    expect(main.some((r) => r.row_key === 'equity_method')).toBe(true)
    expect(main.some((r) => r.is_total === true)).toBe(true)
    expect(payloads[0].sub_table_data[G11_LISTED_TRADING_SUBTABLE]).toBeDefined()
    expect(payloads[0].sub_table_data._note_texts?.[0]).toMatchObject({ section: 'disclosure-note' })
  })

  it('buildG11SoeSyncPayloads 对齐八、70', () => {
    const store = defaultG11DiscStore('soe')
    store.rows = store.rows.map((r) =>
      r.rowKey === 'other' ? { ...r, currentAmount: 200, priorAmount: 100 } : r,
    )
    store.repatriationNote = '不存在汇回限制。'
    const payloads = buildG11SoeSyncPayloads('wp-g11', ['soe_standalone'], {
      store,
      noteText: '',
      auditNote: '国企说明',
      auditConclusion: '',
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(G11_NOTE_SECTION.soe)
    expect(payloads[0].sheet_name).toBe(G11_DISCLOSURE_SHEET_NAME.soe)
    const main = payloads[0].sub_table_data[G11_MAIN_SUBTABLE]
    expect(main.some((r) => r.row_key === 'other')).toBe(true)
    expect(payloads[0].sub_table_data._note_texts?.some((t) => t.section === 'repatriation-note')).toBe(true)
  })
})
