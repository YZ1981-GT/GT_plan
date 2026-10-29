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
  adjudicationRows?: Array<{ rowKey: string; currentAudited?: number | null }>
  hedgeDetailJson?: string | null
}

export interface G12DisclosureSyncPatchResult {
  rows: G12DisclosureRow[]
  changed: boolean
  sourceFound: boolean
  fieldsChanged: number
}

interface AmountSource {
  found: boolean
  value: number
}

const MISSING_AMOUNT: AmountSource = { found: false, value: 0 }

function amountSource(value: unknown): AmountSource {
  if (value == null || (typeof value === 'string' && value.trim() === '')) return MISSING_AMOUNT
  const parsed = typeof value === 'number' ? value : Number(value)
  return Number.isFinite(parsed) ? { found: true, value: parsed } : MISSING_AMOUNT
}

function firstAmount(...sources: AmountSource[]): AmountSource {
  return sources.find((source) => source.found) ?? MISSING_AMOUNT
}

function priorAudited(entry?: G12AdjudicationPriorEntry): AmountSource {
  if (!entry) return MISSING_AMOUNT
  const audited = amountSource(entry.priorAudited)
  if (audited.found) return audited

  const unadjusted = amountSource(entry.priorUnadjusted)
  const adjustment = amountSource(entry.priorAdjustment)
  if (!unadjusted.found && !adjustment.found) return MISSING_AMOUNT
  return { found: true, value: unadjusted.value + adjustment.value }
}

/** 从 G12-1 审定表与 G12-2 明细汇总填充附注各行；缺失来源保留原值。 */
export function buildG12DisclosureSyncPatch(
  rows: G12DisclosureRow[],
  input: G12DisclosureSyncInput,
): G12DisclosureSyncPatchResult {
  const { variant, adjudicatedTotal, priorStore, adjudicationRows, hedgeDetailJson } = input
  const detailTotals = parseHedgeDetailTotals(hedgeDetailJson)
  const adjByKey = new Map<string, AmountSource>()
  for (const row of adjudicationRows ?? []) {
    const source = amountSource(row.currentAudited)
    if (source.found) adjByKey.set(row.rowKey, source)
  }

  let sourceFound = false
  let fieldsChanged = 0
  const patchedRows = rows.map((row) => {
    let current = MISSING_AMOUNT
    let prior = MISSING_AMOUNT

    if (variant === 'listed' && row.rowKey === 'net_hedge') {
      current = firstAmount(amountSource(adjudicatedTotal), adjByKey.get('net_hedge') ?? MISSING_AMOUNT)
      prior = priorAudited(priorStore.net_hedge)
    } else if (variant === 'soe' && row.rowKey === 'hedged_fv_to_pl') {
      current = firstAmount(
        detailTotals?.purchasePortion ?? MISSING_AMOUNT,
        adjByKey.get('item_fv') ?? MISSING_AMOUNT,
      )
      prior = firstAmount(
        priorAudited(priorStore.item_fv),
        priorAudited(priorStore.hedged_fv_to_pl),
      )
    } else if (variant === 'soe' && row.rowKey === 'cf_reserve_to_pl') {
      const netHedge = adjByKey.get('net_hedge') ?? MISSING_AMOUNT
      const itemFv = adjByKey.get('item_fv') ?? MISSING_AMOUNT
      const derivedCurrent = netHedge.found && itemFv.found
        ? { found: true, value: Math.max(0, netHedge.value - itemFv.value) }
        : MISSING_AMOUNT
      current = firstAmount(
        detailTotals?.hedgeAdjAmortization ?? MISSING_AMOUNT,
        derivedCurrent,
      )
      prior = firstAmount(
        priorAudited(priorStore.cf_reserve),
        priorAudited(priorStore.cf_reserve_to_pl),
      )
    }

    let next = row
    if (current.found) {
      sourceFound = true
      if (parseNum(row.currentAmount) !== current.value) {
        next = { ...next, currentAmount: current.value }
        fieldsChanged += 1
      }
    }
    if (prior.found) {
      sourceFound = true
      if (parseNum(row.priorAmount) !== prior.value) {
        next = { ...next, priorAmount: prior.value }
        fieldsChanged += 1
      }
    }
    return next
  })

  return {
    rows: patchedRows,
    changed: fieldsChanged > 0,
    sourceFound,
    fieldsChanged,
  }
}

function parseHedgeDetailTotals(json?: string | null): {
  purchasePortion: AmountSource
  hedgeAdjAmortization: AmountSource
} | null {
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
    const totals = summarizeG12NetHedgeDetailRows(rows.map((r) => ({
      rowKind: (r.rowKind === 'amortization' ? 'amortization' : 'fv_allocation') as 'fv_allocation' | 'amortization',
      instrumentFvCumulative: parseNum(r.instrumentFvCumulative),
      salesPortion: parseNum(r.salesPortion),
      purchasePortion: parseNum(r.purchasePortion),
      hedgeAdjAmortization: parseNum(r.hedgeAdjAmortization),
    })))
    const purchaseFound = rows.some((r) => r.rowKind !== 'amortization' && amountSource(r.purchasePortion).found)
    const amortizationFound = rows.some((r) => r.rowKind === 'amortization' && amountSource(r.hedgeAdjAmortization).found)
    return {
      purchasePortion: purchaseFound ? { found: true, value: totals.purchasePortion } : MISSING_AMOUNT,
      hedgeAdjAmortization: amortizationFound
        ? { found: true, value: totals.hedgeAdjAmortization }
        : MISSING_AMOUNT,
    }
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
