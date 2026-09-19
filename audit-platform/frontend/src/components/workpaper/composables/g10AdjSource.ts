/**
 * G10-3 调整分录 — 来源识别与筛选
 */
import { isG10ClassificationAdjDraft, isPendingG10ClassificationAdjDraft } from './g10ClassificationCross'
import { isFromG106 } from './g10L3CrossHelpers'
import { isFromG108 } from './g10DerivativeCross'
import { isFromG107 } from './g10VoucherCross'
import { parseNum } from './useG10FormulaEngine'

export type G10AdjSourceKind = 'manual' | 'g104' | 'g105' | 'g106' | 'g107' | 'g108' | 'module'

export type G10AdjSourceFilter =
  | 'all'
  | G10AdjSourceKind
  | 'pending_g104'
  | 'zero_memo'

export interface G10AdjSourceRow {
  summary?: string
  remark?: string
  indexRef?: string
  sourceGroupId?: string
  draftReviewStatus?: string
  debitAmount?: number
  creditAmount?: number
}

export function isFromG105(row: G10AdjSourceRow): boolean {
  if (isG10ClassificationAdjDraft(row) || isFromG106(row) || isFromG107(row) || isFromG108(row)) return false
  const t = `${row.summary || ''} ${row.remark || ''} ${row.indexRef || ''}`
  return /G10-5|公允测试差异/.test(t)
}

export function resolveG10AdjSource(row: G10AdjSourceRow): G10AdjSourceKind {
  if (isG10ClassificationAdjDraft(row)) return 'g104'
  if (isFromG106(row)) return 'g106'
  if (isFromG107(row)) return 'g107'
  if (isFromG108(row)) return 'g108'
  if (isFromG105(row)) return 'g105'
  if (row.sourceGroupId) return 'module'
  return 'manual'
}

/** 零金额备忘行（G10-7/G10-8 推送，待追查补录） */
export function isG10AdjZeroAmountMemoRow(row: G10AdjSourceRow): boolean {
  if (parseNum(row.debitAmount) > 0.005 || parseNum(row.creditAmount) > 0.005) return false
  return isFromG107(row)
    || isFromG108(row)
    || /待追查补录|金额待补录|金额待/.test(String(row.remark || ''))
}

export interface G10AdjSourceCounts {
  all: number
  g104: number
  g105: number
  g106: number
  g107: number
  g108: number
  module: number
  manual: number
  pending_g104: number
  zero_memo: number
}

export function countG10AdjBySource(rows: G10AdjSourceRow[]): G10AdjSourceCounts {
  const counts: G10AdjSourceCounts = {
    all: rows.length,
    g104: 0,
    g105: 0,
    g106: 0,
    g107: 0,
    g108: 0,
    module: 0,
    manual: 0,
    pending_g104: 0,
    zero_memo: 0,
  }
  for (const row of rows) {
    counts[resolveG10AdjSource(row)] += 1
    if (isPendingG10ClassificationAdjDraft(row)) counts.pending_g104 += 1
    if (isG10AdjZeroAmountMemoRow(row)) counts.zero_memo += 1
  }
  return counts
}

export function filterG10AdjRows<T extends G10AdjSourceRow>(
  rows: T[],
  filter: G10AdjSourceFilter,
): T[] {
  if (filter === 'all') return rows
  if (filter === 'pending_g104') return rows.filter(isPendingG10ClassificationAdjDraft)
  if (filter === 'zero_memo') return rows.filter(isG10AdjZeroAmountMemoRow)
  return rows.filter((r) => resolveG10AdjSource(r) === filter)
}

/** 跨表推送事件 detail.source → G10-3 来源筛选 */
export function g10AdjSourceFilterFromEvent(source?: string): G10AdjSourceFilter | null {
  switch (source) {
    case 'G10-4': return 'pending_g104'
    case 'G10-5': return 'g105'
    case 'G10-6': return 'g106'
    case 'G10-7': return 'g107'
    case 'G10-8': return 'g108'
    default: return null
  }
}

export const G10_ADJ_SOURCE_FILTER_OPTIONS: Array<{ value: G10AdjSourceFilter; label: string }> = [
  { value: 'all', label: '全部' },
  { value: 'g104', label: 'G10-4' },
  { value: 'g105', label: 'G10-5' },
  { value: 'g106', label: 'G10-6' },
  { value: 'g107', label: 'G10-7' },
  { value: 'g108', label: 'G10-8' },
  { value: 'module', label: '模块' },
  { value: 'pending_g104', label: '待复核' },
  { value: 'zero_memo', label: '零金额备忘' },
  { value: 'manual', label: '手工' },
]
