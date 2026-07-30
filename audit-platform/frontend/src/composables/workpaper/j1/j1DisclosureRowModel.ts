/**
 * j1DisclosureRowModel — J1 披露表行模型与合计口径（**leaf 模块，零依赖**）
 *
 * 从 `useJ1DisclosureSections.ts` 抽出，供三方共用而不产生循环依赖：
 *
 * - `useJ1DisclosureSections`（UI 状态 + 持久化，并 re-export 本模块保持既有 import 可用）
 * - `j1DisclosureDetailPull`（从 J1-2 明细带入）
 * - `components/workpaper/composables/j1NoteSectionMap`（同步载荷需要自己补合计行）
 *
 * 口径（源模板实证）：
 * - 期末 = 期初 + 本期增加 − 本期减少（负债贷方；国企侧 E 列显式 `=B+C-D`）
 * - 合计只累加**非缩进**行 —— 缩进行是「其中：」明细，源模板合计公式显式排除
 *   （上市 `B35=SUM(B18:B20)+SUM(B28:B34)`；国企 `B29=SUM(B17:B28)-SUM(B20:B23)`）
 */

export type J1DisclosureVariant = 'listed' | 'soe'

export interface J1DisclosureRow {
  id: string
  label: string
  category: string
  indent?: number
  beginBalance: number
  increase: number
  decrease: number
  endBalance: number
  isSubtotal?: boolean
}

/** 期末余额 = 期初 + 增加 − 减少 */
export function recalcDisclosureRow(row: J1DisclosureRow): J1DisclosureRow {
  row.endBalance = (row.beginBalance || 0) + (row.increase || 0) - (row.decrease || 0)
  return row
}

/** 小计 / 合计：只累加非缩进行（缩进行为「其中：」明细，避免双算） */
export function buildDisclosureSubtotal(
  id: string,
  label: string,
  category: string,
  rows: J1DisclosureRow[],
): J1DisclosureRow {
  const top = rows.filter((r) => !r.indent && !r.isSubtotal)
  return {
    id,
    label,
    category,
    isSubtotal: true,
    beginBalance: top.reduce((s, r) => s + (r.beginBalance || 0), 0),
    increase: top.reduce((s, r) => s + (r.increase || 0), 0),
    decrease: top.reduce((s, r) => s + (r.decrease || 0), 0),
    endBalance: top.reduce((s, r) => s + (r.endBalance || 0), 0),
  }
}
