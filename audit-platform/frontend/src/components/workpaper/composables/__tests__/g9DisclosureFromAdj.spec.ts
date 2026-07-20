/**
 * g9DisclosureFromAdj — 附注分项带入（G9-1 + G9-2）
 */
import { describe, expect, it } from 'vitest'
import { defaultG9AdjStore, patchG9AdjRow } from '../g9AdjStorage'
import {
  buildG9DisclosureAmountsFromAdjStore,
  buildG9DisclosureAmountsFromDetailRows,
  mergeG9DisclosureAmounts,
  applyG9DisclosureAmountsToStore,
  formatG9DiscPullSummary,
  g9DiscLabelToBucket,
} from '../g9DisclosureFromAdj'
import { G9_DISCLOSURE_LISTED_SCHEMA, G9_DISCLOSURE_COL_LABELS } from '../g9SchemaRows'
import { buildG9CrossChecks } from '../g9CrossHelpers'
import type { ChecklistResponse } from '../useF1FormData'

describe('g9DiscLabelToBucket', () => {
  it('映射四类披露行', () => {
    expect(g9DiscLabelToBucket('债务工具投资')).toBe('debt')
    expect(g9DiscLabelToBucket('权益工具投资')).toBe('equity')
    expect(g9DiscLabelToBucket('指定为以公允价值计量且其变动计入当期损益的金融资产')).toBe('designated')
    expect(g9DiscLabelToBucket('其他')).toBe('other')
  })
})

describe('G9_DISCLOSURE_COL_LABELS', () => {
  it('上市/国企表头与 Excel 一致', () => {
    expect(G9_DISCLOSURE_COL_LABELS.listed.current).toBe('期末余额')
    expect(G9_DISCLOSURE_COL_LABELS.soe.current).toBe('期末公允价值')
  })
})

describe('buildG9DisclosureAmountsFromAdjStore', () => {
  it('跨组汇总债务/权益分项', () => {
    let store = defaultG9AdjStore()
    store = patchG9AdjRow(store, 'fvtpl_22', { closingUnadjusted: 100, openingUnadjusted: 40 })
    store = patchG9AdjRow(store, 'fvoci_22', { closingUnadjusted: 50, openingUnadjusted: 10 })
    store = patchG9AdjRow(store, 'fvtpl_21', { closingUnadjusted: 200, openingUnadjusted: 80 })
    const amounts = buildG9DisclosureAmountsFromAdjStore(store)
    expect(amounts.debt.currentAmount).toBe(150)
    expect(amounts.equity.currentAmount).toBe(200)
  })
})

describe('buildG9DisclosureAmountsFromDetailRows', () => {
  it('按工具种类与指定汇总', () => {
    const amounts = buildG9DisclosureAmountsFromDetailRows([
      { instrumentType: '债务工具投资', closingAdjusted: 100, openingAdjusted: 40 },
      { instrumentType: '权益工具投资', closingAdjusted: 50, openingAdjusted: 10 },
      {
        instrumentType: '债务工具投资',
        isDesignated: true,
        classification: 'FVTPL',
        closingAdjusted: 30,
        openingAdjusted: 5,
      },
      { instrumentType: '衍生金融资产', closingAdjusted: 8, openingAdjusted: 0 },
    ])
    expect(amounts.debt.currentAmount).toBe(100)
    expect(amounts.equity.currentAmount).toBe(50)
    expect(amounts.designated.currentAmount).toBe(30)
    expect(amounts.other.currentAmount).toBe(8)
  })
})

describe('mergeG9DisclosureAmounts', () => {
  it('明细有数优先，否则用审定', () => {
    const fromAdj = {
      debt: { currentAmount: 1, priorAmount: 0 },
      equity: { currentAmount: 2, priorAmount: 0 },
      designated: { currentAmount: 0, priorAmount: 0 },
      other: { currentAmount: 9, priorAmount: 0 },
    }
    const fromDetail = {
      debt: { currentAmount: 100, priorAmount: 40 },
      equity: { currentAmount: 0, priorAmount: 0 },
      designated: { currentAmount: 30, priorAmount: 5 },
      other: { currentAmount: 0, priorAmount: 0 },
    }
    const { amounts, sources } = mergeG9DisclosureAmounts(fromAdj, fromDetail)
    expect(amounts.debt.currentAmount).toBe(100)
    expect(sources.debt).toBe('detail')
    expect(amounts.equity.currentAmount).toBe(2)
    expect(sources.equity).toBe('adj')
    expect(amounts.designated.currentAmount).toBe(30)
    expect(sources.designated).toBe('detail')
    expect(amounts.other.currentAmount).toBe(9)
    expect(sources.other).toBe('adj')
  })
})

describe('applyG9DisclosureAmountsToStore', () => {
  it('无分项时残差进其他', () => {
    const amounts = {
      debt: { currentAmount: 0, priorAmount: 0 },
      equity: { currentAmount: 0, priorAmount: 0 },
      designated: { currentAmount: 0, priorAmount: 0 },
      other: { currentAmount: 0, priorAmount: 0 },
    }
    const { next, usedResidual, sources } = applyG9DisclosureAmountsToStore(
      G9_DISCLOSURE_LISTED_SCHEMA,
      {},
      amounts,
      { residualCurrent: 999, residualPrior: 100 },
    )
    expect(usedResidual).toBe(true)
    expect(next.listed_4.currentAmount).toBe(999)
    expect(sources.other).toBe('residual')
    expect(formatG9DiscPullSummary(sources, true)).toContain('残差')
  })
})

describe('l3-disclosure-note-missing', () => {
  it('有 L3 余额且附注未提及时给出 info 软校验', () => {
    const m = new Map<string, ChecklistResponse>()
    m.set('G9-detail-rows', {
      item_id: 'G9-detail-rows',
      remark: JSON.stringify([
        { assetName: 'A', fairValueLevel: 'Level3', closingAdjusted: 500 },
      ]),
    } as ChecklistResponse)
    const checks = buildG9CrossChecks(m, { disclosureNoteText: '本年无重大变动' })
    expect(checks.some((c) => c.code === 'l3-disclosure-note-missing')).toBe(true)
  })

  it('附注已提及第三层次则不提示', () => {
    const m = new Map<string, ChecklistResponse>()
    m.set('G9-detail-rows', {
      item_id: 'G9-detail-rows',
      remark: JSON.stringify([
        { assetName: 'A', fairValueLevel: 'Level3', closingAdjusted: 500 },
      ]),
    } as ChecklistResponse)
    const checks = buildG9CrossChecks(m, {
      disclosureNoteText: '第三层次公允价值调节过程已披露',
    })
    expect(checks.some((c) => c.code === 'l3-disclosure-note-missing')).toBe(false)
  })
})
