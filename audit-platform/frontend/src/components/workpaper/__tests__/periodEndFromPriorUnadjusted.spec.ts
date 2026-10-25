/**
 * D 循环明细表「期末余额族」以期初未审起算（spec oo-formula-recompute-not-tamper R4）。
 *
 * 权威模板 D1-2 / D1-3 / D2-2 / D3-2 / D5-2 / D6-2 / D7-2 的期末余额（或期末未审）列公式都从
 * 「期初未审」起算，不含期初账项调整 / 重分类调整；D5-2 的期末审定取期末余额列、不含被审计单位
 * 重分类。表单原先按「期初审定」（D5-2 审定按「期末未审」）算，有期初调整的行在表单与
 * OnlyOffice 之间来回变值：OO 按模板公式重算公式格，保存回来公式格的值与表单值对不上。
 * 先例：useF1Detail.recalcRowFormulas（F1-2 裁决 F1-H3「以模板为准」）。
 *
 * 每个写入点都用同一组「期初调整非 0」的数直接走生产代码，并先断言旧口径算出的值不同
 * （样例能区分两种口径）——回退任意一处都会打红。
 *
 * 第二组（触类旁通，全仓扫「期初审定作滚动起点」后逐个对照模板）：D2-3 / G2-3 / G5-3 / K1-3
 * 坏账准备滚动表与 G2-2 应收利息明细同一问题，连同两处跨表读取（G2-3 → G2-1 / 附注、
 * G5-3 → G5-1 / 上市附注）一起改。
 */
import { mount } from '@vue/test-utils'
import { describe, expect, it, vi } from 'vitest'
import { defineComponent, ref } from 'vue'

import type { ChecklistResponse } from '../composables/useD1FormData'

vi.mock('@/composables/useAgingConfig', async (importOriginal) => {
  const actual = await importOriginal<typeof import('@/composables/useAgingConfig')>()
  return {
    ...actual,
    useAgingConfig: () => ({
      segments: ref([]), bands: ref([]), preset: ref(''), loading: ref(false), refresh: vi.fn(),
    }),
  }
})

const { useD1DetailCategory } = await import('../composables/useD1DetailCategory')
const { useD1DetailCustomer } = await import('../composables/useD1DetailCustomer')
const { useD1MemoReconciliation } = await import('../composables/useD1MemoReconciliation')
const { useD2Detail } = await import('../composables/useD2Detail')
const { recalcRowFormulas: recalcD3, createEmptyRow: emptyD3 } = await import('../composables/useD3Detail')
const { recalcRow: recalcD5, createEmptyRow: emptyD5 } = await import('../composables/useD5Detail')
const { recalcRow: recalcD6, createEmptyRow: emptyD6 } = await import('../composables/useD6Detail')
const { recalcRow: recalcD7, createEmptyRow: emptyD7 } = await import('../composables/useD7Detail')
const { useD2BadDebt } = await import('../composables/useD2BadDebt')
const { useG2Detail } = await import('../composables/useG2Detail')
const { buildBadDebtDisplayRows: buildG23Rows } = await import('../composables/useG2BadDebtDetail')
const { loadG2BadDebtLeaves } = await import('../composables/g2CrossHelpers')
const { computeMovement: computeG53, buildDisplayRows: buildG53Rows } = await import('../composables/useG5BadDebtDetail')
const { aggregateProvisionFromG53 } = await import('../composables/g5CrossHelpers')
const { extractBadDebtForDisclosure } = await import('../composables/g5ListedDisclosureRows')
const { recalcK1BadDebtMainRow } = await import('../composables/useK1BadDebt')

// ─── 同一组样例：期初未审 1000，期初调整 200 + 50（期初审定 1250），本期增加 300、减少 100 ──
const PRIOR_UNADJUSTED = 1000
const PRIOR_AJE = 200
const PRIOR_RJE = 50
const INCREASE = 300
const DECREASE = 100
const RECLASS = 30
const END_AJE = 7
const END_RJE = 3

const PRIOR_AUDITED = PRIOR_UNADJUSTED + PRIOR_AJE + PRIOR_RJE // 1250
/** 模板口径：期初未审 + 增加 - 减少 */
const END_FROM_UNADJUSTED = PRIOR_UNADJUSTED + INCREASE - DECREASE // 1200
/** 旧口径：期初审定 + 增加 - 减少 */
const END_FROM_AUDITED = PRIOR_AUDITED + INCREASE - DECREASE // 1450

function responses(entries: Record<string, unknown>) {
  const map = new Map<string, ChecklistResponse>()
  for (const [key, value] of Object.entries(entries)) {
    map.set(key, { item_id: key, conclusion: null, remark: JSON.stringify(value) } as ChecklistResponse)
  }
  return ref(map)
}

/** 在组件 setup 里跑 composable（生命周期钩子有宿主，不产生告警） */
function withSetup<T>(fn: () => T): T {
  let result!: T
  mount(defineComponent({
    setup() {
      result = fn()
      return () => null
    },
  }))
  return result
}

const baseOptions = () => ({
  wpId: ref('wp-1'),
  projectId: ref('proj-1'),
  saveImmediate: vi.fn(async () => {}),
  isReadonly: ref(false),
})

describe('期末余额族以期初未审起算（与权威模板一致）', () => {
  it('样例能区分两种口径', () => {
    expect(END_FROM_UNADJUSTED).not.toBe(END_FROM_AUDITED)
  })

  it('D1-2 按类别：期末未审 H = B + F - G', () => {
    const { rows } = withSetup(() => useD1DetailCategory({
      ...baseOptions(),
      allResponses: responses({
        'D1-cat-rows': [{
          rowId: 'fixed-bank', category: '银行承兑汇票', isFixed: true,
          priorUnadjusted: PRIOR_UNADJUSTED, priorAje: PRIOR_AJE, priorRje: PRIOR_RJE,
          currentIncrease: INCREASE, currentDecrease: DECREASE,
          currentAje: END_AJE, currentRje: END_RJE,
        }],
      }),
    }))
    const row = rows.value.find((r) => r.rowId === 'fixed-bank')!
    expect(row.priorAudited).toBe(PRIOR_AUDITED)
    expect(row.currentUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(row.currentAudited).toBe(END_FROM_UNADJUSTED + END_AJE + END_RJE)
  })

  it('D1-3 按客户：期末余额 J = D + H - I', () => {
    const { rows } = withSetup(() => useD1DetailCustomer({
      ...baseOptions(),
      relatedParties: ref<string[]>([]),
      allResponses: responses({
        'D1-cust-rows': [{
          rowId: 'cust-1', customerName: '甲公司', companyCode: 'A001', relationType: '非关联方',
          priorUnadjusted: PRIOR_UNADJUSTED, priorAje: PRIOR_AJE, priorRje: PRIOR_RJE,
          currentIncrease: INCREASE, currentDecrease: DECREASE,
          reclassification: RECLASS, currentAje: END_AJE, currentRje: END_RJE,
        }],
      }),
    }))
    const row = rows.value[0]
    expect(row.currentBalance).toBe(END_FROM_UNADJUSTED)
    expect(row.currentUnadjusted).toBe(END_FROM_UNADJUSTED + RECLASS)
    expect(row.currentAudited).toBe(END_FROM_UNADJUSTED + RECLASS + END_AJE + END_RJE)
  })

  it('D1-7 备查簿核对：明细账(D1-2) 行与 D1-2 同口径', () => {
    const { reconciliationRows } = withSetup(() => useD1MemoReconciliation({
      ...baseOptions(),
      allResponses: responses({
        'D1-cat-rows': [{
          priorUnadjusted: PRIOR_UNADJUSTED, priorAje: PRIOR_AJE, priorRje: PRIOR_RJE,
          currentIncrease: INCREASE, currentDecrease: DECREASE,
          currentAje: END_AJE, currentRje: END_RJE,
        }],
      }),
    }))
    const ledger = reconciliationRows.value[1]
    expect(ledger.label).toBe('明细账(D1-2)')
    expect(ledger.beginningBalance).toBe(PRIOR_AUDITED)
    expect(ledger.endingBalance).toBe(END_FROM_UNADJUSTED + END_AJE + END_RJE)
  })

  it('D2-2：期末余额 Q = E + O - P', () => {
    const api = withSetup(() => useD2Detail({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      isReadonly: ref(false),
      relatedParties: ref([]),
      allResponses: responses({
        'D2-detail-rows': [{
          rowId: 'dr-1', seq: 1, customerName: '甲公司', companyCode: '',
          priorUnadjusted: PRIOR_UNADJUSTED, priorAje: PRIOR_AJE, priorRje: PRIOR_RJE,
          debitOccurrence: INCREASE, creditOccurrence: DECREASE,
          reclassification: RECLASS, currentAje: END_AJE, currentRje: END_RJE,
        }],
      }),
    } as never))
    const row = api.rows.value[0]
    expect(row.priorAudited).toBe(PRIOR_AUDITED)
    expect(row.endBalance).toBe(END_FROM_UNADJUSTED)
    expect(row.currentUnadjusted).toBe(END_FROM_UNADJUSTED + RECLASS)
    expect(row.currentAudited).toBe(END_FROM_UNADJUSTED + RECLASS + END_AJE + END_RJE)
  })

  it('D3-2（贷方科目）：期末余额 O = E + N - M', () => {
    const row = recalcD3({
      ...emptyD3(),
      priorUnadjusted: PRIOR_UNADJUSTED, priorAdjustment: PRIOR_AJE, priorReclass: PRIOR_RJE,
      credit: INCREASE, debit: DECREASE,
      entityReclass: RECLASS, endAje: END_AJE, endRje: END_RJE,
    })
    expect(row.priorAudited).toBe(PRIOR_AUDITED)
    expect(row.endBalance).toBe(END_FROM_UNADJUSTED)
    expect(row.endUnadjusted).toBe(END_FROM_UNADJUSTED + RECLASS)
    expect(row.endAudited).toBe(END_FROM_UNADJUSTED + RECLASS + END_AJE + END_RJE)
  })

  it('D5-2：期末余额 J = C + H - I，期末审定 O = J + M + N（不含重分类 K）', () => {
    const row = recalcD5({
      ...emptyD5(),
      priorUnadjusted: PRIOR_UNADJUSTED, priorAje: PRIOR_AJE, priorRje: PRIOR_RJE,
      periodIncrease: INCREASE, periodDecrease: DECREASE,
      entityReclass: RECLASS, endAje: END_AJE, endRje: END_RJE,
    })
    expect(row.priorAudited).toBe(PRIOR_AUDITED)
    expect(row.endBalance).toBe(END_FROM_UNADJUSTED)
    expect(row.endUnadjusted).toBe(END_FROM_UNADJUSTED + RECLASS)
    // 旧口径取期末未审 L：两者相差的正好是重分类 K
    expect(row.endAudited).toBe(END_FROM_UNADJUSTED + END_AJE + END_RJE)
    expect(row.endAudited).not.toBe(row.endUnadjusted + END_AJE + END_RJE)
  })

  it('D6-2（借方科目）：期末未审 Q = G + O - P', () => {
    const row = recalcD6({
      ...emptyD6(1),
      priorUnadjusted: PRIOR_UNADJUSTED, priorAje: PRIOR_AJE, priorRje: PRIOR_RJE,
      debitAmount: INCREASE, creditAmount: DECREASE,
      endAje: END_AJE, endRje: END_RJE,
    })
    expect(row.priorAudited).toBe(PRIOR_AUDITED)
    expect(row.endUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(row.endAudited).toBe(END_FROM_UNADJUSTED + END_AJE + END_RJE)
  })

  it('D7-2（贷方科目）：期末余额 = 期初未审 - 借方 + 贷方', () => {
    const row = recalcD7({
      ...emptyD7(),
      priorUnadjusted: PRIOR_UNADJUSTED, priorAje: PRIOR_AJE, priorRje: PRIOR_RJE,
      creditAmount: INCREASE, debitAmount: DECREASE,
      entityReclass: RECLASS, endAje: END_AJE, endRje: END_RJE,
    })
    expect(row.priorAudited).toBe(PRIOR_AUDITED)
    expect(row.endBalance).toBe(END_FROM_UNADJUSTED)
    expect(row.endUnadjusted).toBe(END_FROM_UNADJUSTED + RECLASS)
    expect(row.endAudited).toBe(END_FROM_UNADJUSTED + RECLASS + END_AJE + END_RJE)
  })
})

// ─── 触类旁通：坏账准备滚动表与 G2-2（模板同样从期初未审起算）──────────────────
// 模板 D2-3 K = B + SUM(F:G) − SUM(H:J)；G2-3 / G5-3 / K1-3 J = B + SUM(E:F) − SUM(G:I)；
// G2-2 H = C + F − G。本期增加拆成计提 200 + 其他增加 100、减少拆成转回 60 + 核销 30 + 其他减少 10，
// 合计仍是 300 / 100，期末账项调整 = END_AJE + END_RJE。
const PROVISION = 200
const OTHER_INCREASE = INCREASE - PROVISION // 100
const REVERSAL = 60
const WRITE_OFF = 30
const OTHER_DECREASE = DECREASE - REVERSAL - WRITE_OFF // 10
const OPENING_ADJ = PRIOR_AJE + PRIOR_RJE // 单列的期初调整
const CLOSING_ADJ = END_AJE + END_RJE

/** G2-3 / G5-3 同形 leaf（字段名两表相同） */
const movementLeaf = (category: 'individual' | 'portfolio' = 'individual') => ({
  id: `${category}-1`, seq: 1, category, item: '甲公司', portfolioType: '' as const, reason: '',
  openingUnadjusted: PRIOR_UNADJUSTED, openingAdjustment: OPENING_ADJ,
  provisionIncrease: PROVISION, otherIncrease: OTHER_INCREASE,
  reversal: REVERSAL, writeOff: WRITE_OFF, otherDecrease: OTHER_DECREASE,
  closingAdjustment: CLOSING_ADJ,
})

describe('触类旁通：坏账准备滚动表与 G2-2 同样以期初未审起算', () => {
  it('D2-3 坏账准备明细：期末未审 K = B + SUM(F:G) − SUM(H:J)', () => {
    const { individualRows } = withSetup(() => useD2BadDebt({
      ...baseOptions(),
      eclTestTotal: ref(0),
      allResponses: responses({
        'D2-bd-individual-rows': [{
          rowId: 'fixed-individual', isFixed: true, label: '按单项计提小计',
          priorUnadjusted: PRIOR_UNADJUSTED, priorAje: PRIOR_AJE, priorRje: PRIOR_RJE,
          currentProvision: PROVISION, currentOtherIncrease: OTHER_INCREASE,
          currentReversal: REVERSAL, currentWriteOff: WRITE_OFF, currentOtherDecrease: OTHER_DECREASE,
          currentAje: END_AJE, currentRje: END_RJE,
        }],
      }),
    } as never))
    const row = individualRows.value.find((r) => r.isFixed)!
    expect(row.priorAudited).toBe(PRIOR_AUDITED)
    expect(row.currentUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(row.currentAudited).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
  })

  it('G2-2 应收利息明细：期末余额 H = C + F − G', () => {
    const { dataRows } = withSetup(() => useG2Detail({
      wpId: ref('wp-1'),
      projectId: ref('proj-1'),
      isReadonly: ref(false),
      allResponses: responses({
        'G2-2-detail-rows': [{
          id: 'g22-1', seq: 1, investTarget: '某债券', investType: '债权投资',
          openingUnadjusted: PRIOR_UNADJUSTED, openingAdjustment: OPENING_ADJ,
          debit: INCREASE, credit: DECREASE, closingAdjustment: CLOSING_ADJ,
        }],
      }),
    } as never))
    const row = dataRows.value[0]
    expect(row.openingAudited).toBe(PRIOR_AUDITED)
    expect(row.closingUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(row.closingAudited).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
  })

  it('G2-3 坏账准备明细：明细行与合计行的期末未审都从期初未审滚动', () => {
    const rows = buildG23Rows([movementLeaf()])
    const leaf = rows.find((r) => r.kind === 'leaf')!
    const total = rows.find((r) => r.kind === 'footer')!
    expect(leaf.openingAudited).toBe(PRIOR_AUDITED)
    expect(leaf.closingUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(leaf.closingAudited).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
    expect(total.closingUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(total.closingAudited).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
  })

  it('G2-3 跨表读取（G2-1 / 附注取数）与表单同口径', () => {
    const map = responses({ 'G2-3-bad-debt-rows': [movementLeaf()] }).value
    const [leaf] = loadG2BadDebtLeaves(map)
    expect(leaf.openingAudited).toBe(PRIOR_AUDITED)
    expect(leaf.closingUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(leaf.closingAudited).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
  })

  it('G5-3 坏账准备明细：明细行与小计 / 合计行的期末未审都从期初未审滚动', () => {
    const d = computeG53(movementLeaf())
    expect(d.openingAudited).toBe(PRIOR_AUDITED)
    expect(d.closingUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(d.closingAudited).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
    const total = buildG53Rows([movementLeaf()]).find((r) => r.kind === 'total')!
    expect(total.closingUnadjusted).toBe(END_FROM_UNADJUSTED)
    expect(total.closingAudited).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
  })

  it('G5-3 跨表兜底（G5-1 汇总、上市附注）没存期末审定时与表单同口径', () => {
    const withoutClosing = movementLeaf() // 不带 closingAudited ⇒ 两处都走滚动兜底
    expect('closingAudited' in withoutClosing).toBe(false)
    const aggregate = aggregateProvisionFromG53([withoutClosing])
    expect(aggregate.individualClosing).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
    const disclosure = extractBadDebtForDisclosure(JSON.stringify([withoutClosing]))
    expect(disclosure.individualTotals.end.provision).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
    expect(disclosure.individualTotals.prior.provision).toBe(PRIOR_AUDITED)
  })

  it('K1-3 坏账准备明细：期末账面 J = B + SUM(E:F) − SUM(G:I)', () => {
    const row = recalcK1BadDebtMainRow({
      id: 'sub-1', category: 'individual', label: '甲公司', isSubRow: true, isFixed: false,
      priorBook: PRIOR_UNADJUSTED, priorAdj: OPENING_ADJ, priorAudited: 0,
      currentProvision: PROVISION, currentOtherIncrease: OTHER_INCREASE,
      currentReversal: REVERSAL, currentWriteOff: WRITE_OFF, currentOtherDecrease: OTHER_DECREASE,
      currentBook: 0, currentAdj: CLOSING_ADJ, currentAudited: 0, reason: '',
    })
    expect(row.priorAudited).toBe(PRIOR_AUDITED)
    expect(row.currentBook).toBe(END_FROM_UNADJUSTED)
    expect(row.currentAudited).toBe(END_FROM_UNADJUSTED + CLOSING_ADJ)
  })
})
