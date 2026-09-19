/**
 * I6 附注披露数据模型（上市/国企）
 *
 * 对齐源 xlsx：按费用性质列示，本期/上期发生额。
 * SUMIF(明细表I6-2.费用性质X, 项目, 本期审定Q / 上期审定W)
 */
import { calcMonthlyTotal, calcAuditedAmount } from './useI6FormulaEngine'
import { I6_DEFAULT_DISCLOSURE_CATEGORIES } from './i6NoteSectionMap'

export { I6_DEFAULT_DISCLOSURE_CATEGORIES as I6_EXPENSE_NATURE_OPTIONS }

export interface I6DisclosureRow {
  rowId: string
  /** 费用性质/项目 */
  item: string
  currentAmount: number
  priorAmount: number
  isAutoFilled: boolean
  remark: string
}

export interface I6DisclosureTotals {
  currentAmount: number
  priorAmount: number
}

export const I6_DISC_KEYS = {
  listedRows: 'I6-disc-listed-rows',
  listedCapitalization: 'I6-disc-L-capitalization',
  listedProjects: 'I6-disc-L-projects',
  listedAuditNote: 'I6-disclosure-listed-audit-note',
  listedAuditConclusion: 'I6-disclosure-listed-audit-conclusion',
  soeRows: 'I6-disc-soe-rows',
  soeSupplement: 'I6-disc-S-supplement',
  soeAuditNote: 'I6-disclosure-soe-audit-note',
  soeAuditConclusion: 'I6-disclosure-soe-audit-conclusion',
  legacyListedRows: 'I6-disc-L-categories',
  legacySoeRows: 'I6-disc-S-categories',
} as const

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _round2(n: number): number {
  return Math.round((n + Number.EPSILON) * 100) / 100
}

/** 解析费用性质：优先 X 列，缺省时回退项目类别（兼容旧数据） */
export function resolveI6ExpenseNature(raw: {
  expenseNature?: string
  category?: string
  col_x?: string
}): string {
  const nature = String(raw.expenseNature ?? raw.col_x ?? '').trim()
  if (nature) return nature
  return String(raw.category ?? '').trim()
}

export function emptyI6DisclosureRow(partial?: Partial<I6DisclosureRow>): I6DisclosureRow {
  return {
    rowId: partial?.rowId || `i6d-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`,
    item: partial?.item ?? '',
    currentAmount: _num(partial?.currentAmount),
    priorAmount: _num(partial?.priorAmount),
    isAutoFilled: !!partial?.isAutoFilled,
    remark: partial?.remark ?? '',
  }
}

export function normalizeI6DisclosureRow(raw: any): I6DisclosureRow {
  return emptyI6DisclosureRow({
    rowId: raw?.rowId,
    item: raw?.item ?? raw?.expenseNature ?? raw?.name ?? raw?.category ?? raw?.项目 ?? '',
    currentAmount: raw?.currentAmount ?? raw?.col_q ?? raw?.本期发生额,
    priorAmount: raw?.priorAmount ?? raw?.col_w ?? raw?.上期发生额,
    isAutoFilled: !!raw?.isAutoFilled,
    remark: raw?.remark ?? '',
  })
}

export function defaultI6DisclosureRows(): I6DisclosureRow[] {
  return I6_DEFAULT_DISCLOSURE_CATEGORIES.map((name) =>
    emptyI6DisclosureRow({ item: name, isAutoFilled: false }),
  )
}

export function summarizeI6Disclosure(rows: I6DisclosureRow[]): I6DisclosureTotals {
  return {
    currentAmount: _round2(rows.reduce((s, r) => s + _num(r.currentAmount), 0)),
    priorAmount: _round2(rows.reduce((s, r) => s + _num(r.priorAmount), 0)),
  }
}

/** 从 I6-2 明细行按费用性质(X列) SUMIF 聚合 → 附注披露 */
export function aggregateI6DetailForDisclosure(detailRows: any[]): I6DisclosureRow[] {
  const map = new Map<string, { current: number; prior: number }>()

  for (const raw of detailRows) {
    const nature = resolveI6ExpenseNature(raw)
    if (!nature || nature === '合计') continue

    const months = Array.isArray(raw?.months) ? raw.months : []
    const unadj = months.length ? calcMonthlyTotal(months) : _num(raw?.unadjTotal ?? raw?.col_n)
    const aje = _num(raw?.aje ?? raw?.col_o)
    const rje = _num(raw?.rje ?? raw?.col_p)
    const current = _num(raw?.auditedAmount ?? raw?.col_q) || calcAuditedAmount(unadj, aje, rje)

    const priorUnadj = _num(raw?.priorUnadj ?? raw?.col_t)
    const priorAje = _num(raw?.priorAje ?? raw?.col_u)
    const priorRje = _num(raw?.priorRje ?? raw?.col_v)
    const prior = _num(raw?.priorAudited ?? raw?.col_w)
      || calcAuditedAmount(priorUnadj, priorAje, priorRje)

    const existing = map.get(nature) || { current: 0, prior: 0 }
    existing.current += current
    existing.prior += prior
    map.set(nature, existing)
  }

  let idx = 0
  return Array.from(map.entries()).map(([item, amounts]) =>
    emptyI6DisclosureRow({
      rowId: `i6disc-auto-${idx++}`,
      item,
      currentAmount: _round2(amounts.current),
      priorAmount: _round2(amounts.prior),
      isAutoFilled: true,
    }),
  )
}

/** 从 I6-1 审定表行按项目类别(A列)聚合 */
export function aggregateI6AdjForDisclosure(adjRows: any[]): I6DisclosureRow[] {
  const map = new Map<string, { current: number; prior: number }>()

  for (const raw of adjRows) {
    const item = String(raw?.类别 ?? raw?.项目 ?? raw?.category ?? '').trim()
    if (!item || item === '合计' || item === '小计' || raw?.isTotal || raw?.isSubtotal) continue

    const prior = _num(raw?.上期审定)
    const current = _num(raw?.本期审定)
    const existing = map.get(item) || { current: 0, prior: 0 }
    existing.current += current
    existing.prior += prior
    map.set(item, existing)
  }

  let idx = 0
  return Array.from(map.entries()).map(([item, amounts]) =>
    emptyI6DisclosureRow({
      rowId: `i6adj-auto-${idx++}`,
      item,
      currentAmount: _round2(amounts.current),
      priorAmount: _round2(amounts.prior),
      isAutoFilled: true,
    }),
  )
}

export function mergeAutoFillPreserveManual(
  existing: I6DisclosureRow[],
  autoRows: I6DisclosureRow[],
): I6DisclosureRow[] {
  const manualByItem = new Map(
    existing.filter((r) => !r.isAutoFilled && r.item).map((r) => [r.item, r]),
  )
  const autoByItem = new Map(autoRows.filter((r) => r.item).map((r) => [r.item, r]))
  const allItems = new Set([...manualByItem.keys(), ...autoByItem.keys()])

  const merged: I6DisclosureRow[] = []
  for (const item of allItems) {
    const manual = manualByItem.get(item)
    if (manual) {
      merged.push({ ...manual, isAutoFilled: false })
      continue
    }
    const auto = autoByItem.get(item)
    if (auto) merged.push({ ...auto, isAutoFilled: true })
  }

  for (const r of existing) {
    if (!r.item && !merged.some((m) => m.rowId === r.rowId)) {
      merged.push(r)
    }
  }

  return merged.length ? merged : autoRows
}

export interface I6ReconcileItemDiff {
  item: string
  disclosureAmount: number
  referenceAmount: number
  diff: number
}

export interface I6DisclosureReconcileView {
  vsAdj: {
    disclosureTotal: number
    adjudicatedTotal: number
    diff: number
    matched: boolean
    hasBoth: boolean
  }
  vsDetail: {
    disclosureTotal: number
    detailTotal: number
    diff: number
    matched: boolean
    hasBoth: boolean
  } | null
  itemDiffs: I6ReconcileItemDiff[]
  headline: string
  severity: 'ok' | 'warn' | 'error'
}

/** 附注披露 vs I6-1 / I6-2 勾稽汇总（含分项差异） */
export function buildI6DisclosureReconcileView(
  discRows: I6DisclosureRow[],
  detailRows: any[],
  adjRows: any[],
): I6DisclosureReconcileView {
  const discTotal = summarizeI6Disclosure(discRows.filter((r) => r.item !== '合计')).currentAmount
  const detailAuto = aggregateI6DetailForDisclosure(detailRows)
  const detailTotal = summarizeI6Disclosure(detailAuto).currentAmount
  const adjTotal = _round2(
    adjRows
      .filter((r) => !r?.isTotal && !r?.isSubtotal && r?.项目 !== '小计' && r?.类别 !== '小计' && r?.类别 !== '合计')
      .reduce((s, r) => s + _num(r.本期审定 ?? r.audited), 0),
  )

  const vsAdjDiff = _round2(discTotal - adjTotal)
  const vsDetailDiff = detailRows.length ? _round2(discTotal - detailTotal) : 0
  const vsAdj = {
    disclosureTotal: discTotal,
    adjudicatedTotal: adjTotal,
    diff: vsAdjDiff,
    matched: Math.abs(vsAdjDiff) <= 0.01 || !(Math.abs(discTotal) > 0.005 && Math.abs(adjTotal) > 0.005),
    hasBoth: Math.abs(discTotal) > 0.005 && Math.abs(adjTotal) > 0.005,
  }
  const vsDetail = detailRows.length
    ? {
        disclosureTotal: discTotal,
        detailTotal,
        diff: vsDetailDiff,
        matched: Math.abs(vsDetailDiff) <= 0.01,
        hasBoth: Math.abs(discTotal) > 0.005 && Math.abs(detailTotal) > 0.005,
      }
    : null

  const refMap = new Map<string, number>()
  for (const r of detailAuto) {
    if (r.item) refMap.set(r.item, _round2((refMap.get(r.item) || 0) + r.currentAmount))
  }
  const itemDiffs: I6ReconcileItemDiff[] = []
  for (const row of discRows) {
    if (!row.item || row.item === '合计') continue
    const ref = refMap.get(row.item) ?? 0
    const diff = _round2(row.currentAmount - ref)
    if (Math.abs(diff) > 0.01) {
      itemDiffs.push({
        item: row.item,
        disclosureAmount: _round2(row.currentAmount),
        referenceAmount: ref,
        diff,
      })
    }
  }

  let severity: 'ok' | 'warn' | 'error' = 'ok'
  if (!vsAdj.matched && vsAdj.hasBoth) severity = 'error'
  else if (vsDetail && !vsDetail.matched && vsDetail.hasBoth) severity = 'warn'
  else if (itemDiffs.length) severity = 'warn'

  const parts: string[] = []
  if (vsAdj.hasBoth && !vsAdj.matched) {
    parts.push(`披露合计 ${discTotal.toLocaleString('zh-CN')} vs I6-1 审定 ${adjTotal.toLocaleString('zh-CN')}，差额 ${vsAdjDiff.toLocaleString('zh-CN')}`)
  }
  if (vsDetail && vsDetail.hasBoth && !vsDetail.matched) {
    parts.push(`披露 vs I6-2 明细差额 ${vsDetailDiff.toLocaleString('zh-CN')}`)
  }
  if (itemDiffs.length) {
    const top = itemDiffs.slice(0, 3).map((d) => `${d.item}(${d.diff > 0 ? '+' : ''}${d.diff.toLocaleString('zh-CN')})`).join('、')
    parts.push(`分项差异: ${top}${itemDiffs.length > 3 ? '…' : ''}`)
  }
  const headline = parts.length ? parts.join('；') : '披露与底稿勾稽一致'

  return { vsAdj, vsDetail, itemDiffs, headline, severity }
}
