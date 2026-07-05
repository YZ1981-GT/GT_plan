/**
 * useF5Adjudication 单元测试 — F5-1 审定表（损益类 6401）
 *
 * Spec: .kiro/specs/f5-cost-of-sales/ Task 4.2
 * 验证：损益类审定公式（无期初期末，本期/上期各自计算）、总计=主营+其他、差异=审定-试算表
 */
import { describe, it, expect } from 'vitest'
import { ref } from 'vue'
import { useF5Adjudication } from '../useF5Adjudication'
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
      { rowKey: 'p1', label: '产品A', isFixed: false, currentUnadjusted: 1000, currentAje: 100, currentRje: -50, priorUnadjusted: 800, priorAje: 20, priorRje: 0, indexRef: '' },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows })
    const row = adj.mainBusinessRows.value[0]
    expect(row.currentAdjusted).toBe(1050) // 1000 + 100 - 50
    expect(row.priorAdjusted).toBe(820) // 800 + 20 + 0
    expect(row.changeAmount).toBe(230) // 1050 - 820
  })

  it('主营小计 = 各品种本期审定 SUM', () => {
    const mainRows = JSON.stringify([
      { rowKey: 'p1', label: 'A', isFixed: false, currentUnadjusted: 1000, currentAje: 0, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '' },
      { rowKey: 'p2', label: 'B', isFixed: false, currentUnadjusted: 500, currentAje: 50, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '' },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows })
    expect(adj.mainSubtotal.value.currentAdjusted).toBe(1550) // 1000 + 550
  })

  it('总计 = 主营小计 + 其他小计', () => {
    const mainRows = JSON.stringify([
      { rowKey: 'p1', label: 'A', isFixed: false, currentUnadjusted: 1000, currentAje: 0, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '' },
    ])
    const otherRows = JSON.stringify([
      { rowKey: 'o1', label: '材料', isFixed: false, currentUnadjusted: 300, currentAje: 0, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '' },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows, 'F5-1-adj-other-rows': otherRows })
    expect(adj.mainSubtotal.value.currentAdjusted).toBe(1000)
    expect(adj.otherSubtotal.value.currentAdjusted).toBe(300)
    expect(adj.grandTotal.value.currentAdjusted).toBe(1300)
  })

  it('差异 = 审定总计 - 试算表数', () => {
    const mainRows = JSON.stringify([
      { rowKey: 'p1', label: 'A', isFixed: false, currentUnadjusted: 1000, currentAje: 0, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: '' },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows, 'F5-1-adj-tb-6401': '950' })
    // grandTotal = main(1000) + other(default 0) = 1000; variance = 1000 - 950 = 50
    expect(adj.trialBalanceAmount.value).toBe(950)
    expect(adj.variance.value).toBe(50)
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

  it('serialize/deserialize 往返一致', () => {
    const mainRows = JSON.stringify([
      { rowKey: 'p1', label: 'A', isFixed: false, currentUnadjusted: 1000, currentAje: 0, currentRje: 0, priorUnadjusted: 0, priorAje: 0, priorRje: 0, indexRef: 'X1' },
    ])
    const { adj } = setup({ 'F5-1-adj-main-rows': mainRows, 'F5-1-adj-tb-6401': '900' })
    const dump = adj.serialize()
    const { adj: adj2 } = setup()
    adj2.deserialize(dump)
    expect(adj2.mainBusinessRows.value[0].currentAdjusted).toBe(1000)
    expect(adj2.trialBalanceAmount.value).toBe(900)
  })
})
