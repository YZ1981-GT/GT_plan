/**
 * useF5Adjudication 单元测试 — F5-1 审定表（损益类 6401）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 4.2
 * 验证：损益类审定公式、总计=主营+其他、差异=审定-试算表、>30%变动、F5-2同步
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import {
  extractF5AdjudicationCandidatesFromMonthly,
  extractF5AdjudicationCandidatesFromOtherCost,
  aggregateF54AdjustmentImpact,
  useF5Adjudication,
} from '../useF5Adjudication'
import type { ChecklistResponse } from '../useF1FormData'

function setup(seed?: Record<string, string>) {
  const map = new Map<string, ChecklistResponse>()
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  const allResponses = ref(map)
  const adj = useF5Adjudication({
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  })
  return { adj, allResponses }
}

describe('useF5Adjudication — 损益类审定公式', () => {
  it('审定 = 未审 + AJE + RJE（本期/上期各自独立计算，无期初期末）', () => {
    const mainRows = JSON.stringify([
      {
        rowKey: 'p1', label: '产品A', isFixed: false,
        currentUnadjusted: 1000, currentAje: 100, currentRje: -50,
        priorUnadjusted: 800, priorAje: 20, priorRje: 0, indexRef: '',
      },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows })
    const row = adj.mainBusinessRows.value[0]
    expect(row.currentAdjusted).toBe(1050)
    expect(row.priorAdjusted).toBe(820)
    expect(row.changeAmount).toBe(230)
    expect(row.changeRate).not.toBe('N/A')
  })

  it('主营小计 = 各品种本期审定 SUM', () => {
    const mainRows = JSON.stringify([
      {
        rowKey: 'p1', label: 'A', isFixed: false,
        currentUnadjusted: 1000, currentAje: 0, currentRje: 0,
        priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '',
      },
      {
        rowKey: 'p2', label: 'B', isFixed: false,
        currentUnadjusted: 500, currentAje: 50, currentRje: 0,
        priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '',
      },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows })
    expect(adj.mainSubtotal.value.currentAdjusted).toBe(1550)
  })

  it('总计 = 主营小计 + 其他小计', () => {
    const mainRows = JSON.stringify([
      {
        rowKey: 'p1', label: 'A', isFixed: false,
        currentUnadjusted: 1000, currentAje: 0, currentRje: 0,
        priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '',
      },
    ])
    const otherRows = JSON.stringify([
      {
        rowKey: 'o1', label: '材料', isFixed: false,
        currentUnadjusted: 300, currentAje: 0, currentRje: 0,
        priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '',
      },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows, 'F5-1-adj-other-rows': otherRows })
    expect(adj.grandTotal.value.currentAdjusted).toBe(1300)
  })

  it('差异 = 审定总计 - 试算表数（本期/上期）', () => {
    const mainRows = JSON.stringify([
      {
        rowKey: 'p1', label: 'A', isFixed: false,
        currentUnadjusted: 1000, currentAje: 0, currentRje: 0,
        priorUnadjusted: 800, priorAje: 0, priorRje: 0, indexRef: '',
      },
    ])
    const { adj } = setup({
      'F5-1-adj-main-rows': mainRows,
      'F5-1-adj-tb-6401': '950',
      'F5-1-adj-tb-6401-prior': '780',
    })
    expect(adj.variance.value).toBe(50)
    expect(adj.priorVariance.value).toBe(20)
  })

  it('变动率超过30%进入显著变动清单', () => {
    const mainRows = JSON.stringify([
      {
        rowKey: 'p1', label: '高波动品种', isFixed: false,
        currentUnadjusted: 200, currentAje: 0, currentRje: 0,
        priorUnadjusted: 100, priorAje: 0, priorRje: 0, indexRef: '',
      },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows })
    expect(adj.significantChanges.value.some((i) => i.label === '高波动品种')).toBe(true)
    expect(adj.mainCostChange.value.changeAmount).toBe(100)
  })

  it('动态品种行增删', () => {
    const { adj } = setup()
    const before = adj.mainBusinessRows.value.length
    adj.addRow('main', '新产品C')
    expect(adj.mainBusinessRows.value.length).toBe(before + 1)
    const added = adj.mainBusinessRows.value.find((r) => r.label === '新产品C')
    expect(added).toBeTruthy()
    adj.removeRow('main', added!.rowKey)
    expect(adj.mainBusinessRows.value.find((r) => r.label === '新产品C')).toBeFalsy()
  })

  it('从F5-2提取品种候选并同步', () => {
    const candidates = extractF5AdjudicationCandidatesFromMonthly(JSON.stringify([
      { id: '1', product: '甲产品', months: [10, 20, 30, 0, 0, 0, 0, 0, 0, 0, 0, 40], priorYearTotal: 80 },
    ]))
    expect(candidates[0]).toMatchObject({
      product: '甲产品',
      currentUnadjusted: 100,
      priorUnadjusted: 80,
    })

    const { adj } = setup({
      'F5-2-monthly-rows': JSON.stringify([
        { id: '1', product: '甲产品', months: [50, 50], priorYearTotal: 60 },
      ]),
    })
    const added = adj.syncFromMonthlyDetail()
    expect(added).toBe(1)
    expect(adj.mainBusinessRows.value.some((r) => r.label === '甲产品')).toBe(true)
  })

  it('从F5-4汇总6401调整净额并同步到专用行', () => {
    const impact = aggregateF54AdjustmentImpact(JSON.stringify([
      { entryType: 'AJE', accountCode: '6401', accountName: '主营业务成本', debitAmount: 100, creditAmount: 0 },
      { entryType: 'RJE', accountCode: '6401.01', accountName: '营业成本', debitAmount: 0, creditAmount: 30 },
      { entryType: 'AJE', accountCode: '2202', accountName: '应付账款', debitAmount: 0, creditAmount: 100 },
    ]))
    expect(impact).toMatchObject({ aje: 100, rje: -30, lineCount: 2 })

    const { adj } = setup({
      'F5-4-rows': JSON.stringify([
        { entryType: 'AJE', accountCode: '6401', debitAmount: 50, creditAmount: 0 },
      ]),
    })
    const synced = adj.syncFromAdjustment()
    expect(synced.aje).toBe(50)
    const row = adj.mainBusinessRows.value.find((r) => r.label.includes('F5-4'))
    expect(row?.currentAje).toBe(50)
  })

  it('从F5-3提取其他业务成本并同步', () => {
    const candidates = extractF5AdjudicationCandidatesFromOtherCost(JSON.stringify([
      { item: '销售材料', currentUnaudited: 200, priorUnaudited: 150 },
    ]))
    expect(candidates[0]).toMatchObject({ item: '销售材料', currentUnadjusted: 200, priorUnadjusted: 150 })

    const { adj } = setup({
      'F5-3-other-cost-rows': JSON.stringify([
        { item: '销售材料', currentUnaudited: 200, priorUnaudited: 150 },
      ]),
    })
    expect(adj.syncFromOtherCost()).toBe(1)
    expect(adj.otherBusinessRows.value.some((r) => r.label === '销售材料')).toBe(true)
  })

  it('serialize/deserialize 往返一致', () => {
    const mainRows = JSON.stringify([
      {
        rowKey: 'p1', label: 'A', isFixed: false,
        currentUnadjusted: 1000, currentAje: 0, currentRje: 0,
        priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: 'X1',
      },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows, 'F5-1-adj-tb-6401': '900' })
    const dump = adj.serialize()
    const { adj: adj2 } = setup()
    adj2.deserialize(dump)
    expect(adj2.mainBusinessRows.value[0].currentAdjusted).toBe(1000)
    expect(adj2.trialBalanceAmount.value).toBe(900)
  })
})
