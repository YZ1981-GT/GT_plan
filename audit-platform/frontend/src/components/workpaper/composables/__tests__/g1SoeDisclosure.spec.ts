/**
 * G1 国企披露行结构 / 审定取数 / 附注章节映射契约测试
 */
import { describe, it, expect } from 'vitest'
import {
  G1_NOTE_SECTION,
  isG1DisclosureApplicable,
  resolveG1NoteSectionTarget,
} from '../g1NoteSectionMap'
import {
  buildDefaultTradingRows,
  extractSoeAmountsFromAdjStore,
  parseSoePersisted,
  serializeSoeRows,
  sumCarryingAmounts,
  tradingTotal,
  G1_SOE_TRADING_ROW_DEFS,
} from '../g1SoeDisclosureRows'
import { buildG1AdjudicationRows } from '../useG1Adjudication'
import {
  buildG1SoeSyncPayloads,
  buildG1SoeTradingSubTableData,
} from '../g1DisclosureSyncPayload'

describe('g1NoteSectionMap', () => {
  it('国企映射到八、2 / 八、3', () => {
    expect(G1_NOTE_SECTION.soe.trading).toBe('八、2')
    expect(G1_NOTE_SECTION.soe.derivative).toBe('八、3')
    const t = resolveG1NoteSectionTarget('soe', ['soe_standalone'])
    expect(t?.tradingSectionId).toBe('八、2')
    expect(t?.derivativeSectionId).toBe('八、3')
  })

  it('上市准则下国企页不适用', () => {
    expect(isG1DisclosureApplicable('soe', ['listed_standalone'])).toBe(false)
    expect(resolveG1NoteSectionTarget('soe', ['listed_standalone'])).toBeNull()
  })

  it('空准则允许编制', () => {
    expect(isG1DisclosureApplicable('soe', [])).toBe(true)
  })
})

describe('g1SoeDisclosureRows', () => {
  it('固定层级含分类/指定及其中项', () => {
    const keys = G1_SOE_TRADING_ROW_DEFS.map((d) => d.rowKey)
    expect(keys).toContain('classified-debt')
    expect(keys).toContain('classified-equity')
    expect(keys).toContain('designated-other')
    expect(keys).not.toContain('total')
  })

  it('从 G1-1 carrying 聚合分类债务/衍生', () => {
    const store = {
      'cost-trading-debt': { closingUnadjusted: 100, openingUnadjusted: 80 },
      'fv-trading-debt': { closingUnadjusted: 10, openingUnadjusted: 5 },
      'cost-trading-derivative': { closingUnadjusted: 50, openingUnadjusted: 40 },
      'fv-trading-derivative': { closingUnadjusted: 2, openingUnadjusted: 1 },
      'cost-designated-debt': { closingUnadjusted: 20, openingUnadjusted: 15 },
      'fv-designated-debt': { closingUnadjusted: 0, openingUnadjusted: 0 },
    }
    const amounts = extractSoeAmountsFromAdjStore(JSON.stringify(store))
    // carrying = cost + fv
    expect(amounts['classified-debt'].endAmount).toBe(110)
    expect(amounts['classified-debt'].priorAmount).toBe(85)
    expect(amounts['designated-debt'].endAmount).toBe(20)
    expect(amounts.derivative.endAmount).toBe(52)

    const rows = buildDefaultTradingRows(amounts)
    const total = tradingTotal(rows)
    expect(total.endAmount).toBe(110 + 20) // classified cat + designated cat（不含衍生）
  })

  it('衍生不计入交易性「其他」', () => {
    const adj = buildG1AdjudicationRows({
      'cost-trading-other': { closingUnadjusted: 7, openingUnadjusted: 3 },
      'fv-trading-other': { closingUnadjusted: 0, openingUnadjusted: 0 },
      'cost-trading-derivative': { closingUnadjusted: 100, openingUnadjusted: 90 },
      'fv-trading-derivative': { closingUnadjusted: 0, openingUnadjusted: 0 },
    })
    const other = sumCarryingAmounts(adj, ['trading', 'classified'], ['wealth', 'structured', 'fund', 'other'])
    expect(other.endAmount).toBe(7)
    const deriv = sumCarryingAmounts(adj, ['trading', 'classified', 'designated'], ['derivative'])
    expect(deriv.endAmount).toBe(100)
  })

  it('v2 序列化往返', () => {
    const trading = buildDefaultTradingRows({
      'classified-debt': { endAmount: 1, priorAmount: 2 },
    })
    const json = serializeSoeRows(trading, [])
    const parsed = parseSoePersisted(json)
    expect(parsed?.trading.find((r) => r.rowKey === 'classified-debt')?.endAmount).toBe(1)
    expect(parsed?.trading.find((r) => r.rowKey === 'classified')?.endAmount).toBe(1)
  })
})

describe('g1DisclosureSyncPayload', () => {
  it('构建八、2 / 八、3 两个 sync payload', () => {
    const trading = buildDefaultTradingRows({
      'classified-debt': { endAmount: 100, priorAmount: 80 },
    })
    const payloads = buildG1SoeSyncPayloads('wp-1', ['soe_standalone'], {
      tradingRows: trading,
      derivativeRows: [{ rowId: 'd1', label: '远期', endAmount: 10, priorAmount: 5, reason: '套保', autoFilled: false }],
      fvBasisNote: '活跃市场报价',
      derivativeTipNote: '前十大',
      auditNote: '未见异常',
    })
    expect(payloads).toHaveLength(2)
    expect(payloads[0].section_id).toBe('八、2')
    expect(payloads[1].section_id).toBe('八、3')
    expect(payloads[0].sub_table_data['交易性金融资产']?.some((r) => r.is_total)).toBe(true)
    expect(payloads[1].sub_table_data['衍生金融资产']?.[0].label).toBe('远期')
  })

  it('上市准则下不生成 payload', () => {
    expect(buildG1SoeSyncPayloads('wp', ['listed_standalone'], {
      tradingRows: [],
      derivativeRows: [],
      fvBasisNote: '',
      derivativeTipNote: '',
      auditNote: '',
    })).toEqual([])
  })

  it('交易性子表含公允价值字段', () => {
    const trading = buildDefaultTradingRows()
    const data = buildG1SoeTradingSubTableData({
      tradingRows: trading,
      derivativeRows: [],
      fvBasisNote: '依据',
      derivativeTipNote: '',
      auditNote: '',
    })
    const first = data['交易性金融资产']![0]
    expect(first).toHaveProperty('end_fair_value')
    expect(first).toHaveProperty('prior_fair_value')
    expect(data._note_texts?.[0].text).toBe('依据')
  })
})
