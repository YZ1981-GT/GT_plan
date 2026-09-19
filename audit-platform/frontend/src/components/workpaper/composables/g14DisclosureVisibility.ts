/**
 * G14 附注披露 — 空项省略
 *
 * 对齐 xlsx「以下不存在的项目可以删除」；附注同步时亦不披露空行。
 */
export const G14_DISCLOSURE_AMOUNT_EPS = 0.005

export interface G14DisclosureAmountRow {
  rowKey: string
  currentAmount: number
  priorAmount: number
  label?: string
  remark?: string
}

export function hasG14DisclosureAmount(
  row: Pick<G14DisclosureAmountRow, 'currentAmount' | 'priorAmount'> & { remark?: string },
): boolean {
  return Math.abs(row.currentAmount) >= G14_DISCLOSURE_AMOUNT_EPS
    || Math.abs(row.priorAmount) >= G14_DISCLOSURE_AMOUNT_EPS
    || Boolean(String(row.remark ?? '').trim())
}

export function filterG14DisclosureRows<T extends G14DisclosureAmountRow>(
  rows: readonly T[],
  opts?: { includeEmpty?: boolean },
): T[] {
  if (opts?.includeEmpty) return rows.filter((r) => r.rowKey !== 'total')
  return rows.filter((r) => r.rowKey !== 'total' && hasG14DisclosureAmount(r))
}

export function g14DisclosureHasAnyAmount(rows: readonly G14DisclosureAmountRow[]): boolean {
  return rows.some((r) => r.rowKey !== 'total' && hasG14DisclosureAmount(r))
}
