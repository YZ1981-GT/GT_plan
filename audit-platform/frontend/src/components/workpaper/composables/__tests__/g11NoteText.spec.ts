/**
 * G11 附注文本生成与章节映射
 */
import { describe, it, expect } from 'vitest'
import { buildG11NoteTextFromStore, formatG11NoteAmount } from '../g11NoteText'
import { G11_NOTE_SECTION } from '../g11NoteSectionMap'
import {
  defaultG11DiscStore,
  parseG11DiscStore,
  type G11DiscStoreV2,
} from '../g11DisclosureFromAdj'

describe('formatG11NoteAmount', () => {
  it('千分位两位小数', () => {
    expect(formatG11NoteAmount(1234567.8)).toBe('1,234,567.80')
  })
})

describe('G11_NOTE_SECTION', () => {
  it('对齐 note_template_variant_matrix', () => {
    expect(G11_NOTE_SECTION.listed).toBe('五、69')
    expect(G11_NOTE_SECTION.soe).toBe('八、70')
  })
})

describe('buildG11NoteTextFromStore', () => {
  function listedStore(partial: Partial<G11DiscStoreV2>): G11DiscStoreV2 {
    const base = defaultG11DiscStore('listed')
    return { ...base, ...partial, version: 2 }
  }

  it('上市：汇总非零分项与处置交易性子表', () => {
    const store = listedStore({
      rows: parseG11DiscStore(undefined, 'listed').rows.map((r) => {
        if (r.rowKey === 'equity_method') {
          return { ...r, currentAmount: 100, priorAmount: 80 }
        }
        if (r.rowKey === 'trading_dispose') {
          return { ...r, currentAmount: 50, priorAmount: 0 }
        }
        return r
      }),
      tradingDispose: {
        equity_stock: { currentAmount: 30, priorAmount: 0 },
        debt_bond: { currentAmount: 20, priorAmount: 0 },
        derivative_non_hedge: { currentAmount: 0, priorAmount: 0 },
        derivative_hedge: { currentAmount: 0, priorAmount: 0 },
        other: { currentAmount: 0, priorAmount: 0 },
      },
    })
    const text = buildG11NoteTextFromStore(store, 'listed', { adjudicatedAmount: 150 })
    expect(text).toContain('本期发生额合计 150.00 元')
    expect(text).toContain('权益法核算的长期股权投资收益')
    expect(text).toContain('与 G11-1 审定数 150.00 元勾稽一致')
    expect(text).toContain('处置交易性金融资产取得的投资收益明细如下')
    expect(text).toContain('股票投资')
    expect(text).toContain('债券投资')
  })

  it('国企：含汇回限制说明', () => {
    const store = defaultG11DiscStore('soe')
    store.rows = store.rows.map((r) =>
      r.rowKey === 'other' ? { ...r, currentAmount: 200, priorAmount: 100 } : r,
    )
    store.repatriationNote = '本公司不存在投资收益汇回的重大限制。'
    const text = buildG11NoteTextFromStore(store, 'soe')
    expect(text).toContain('其他：本期 200.00 元')
    expect(text).toContain('不存在投资收益汇回的重大限制')
  })

  it('跳过占位符汇回说明', () => {
    const store = defaultG11DiscStore('soe')
    store.repatriationNote = '注：若投资收益汇回有重大限制的，应予以说明。若不存在此类重大限制，也应做出说明。'
    const text = buildG11NoteTextFromStore(store, 'soe')
    expect(text).not.toContain('若投资收益汇回有重大限制')
  })
})
