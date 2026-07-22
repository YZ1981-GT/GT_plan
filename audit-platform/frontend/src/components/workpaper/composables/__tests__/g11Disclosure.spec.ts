/**
 * G11 附注披露 — 分项带入与行结构
 */
import { describe, it, expect } from 'vitest'
import {
  G11_LISTED_DISC_SCHEMA,
  G11_SOE_DISC_SCHEMA,
  G11_DISCLOSURE_COL_LABELS,
  G11_LISTED_TRADING_DISPOSE_ROWS,
  isG11DisclosureLeaf,
  G11_LISTED_MAIN_ROW_KEYS,
  G11_ADJUDICATED_KEY,
  G11_DISCLOSURE_LISTED_KEY,
  G11_DISCLOSURE_SOE_KEY,
} from '../g11SchemaRows'
import {
  buildG11DisclosureAmountsFromAdjStore,
  buildG11DisclosureAmountsFromDetailRows,
  buildG11TradingDisposeFromDetailRows,
  mergeG11DisclosureAmounts,
  applyG11DisclosureAmountsToRows,
  applyG11DisclosurePullToResponses,
  formatG11DiscPullSummary,
  g11DetailItemToRowKey,
  g11TradingDisposeSubtype,
  sumG11DisclosureLeafCurrent,
  sumG11TradingDisposeCurrent,
  computeG11DisclosurePull,
  parseG11DiscStore,
  summarizeG11DisclosureDirectoryStatus,
} from '../g11DisclosureFromAdj'
import { defaultG11AdjStore, patchG11AdjRow } from '../g11AdjStorage'
import { G11_DISCLOSURE_LISTED_ROWS, G11_DISCLOSURE_SOE_ROWS } from '../g11Constants'
import type { ChecklistResponse } from '../useF1FormData'

describe('G11 附注披露行结构', () => {
  it('上市/国企表头与 Excel 一致', () => {
    expect(G11_DISCLOSURE_COL_LABELS.listed.current).toBe('本期发生额')
    expect(G11_DISCLOSURE_COL_LABELS.soe.prior).toBe('上期发生额')
  })

  it('主表 leaf 计入合计，「其中/减」不计', () => {
    expect(isG11DisclosureLeaf('equity_method')).toBe(true)
    expect(isG11DisclosureLeaf('listed_sub_1')).toBe(false)
    expect(isG11DisclosureLeaf('soe_sub_3')).toBe(false)
    expect(G11_LISTED_DISC_SCHEMA.filter((r) => r.isLeaf).length).toBe(G11_LISTED_MAIN_ROW_KEYS.size)
    expect(G11_SOE_DISC_SCHEMA.filter((r) => !r.isLeaf)).toHaveLength(7)
  })

  it('与 constants 行数一致', () => {
    expect(G11_LISTED_DISC_SCHEMA).toHaveLength(G11_DISCLOSURE_LISTED_ROWS.length)
    expect(G11_SOE_DISC_SCHEMA).toHaveLength(G11_DISCLOSURE_SOE_ROWS.length)
  })

  it('上市处置交易性子表 5 行对齐 Excel', () => {
    expect(G11_LISTED_TRADING_DISPOSE_ROWS).toHaveLength(5)
    expect(G11_LISTED_TRADING_DISPOSE_ROWS.map((r) => r.rowKey)).toEqual([
      'equity_stock',
      'debt_bond',
      'derivative_non_hedge',
      'derivative_hedge',
      'other',
    ])
  })
})

describe('g11DetailItemToRowKey', () => {
  it('精确与别名映射', () => {
    expect(g11DetailItemToRowKey('权益法核算的长期股权投资收益')).toBe('equity_method')
    expect(g11DetailItemToRowKey('其他债权投资持有期间的利息收入')).toBe('oth_debt_hold_interest')
    expect(g11DetailItemToRowKey('债权投资持有期间的利息收入')).toBe('debt_hold_interest')
    expect(g11DetailItemToRowKey('处置交易性金融资产取得的投资收益')).toBe('trading_dispose')
  })
})

describe('处置交易性子表映射', () => {
  it('按文本拆分股票/债券/衍生/套期', () => {
    expect(g11TradingDisposeSubtype('某某股票')).toBe('equity_stock')
    expect(g11TradingDisposeSubtype('国债债券投资')).toBe('debt_bond')
    expect(g11TradingDisposeSubtype('外汇远期合约')).toBe('derivative_non_hedge')
    expect(g11TradingDisposeSubtype('公允价值套期')).toBe('derivative_hedge')
  })

  it('G11-2 明细灌入子表，骨架整笔行跳过', () => {
    const { amounts, filled } = buildG11TradingDisposeFromDetailRows([
      {
        rowKey: 'trading_dispose',
        itemName: '处置交易性金融资产取得的投资收益',
        investeeName: '',
        currentAudited: 999,
        priorAudited: 0,
      },
      {
        rowKey: 'trading_dispose',
        itemName: '处置交易性',
        investeeName: 'A股股票',
        currentAudited: 40,
        priorAudited: 10,
      },
      {
        rowKey: 'trading_dispose',
        itemName: '处置',
        investeeName: '商品期货',
        currentAudited: 15,
        priorAudited: 0,
      },
    ])
    expect(filled).toContain('equity_stock')
    expect(filled).toContain('derivative_non_hedge')
    expect(amounts.equity_stock.currentAmount).toBe(40)
    expect(amounts.derivative_non_hedge.currentAmount).toBe(15)
    expect(sumG11TradingDisposeCurrent(amounts)).toBe(55)
  })

  it('显式 tradingDisposeSubtype 优先于文本推断', () => {
    const { amounts, filled } = buildG11TradingDisposeFromDetailRows([
      {
        rowKey: 'trading_dispose',
        itemName: '处置',
        investeeName: '某股票',
        tradingDisposeSubtype: 'derivative_hedge',
        currentAudited: 30,
        priorAudited: 0,
      },
    ])
    expect(filled).toEqual(['derivative_hedge'])
    expect(amounts.derivative_hedge.currentAmount).toBe(30)
    expect(amounts.equity_stock.currentAmount).toBe(0)
  })
})

describe('G11 附注 ← G11-1/G11-2 分项带入', () => {
  it('G11-1 审定数映射到披露行', () => {
    let store = defaultG11AdjStore()
    store = patchG11AdjRow(store, 'equity_method', {
      currentUnadjusted: 100,
      currentAdjustment: 10,
      priorUnadjusted: 40,
    })
    store = patchG11AdjRow(store, 'trading_dispose', {
      currentUnadjusted: 50,
      priorUnadjusted: 20,
    })
    const amounts = buildG11DisclosureAmountsFromAdjStore(store)
    expect(amounts.equity_method.currentAmount).toBe(110)
    expect(amounts.equity_method.priorAmount).toBe(40)
    expect(amounts.trading_dispose.currentAmount).toBe(50)
  })

  it('G11-2 明细按项目汇总，明细优先于审定', () => {
    const fromAdj = buildG11DisclosureAmountsFromAdjStore(
      patchG11AdjRow(defaultG11AdjStore(), 'equity_method', { currentUnadjusted: 1 }),
    )
    const fromDetail = buildG11DisclosureAmountsFromDetailRows([
      { itemName: '权益法核算的长期股权投资收益', currentAudited: 200, priorAudited: 80 },
      { itemName: '处置交易性金融资产取得的投资收益', currentAudited: 30, priorAudited: 0 },
    ])
    const { amounts, sources } = mergeG11DisclosureAmounts(fromAdj, fromDetail)
    expect(amounts.equity_method.currentAmount).toBe(200)
    expect(sources.equity_method).toBe('detail')
    expect(amounts.trading_dispose.currentAmount).toBe(30)
    expect(sources.trading_dispose).toBe('detail')
  })

  it('无分项时残差写入「其他」', () => {
    const rows = G11_DISCLOSURE_SOE_ROWS.map((d) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: 0,
      priorAmount: 0,
      remark: '',
    }))
    const amounts = buildG11DisclosureAmountsFromAdjStore(defaultG11AdjStore())
    const result = applyG11DisclosureAmountsToRows(rows, amounts, 'soe', {
      residualCurrent: 888,
      residualPrior: 0,
    })
    expect(result.usedResidual).toBe(true)
    expect(result.next.find((r) => r.rowKey === 'other')?.currentAmount).toBe(888)
    expect(result.sources.other).toBe('residual')
  })

  it('合计排除「其中」子行，避免双计', () => {
    const sum = sumG11DisclosureLeafCurrent([
      { rowKey: 'equity_method', currentAmount: 100 },
      { rowKey: 'listed_sub_1', currentAmount: 100 },
      { rowKey: 'other', currentAmount: 20 },
    ])
    expect(sum).toBe(120)
  })

  it('computeG11DisclosurePull 从 responses 带入上市主表', () => {
    const store = patchG11AdjRow(defaultG11AdjStore(), 'trading_hold', {
      currentUnadjusted: 60,
      priorUnadjusted: 10,
    })
    const responses = new Map<string, ChecklistResponse>([
      ['G11-adj-rows', { item_id: 'G11-adj-rows', conclusion: null, remark: JSON.stringify(store) }],
      ['G11-1-adjudicated-amount', { item_id: 'G11-1-adjudicated-amount', conclusion: '60', remark: null }],
    ])
    const rows = G11_DISCLOSURE_LISTED_ROWS.map((d) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: 0,
      priorAmount: 0,
      remark: '',
    }))
    const result = computeG11DisclosurePull(responses, rows, 'listed')
    expect(result.filledKeys).toContain('trading_hold')
    expect(result.next.find((r) => r.rowKey === 'trading_hold')?.currentAmount).toBe(60)
    expect(result.usedResidual).toBe(false)
    expect(formatG11DiscPullSummary(result.sources, false, result.filledKeys)).toContain('G11-1')
  })

  it('旧数组 store 可迁移为 v2', () => {
    const legacy = JSON.stringify([
      { rowKey: 'equity_method', label: '权益法', currentAmount: 10, priorAmount: 1, remark: '' },
    ])
    const store = parseG11DiscStore(legacy, 'listed')
    expect(store.version).toBe(2)
    expect(store.rows.find((r) => r.rowKey === 'equity_method')?.currentAmount).toBe(10)
    expect(store.tradingDispose).toBeDefined()
  })

  it('applyG11DisclosurePullToResponses 同步上市与国企', () => {
    const adjStore = patchG11AdjRow(defaultG11AdjStore(), 'equity_method', {
      currentUnadjusted: 100,
      priorUnadjusted: 40,
    })
    const responses = new Map<string, ChecklistResponse>([
      ['G11-adj-rows', { item_id: 'G11-adj-rows', conclusion: null, remark: JSON.stringify(adjStore) }],
      ['G11-1-adjudicated-amount', { item_id: 'G11-1-adjudicated-amount', conclusion: '100', remark: null }],
      ['G11-detail-rows', {
        item_id: 'G11-detail-rows',
        conclusion: null,
        remark: JSON.stringify([
          {
            rowKey: 'trading_dispose',
            itemName: '处置',
            investeeName: '股票A',
            currentAudited: 25,
            priorAudited: 5,
          },
        ]),
      }],
    ])
    const saved: string[] = []
    const batch = applyG11DisclosurePullToResponses(responses, (id) => { saved.push(id) })
    expect(saved).toContain('G11-disclosure-listed')
    expect(saved).toContain('G11-disclosure-soe')
    expect(batch.listedStore.rows.find((r) => r.rowKey === 'equity_method')?.currentAmount).toBe(100)
    expect(batch.soeStore.rows.find((r) => r.rowKey === 'equity_method')?.currentAmount).toBe(100)
    expect(batch.tradingDisposeFilled).toBe(1)
    expect(batch.listedStore.tradingDispose?.equity_stock.currentAmount).toBe(25)
    expect(batch.soeStore.repatriationNote).toContain('重大限制')
  })
})

describe('summarizeG11DisclosureDirectoryStatus', () => {
  it('汇总上市/国企附注编制与审定勾稽', () => {
    const listedStore = {
      version: 2,
      rows: [
        { rowKey: 'equity_method', label: '权益法', currentAmount: 100, priorAmount: 40, remark: '' },
        { rowKey: 'other', label: '其他', currentAmount: 0, priorAmount: 0, remark: '' },
      ],
      tradingDispose: {
        equity_stock: { currentAmount: 25, priorAmount: 5 },
        debt_bond: { currentAmount: 0, priorAmount: 0 },
        derivative_non_hedge: { currentAmount: 0, priorAmount: 0 },
        derivative_hedge: { currentAmount: 0, priorAmount: 0 },
        other: { currentAmount: 0, priorAmount: 0 },
      },
    }
    const soeStore = {
      version: 2,
      rows: [{ rowKey: 'equity_method', label: '权益法', currentAmount: 100, priorAmount: 40, remark: '' }],
      repatriationNote: '无重大限制',
    }
    const m = new Map<string, { remark?: string; conclusion?: string }>([
      [G11_ADJUDICATED_KEY, { conclusion: '100' }],
      [G11_DISCLOSURE_LISTED_KEY, { remark: JSON.stringify(listedStore) }],
      [G11_DISCLOSURE_SOE_KEY, { remark: JSON.stringify(soeStore) }],
    ])
    const store = parseG11DiscStore(JSON.stringify(listedStore), 'listed')
    expect(store.rows.find((r) => r.rowKey === 'equity_method')?.currentAmount).toBe(100)
    const status = summarizeG11DisclosureDirectoryStatus(m)
    expect(status.adjudicated).toBe(100)
    const listed = status.variants.find((v) => v.code === '附注上市')
    expect(listed?.crossOk).toBe(true)
    expect(listed?.filled).toBe(true)
    const soe = status.variants.find((v) => v.code === '附注国企')
    expect(soe?.crossOk).toBe(true)
  })
})
