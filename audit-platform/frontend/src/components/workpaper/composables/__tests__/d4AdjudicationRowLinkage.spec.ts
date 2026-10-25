/**
 * d4AdjudicationRowLinkage 守卫 —— D4-2/D4-3 明细行 → D4-1 审定表行 computed 派生（打通死代码）
 *
 * Spec: .kiro/specs/d4-price-analysis-writeback-linkage/  Property 1 / Requirements 1.1-1.6
 *
 * 背景：D4 原用 `d4:sync-row` CustomEvent 同步行结构但**无接收端**（死代码）。
 * 参照 D2 范式改为 computed 派生：D4-1 审定表主营/其他产品行 = computed 自
 * mainRevenueByProduct/otherRevenueByItem（读 D4-2-rows/D4-3-rows）。
 *
 * 本守卫断言**行为**（派生行数随上游明细增减）而非字符串存在。变异检验：
 * 把 sections 的 crossSheet 派生依赖改空 → 派生行数恒 0 → 本守卫必红。
 */
import { describe, it, expect } from 'vitest'
import { ref, effectScope, type Ref } from 'vue'
import { useD4Adjudication } from '../useD4Adjudication'
import type { ChecklistResponse } from '../useD4FormData'

function buildResponses(d4Row2: any[], d4Row3: any[] = []): Ref<Map<string, ChecklistResponse>> {
  const map = new Map<string, ChecklistResponse>()
  if (d4Row2.length > 0) {
    map.set('D4-2-rows', { item_id: 'D4-2-rows', conclusion: null, remark: JSON.stringify(d4Row2) })
  }
  if (d4Row3.length > 0) {
    map.set('D4-3-rows', { item_id: 'D4-3-rows', conclusion: null, remark: JSON.stringify(d4Row3) })
  }
  return ref(map)
}

/** 在 effectScope 内调 useD4Adjudication（避开 onBeforeUnmount 无活动组件告警），返回结果 + dispose */
function runAdjudication(allResponses: Ref<Map<string, ChecklistResponse>>) {
  const scope = effectScope()
  const api = scope.run(() =>
    useD4Adjudication({
      wpId: ref('wp-test'),
      projectId: ref('proj-test'),
      allResponses,
      isReadonly: ref(false),
    }),
  )!
  return { api, dispose: () => scope.stop() }
}

const monthRow = (product: string, monthVal: number) => ({
  rowId: `r-${product}`,
  product,
  months: Array(12).fill(monthVal),
  auditAdjustment: 0,
  priorUnadjusted: 0,
  priorAdjustment: 0,
})

describe('d4-price-analysis-writeback-linkage / Property 1: D4-1 审定行 computed 派生自 D4-2/D4-3', () => {
  it('D4-2 两产品 → 主营区块恰含 2 个 isFromCrossSheet 派生行', () => {
    const responses = buildResponses([monthRow('产品A', 100), monthRow('产品B', 200)])
    const { api, dispose } = runAdjudication(responses)
    try {
      const mainSection = api.sections.value.find(s => s.sectionKey === 'main-revenue')!
      const crossRows = mainSection.rows.filter(r => r.isFromCrossSheet)
      expect(crossRows.map(r => r.label).sort()).toEqual(['产品A', '产品B'])
      // 派生行未审数 = 上游聚合（12 月 × 值）
      const a = crossRows.find(r => r.label === '产品A')!
      expect(a.currentUnadjusted).toBeCloseTo(1200, 5)
    } finally {
      dispose()
    }
  })

  it('删除一个产品 → 派生行数从 2 降到 1（行结构真联动）', () => {
    const responses = buildResponses([monthRow('产品A', 100), monthRow('产品B', 200)])
    const { api, dispose } = runAdjudication(responses)
    try {
      let mainCross = api.sections.value
        .find(s => s.sectionKey === 'main-revenue')!.rows.filter(r => r.isFromCrossSheet)
      expect(mainCross).toHaveLength(2)

      // 模拟 D4-2 删掉产品B（宿主保存后 allResponses 变化）
      responses.value = new Map(responses.value)
      responses.value.set('D4-2-rows', {
        item_id: 'D4-2-rows', conclusion: null,
        remark: JSON.stringify([monthRow('产品A', 100)]),
      })

      mainCross = api.sections.value
        .find(s => s.sectionKey === 'main-revenue')!.rows.filter(r => r.isFromCrossSheet)
      expect(mainCross).toHaveLength(1)
      expect(mainCross[0].label).toBe('产品A')
    } finally {
      dispose()
    }
  })

  it('D4-3 项目 → 其他区块派生行', () => {
    const responses = buildResponses(
      [],
      [{ rowId: 'o1', item: '废料销售', currentUnadjusted: 5000, currentAdjustment: 0, priorUnadjusted: 0, priorAdjustment: 0 }],
    )
    const { api, dispose } = runAdjudication(responses)
    try {
      const otherSection = api.sections.value.find(s => s.sectionKey === 'other-revenue')!
      const crossRows = otherSection.rows.filter(r => r.isFromCrossSheet)
      expect(crossRows.map(r => r.label)).toEqual(['废料销售'])
      expect(crossRows[0].currentUnadjusted).toBeCloseTo(5000, 5)
    } finally {
      dispose()
    }
  })

  it('派生行金额只读（isFromCrossSheet=true 且 isEditable=false）', () => {
    const responses = buildResponses([monthRow('产品A', 100)])
    const { api, dispose } = runAdjudication(responses)
    try {
      const row = api.sections.value
        .find(s => s.sectionKey === 'main-revenue')!.rows.find(r => r.isFromCrossSheet)!
      expect(row.isFromCrossSheet).toBe(true)
      expect(row.isEditable).toBe(false)
    } finally {
      dispose()
    }
  })

  it('派生行与同名手工行去重（派生优先，Req 1.6）', () => {
    const responses = buildResponses([monthRow('产品A', 100)])
    // 加一个同名手工行清单
    responses.value.set('D4-1-rows', {
      item_id: 'D4-1-rows', conclusion: null,
      remark: JSON.stringify([{ rowId: 'm1', label: '产品A', source: 'manual' }]),
    })
    const { api, dispose } = runAdjudication(responses)
    try {
      const rows = api.sections.value.find(s => s.sectionKey === 'main-revenue')!.rows
      const productA = rows.filter(r => r.label === '产品A')
      expect(productA).toHaveLength(1) // 不重复
      expect(productA[0].isFromCrossSheet).toBe(true) // 派生优先
    } finally {
      dispose()
    }
  })
})
