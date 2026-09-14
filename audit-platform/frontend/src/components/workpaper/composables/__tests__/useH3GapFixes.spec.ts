import { describe, it, expect } from 'vitest'
import { ref, computed } from 'vue'

import { useH3AdditionCheck } from '../useH3AdditionCheck'
import { useH3Depreciation } from '../useH3Depreciation'
import { useH3Disclosure } from '../useH3Disclosure'

function makeStore(initial: Record<string, any> = {}) {
  const store = new Map<string, any>(Object.entries(initial))
  const allResponses = ref(store)
  const getValue = (id: string) => store.get(id)
  const setValue = (id: string, value: any) => { store.set(id, value) }
  const saveImmediate = async () => {}
  return { store, allResponses, getValue, setValue, saveImmediate }
}

// ─── #2 抽凭引擎回填 ──────────────────────────────────────────────────────────
describe('useH3AdditionCheck.fillFromSampledVouchers', () => {
  it('成本模式回填增减检查行，按凭证号去重', () => {
    const { allResponses, getValue, setValue, saveImmediate } = makeStore()
    const measurementModel = ref<'cost' | 'fair_value'>('cost')
    const api = useH3AdditionCheck({
      allResponses: computed(() => allResponses.value) as any,
      wpId: ref('wp'), projectId: ref('p'),
      getValue, setValue, saveImmediate, measurementModel,
    })
    const samples = [
      { voucherNo: 'V1', voucherDate: '2025-03-01', counterpartName: 'ABC置业', counterpartAccount: '1002', debitAmount: 500000, abnormal: false, selectionReason: '大额' },
      { voucherNo: 'V2', voucherDate: '2025-06-01', counterpartName: 'XYZ', counterpartAccount: '1122', creditAmount: 200000, abnormal: true, selectionReason: '关联方' },
    ]
    const added = api.fillFromSampledVouchers(samples)
    expect(added).toBe(2)
    expect(api.costRows.value.length).toBe(2)
    const r1 = api.costRows.value[0]
    expect(r1.assetName).toBe('ABC置业')
    expect(r1.originalCost).toBe(500000)
    expect(r1.voucherNo).toBe('V1')
    expect(r1.creditAccount).toBe('1002')
    const r2 = api.costRows.value[1]
    expect(r2.originalCost).toBe(200000) // 无借方时取贷方
    expect(r2.isAbnormal).toBe('Y')
    // 去重：相同凭证号不重复追加
    const again = api.fillFromSampledVouchers(samples)
    expect(again).toBe(0)
    expect(api.costRows.value.length).toBe(2)
  })

  it('公允价值模式回填 fairRows', () => {
    const { allResponses, getValue, setValue, saveImmediate } = makeStore()
    const measurementModel = ref<'cost' | 'fair_value'>('fair_value')
    const api = useH3AdditionCheck({
      allResponses: computed(() => allResponses.value) as any,
      wpId: ref('wp'), projectId: ref('p'),
      getValue, setValue, saveImmediate, measurementModel,
    })
    const added = api.fillFromSampledVouchers([
      { voucherNo: 'F1', voucherDate: '2025-05-01', counterpartName: '公允资产', debitAmount: 800000 },
    ])
    expect(added).toBe(1)
    expect(api.fairRows.value.length).toBe(1)
    expect(api.fairRows.value[0].fairValue).toBe(800000)
    expect(api.fairRows.value[0].endBalance).toBe(800000)
  })
})

// ─── #3 折旧整体重算 ──────────────────────────────────────────────────────────
describe('useH3Depreciation.depreciationRecalc', () => {
  function seed() {
    return {
      'H3-7-dep-rows': [
        { rowId: 'a', assetName: '楼A', originalCost: 1000000, usefulLife: 20, salvageRate: 0.05, bookDepreciation: 47500 },
        { rowId: 'b', assetName: '楼B', originalCost: 1000000, usefulLife: 20, salvageRate: 0.05, bookDepreciation: 47500 },
      ],
    }
  }
  function build(store: ReturnType<typeof makeStore>) {
    const branch = ref<'noImpair' | 'withImpair'>('noImpair')
    return useH3Depreciation({
      allResponses: computed(() => store.allResponses.value) as any,
      wpId: ref('wp'), projectId: ref('p'), branch,
      auditYear: ref(2025),
      getValue: store.getValue, setValue: store.setValue, saveImmediate: store.saveImmediate,
    })
  }

  it('理论综合折旧率与预期折旧正确，账面一致时不告警', () => {
    const store = makeStore(seed())
    const api = build(store)
    // 综合率 = Σ(cost×0.95/20)/Σcost = 95000/2000000 = 0.0475
    expect(api.impliedCompositeRate.value).toBeCloseTo(0.0475, 6)
    const rc = api.depreciationRecalc.value
    expect(rc.grossTotal).toBe(2000000)
    expect(rc.expected).toBeCloseTo(95000, 2)
    expect(rc.booked).toBeCloseTo(95000, 2)
    expect(rc.flagged).toBe(false)
    expect(rc.hasBasis).toBe(true)
  })

  it('账面显著偏离预期时触发差异率>10%告警', () => {
    const store = makeStore({
      'H3-7-dep-rows': [
        { rowId: 'a', assetName: '楼A', originalCost: 1000000, usefulLife: 20, salvageRate: 0.05, bookDepreciation: 80000 },
      ],
    })
    const api = build(store)
    const rc = api.depreciationRecalc.value
    // expected = 1000000*0.0475 = 47500; booked 80000; diffRate = 32500/47500 ≈ 68% > 10%
    expect(rc.flagged).toBe(true)
    expect(rc.diffRatePct).toBeGreaterThan(10)
  })

  it('手工综合折旧率覆盖生效', () => {
    const store = makeStore(seed())
    const api = build(store)
    api.setDepRecalcRate(10) // 10%
    expect(api.depreciationRecalc.value.isManualRate).toBe(true)
    expect(api.depreciationRecalc.value.rate).toBeCloseTo(0.1, 6)
    expect(api.depreciationRecalc.value.expected).toBeCloseTo(200000, 2)
    api.setDepRecalcRate(null) // 恢复推导
    expect(api.depreciationRecalc.value.isManualRate).toBe(false)
    expect(api.depreciationRecalc.value.rate).toBeCloseTo(0.0475, 6)
  })
})

// ─── #4 CAS39 公允价值层次披露 ────────────────────────────────────────────────
describe('useH3Disclosure fair value hierarchy', () => {
  function build(store: ReturnType<typeof makeStore>, variant: 'listed' | 'soe' = 'listed') {
    return useH3Disclosure({
      allResponses: computed(() => store.allResponses.value) as any,
      wpId: ref('wp'),
      getValue: store.getValue, setValue: store.setValue, saveImmediate: store.saveImmediate,
      measurementModel: ref('fair_value'),
      variant: ref(variant),
    } as any)
  }

  it('按层次汇总合计', () => {
    const store = makeStore()
    const api = build(store)
    api.addFvHierarchyRow({ category: '写字楼', level: '2', fairValue: 3000000 })
    api.addFvHierarchyRow({ category: '商铺', level: '3', fairValue: 2000000, valuationTechnique: '收益法', keyInputs: '资本化率' })
    const t = api.fvHierarchyTotalsByLevel.value
    expect(t.level2).toBe(3000000)
    expect(t.level3).toBe(2000000)
    expect(t.total).toBe(5000000)
  })

  it('从 H3-8 复核带入层次行（默认第三层次），按名称去重', () => {
    const store = makeStore({
      'H3-8-calc-rows': [
        { assetName: '写字楼', endingBalance: 4000000 },
        { assetName: '商铺', appraisalValue: 1500000 },
      ],
    })
    const api = build(store)
    const r = api.importFvHierarchyFromH38()
    expect(r.added).toBe(2)
    expect(api.fvHierarchyRows.value.length).toBe(2)
    expect(api.fvHierarchyRows.value[0].level).toBe('3')
    expect(api.fvHierarchyRows.value[0].fairValue).toBe(4000000)
    expect(api.fvHierarchyTotalsByLevel.value.total).toBe(5500000)
    // 再次带入不重复
    const again = api.importFvHierarchyFromH38()
    expect(again.added).toBe(0)
  })
})

// ─── #7 crossWpEventBridge 桥接 impairment:calculated ─────────────────────────
import { BRIDGED_EVENTS, normalizeBridgedPayload } from '@/utils/crossWpEventBridge'

describe('crossWpEventBridge impairment:calculated', () => {
  it('已纳入桥接事件集合', () => {
    expect(BRIDGED_EVENTS.has('impairment:calculated')).toBe(true)
  })

  it('金额别名 totalRequiredProvision / amount / supplement 互填并兜底 wpCode', () => {
    const p1 = normalizeBridgedPayload('impairment:calculated', { supplement: 1234, wp_code: 'H3' })
    expect(p1.totalRequiredProvision).toBe(1234)
    expect(p1.amount).toBe(1234)
    expect(p1.wpCode).toBe('H3')
    expect(typeof p1.timestamp).toBe('number')

    const p2 = normalizeBridgedPayload('impairment:calculated', { totalRequiredProvision: 500 })
    expect(p2.amount).toBe(500)
  })
})
