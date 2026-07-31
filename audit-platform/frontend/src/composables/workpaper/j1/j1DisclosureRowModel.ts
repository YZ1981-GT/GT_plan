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

// ─────────────────── 父行派生（源模板同表内 SUM 公式） ───────────────────
//
// 源模板里父行是 SUM 公式而非录入项：
//   上市 `B20=SUM(B21:B27)`（社会保险费 = Σ 其中：医疗/工伤/生育 + 预留区）
//   上市 `B41=SUM(B42:B45)`（离职后福利 = Σ 其中：基本养老/失业/年金/其他）
//   国企 `B19=SUM(B20:B23)` / `B32=SUM(B33:B36)` 同构
// 且合计行公式显式排除这些「其中：」子行（`B35=SUM(B18:B20)+SUM(B28:B34)`）→
// 父行是纯派生量，不能手工录入，否则与子项之和打架且无从判断谁对。
//
// 通用规则（覆盖上述两处，且对「+ 新增行」自动生效）：
//   **非缩进行若其后紧跟 ≥1 个连续缩进行，则该行 期初/增加/减少 = 子行对应列之和**
// 期末列不单独求和 —— 仍由 `recalcDisclosureRow` 按「期初 + 增加 − 减少」派生，
// 与其余行同口径（源模板国企 E 列亦是 `=B+C-D`）。

/** 找出每个派生父行在 `rows` 中的下标 → 其连续缩进子行下标区间 */
function parentChildSpans(rows: readonly J1DisclosureRow[]): Array<[number, number[]]> {
  const out: Array<[number, number[]]> = []
  for (let i = 0; i < rows.length; i += 1) {
    const row = rows[i]
    if (row.isSubtotal || row.indent) continue
    const children: number[] = []
    for (let j = i + 1; j < rows.length; j += 1) {
      const next = rows[j]
      if (next.isSubtotal || !next.indent) break
      children.push(j)
    }
    if (children.length > 0) out.push([i, children])
  }
  return out
}

/**
 * 派生父行的 id 集合（供 UI 把这些行渲染成只读公式单元格）。
 *
 * 无缩进子行的行**不在其中** —— 行为与历史实现一致（可手工录入）。
 */
export function derivedParentIds(rows: readonly J1DisclosureRow[]): string[] {
  return parentChildSpans(rows).map(([i]) => rows[i].id)
}

/**
 * 把派生父行改写为其紧邻缩进子行之和（就地修改）。
 *
 * @returns 实际被改写的父行数（值本就相等时不计入，便于调用方判断是否需要落库）
 */
export function applyParentSums(rows: J1DisclosureRow[]): number {
  let changed = 0
  for (const [i, children] of parentChildSpans(rows)) {
    const parent = rows[i]
    const begin = children.reduce((s, j) => s + (rows[j].beginBalance || 0), 0)
    const increase = children.reduce((s, j) => s + (rows[j].increase || 0), 0)
    const decrease = children.reduce((s, j) => s + (rows[j].decrease || 0), 0)
    if (
      parent.beginBalance === begin &&
      parent.increase === increase &&
      parent.decrease === decrease
    ) {
      continue
    }
    parent.beginBalance = begin
    parent.increase = increase
    parent.decrease = decrease
    recalcDisclosureRow(parent)
    changed += 1
  }
  return changed
}
