/**
 * d4PriceUpstreamMerge — D4-10/11 上游取数 merge 纯函数（零 Vue 依赖，可测）
 *
 * spec: .kiro/specs/d4-price-analysis-writeback-linkage/ Req 2.2 / 3.2 / Property 2
 *
 * merge 语义（两表共用）：按业务键（客户名 / 品种）并集导入上游行，
 * **不覆盖已有手工行的非导入字段**；已存在的键仅在导入列为空时补值。
 */

/** D4-10 客户价格行（仅列出 merge 涉及字段） */
export interface CustomerPriceRowLike {
  customer: string
  amount: number
  [k: string]: any
}

/** D4-11 产品价格行（仅列出 merge 涉及字段） */
export interface ProductPriceRowLike {
  product: string
  [k: string]: any
}

export interface UpstreamCustomer { name: string; amount: number }
export interface UpstreamProduct { product: string; revenue: number }

export interface MergeSummary { added: number; updated: number }

/**
 * D4-10：按客户名 merge 上游客户结构。
 * - 新客户 → push（带 amount）
 * - 已存在客户 → 仅当 amount 为空(0/未填)时补 amount，不覆盖手工值
 * @param mkRow 新行工厂（组件传入，保证行结构完整）
 */
export function mergeCustomers(
  rows: CustomerPriceRowLike[],
  upstream: readonly UpstreamCustomer[],
  mkRow: (name: string, amount: number) => CustomerPriceRowLike,
): MergeSummary {
  const byName = new Map(rows.map(r => [String(r.customer ?? '').trim(), r]))
  let added = 0, updated = 0
  for (const u of upstream) {
    const name = String(u.name ?? '').trim()
    if (!name) continue
    const hit = byName.get(name)
    if (hit) {
      if (!hit.amount) { hit.amount = u.amount; updated++ }
    } else {
      const row = mkRow(name, u.amount)
      rows.push(row)
      byName.set(name, row)
      added++
    }
  }
  return { added, updated }
}

/**
 * D4-11：按品种 merge 上游产品清单（只带产品名，单价/数量手工录）。
 * - 新品种 → push；已存在 → 跳过（不改任何字段）
 */
export function mergeProducts(
  rows: ProductPriceRowLike[],
  upstream: readonly UpstreamProduct[],
  mkRow: (product: string) => ProductPriceRowLike,
): MergeSummary {
  const existing = new Set(rows.map(r => String(r.product ?? '').trim()))
  let added = 0
  for (const u of upstream) {
    const name = String(u.product ?? '').trim()
    if (!name || existing.has(name)) continue
    rows.push(mkRow(name))
    existing.add(name)
    added++
  }
  return { added, updated: 0 }
}
