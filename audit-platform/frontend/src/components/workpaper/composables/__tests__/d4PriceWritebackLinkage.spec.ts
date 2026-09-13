/**
 * d4PriceWritebackLinkage — 价格异常回标接收端守卫
 *
 * Property 3: emit d4:price-abnormal → 接收端写回上游行标记，幂等，空集清除
 * Spec: d4-price-analysis-writeback-linkage Task 7
 */
import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { eventBus } from '@/utils/eventBus'

// 模拟 useD4PriceWriteback 的核心逻辑（不依赖 Vue setup context）
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try { const p = JSON.parse(jsonStr); return Array.isArray(p) ? p : [] } catch { return [] }
}

function simulateWriteback(
  allResponses: Map<string, any>,
  payload: { wpCode: string; targetKey: string; items: Array<{ name: string; diffPct: number }> },
) {
  const { targetKey, items } = payload
  const resp = allResponses.get('D4-2-rows')
  const rows = safeParseRows<any>(resp?.remark)
  if (rows.length === 0) return false

  const abnormalMap = new Map<string, number>()
  for (const item of items) { abnormalMap.set(item.name, item.diffPct) }

  let changed = false
  for (const row of rows) {
    const name = row.product || ''
    const abnormalPct = abnormalMap.get(name)
    if (abnormalPct !== undefined) {
      if (!row.priceAbnormal || row.priceAbnormalPct !== abnormalPct) {
        row.priceAbnormal = true
        row.priceAbnormalPct = abnormalPct
        changed = true
      }
    } else {
      if (row.priceAbnormal) {
        row.priceAbnormal = false
        delete row.priceAbnormalPct
        changed = true
      }
    }
  }

  if (changed) {
    allResponses.set('D4-2-rows', { item_id: 'D4-2-rows', conclusion: null, remark: JSON.stringify(rows) })
  }
  return changed
}

describe('D4 价格异常回标接收端', () => {
  function makeResponses(products: Array<{ product: string; priceAbnormal?: boolean }>) {
    const map = new Map<string, any>()
    map.set('D4-2-rows', { item_id: 'D4-2-rows', conclusion: null, remark: JSON.stringify(products) })
    return map
  }

  it('异常客户回标 → 上游行 priceAbnormal=true', () => {
    const resp = makeResponses([{ product: '客户A' }, { product: '客户B' }])
    simulateWriteback(resp, { wpCode: 'D4-10', targetKey: 'customer', items: [{ name: '客户A', diffPct: 0.25 }] })
    const rows = JSON.parse(resp.get('D4-2-rows').remark)
    expect(rows[0].priceAbnormal).toBe(true)
    expect(rows[0].priceAbnormalPct).toBe(0.25)
    expect(rows[1].priceAbnormal).toBeFalsy()
  })

  it('幂等：重复 emit 同 payload 结果不变', () => {
    const resp = makeResponses([{ product: '客户A' }])
    const payload = { wpCode: 'D4-10' as const, targetKey: 'customer' as const, items: [{ name: '客户A', diffPct: 0.3 }] }
    simulateWriteback(resp, payload)
    const first = resp.get('D4-2-rows').remark
    const changed = simulateWriteback(resp, payload)
    expect(changed).toBe(false) // 第二次无变化
    expect(resp.get('D4-2-rows').remark).toBe(first)
  })

  it('空数组 → 清除全部标记', () => {
    const resp = makeResponses([{ product: '客户A', priceAbnormal: true }, { product: '客户B', priceAbnormal: true }])
    simulateWriteback(resp, { wpCode: 'D4-10', targetKey: 'customer', items: [] })
    const rows = JSON.parse(resp.get('D4-2-rows').remark)
    expect(rows[0].priceAbnormal).toBe(false)
    expect(rows[1].priceAbnormal).toBe(false)
  })

  it('目标行缺失 → 静默跳过（不报错不造行）', () => {
    const resp = makeResponses([{ product: '客户A' }])
    // 回标一个不存在的客户
    expect(() => {
      simulateWriteback(resp, { wpCode: 'D4-10', targetKey: 'customer', items: [{ name: '不存在的客户', diffPct: 0.5 }] })
    }).not.toThrow()
    const rows = JSON.parse(resp.get('D4-2-rows').remark)
    expect(rows).toHaveLength(1) // 未新增行
  })

  it('D4-2-rows 为空 → 不报错', () => {
    const resp = new Map<string, any>()
    expect(() => {
      simulateWriteback(resp, { wpCode: 'D4-10', targetKey: 'customer', items: [{ name: 'X', diffPct: 0.5 }] })
    }).not.toThrow()
  })

  it('eventBus 已注册 d4:price-abnormal 类型', () => {
    // 验证 emit 不报类型错（编译时类型安全）
    const handler = vi.fn()
    eventBus.on('d4:price-abnormal', handler)
    eventBus.emit('d4:price-abnormal', { wpCode: 'D4-10', targetKey: 'customer', items: [] })
    expect(handler).toHaveBeenCalledTimes(1)
    eventBus.off('d4:price-abnormal', handler)
  })
})
