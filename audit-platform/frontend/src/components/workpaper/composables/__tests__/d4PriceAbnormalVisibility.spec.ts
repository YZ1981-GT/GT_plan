/**
 * D4-2 价格异常回标可见性 + parse/persist 不剥掉 priceAbnormal。
 *
 * spec: .kiro/specs/d4-price-analysis-writeback-linkage/ Task 8 / Req 4
 */
import { describe, it, expect, afterEach } from 'vitest'
import { ref, effectScope } from 'vue'
import { useD4RevenueDetail } from '../useD4RevenueDetail'
import { applyPriceAbnormal } from '../useD4PriceWriteback'
import type { ChecklistResponse } from '../useD4FormData'

function seedRows(mark?: Record<string, number>) {
  const row: Record<string, unknown> = {
    rowId: 'r1',
    product: '产品A',
    months: [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0],
    auditAdjustment: 0,
    priorUnadjusted: 0,
    priorAdjustment: 0,
    remark: '',
  }
  if (mark) row.priceAbnormal = mark
  return [row]
}

describe('useD4RevenueDetail — priceAbnormal 保留与可见', () => {
  const scopes: Array<ReturnType<typeof effectScope>> = []
  afterEach(() => {
    while (scopes.length) scopes.pop()!.stop()
  })

  function mount(rowsJson: string) {
    const allResponses = ref(
      new Map<string, ChecklistResponse>([
        ['D4-2-rows', { item_id: 'D4-2-rows', conclusion: null, remark: rowsJson }],
      ]),
    )
    const scope = effectScope()
    scopes.push(scope)
    const api = scope.run(() =>
      useD4RevenueDetail({
        wpId: ref('wp'),
        projectId: ref('proj'),
        allResponses,
        isReadonly: ref(false),
      }),
    )!
    return { allResponses, api }
  }

  it('parse 保留 priceAbnormal，rows 暴露给 UI', () => {
    const { api } = mount(JSON.stringify(seedRows({ 'D4-10': 0.35 })))
    expect(api.rows.value).toHaveLength(1)
    expect(api.rows.value[0].priceAbnormal).toEqual({ 'D4-10': 0.35 })
    expect(api.rows.value[0].periodTotal).toBe(100)
  })

  it('applyPriceAbnormal 写回 JSON 后重新 mount 可读到标记', () => {
    const rows = seedRows()
    const items = [{ name: '产品A', diffPct: 0.22 }]
    expect(applyPriceAbnormal(rows, 'D4-11', items)).toBe(true)
    expect(rows[0].priceAbnormal).toEqual({ 'D4-11': 0.22 })

    const { api } = mount(JSON.stringify(rows))
    expect(api.rows.value[0].priceAbnormal).toEqual({ 'D4-11': 0.22 })
  })

  it('无标记行 parse 后 priceAbnormal 为空；带多来源标记往返不丢', () => {
    const { api: emptyApi } = mount(JSON.stringify(seedRows()))
    expect(emptyApi.rows.value[0].priceAbnormal).toBeUndefined()

    const marked = seedRows({ 'D4-10': 0.4, 'D4-11': 0.15 })
    marked[0].remark = 'keep-mark'
    const { api } = mount(JSON.stringify(marked))
    expect(api.rows.value[0].priceAbnormal).toEqual({ 'D4-10': 0.4, 'D4-11': 0.15 })
    expect(api.rows.value[0].remark).toBe('keep-mark')
  })
})
