/**
 * D4 Phase 3 前端种子/预填守卫 —— Property 10 + Property 11
 *
 * spec: four-table-extraction-entry-completion Phase 3 Task 22
 *
 * 🔴 改进（复盘修复项 2）：守卫直接 import 生产代码 d4MarginSeedUtils，
 *    不再在测试文件内重新实现函数副本。组件 D4TabMarginMonthly.vue 消费
 *    同一份代码，守卫与生产指向同一实现。
 */
import { describe, it, expect } from 'vitest'
import {
  seedMonthlyFromD42,
  prefillProductsFromSegments,
} from '../d4/composables/d4MarginSeedUtils'

// ── Property 10: D4-7 月度种子与 D4-2 一致性 ──────────────────────────

describe('Property 10: D4-7 月度种子与 D4-2 一致性', () => {
  it('种子收入 = D4-2 所有产品行 months 按月 SUM', () => {
    const d42Rows = [
      { rowId: 'r1', product: '产品A', months: [100, 200, 300, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
      { rowId: 'r2', product: '产品B', months: [50, 150, 250, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
    ]
    const result = seedMonthlyFromD42(JSON.stringify(d42Rows))!
    expect(result.revenue[0]).toBe(150) // 100+50
    expect(result.revenue[1]).toBe(350) // 200+150
    expect(result.revenue[2]).toBe(550) // 300+250
    for (let i = 3; i < 12; i++) {
      expect(result.revenue[i]).toBe(0)
    }
  })

  it('成本侧恒为 0（D4-2 无成本数据，不伪造）', () => {
    const d42Rows = [
      { rowId: 'r1', product: '产品A', months: [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
    ]
    const result = seedMonthlyFromD42(JSON.stringify(d42Rows))!
    expect(result.cost).toEqual(new Array(12).fill(0))
  })

  it('D4-2 无数据时返回 null（不阻塞手填）', () => {
    expect(seedMonthlyFromD42(null)).toBeNull()
    expect(seedMonthlyFromD42('')).toBeNull()
    expect(seedMonthlyFromD42('[]')).toBeNull()
  })

  it('D4-2 解析失败时返回 null', () => {
    expect(seedMonthlyFromD42('not json')).toBeNull()
  })

  it('行 months 缺失或非数组时跳过该行', () => {
    const d42Rows = [
      { rowId: 'r1', product: 'A', months: [100, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0] },
      { rowId: 'r2', product: 'B', months: 'bad' },
      { rowId: 'r3', product: 'C' },
    ]
    const result = seedMonthlyFromD42(JSON.stringify(d42Rows))!
    expect(result.revenue[0]).toBe(100)
  })
})

// ── Property 11: D4-7 产品预填与 segment_prefill 一致性 ──────────────

describe('Property 11: D4-7 产品预填与 segment_prefill 一致性', () => {
  let seqId = 0
  const testRowIdFactory = () => `test-${++seqId}`

  it('产品数 = segment_prefill.length', () => {
    const segments = [
      { label: '批发', current_revenue: 1000, current_cost: 800, prior_revenue: 900, prior_cost: 700 },
      { label: '零售', current_revenue: 500, current_cost: 400, prior_revenue: 450, prior_cost: 350 },
    ]
    const result = prefillProductsFromSegments(segments, testRowIdFactory)
    expect(result).toHaveLength(2)
  })

  it('字段映射正确：label→name, current_revenue→curRevenue 等', () => {
    const segments = [
      { label: '医疗', current_revenue: 1200, current_cost: 900, prior_revenue: 1100, prior_cost: 850 },
    ]
    const result = prefillProductsFromSegments(segments, testRowIdFactory)
    expect(result[0].name).toBe('医疗')
    expect(result[0].curRevenue).toBe(1200)
    expect(result[0].curCost).toBe(900)
    expect(result[0].priorRevenue).toBe(1100)
    expect(result[0].priorCost).toBe(850)
    expect(result[0].curQty).toBe(0)
    expect(result[0].priorQty).toBe(0)
  })

  it('segment_prefill 为空时产品表为空（不伪造）', () => {
    expect(prefillProductsFromSegments(null)).toEqual([])
    expect(prefillProductsFromSegments([])).toEqual([])
  })

  it('每行有稳定 rowId', () => {
    const segments = [{ label: 'A', current_revenue: 100, current_cost: 80 }]
    const result = prefillProductsFromSegments(segments, testRowIdFactory)
    expect(result[0].rowId).toBeTruthy()
    expect(typeof result[0].rowId).toBe('string')
  })

  it('缺少的字段回退 0 而非 undefined', () => {
    const segments = [{ label: '产品X' }]
    const result = prefillProductsFromSegments(segments, testRowIdFactory)
    expect(result[0].curRevenue).toBe(0)
    expect(result[0].curCost).toBe(0)
    expect(result[0].priorRevenue).toBe(0)
    expect(result[0].priorCost).toBe(0)
  })
})
