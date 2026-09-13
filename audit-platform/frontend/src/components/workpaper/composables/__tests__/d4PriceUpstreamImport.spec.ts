/**
 * d4PriceUpstreamImport — D4-10/11 上游导入守卫
 *
 * Property 2: 导入后 rows 客户名集合 ⊇ 上游，手工行不被覆盖
 * Spec: d4-price-analysis-writeback-linkage Task 7
 */
import { describe, it, expect } from 'vitest'

describe('D4-10 上游导入 merge', () => {
  interface PriceRow {
    customer: string
    product: string
    amount: number
    quantity: number
    unitPrice: number
  }

  /**
   * 模拟 D4-10 importFromUpstream 的核心 merge 逻辑
   */
  function mergeUpstreamCustomers(
    existing: PriceRow[],
    upstream: Array<{ name: string; amount: number }>,
  ): PriceRow[] {
    const result = [...existing]
    const existingNames = new Set(existing.map(r => r.customer))
    for (const c of upstream) {
      if (existingNames.has(c.name)) continue
      result.push({
        customer: c.name,
        product: '',
        amount: c.amount,
        quantity: 0,
        unitPrice: 0,
      })
    }
    return result
  }

  it('空表 + 3 上游客户 → 3 行', () => {
    const result = mergeUpstreamCustomers([], [
      { name: '客户A', amount: 100 },
      { name: '客户B', amount: 200 },
      { name: '客户C', amount: 300 },
    ])
    expect(result).toHaveLength(3)
    expect(result.map(r => r.customer)).toEqual(['客户A', '客户B', '客户C'])
  })

  it('已有 1 行 + 3 上游 → merge 后 3 行（不重复）', () => {
    const existing: PriceRow[] = [{ customer: '客户A', product: '改过的产品', amount: 999, quantity: 10, unitPrice: 99 }]
    const result = mergeUpstreamCustomers(existing, [
      { name: '客户A', amount: 100 },
      { name: '客户B', amount: 200 },
      { name: '客户C', amount: 300 },
    ])
    expect(result).toHaveLength(3)
    // 手工行不被覆盖
    expect(result[0].amount).toBe(999)
    expect(result[0].product).toBe('改过的产品')
  })

  it('上游空 → 不新增行', () => {
    const existing: PriceRow[] = [{ customer: 'X', product: '', amount: 0, quantity: 0, unitPrice: 0 }]
    const result = mergeUpstreamCustomers(existing, [])
    expect(result).toHaveLength(1)
  })

  it('只填录入列，不填派生列', () => {
    const result = mergeUpstreamCustomers([], [{ name: '客户A', amount: 100 }])
    expect(result[0].unitPrice).toBe(0) // 派生/手工列保持 0
    expect(result[0].quantity).toBe(0)
  })
})

describe('D4-11 上游导入 merge', () => {
  interface D11Row {
    product: string
    customer: string
    unitPrice: number
  }

  function mergeUpstreamProducts(
    existing: D11Row[],
    upstream: Array<{ product: string }>,
  ): D11Row[] {
    const result = [...existing]
    const existingProducts = new Set(existing.map(r => r.product))
    for (const p of upstream) {
      if (existingProducts.has(p.product)) continue
      result.push({ product: p.product, customer: '', unitPrice: 0 })
    }
    return result
  }

  it('空表 + 2 上游产品 → 2 行', () => {
    const result = mergeUpstreamProducts([], [{ product: '铝材' }, { product: '钢材' }])
    expect(result).toHaveLength(2)
  })

  it('已有行不被覆盖', () => {
    const existing: D11Row[] = [{ product: '铝材', customer: '手工填的', unitPrice: 99 }]
    const result = mergeUpstreamProducts(existing, [{ product: '铝材' }, { product: '钢材' }])
    expect(result).toHaveLength(2)
    expect(result[0].unitPrice).toBe(99) // 手工值保留
  })
})

describe('D4-11 chip bug 修复', () => {
  it('D4-11 chip 应指向 wp:D4-2 而非 wp:D4-10', async () => {
    // 静态检查：读取 D4TabProductPrice.vue 源码中的 GtIndexChip value
    const fs = await import('fs')
    const path = await import('path')
    const vuePath = path.resolve(__dirname, '../../d4/analysis/D4TabProductPrice.vue')
    const content = fs.readFileSync(vuePath, 'utf-8')
    // 不应包含错误的 wp:D4-10 chip（GtIndexChip 范围内）
    const chipMatches = content.match(/GtIndexChip\s+value="wp:D4-\d+"/g) || []
    expect(chipMatches).not.toContain('GtIndexChip value="wp:D4-10"')
    expect(chipMatches.some(m => m.includes('wp:D4-2'))).toBe(true)
  })
})
