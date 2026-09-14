/**
 * useG2Adjudication 单元测试 — G2-1 审定表（原值/坏账/净值）
 *
 * 验证：审定=本账+调整、净值=原值−坏账、变动分析、试算差异
 */
import { describe, it, expect, vi } from 'vitest'
import { ref } from 'vue'
import { useG2Adjudication, buildG2AdjudicationRows } from '../useG2Adjudication'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('vue', async () => {
  const actual = await vi.importActual('vue')
  return {
    ...actual as any,
    onBeforeUnmount: vi.fn(),
  }
})

function setup(seed?: Record<string, string>) {
  const map = new Map<string, ChecklistResponse>()
  if (seed) {
    for (const [k, v] of Object.entries(seed)) {
      map.set(k, { item_id: k, conclusion: null, remark: v })
    }
  }
  const allResponses = ref(map)
  const adj = useG2Adjudication({
    wpId: ref('wp-1'),
    projectId: ref('proj-1'),
    allResponses,
    isReadonly: ref(false),
  })
  return { adj, allResponses }
}

describe('useG2Adjudication — 模板结构审定公式', () => {
  it('审定 = 本账 + 账项调整；小计自动汇总', () => {
    const store = JSON.stringify({
      'gross-individual': {
        openingUnadjusted: 1000,
        openingAdjustment: 100,
        closingUnadjusted: 2000,
        closingAdjustment: 50,
      },
      'gross-collective': {
        openingUnadjusted: 500,
        openingAdjustment: 0,
        closingUnadjusted: 800,
        closingAdjustment: -20,
      },
      'provision-individual': {
        openingUnadjusted: 50,
        openingAdjustment: 0,
        closingUnadjusted: 80,
        closingAdjustment: 0,
      },
      'provision-collective': {
        openingUnadjusted: 20,
        openingAdjustment: 0,
        closingUnadjusted: 30,
        closingAdjustment: 0,
      },
    })
    const { adj } = setup({ 'G2-1-rows': store })
    const grossSub = adj.dataRows.value.find((r) => r.rowKey === 'gross__subtotal')!
    expect(grossSub.openingAudited).toBe(1600) // 1100+500
    expect(grossSub.closingAudited).toBe(2830) // 2050+780

    const provSub = adj.dataRows.value.find((r) => r.rowKey === 'provision__subtotal')!
    expect(provSub.openingAudited).toBe(70)
    expect(provSub.closingAudited).toBe(110)

    const net = adj.dataRows.value.find((r) => r.rowKey === 'net__row')!
    expect(net.openingAudited).toBe(1530) // 1600-70
    expect(net.closingAudited).toBe(2720) // 2830-110
  })

  it('变动额/变动率自动计算；|变动率|>30% 高亮', () => {
    const store = JSON.stringify({
      'gross-collective': {
        openingUnadjusted: 100,
        openingAdjustment: 0,
        closingUnadjusted: 200,
        closingAdjustment: 0,
      },
    })
    const { adj } = setup({ 'G2-1-rows': store })
    const leaf = adj.dataRows.value.find((r) => r.rowKey === 'gross-collective')!
    expect(leaf.changeAmount).toBe(100)
    expect(leaf.changeRate).toBe(1)
    expect(leaf.changeRateHighlight).toBe(true)
    expect(leaf.reasonRequired).toBe(true)
  })

  it('合计=净值；差异=审定-试算表数', () => {
    const store = JSON.stringify({
      'gross-collective': {
        openingUnadjusted: 1000,
        openingAdjustment: 0,
        closingUnadjusted: 1400,
        closingAdjustment: 0,
      },
    })
    const { adj } = setup({ 'G2-1-rows': store, 'G2-1-tb': '1400' })
    expect(adj.subtotalRow.value.closingAudited).toBe(1400)
    expect(adj.variance.value).toBe(0)
    expect(adj.hasVarianceHighlight.value).toBe(false)
  })

  it('差异≠0 时红色标记', () => {
    const store = JSON.stringify({
      'gross-collective': {
        openingUnadjusted: 0,
        openingAdjustment: 0,
        closingUnadjusted: 1500,
        closingAdjustment: 0,
      },
    })
    const { adj } = setup({ 'G2-1-rows': store, 'G2-1-tb': '1000' })
    expect(adj.variance.value).toBe(500)
    expect(adj.hasVarianceHighlight.value).toBe(true)
  })

  it('兼容旧版数组存储（投资类型行）', () => {
    const legacy = JSON.stringify([
      {
        rowKey: 'bond-interest',
        label: '债权投资利息',
        openingUnadjusted: 1000,
        openingAJE: 100,
        openingRJE: -50,
        periodDebit: 500,
        periodCredit: 200,
        closingAJE: 0,
        closingRJE: 0,
        indexRef: '',
      },
    ])
    const { adj } = setup({ 'G2-1-adj-rows': legacy })
    const mapped = adj.dataRows.value.find((r) => r.rowKey === 'gross-collective')!
    // 期初审定 = 1050；期末未审 = 1050+500-200 = 1350
    expect(mapped.openingAudited).toBe(1050)
    expect(mapped.closingUnadjusted).toBe(1350)
  })

  it('buildG2AdjudicationRows 纯函数可复用', () => {
    const rows = buildG2AdjudicationRows({
      'gross-individual': { closingUnadjusted: 10, closingAdjustment: 1 },
      'provision-individual': { closingUnadjusted: 2, closingAdjustment: 0 },
    })
    const net = rows.find((r) => r.rowKey === 'net__row')!
    expect(net.closingAudited).toBe(9) // 11 - 2
  })

  it('syncFromSupporting：G2-2/G2-3 → 未审本账，保留账项调整', () => {
    const detail = JSON.stringify([
      {
        id: 'd1',
        investTarget: 'A债',
        eclStage: 'Stage3',
        faceValue: 0,
        couponRate: 0,
        receivedInterest: 0,
        netReceivable: 500,
        agingPrior: { within1: 100 },
        agingAudited: { within1: 500 },
      },
      {
        id: 'd2',
        investTarget: 'B债',
        eclStage: 'Stage1',
        faceValue: 0,
        couponRate: 0,
        receivedInterest: 0,
        netReceivable: 300,
        agingPrior: { within1: 200 },
        agingAudited: { within1: 300 },
      },
    ])
    const badDebt = JSON.stringify([
      {
        id: 'i1', category: 'individual', item: 'A债',
        openingUnadjusted: 40, openingAdjustment: 0,
        provisionIncrease: 10, otherIncrease: 0, reversal: 0, writeOff: 0, otherDecrease: 0,
        closingAdjustment: 0,
      },
      {
        id: 'p1', category: 'portfolio', item: '1年以内', agingKey: 'within1',
        openingUnadjusted: 20, openingAdjustment: 0,
        provisionIncrease: 5, otherIncrease: 0, reversal: 0, writeOff: 0, otherDecrease: 0,
        closingAdjustment: 0,
      },
    ])
    const store = JSON.stringify({
      'gross-collective': { closingAdjustment: 15, reasonAnalysis: 'keep-me' },
    })
    const { adj } = setup({
      'G2-1-rows': store,
      'G2-2-detail-rows': detail,
      'G2-3-bad-debt-rows': badDebt,
    })
    const r = adj.syncFromSupporting()
    expect(r.gross).toBe(2)
    expect(r.provision).toBe(2)
    const gi = adj.dataRows.value.find((x) => x.rowKey === 'gross-individual')!
    const gc = adj.dataRows.value.find((x) => x.rowKey === 'gross-collective')!
    expect(gi.closingUnadjusted).toBe(500)
    expect(gc.closingUnadjusted).toBe(300)
    expect(gc.closingAdjustment).toBe(15)
    expect(gc.reasonAnalysis).toBe('keep-me')
    const pi = adj.dataRows.value.find((x) => x.rowKey === 'provision-individual')!
    expect(pi.closingUnadjusted).toBe(50) // 40+10
  })

  it('applyAdjustmentWriteback：G2-4 净调整写入原值·组合期末调整', () => {
    const { adj } = setup({
      'G2-1-rows': JSON.stringify({
        'gross-collective': { closingUnadjusted: 1000, closingAdjustment: 0 },
      }),
    })
    adj.applyAdjustmentWriteback(88)
    const gc = adj.dataRows.value.find((x) => x.rowKey === 'gross-collective')!
    expect(gc.closingAdjustment).toBe(88)
  })

  it('publishAdjudicated 派发试算回写事件', () => {
    const store = JSON.stringify({
      'gross-collective': {
        openingUnadjusted: 0,
        openingAdjustment: 0,
        closingUnadjusted: 1500,
        closingAdjustment: 0,
      },
    })
    const { adj } = setup({ 'G2-1-rows': store })
    const seen: any[] = []
    const handler = (e: Event) => seen.push((e as CustomEvent).detail)
    window.addEventListener('g2:writeback-trial-balance', handler)
    adj.publishAdjudicated()
    window.removeEventListener('g2:writeback-trial-balance', handler)
    expect(seen[0]?.accountCode).toBe('1132')
    expect(seen[0]?.auditedAmount).toBe(1500)
  })
})
