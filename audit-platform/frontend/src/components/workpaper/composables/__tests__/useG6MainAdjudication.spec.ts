/**
 * useG6MainAdjudication — 对齐 Excel《审定表G6-1》公式单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import { useG6MainAdjudication } from '../useG6MainAdjudication'
import {
  G6_CHANGE_RATE_THRESHOLD,
  parseG6AdjStore,
  applyG6SplitAdjustmentWriteback,
} from '../g6AdjudicationItems'
import type { ChecklistResponse } from '../useF1FormData'

vi.mock('@/services/apiProxy', () => ({
  api: { get: vi.fn().mockResolvedValue({ data: [] }), post: vi.fn().mockResolvedValue({}) },
}))

function makeAdj(storeJson?: string, tb = 0) {
  const map = new Map<string, ChecklistResponse>()
  if (storeJson) {
    map.set('G6-1-rows', { item_id: 'G6-1-rows', conclusion: storeJson, remark: storeJson })
  }
  if (tb) {
    map.set('G6-1-adj-tb-1503', { item_id: 'G6-1-adj-tb-1503', conclusion: null, remark: String(tb) })
  }
  return useG6MainAdjudication({
    wpId: ref('wp-g6'),
    projectId: ref('proj-1'),
    allResponses: ref(map),
    isReadonly: ref(false),
  })
}

describe('g6AdjudicationItems', () => {
  it('变动率阈值为 30%', () => {
    expect(G6_CHANGE_RATE_THRESHOLD).toBe(0.3)
  })

  it('parseG6AdjStore 解析扁平 store', () => {
    const s = parseG6AdjStore(JSON.stringify({
      'cost-portfolio': { openingUnadjusted: 100, closingUnadjusted: 120 },
    }))
    expect(s['cost-portfolio']?.openingUnadjusted).toBe(100)
    expect(s['cost-portfolio']?.closingUnadjusted).toBe(120)
  })

  it('分离回写写入成本与减值组合行', () => {
    const next = applyG6SplitAdjustmentWriteback({}, 500, 80)
    expect(next['cost-portfolio']?.closingAdjustment).toBe(500)
    expect(next['impairment-portfolio']?.closingAdjustment).toBe(80)
  })
})

describe('useG6MainAdjudication 公式链', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('审定 = 未审 + 账项调整', () => {
    const store = JSON.stringify({
      'cost-individual': {
        openingUnadjusted: 1000,
        openingAdjustment: 50,
        closingUnadjusted: 1100,
        closingAdjustment: -20,
      },
    })
    const adj = makeAdj(store)
    const row = adj.rows.value.find((r) => r.rowKey === 'cost-individual')!
    expect(row.openingAudited).toBe(1050)
    expect(row.closingAudited).toBe(1080)
  })

  it('账面余额叶子 = 成本审定 + 利息调整审定', () => {
    const store = JSON.stringify({
      'cost-individual': {
        openingUnadjusted: 1000, openingAdjustment: 0,
        closingUnadjusted: 1000, closingAdjustment: 0,
      },
      'interest-individual': {
        openingUnadjusted: -20, openingAdjustment: 0,
        closingUnadjusted: -10, closingAdjustment: 0,
      },
    })
    const adj = makeAdj(store)
    const book = adj.rows.value.find((r) => r.rowKey === 'book-individual')!
    expect(book.openingAudited).toBe(980)
    expect(book.closingAudited).toBe(990)
    expect(book.editable).toBe(false)
  })

  it('账面价值叶子 = 账面余额 − 减值', () => {
    const store = JSON.stringify({
      'cost-portfolio': {
        openingUnadjusted: 5000, openingAdjustment: 0,
        closingUnadjusted: 5000, closingAdjustment: 0,
      },
      'interest-portfolio': {
        openingUnadjusted: 0, openingAdjustment: 0,
        closingUnadjusted: 0, closingAdjustment: 0,
      },
      'impairment-portfolio': {
        openingUnadjusted: 200, openingAdjustment: 0,
        closingUnadjusted: 250, closingAdjustment: 0,
      },
    })
    const adj = makeAdj(store)
    const carrying = adj.rows.value.find((r) => r.rowKey === 'carrying-portfolio')!
    expect(carrying.openingAudited).toBe(4800)
    expect(carrying.closingAudited).toBe(4750)
  })

  it('账面一年内到期 = 成本一年内 + 利息一年内', () => {
    const store = JSON.stringify({
      'cost__one-year': {
        openingUnadjusted: 100, openingAdjustment: 0,
        closingUnadjusted: 120, closingAdjustment: 0,
      },
      'interest__one-year': {
        openingUnadjusted: 5, openingAdjustment: 0,
        closingUnadjusted: 8, closingAdjustment: 0,
      },
    })
    const adj = makeAdj(store)
    const oy = adj.rows.value.find((r) => r.rowKey === 'book__one-year')!
    expect(oy.openingAudited).toBe(105)
    expect(oy.closingAudited).toBe(128)
    expect(oy.editable).toBe(false)
  })

  it('层小计净额 = 小计 − 一年内到期', () => {
    const store = JSON.stringify({
      'cost-individual': {
        openingUnadjusted: 800, openingAdjustment: 0,
        closingUnadjusted: 800, closingAdjustment: 0,
      },
      'cost-portfolio': {
        openingUnadjusted: 200, openingAdjustment: 0,
        closingUnadjusted: 200, closingAdjustment: 0,
      },
      'cost__one-year': {
        openingUnadjusted: 150, openingAdjustment: 0,
        closingUnadjusted: 150, closingAdjustment: 0,
      },
    })
    const adj = makeAdj(store)
    const net = adj.rows.value.find((r) => r.rowKey === 'cost__net')!
    expect(net.closingAudited).toBe(850) // 1000 - 150
  })

  it('差异数 = 账面价值合计 − 试算平衡表数', () => {
    const store = JSON.stringify({
      'cost-portfolio': {
        openingUnadjusted: 10000, openingAdjustment: 0,
        closingUnadjusted: 10000, closingAdjustment: 0,
      },
      'impairment-portfolio': {
        openingUnadjusted: 500, openingAdjustment: 0,
        closingUnadjusted: 500, closingAdjustment: 0,
      },
    })
    const adj = makeAdj(store, 9500)
    expect(adj.carryingNetRow.value?.closingAudited).toBe(9500)
    expect(adj.variance.value).toBe(0)
    expect(adj.hasVarianceHighlight.value).toBe(false)
  })

  it('|变动率|>30% 触发原因分析必填', () => {
    const store = JSON.stringify({
      'fv-item-1': {
        openingUnadjusted: 100, openingAdjustment: 0,
        closingUnadjusted: 150, closingAdjustment: 0,
      },
    })
    const adj = makeAdj(store)
    const row = adj.rows.value.find((r) => r.rowKey === 'fv-item-1')!
    expect(row.changeRate).toBeCloseTo(0.5, 4)
    expect(row.changeRateHighlight).toBe(true)
    expect(row.reasonRequired).toBe(true)
  })

  it('公允价值合计 = 明细小计 − 一年内到期', () => {
    const store = JSON.stringify({
      'fv-item-1': {
        openingUnadjusted: 1000, openingAdjustment: 0,
        closingUnadjusted: 1000, closingAdjustment: 0,
      },
      'fv-item-2': {
        openingUnadjusted: 500, openingAdjustment: 0,
        closingUnadjusted: 500, closingAdjustment: 0,
      },
      'fv__one-year': {
        openingUnadjusted: 200, openingAdjustment: 0,
        closingUnadjusted: 200, closingAdjustment: 0,
      },
    })
    const adj = makeAdj(store)
    expect(adj.fvNetRow.value?.closingAudited).toBe(1300)
  })
})
