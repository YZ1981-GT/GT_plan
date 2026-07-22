/**
 * G12-5 风险净敞口 ↔ G12-2 / G12-4 交叉验证
 */
import {
  inferCurrencyFromAmount,
  parseNetAbs,
  parsePositionAmount,
  suggestNetPosition,
} from './g12NetExposureCalc'
import type { ChecklistResponse } from './useF1FormData'

export type G12NetExposureCrossKind =
  | 'net_calc_mismatch'
  | 'currency_mismatch'
  | 'missing_in_g12_2'
  | 'missing_in_g12_4'
  | 'fv_amount_mismatch'

export interface G12NetExposureCrossIssue {
  rowId: string
  seq: number
  item: string
  hedgingInstrument: string
  kind: G12NetExposureCrossKind
  detail: string
}

export interface G12NetExposureCrossRow {
  rowId: string
  seq: number
  item: string
  currency: string
  hedgeRelationId?: string
  position1Amount: string
  position2Amount: string
  netPosition: string
  hedgingInstrument: string
  indexRef: string
}

export interface G12FvTestCrossRow {
  hedgeRelationId: string
  instrumentClosingFV: number
  instrumentName?: string
}

const FV_AMOUNT_TOLERANCE = 0.05

function norm(s: string): string {
  return s.trim().toLowerCase().replace(/\s+/g, '')
}

/** 从索引号中提取可能的套期关系编号（如 G12-2/HR-001 → HR-001） */
export function extractHedgeRelationId(indexRef: string): string {
  const t = indexRef.trim()
  if (!t) return ''
  const parts = t.split(/[/\\|,;；，]/).map((p) => p.trim()).filter(Boolean)
  for (const p of parts) {
    if (/^G12-[246]$/i.test(p)) continue
    if (/^wp:/i.test(p)) continue
    return p
  }
  return t
}

function resolveRelationId(r: G12NetExposureCrossRow): string {
  return String(r.hedgeRelationId ?? '').trim() || extractHedgeRelationId(r.indexRef)
}

function resolveLinkageLabel(r: G12NetExposureCrossRow): string {
  return String(r.hedgingInstrument ?? '').trim() || resolveRelationId(r)
}

function matchesKey(key: string, pool: string[]): boolean {
  if (!key) return false
  return pool.some((h) => h === key || h.includes(key) || key.includes(h))
}

export function findG12NetExposureInternalMismatches(
  rows: G12NetExposureCrossRow[],
): G12NetExposureCrossIssue[] {
  const out: G12NetExposureCrossIssue[] = []
  for (const r of rows) {
    const suggested = suggestNetPosition(r.position1Amount, r.position2Amount, r.currency)
    if (suggested && r.netPosition.trim()) {
      const a = parseNetAbs(suggested)
      const b = parseNetAbs(r.netPosition)
      if (a != null && b != null && Math.abs(a - b) > 0.01) {
        out.push({
          rowId: r.rowId,
          seq: r.seq,
          item: r.item,
          hedgingInstrument: r.hedgingInstrument,
          kind: 'net_calc_mismatch',
          detail: `[${r.currency}] 净头寸「${r.netPosition}」与建议「${suggested}」不一致`,
        })
      }
    }

    for (const [label, amount] of [
      ['头寸1', r.position1Amount],
      ['头寸2', r.position2Amount],
    ] as const) {
      const parsed = parsePositionAmount(amount)
      const embedded = inferCurrencyFromAmount(amount)
      if (parsed?.unit && embedded && r.currency && embedded !== r.currency) {
        out.push({
          rowId: r.rowId,
          seq: r.seq,
          item: r.item,
          hedgingInstrument: r.hedgingInstrument,
          kind: 'currency_mismatch',
          detail: `[${r.currency}] ${label}金额币种（${embedded}）与行币种不一致`,
        })
      }
    }
  }
  return out
}

/** G12-5 净头寸 vs G12-4 工具期末 FV（名义覆盖 sanity check） */
export function findG12NetExposureFvAmountMismatches(
  rows: G12NetExposureCrossRow[],
  fvRows: G12FvTestCrossRow[],
): G12NetExposureCrossIssue[] {
  const fvMap = new Map<string, G12FvTestCrossRow>()
  for (const f of fvRows) {
    const id = f.hedgeRelationId?.trim()
    if (id) fvMap.set(id, f)
  }
  if (!fvMap.size) return []

  const out: G12NetExposureCrossIssue[] = []
  for (const r of rows) {
    const relId = resolveRelationId(r)
    if (!relId) continue
    const fv = fvMap.get(relId)
    if (!fv) continue

    const fvAmount = Math.abs(Number(fv.instrumentClosingFV) || 0)
    if (fvAmount <= 0) continue

    const netAbs = parseNetAbs(r.netPosition)
    if (netAbs == null || netAbs <= 0) continue

    const variance = Math.abs(netAbs - fvAmount)
    const base = Math.max(netAbs, fvAmount, 1)
    if (variance / base > FV_AMOUNT_TOLERANCE && variance > 0.01) {
      out.push({
        rowId: r.rowId,
        seq: r.seq,
        item: r.item,
        hedgingInstrument: r.hedgingInstrument || fv.instrumentName || relId,
        kind: 'fv_amount_mismatch',
        detail: `[${relId}] 净头寸绝对值 ${netAbs.toLocaleString('zh-CN')} vs G12-4 工具期末FV ${fvAmount.toLocaleString('zh-CN')}（偏差 ${(variance / base * 100).toFixed(1)}%）`,
      })
    }
  }
  return out
}

export function findG12NetExposureLinkageIssues(
  rows: G12NetExposureCrossRow[],
  hedgeInstruments: string[],
  hedgeRelationIds: string[],
  fvInstrumentNames: string[],
  fvRelationIds: string[],
): G12NetExposureCrossIssue[] {
  const hedgeKeys = [...hedgeInstruments, ...hedgeRelationIds].map(norm).filter(Boolean)
  const fvKeys = [...fvInstrumentNames, ...fvRelationIds].map(norm).filter(Boolean)
  const hedgeIdSet = new Set(hedgeRelationIds.map(norm).filter(Boolean))
  const fvIdSet = new Set(fvRelationIds.map(norm).filter(Boolean))
  const hasHedge = hedgeKeys.length > 0
  const hasFv = fvKeys.length > 0
  const out: G12NetExposureCrossIssue[] = []

  for (const r of rows) {
    const relId = resolveRelationId(r)
    const label = resolveLinkageLabel(r)
    const labelKey = norm(label)
    if (!relId && !labelKey) continue

    if (hasHedge) {
      const hit = (relId && hedgeIdSet.has(norm(relId))) || matchesKey(labelKey, hedgeKeys)
      if (!hit) {
        out.push({
          rowId: r.rowId,
          seq: r.seq,
          item: r.item,
          hedgingInstrument: label || relId,
          kind: 'missing_in_g12_2',
          detail: `套期关系「${relId || label}」未在 G12-2 找到`,
        })
      }
    }

    if (hasFv) {
      const hit = (relId && fvIdSet.has(norm(relId))) || matchesKey(labelKey, fvKeys)
      if (!hit) {
        out.push({
          rowId: r.rowId,
          seq: r.seq,
          item: r.item,
          hedgingInstrument: label || relId,
          kind: 'missing_in_g12_4',
          detail: `套期关系「${relId || label}」未在 G12-4 找到`,
        })
      }
    }
  }
  return out
}

export function parseG12FvTestCrossRows(allResponses: Map<string, ChecklistResponse>): G12FvTestCrossRow[] {
  const raw = allResponses.get('G12-fv-test-rows')?.remark
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr)) return []
    return arr.map((r: Record<string, unknown>) => ({
      hedgeRelationId: String(r.hedgeRelationId ?? ''),
      instrumentClosingFV: Number(r.instrumentClosingFV) || 0,
      instrumentName: r.instrumentName ? String(r.instrumentName) : undefined,
    }))
  } catch {
    return []
  }
}

export function findG12NetExposureCrossIssues(
  rows: G12NetExposureCrossRow[],
  allResponses: Map<string, ChecklistResponse>,
): G12NetExposureCrossIssue[] {
  const issues = [...findG12NetExposureInternalMismatches(rows)]

  const hedgeInstruments: string[] = []
  const hedgeRelationIds: string[] = []
  const fvInstrumentNames: string[] = []
  const fvRelationIds: string[] = []

  try {
    const hedgeRaw = allResponses.get('G12-hedge-detail-rows')?.remark
    if (hedgeRaw) {
      const arr = JSON.parse(hedgeRaw)
      if (Array.isArray(arr)) {
        for (const r of arr) {
          if (r.hedgingInstrument) hedgeInstruments.push(String(r.hedgingInstrument))
          if (r.indexRef) hedgeRelationIds.push(String(r.indexRef))
          if (r.item) hedgeRelationIds.push(String(r.item))
          // 旧版兼容
          if (r.hedgeRelationId) hedgeRelationIds.push(String(r.hedgeRelationId))
        }
      }
    }
  } catch { /* ignore */ }

  const fvRows = parseG12FvTestCrossRows(allResponses)
  for (const f of fvRows) {
    if (f.instrumentName) fvInstrumentNames.push(f.instrumentName)
    if (f.hedgeRelationId) fvRelationIds.push(f.hedgeRelationId)
  }

  issues.push(...findG12NetExposureLinkageIssues(
    rows, hedgeInstruments, hedgeRelationIds, fvInstrumentNames, fvRelationIds,
  ))
  issues.push(...findG12NetExposureFvAmountMismatches(rows, fvRows))
  return issues
}

export function formatG12NetExposureCrossMessage(issues: G12NetExposureCrossIssue[]): string | null {
  if (!issues.length) return null
  const first = issues[0]
  const head = `#${first.seq} ${first.item || first.hedgingInstrument}：${first.detail}`
  if (issues.length === 1) return `G12-5 交叉验证 — ${head}`
  return `G12-5 交叉验证 — ${issues.length} 处问题；${head}`
}

export function hasG12NetExposureData(allResponses: Map<string, ChecklistResponse>): boolean {
  const raw = allResponses.get('G12-net-exposure-rows')?.remark
  if (!raw) return false
  try {
    const arr = JSON.parse(raw)
    return Array.isArray(arr) && arr.length > 0 && !('checkItem' in (arr[0] ?? {}))
  } catch {
    return false
  }
}
