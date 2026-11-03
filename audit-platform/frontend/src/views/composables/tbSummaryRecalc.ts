export interface TbSummaryAuditedRow {
  unadjusted?: unknown
  aje_dr?: unknown
  aje_cr?: unknown
  rcl_dr?: unknown
  rcl_cr?: unknown
  audited?: number | null
}

function amount(value: unknown): number {
  const parsed = Number(value)
  return Number.isFinite(parsed) ? parsed : 0
}

/** 保持试算汇总表既有口径：未审 + AJE借-贷 + RCL借-贷，分币四舍五入，零记空。 */
export function calculateTbSummaryAudited(row: TbSummaryAuditedRow): number | null {
  const value = amount(row.unadjusted)
    + amount(row.aje_dr)
    - amount(row.aje_cr)
    + amount(row.rcl_dr)
    - amount(row.rcl_cr)
  const rounded = Math.round(value * 100) / 100
  return rounded === 0 ? null : rounded
}

/** 只重算发生编辑的这一行；值未变化时不触发额外响应式更新。 */
export function recalcTbSummaryRow(row: TbSummaryAuditedRow): boolean {
  const next = calculateTbSummaryAudited(row)
  if (Object.is(row.audited ?? null, next)) return false
  row.audited = next
  return true
}

/** 加载、导入等批量边界显式调用，不由 deep watch 隐式扫描全表。 */
export function recalcTbSummaryRows(rows: TbSummaryAuditedRow[]): number {
  let changed = 0
  for (const row of rows) {
    if (recalcTbSummaryRow(row)) changed += 1
  }
  return changed
}
