/** G12 附注披露 — 与 G12-1 / G12-2 同步与历史数据迁移 */
import { parseNum } from './useG12FormulaEngine'
import {
  G12_DISCLOSURE_LEGACY_KEY_MAP,
  G12_DISCLOSURE_LISTED_ROWS,
  G12_DISCLOSURE_SOE_ROWS,
} from './g12Constants'
import { summarizeG12NetHedgeDetailRows } from './g12NetHedgeDetailCalc'
import type { G12DisclosureRow } from './useG12Disclosure'

type Variant = 'listed' | 'soe'

function rowDefs(variant: Variant) {
  return variant === 'listed' ? G12_DISCLOSURE_LISTED_ROWS : G12_DISCLOSURE_SOE_ROWS
}

function targetKey(variant: Variant, rowKey: string): string {
  if (rowDefs(variant).some((d) => d.rowKey === rowKey)) return rowKey
  if (variant === 'listed') return 'net_hedge'
  return G12_DISCLOSURE_LEGACY_KEY_MAP[rowKey] ?? rowKey
}

/** 将旧版 12 行附注数据迁移为现行模板行 */
export function migrateG12DisclosureRows(
  parsed: Array<Partial<G12DisclosureRow> & { rowKey: string }>,
  variant: Variant,
): Array<Partial<G12DisclosureRow> & { rowKey: string }> {
  const defs = rowDefs(variant)
  const acc = new Map<string, Partial<G12DisclosureRow> & { rowKey: string }>()

  for (const def of defs) {
    acc.set(def.rowKey, { rowKey: def.rowKey, label: def.label, currentAmount: 0, priorAmount: 0, remark: '' })
  }

  for (const raw of parsed) {
    const key = targetKey(variant, raw.rowKey)
    if (!acc.has(key)) continue
    const row = acc.get(key)!
    row.currentAmount = parseNum(row.currentAmount) + parseNum(raw.currentAmount)
    row.priorAmount = parseNum(row.priorAmount) + parseNum(raw.priorAmount)
    if (raw.remark && !row.remark) row.remark = raw.remark
  }

  return defs.map((d) => acc.get(d.rowKey)!)
}

export interface G12AdjudicationPriorEntry {
  priorUnadjusted?: number
  priorAdjustment?: number
  priorAudited?: number
}

export interface G12DisclosureSyncInput {
  variant: Variant
  adjudicatedTotal: number | null
  priorStore: Record<string, G12AdjudicationPriorEntry>
  adjudicationRows?: Array<{ rowKey: string; currentAudited: number }>
  hedgeDetailJson?: string | null
}

function priorAudited(entry?: G12AdjudicationPriorEntry): number {
  if (!entry) return 0
  if (entry.priorAudited != null) return parseNum(entry.priorAudited)
  return parseNum(entry.priorUnadjusted) + parseNum(entry.priorAdjustment)
}

/** 从 G12-1 审定表与 G12-2 明细汇总填充附注各行 */
export function buildG12DisclosureSyncPatch(
  rows: G12DisclosureRow[],
  input: G12DisclosureSyncInput,
): G12DisclosureRow[] {
  const { variant, adjudicatedTotal, priorStore, adjudicationRows, hedgeDetailJson } = input
  const detailTotals = parseHedgeDetailTotals(hedgeDetailJson)
  const adjByKey = new Map(adjudicationRows?.map((r) => [r.rowKey, r.currentAudited]) ?? [])

  return rows.map((row) => {
    if (variant === 'listed' && row.rowKey === 'net_hedge') {
      const current = adjudicatedTotal ?? parseNum(adjByKey.get('net_hedge'))
      const prior = priorAudited(priorStore.net_hedge)
      return { ...row, currentAmount: current, priorAmount: prior }
    }

    if (variant === 'soe' && row.rowKey === 'hedged_fv_to_pl') {
      const current = detailTotals
        ? detailTotals.purchasePortion
        : parseNum(adjByKey.get('item_fv'))
      const prior = priorAudited(priorStore.item_fv ?? priorStore.hedged_fv_to_pl)
      return { ...row, currentAmount: current, priorAmount: prior }
    }

    if (variant === 'soe' && row.rowKey === 'cf_reserve_to_pl') {
      const current = detailTotals
        ? detailTotals.hedgeAdjAmortization
        : Math.max(0, parseNum(adjByKey.get('net_hedge')) - parseNum(adjByKey.get('item_fv')))
      const prior = priorAudited(priorStore.cf_reserve ?? priorStore.cf_reserve_to_pl)
      return { ...row, currentAmount: current, priorAmount: prior }
    }

    return row
  })
}

function parseHedgeDetailTotals(json?: string | null) {
  if (!json) return null
  try {
    const rows = JSON.parse(json) as Array<{
      rowKind?: string
      instrumentFvCumulative?: number
      salesPortion?: number
      purchasePortion?: number
      hedgeAdjAmortization?: number
    }>
    if (!Array.isArray(rows)) return null
    return summarizeG12NetHedgeDetailRows(rows.map((r) => ({
      rowKind: (r.rowKind === 'amortization' ? 'amortization' : 'fv_allocation') as 'fv_allocation' | 'amortization',
      instrumentFvCumulative: parseNum(r.instrumentFvCumulative),
      salesPortion: parseNum(r.salesPortion),
      purchasePortion: parseNum(r.purchasePortion),
      hedgeAdjAmortization: parseNum(r.hedgeAdjAmortization),
    })))
  } catch {
    return null
  }
}

export function calcG12DisclosureReconciliationDiff(
  disclosureTotal: number,
  adjudicatedAmount: number | null,
): number | null {
  if (adjudicatedAmount == null) return null
  return disclosureTotal - adjudicatedAmount
}
