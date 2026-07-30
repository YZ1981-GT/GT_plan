import { describe, expect, it } from 'vitest'
import {
  buildG10ListedSyncPayloads,
  buildG10SoeSyncPayloads,
} from '../g10DisclosureSyncPayload'
import { defaultG10ListedDiscStore, defaultG10SoeDiscStore } from '../g10DisclosureFromAdj'
import { G10_DISCLOSURE_SHEET_NAME, G10_NOTE_SECTION } from '../g10NoteSectionMap'

describe('g10DisclosureSyncPayload', () => {
  it('buildG10ListedSyncPayloads 对齐五、34', () => {
    const store = defaultG10ListedDiscStore()
    store.movement.mv_trading_bond = {
      openingAmount: 100,
      increaseAmount: 20,
      decreaseAmount: 10,
      closingAmount: 110,
    }
    const payloads = buildG10ListedSyncPayloads('wp-g10', [], {
      store,
      auditNote: '审计说明',
      auditYear: 2025,
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(G10_NOTE_SECTION.listed.trading)
    // sheet_name = 源 xlsx 真实 tab 名（非 `附注上市` 短名，否则附注反向跳转匹配不上）
    expect(payloads[0].sheet_name).toBe(G10_DISCLOSURE_SHEET_NAME.listed)
    const rows = payloads[0].sub_table_data['交易性金融负债']
    expect(rows.some((r) => r.row_key === 'mv_trading_bond')).toBe(true)
    expect(rows.some((r) => r.is_total === true)).toBe(true)
  })

  it('buildG10ListedSyncPayloads 衍生负债写入五、35', () => {
    const store = defaultG10ListedDiscStore()
    store.derivativeRows = [
      { rowKey: 'd1', label: '利率互换', currentAmount: 50, priorAmount: 40 },
    ]
    const payloads = buildG10ListedSyncPayloads('wp-g10', [], {
      store,
      auditNote: '',
      auditYear: 2025,
    })
    expect(payloads).toHaveLength(2)
    expect(payloads[1].section_id).toBe(G10_NOTE_SECTION.listed.derivative)
    expect(payloads[1].sub_table_data['衍生金融负债']).toBeDefined()
  })

  it('buildG10SoeSyncPayloads 对齐八、34', () => {
    const store = defaultG10SoeDiscStore()
    store.balance.soe_trading_bond = { currentAmount: 200, priorAmount: 180 }
    const payloads = buildG10SoeSyncPayloads('wp-g10', ['soe_standalone'], {
      store,
      auditNote: '国企说明',
      auditYear: 2025,
    })
    expect(payloads).toHaveLength(1)
    expect(payloads[0].section_id).toBe(G10_NOTE_SECTION.soe.trading)
    expect(payloads[0].sheet_name).toBe(G10_DISCLOSURE_SHEET_NAME.soe)
  })
})
