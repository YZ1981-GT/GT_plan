/**
 * G13 附注披露 — 空项省略与「其中」父子可见性
 *
 * 对齐 xlsx「不存在的项目可以删除」；附注同步时亦不披露空行。
 */
import type { G13DisclosureRowDef } from './g13Constants'

export const G13_DISCLOSURE_AMOUNT_EPS = 0.005

export interface G13DisclosureAmountRow {
  rowKey: string
  currentAmount: number
  priorAmount: number
  label?: string
  remark?: string
}

export function hasG13DisclosureAmount(
  row: Pick<G13DisclosureAmountRow, 'currentAmount' | 'priorAmount'> & { remark?: string },
): boolean {
  return Math.abs(row.currentAmount) >= G13_DISCLOSURE_AMOUNT_EPS
    || Math.abs(row.priorAmount) >= G13_DISCLOSURE_AMOUNT_EPS
    || Boolean(String(row.remark ?? '').trim())
}

function amountByKey(rows: readonly G13DisclosureAmountRow[]): Map<string, G13DisclosureAmountRow> {
  return new Map(rows.map((r) => [r.rowKey, r]))
}

function childDefsOf(defs: readonly G13DisclosureRowDef[], parentKey: string): G13DisclosureRowDef[] {
  return defs.filter((d) => d.parentKey === parentKey)
}

/**
 * - 主行：自身有数，或任一「其中」子行有数（避免孤儿其中）
 * - 「其中」：自身有数才显示
 */
export function isG13DisclosureRowVisible(
  rowKey: string,
  rows: readonly G13DisclosureAmountRow[],
  defs: readonly G13DisclosureRowDef[],
  opts?: { includeEmpty?: boolean },
): boolean {
  if (opts?.includeEmpty) return true
  if (rowKey === 'total') return true
  const def = defs.find((d) => d.rowKey === rowKey)
  if (!def) return false
  const byKey = amountByKey(rows)
  const self = byKey.get(rowKey)
  if (!self) return false

  if (def.ofWhich) {
    return hasG13DisclosureAmount(self)
  }

  if (hasG13DisclosureAmount(self)) return true
  return childDefsOf(defs, rowKey).some((c) => {
    const child = byKey.get(c.rowKey)
    return child != null && hasG13DisclosureAmount(child)
  })
}

export function filterG13DisclosureRows<T extends G13DisclosureAmountRow>(
  rows: readonly T[],
  defs: readonly G13DisclosureRowDef[],
  opts?: { includeEmpty?: boolean },
): T[] {
  const byKey = amountByKey(rows)
  const out: T[] = []
  for (const def of defs) {
    if (!isG13DisclosureRowVisible(def.rowKey, rows, defs, opts)) continue
    const row = byKey.get(def.rowKey) as T | undefined
    if (row) out.push(row)
  }
  return out
}

export function g13DisclosureHasAnyAmount(rows: readonly G13DisclosureAmountRow[]): boolean {
  return rows.some((r) => r.rowKey !== 'total' && hasG13DisclosureAmount(r))
}
