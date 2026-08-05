/**
 * useH8Adjudication — H8-1 审定表单测
 */
import { describe, it, expect, vi, beforeEach } from 'vitest'
import { ref } from 'vue'
import {
  useH8Adjudication,
  normalizeH81Row,
  aggregateH82ByCategory,
  H8_ROU_CATEGORIES,
  CHANGE_RATE_THRESHOLD,
} from '../useH8Adjudication'
import { calcChangeRate } from '../useH8FormulaEngine'
import { H8_ROU_COST_CODE, H8_ROU_DEP_CODE } from '../useH8Adjustment'
import { h9Scope } from '../hCycleAccountScope'

const LEASE_LIABILITY_CODE = h9Scope.def.grossFallback

function makeMap(entries?: Record<string, unknown>) {
  const m = new Map<string, { item_id: string; conclusion: null; remark: string | null }>()
  if (entries) {
    for (const [k, v] of Object.entries(entries)) {
      m.set(k, {
        item_id: k,
        conclusion: null,
        remark: typeof v === 'string' ? v : JSON.stringify(v),
      })
    }
  }
  return ref(m)
}

describe('calcChangeRate / normalizeH81Row', () => {
  it('change rate matches Excel edge cases', () => {
    expect(calcChangeRate(0, 0)).toBe(0)
    expect(calcChangeRate(100, 0)).toBe(100)
    expect(calcChangeRate(-50, 0)).toBe(-100)
    expect(calcChangeRate(50, 200)).toBeCloseTo(25, 5)
  })

  it('migrates legacy beginBalance/unadjusted/aje', () => {
    const row = normalizeH81Row({
      name: '房屋租赁',
      block: 'accDep',
      beginBalance: 1000,
      unadjusted: 1200,
      aje: 50,
      rje: 10,
    })
    expect(row).not.toBeNull()
    expect(row!.block).toBe('dep')
    expect(row!.category).toBe('房屋及建筑物')
    expect(row!.beginUnadjusted).toBe(1000)
    expect(row!.endUnadjusted).toBe(1200)
    expect(row!.endAdjustment).toBe(60)
    expect(row!.endAudited).toBe(1260)
  })
})

describe('useH8Adjudication', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  it('defaults to five ROU categories × three blocks', () => {
    const allResponses = makeMap()
    const state = useH8Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
    })
    expect(state.costRows.value).toHaveLength(H8_ROU_CATEGORIES.length)
    expect(state.depRows.value).toHaveLength(H8_ROU_CATEGORIES.length)
    expect(state.impairRows.value).toHaveLength(H8_ROU_CATEGORIES.length)
    expect(state.costRows.value[0].category).toBe('房屋及建筑物')
    expect(state.netRows.value.some((r) => r.isSubtotal)).toBe(true)
  })

  it('audited = unadjusted + adjustment; net = cost − dep − impair', () => {
    const allResponses = makeMap()
    const saves: { id: string; val: unknown }[] = []
    const state = useH8Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: (id, val) => saves.push({ id, val }),
    })
    const cat = '房屋及建筑物'
    const cost = state.costRows.value.find((r) => r.category === cat)!
    const dep = state.depRows.value.find((r) => r.category === cat)!
    const impair = state.impairRows.value.find((r) => r.category === cat)!

    state.updateCell('cost', cost.rowId, 'endUnadjusted', 1000)
    state.updateCell('cost', cost.rowId, 'endAdjustment', 100)
    state.updateCell('dep', dep.rowId, 'endUnadjusted', 200)
    state.updateCell('impair', impair.rowId, 'endUnadjusted', 50)

    expect(cost.endAudited).toBe(1100)
    expect(state.netAudited.value).toBe(1100 - 200 - 50)
    expect(saves.some((s) => s.id === 'H8-1-cost-audited-total')).toBe(true)
  })

  it('syncEndAdjFromH83 allocates 原值/折旧 nets by endUnadjusted weight', () => {
    const allResponses = makeMap({
      'H8-3-rows': [
        {
          category: '账项调整',
          accountCode: H8_ROU_COST_CODE,
          debitAmount: 300,
          creditAmount: 0,
        },
        {
          category: '账项调整',
          accountCode: LEASE_LIABILITY_CODE,
          debitAmount: 0,
          creditAmount: 300,
        },
        {
          category: '账项调整',
          accountCode: H8_ROU_DEP_CODE,
          debitAmount: 0,
          creditAmount: 90,
        },
        {
          category: '账项调整',
          accountCode: '6603',
          debitAmount: 90,
          creditAmount: 0,
        },
      ],
    })
    const state = useH8Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: (id, val) => {
        allResponses.value.set(id, {
          item_id: id,
          conclusion: null,
          remark: typeof val === 'string' ? val : JSON.stringify(val),
        })
      },
    })

    // 两行有未审权重：房屋 200、机器 100 → 原值净额 300 分摊 200/100
    const b = state.costRows.value.find((r) => r.category === '房屋及建筑物')!
    const m = state.costRows.value.find((r) => r.category === '机器设备')!
    state.updateCell('cost', b.rowId, 'endUnadjusted', 200)
    state.updateCell('cost', m.rowId, 'endUnadjusted', 100)
    const d0 = state.depRows.value.find((r) => r.category === '房屋及建筑物')!
    state.updateCell('dep', d0.rowId, 'endUnadjusted', 90)

    const res = state.syncEndAdjFromH83()
    expect(res.applied).toBe(true)
    expect(b.endAdjustment + m.endAdjustment).toBeCloseTo(300, 1)
    expect(b.endAdjustment).toBeCloseTo(200, 0)
    expect(m.endAdjustment).toBeCloseTo(100, 0)
    expect(state.depSubtotal.value.endAdjustment).toBeCloseTo(-90, 1)
  })

  it('flags significant net change when |rate| ≥ threshold', () => {
    const allResponses = makeMap()
    const state = useH8Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: () => {},
    })
    const cat = '运输设备'
    const cost = state.costRows.value.find((r) => r.category === cat)!
    state.updateCell('cost', cost.rowId, 'beginUnadjusted', 100)
    state.updateCell('cost', cost.rowId, 'endUnadjusted', 200)
    const net = state.netRows.value.find((r) => r.category === cat)!
    expect(Math.abs(net.changeRate ?? 0)).toBeGreaterThanOrEqual(CHANGE_RATE_THRESHOLD)
    expect(net.isSignificant).toBe(true)
    expect(state.significantNetChanges.value.length).toBeGreaterThanOrEqual(1)
  })

  it('aggregateH82ByCategory sums book columns by category', () => {
    const { map, unmatchedCount } = aggregateH82ByCategory(
      [
        {
          category: '房屋及建筑物',
          costBeginUnadj: 100_000,
          costEndUnadj: 124_000,
          depBeginUnadj: 10_000,
          depEndUnadj: 22_000,
          impairBeginUnadj: 0,
          impairEndUnadj: 0,
        },
        {
          category: '房屋租赁', // alias → 房屋及建筑物
          costBeginUnadj: 50_000,
          costEndUnadj: 50_000,
          depBeginUnadj: 5_000,
          depProvUnadj: 1_000,
          accDepBegin: 5_000,
        },
      ],
      'book',
    )
    expect(unmatchedCount).toBe(0)
    expect(map['房屋及建筑物'].count).toBe(2)
    expect(map['房屋及建筑物'].costBegin).toBe(150_000)
    expect(map['房屋及建筑物'].costEnd).toBe(174_000)
    expect(map['房屋及建筑物'].depBegin).toBe(15_000)
    expect(map['房屋及建筑物'].depEnd).toBe(28_000) // 22k + (5k+1k)
  })

  it('aggregateH82ByCategory lists unmatched non-standard categories', () => {
    const { unmatchedCount, unmatchedCategories } = aggregateH82ByCategory(
      [
        {
          category: '特种租赁资产X',
          costBeginUnadj: 1,
          costEndUnadj: 1,
        },
      ],
      'book',
    )
    expect(unmatchedCount).toBe(1)
    expect(unmatchedCategories).toContain('特种租赁资产X')
  })

  it('fillFromH82Detail book mode writes unadj and keeps AJE', () => {
    const detail = [
      {
        category: '机器设备',
        costBeginUnadj: 80_000,
        costEndUnadj: 90_000,
        depBeginUnadj: 8_000,
        depEndUnadj: 12_000,
        impairBeginUnadj: 1_000,
        impairEndUnadj: 1_500,
      },
    ]
    const allResponses = makeMap({ 'H8-2-rows': detail })
    const saves: string[] = []
    const state = useH8Adjudication({
      wpId: ref('wp1'),
      projectId: ref('p1'),
      allResponses: allResponses as any,
      isReadonly: ref(false),
      onSave: (id) => { saves.push(id) },
    })
    const cost = state.costRows.value.find((r) => r.category === '机器设备')!
    state.updateCell('cost', cost.rowId, 'endAdjustment', 500)

    const res = state.fillFromH82Detail('book')
    expect(res.costFilled).toBe(1)
    expect(res.depFilled).toBe(1)
    expect(res.impairFilled).toBe(1)
    expect(cost.beginUnadjusted).toBe(80_000)
    expect(cost.endUnadjusted).toBe(90_000)
    expect(cost.endAdjustment).toBe(500) // book 模式保留 AJE
    expect(cost.endAudited).toBe(90_500)
    const dep = state.depRows.value.find((r) => r.category === '机器设备')!
    expect(dep.endUnadjusted).toBe(12_000)
    expect(saves).toContain('H8-1-cost-rows')
  })
})
