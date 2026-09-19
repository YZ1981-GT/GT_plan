/**
 * d4PriceWritebackLinkage 守卫 —— D4-10/11 价格异常回标 D4-2（方案 C 回写侧，非死代码）
 *
 * Spec: .kiro/specs/d4-price-analysis-writeback-linkage/ Property 3 / Requirements 4.1-4.5, 6.2
 *
 * 断言接线**行为**：emit d4:price-abnormal → 接收端真消费、写回 D4-2-rows 行标记；
 * 幂等（同集重复不变、空集清除）；目标行缺失静默跳过。变异：删接收端 eventBus.on → 必红。
 */
import { describe, it, expect, beforeEach, afterEach } from 'vitest'
import * as fc from 'fast-check'
import { ref, effectScope, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { applyPriceAbnormal, useD4PriceWriteback } from '../useD4PriceWriteback'
import type { ChecklistResponse } from '../useD4FormData'

// ─── 纯函数 applyPriceAbnormal（Property 3 幂等） ────────────────────────

describe('applyPriceAbnormal — 幂等回标（Property 3）', () => {
  const mkRows = () => [
    { rowId: 'r1', product: '产品A', months: [] },
    { rowId: 'r2', product: '产品B', months: [] },
    { rowId: 'r3', product: '产品C', months: [] },
  ]

  it('异常集写回对应行的 priceAbnormal[wpCode]', () => {
    const rows = mkRows()
    const changed = applyPriceAbnormal(rows, 'D4-10', [{ name: '产品A', diffPct: 0.35 }])
    expect(changed).toBe(true)
    expect((rows[0] as any).priceAbnormal).toEqual({ 'D4-10': 0.35 })
    expect((rows[1] as any).priceAbnormal).toBeUndefined()
  })

  it('幂等：同一异常集重复写入第二次无变化', () => {
    const rows = mkRows()
    applyPriceAbnormal(rows, 'D4-10', [{ name: '产品A', diffPct: 0.35 }])
    const changed2 = applyPriceAbnormal(rows, 'D4-10', [{ name: '产品A', diffPct: 0.35 }])
    expect(changed2).toBe(false)
    expect((rows[0] as any).priceAbnormal).toEqual({ 'D4-10': 0.35 })
  })

  it('空集清除该来源标记（Req 4.5）', () => {
    const rows = mkRows()
    applyPriceAbnormal(rows, 'D4-10', [{ name: '产品A', diffPct: 0.35 }])
    const changed = applyPriceAbnormal(rows, 'D4-10', [])
    expect(changed).toBe(true)
    expect((rows[0] as any).priceAbnormal).toBeUndefined()
  })

  it('两来源(D4-10/D4-11)标记互不覆盖，同行可并存', () => {
    const rows = mkRows()
    applyPriceAbnormal(rows, 'D4-10', [{ name: '产品A', diffPct: 0.3 }])
    applyPriceAbnormal(rows, 'D4-11', [{ name: '产品A', diffPct: 0.15 }])
    expect((rows[0] as any).priceAbnormal).toEqual({ 'D4-10': 0.3, 'D4-11': 0.15 })
    // 清 D4-10 不影响 D4-11
    applyPriceAbnormal(rows, 'D4-10', [])
    expect((rows[0] as any).priceAbnormal).toEqual({ 'D4-11': 0.15 })
  })

  it('目标行缺失（异常项 name 无对应产品）静默跳过（Req 4.4）', () => {
    const rows = mkRows()
    const changed = applyPriceAbnormal(rows, 'D4-10', [{ name: '不存在的产品', diffPct: 0.5 }])
    expect(changed).toBe(false)
    expect(rows.every(r => !(r as any).priceAbnormal)).toBe(true)
  })

  it('PBT: 标记集恰等于异常项名集（幂等收敛）', () => {
    fc.assert(
      fc.property(
        fc.uniqueArray(fc.constantFrom('产品A', '产品B', '产品C'), { minLength: 0, maxLength: 3 }),
        (names) => {
          const rows = mkRows()
          const items = names.map(name => ({ name, diffPct: 0.3 }))
          applyPriceAbnormal(rows, 'D4-10', items)
          const marked = rows.filter(r => (r as any).priceAbnormal?.['D4-10'] != null).map(r => r.product)
          expect(new Set(marked)).toEqual(new Set(names))
          // 重复一次幂等
          const changed2 = applyPriceAbnormal(rows, 'D4-10', items)
          expect(changed2).toBe(false)
        },
      ),
      { numRuns: 20 },
    )
  })
})

// ─── 接收端接线（emit → 真消费写回 allResponses） ────────────────────────

describe('useD4PriceWriteback — eventBus 接收端真接线（防死代码回归，Req 6.2）', () => {
  let responses: Ref<Map<string, ChecklistResponse>>
  let scope: ReturnType<typeof effectScope>
  let persisted: ChecklistResponse[]

  beforeEach(() => {
    responses = ref(new Map<string, ChecklistResponse>())
    responses.value.set('D4-2-rows', {
      item_id: 'D4-2-rows', conclusion: null,
      remark: JSON.stringify([{ rowId: 'r1', product: '产品A', months: [] }, { rowId: 'r2', product: '产品B', months: [] }]),
    })
    persisted = []
    scope = effectScope()
    scope.run(() => useD4PriceWriteback({ allResponses: responses, onPersist: (i) => persisted.push(i) }))
  })

  afterEach(() => { scope.stop() })

  it('emit d4:price-abnormal → 接收端写回 D4-2-rows 行标记 + 触发 onPersist', () => {
    eventBus.emit('d4:price-abnormal', { wpCode: 'D4-10', targetKey: 'customer', items: [{ name: '产品A', diffPct: 0.4 }], timestamp: Date.now() })
    const rows = JSON.parse(responses.value.get('D4-2-rows')!.remark!)
    expect(rows[0].priceAbnormal).toEqual({ 'D4-10': 0.4 })
    expect(persisted).toHaveLength(1)
    expect(persisted[0].item_id).toBe('D4-2-rows')
  })

  it('D4-2 未编制（无 D4-2-rows）→ 静默跳过不报错', () => {
    responses.value.delete('D4-2-rows')
    expect(() => {
      eventBus.emit('d4:price-abnormal', { wpCode: 'D4-11', targetKey: 'product', items: [{ name: 'X', diffPct: 0.9 }], timestamp: Date.now() })
    }).not.toThrow()
    expect(persisted).toHaveLength(0)
  })

  it('无变化不触发 onPersist（幂等：连发两次同集只落一次）', () => {
    const payload = { wpCode: 'D4-10' as const, targetKey: 'customer' as const, items: [{ name: '产品A', diffPct: 0.4 }], timestamp: Date.now() }
    eventBus.emit('d4:price-abnormal', payload)
    eventBus.emit('d4:price-abnormal', { ...payload, timestamp: Date.now() + 1 })
    expect(persisted).toHaveLength(1)
  })
})
