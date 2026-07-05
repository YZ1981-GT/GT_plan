/**
 * G12/G13/G14 跨底稿勾稽 — 纯函数（EventBus + 缓存 item 驱动）
 */
import { parseNum, calcSubtotal } from './useG13FormulaEngine'
import { G13_BELONG_ACCOUNT_LABELS, G13_BELONG_TO_ADJ } from './g13Constants'
import { G14_LINE_ITEMS } from './g14Constants'

const TOLERANCE = 0.01

export const G13_FV_SOURCES = ['G1', 'G8', 'G9', 'G10'] as const
export type G13FvSource = (typeof G13_FV_SOURCES)[number]

export interface G13SourceFvMismatch {
  source: G13FvSource
  label: string
  detailTotal: number
  sourceTotal: number
  variance: number
}

export interface G14EclMismatch {
  rowKey: string
  label: string
  detailProfitLoss: number
  sourceAmount: number
  variance: number
}

export interface G13DetailRowLike {
  belongAccount: string
  currentAudited: number
  rowId?: string
}

export interface G14DetailRowLike {
  rowKey: string
  label?: string
  profitLoss: number
}

export function sumG13DetailAuditedBySource(
  rows: G13DetailRowLike[],
  source: G13FvSource,
): number {
  return calcSubtotal(
    rows
      .filter((r) => r.rowId !== 'total' && r.belongAccount === source)
      .map((r) => r.currentAudited),
  )
}

export function findG13SourceFvMismatches(
  detailRows: G13DetailRowLike[],
  externalBySource: Partial<Record<G13FvSource, number | null | undefined>>,
): G13SourceFvMismatch[] {
  const out: G13SourceFvMismatch[] = []
  for (const source of G13_FV_SOURCES) {
    const sourceTotal = externalBySource[source]
    if (sourceTotal == null || Number.isNaN(sourceTotal)) continue
    const detailTotal = sumG13DetailAuditedBySource(detailRows, source)
    if (detailTotal === 0 && sourceTotal === 0) continue
    const variance = detailTotal - sourceTotal
    if (Math.abs(variance) > TOLERANCE) {
      out.push({
        source,
        label: G13_BELONG_ACCOUNT_LABELS[source] ?? source,
        detailTotal,
        sourceTotal,
        variance,
      })
    }
  }
  return out
}

export function formatG13SourceFvCrossMessage(mismatches: G13SourceFvMismatch[]): string | null {
  if (!mismatches.length) return null
  const parts = mismatches.map(
    (m) =>
      `${m.label}：G13-2 ${m.detailTotal.toFixed(2)} ≠ 源科目 ${m.sourceTotal.toFixed(2)}（差 ${m.variance.toFixed(2)}）`,
  )
  return `G13-2 与源科目 FV 变动不一致 — ${parts.join('；')}`
}

export function sumG13AdjudicationBySourceKey(
  detailRows: G13DetailRowLike[],
  adjRowKey: string,
): number {
  return calcSubtotal(
    detailRows
      .filter((r) => r.rowId !== 'total' && (G13_BELONG_TO_ADJ[r.belongAccount] ?? 'other') === adjRowKey)
      .map((r) => r.currentAudited),
  )
}

export function parseExternalAmountCache(json: string | null | undefined): Record<string, number> {
  if (!json) return {}
  try {
    const parsed = JSON.parse(json)
    if (!parsed || typeof parsed !== 'object') return {}
    const out: Record<string, number> = {}
    for (const [k, v] of Object.entries(parsed)) {
      out[k] = parseNum(v)
    }
    return out
  } catch {
    return {}
  }
}

export function findG14EclMismatches(
  detailRows: G14DetailRowLike[],
  externalByRowKey: Record<string, number | null | undefined>,
): G14EclMismatch[] {
  const out: G14EclMismatch[] = []
  for (const def of G14_LINE_ITEMS) {
    if (def.rowKey === 'other' || def.rowKey === 'guarantee') continue
    const sourceAmount = externalByRowKey[def.rowKey]
    if (sourceAmount == null || Number.isNaN(sourceAmount)) continue
    const row = detailRows.find((r) => r.rowKey === def.rowKey)
    const detailProfitLoss = row?.profitLoss ?? 0
    if (detailProfitLoss === 0 && sourceAmount === 0) continue
    const variance = detailProfitLoss - sourceAmount
    if (Math.abs(variance) > TOLERANCE) {
      out.push({
        rowKey: def.rowKey,
        label: def.label,
        detailProfitLoss,
        sourceAmount,
        variance,
      })
    }
  }
  return out
}

export function formatG14EclCrossMessage(mismatches: G14EclMismatch[]): string | null {
  if (!mismatches.length) return null
  const parts = mismatches.map(
    (m) =>
      `${m.label}：G14-2 ${m.detailProfitLoss.toFixed(2)} ≠ 源科目 ${m.sourceAmount.toFixed(2)}（差 ${m.variance.toFixed(2)}）`,
  )
  return `G14-2 与源科目 ECL 不一致 — ${parts.join('；')}`
}

/** G1 审定表 — 公允价值变动行本期审定合计 */
export function calcG1FvChangeAuditedTotal(
  rows: Array<{ measureKey: string; currentAudited: number }>,
): number {
  return calcSubtotal(
    rows.filter((r) => r.measureKey === 'fv-change').map((r) => r.currentAudited),
  )
}
