/**
 * G9 附注 ← G9-1 分项 + G9-2 工具种类/指定
 * 对齐 Excel：债务/权益/指定/其他；明细有工具种类时优先用明细，否则用审定标签汇总。
 */
import { G9_ADJUDICATION_ITEMS } from './g9AdjudicationItems'
import { parseG9AdjStore, type G9AdjRowStore } from './g9AdjStorage'
import { parseNum, calcAdjustedAmount, calcSubtotal } from './useG9FormulaEngine'
import { G9_ADJ_ROWS_KEY } from './g9CrossHelpers'
import { G9_DETAIL_KEY } from './g9VoucherCross'
import type { ChecklistResponse } from './useF1FormData'
import type { G9DisclosureRowDef } from './g9SchemaRows'

export type G9DiscBucket = 'debt' | 'equity' | 'designated' | 'other'
export type G9DiscAmountSource = 'adj' | 'detail' | 'residual' | 'none'

export interface G9DiscAmountPair {
  currentAmount: number
  priorAmount: number
}

export type G9DiscAmountMap = Record<G9DiscBucket, G9DiscAmountPair>

const BUCKET_MATCHERS: Record<G9DiscBucket, RegExp> = {
  debt: /债务工具投资/,
  equity: /权益工具投资/,
  designated: /指定为以公允价值计量且其变动计入当期损益的金融资产|指定为.*公允价值/,
  other: /衍生金融|其中：其他投资|其中：其他(?!投资)/,
}

const INSTRUMENT_TO_BUCKET: Record<string, G9DiscBucket> = {
  债务工具投资: 'debt',
  权益工具投资: 'equity',
  衍生金融资产: 'other',
  其他: 'other',
}

/** 披露行标签 → 分项桶 */
export function g9DiscLabelToBucket(label: string): G9DiscBucket | null {
  if (/指定为/.test(label)) return 'designated'
  if (/债务工具/.test(label)) return 'debt'
  if (/权益工具/.test(label)) return 'equity'
  if (/其他/.test(label)) return 'other'
  return null
}

function emptyMap(): G9DiscAmountMap {
  return {
    debt: { currentAmount: 0, priorAmount: 0 },
    equity: { currentAmount: 0, priorAmount: 0 },
    designated: { currentAmount: 0, priorAmount: 0 },
    other: { currentAmount: 0, priorAmount: 0 },
  }
}

function pairNonZero(p: G9DiscAmountPair): boolean {
  return Math.abs(p.currentAmount) > 0.005 || Math.abs(p.priorAmount) > 0.005
}

function adjustedPair(raw: G9AdjRowStore[string] | undefined): G9DiscAmountPair {
  const opening = calcAdjustedAmount(
    parseNum(raw?.openingUnadjusted),
    parseNum(raw?.openingAJE),
    parseNum(raw?.openingRJE),
  )
  const closing = calcAdjustedAmount(
    parseNum(raw?.closingUnadjusted),
    parseNum(raw?.closingAJE),
    parseNum(raw?.closingRJE),
  )
  return { currentAmount: closing, priorAmount: opening }
}

/** 从 G9-1 rowStore 按标签汇总 */
export function buildG9DisclosureAmountsFromAdjStore(store: G9AdjRowStore): G9DiscAmountMap {
  const out = emptyMap()
  for (const def of G9_ADJUDICATION_ITEMS) {
    let bucket: G9DiscBucket | null = null
    for (const [key, re] of Object.entries(BUCKET_MATCHERS) as Array<[G9DiscBucket, RegExp]>) {
      if (re.test(def.label)) {
        bucket = key
        break
      }
    }
    if (!bucket) continue
    const pair = adjustedPair(store[def.rowKey])
    out[bucket].currentAmount += pair.currentAmount
    out[bucket].priorAmount += pair.priorAmount
  }
  return out
}

/** 从 G9-2：工具种类 → 债务/权益/其他；isDesignated → 指定（并从种类桶扣除避免重复） */
export function buildG9DisclosureAmountsFromDetailRows(
  rows: Array<{
    instrumentType?: string
    isDesignated?: boolean
    classification?: string
    openingAdjusted?: number
    closingAdjusted?: number
    openingBalance?: number
    closingBalance?: number
  }>,
): G9DiscAmountMap {
  const out = emptyMap()
  for (const r of rows) {
    const closing = parseNum(r.closingAdjusted ?? r.closingBalance)
    const opening = parseNum(r.openingAdjusted ?? r.openingBalance)
    if (r.isDesignated && (r.classification === 'FVTPL' || !r.classification)) {
      out.designated.currentAmount += closing
      out.designated.priorAmount += opening
      continue
    }
    const bucket = INSTRUMENT_TO_BUCKET[String(r.instrumentType ?? '').trim()]
    if (!bucket) continue
    out[bucket].currentAmount += closing
    out[bucket].priorAmount += opening
  }
  return out
}

/** 各桶：明细有数用明细，否则用审定 */
export function mergeG9DisclosureAmounts(
  fromAdj: G9DiscAmountMap,
  fromDetail: G9DiscAmountMap,
): { amounts: G9DiscAmountMap; sources: Record<G9DiscBucket, G9DiscAmountSource> } {
  const amounts = emptyMap()
  const sources = {} as Record<G9DiscBucket, G9DiscAmountSource>
  for (const key of Object.keys(amounts) as G9DiscBucket[]) {
    if (pairNonZero(fromDetail[key])) {
      amounts[key] = { ...fromDetail[key] }
      sources[key] = 'detail'
    } else if (pairNonZero(fromAdj[key])) {
      amounts[key] = { ...fromAdj[key] }
      sources[key] = 'adj'
    } else {
      amounts[key] = { currentAmount: 0, priorAmount: 0 }
      sources[key] = 'none'
    }
  }
  return { amounts, sources }
}

export function buildG9DisclosureAmountsFromResponses(
  responses: Map<string, ChecklistResponse>,
): {
  amounts: G9DiscAmountMap
  sources: Record<G9DiscBucket, G9DiscAmountSource>
  fromAdj: G9DiscAmountMap
  fromDetail: G9DiscAmountMap
} {
  const fromAdj = buildG9DisclosureAmountsFromAdjStore(
    parseG9AdjStore(responses.get(G9_ADJ_ROWS_KEY)?.remark),
  )
  let detailRows: unknown[] = []
  try {
    const raw = responses.get(G9_DETAIL_KEY)?.remark
    detailRows = raw ? JSON.parse(raw) : []
    if (!Array.isArray(detailRows)) detailRows = []
  } catch {
    detailRows = []
  }
  const fromDetail = buildG9DisclosureAmountsFromDetailRows(detailRows as any[])
  const { amounts, sources } = mergeG9DisclosureAmounts(fromAdj, fromDetail)
  return { amounts, sources, fromAdj, fromDetail }
}

export interface G9DiscPullApplyResult {
  next: Record<string, { currentAmount: number; priorAmount: number; noteText: string }>
  filledBuckets: G9DiscBucket[]
  categoryCurrentSum: number
  categoryPriorSum: number
  usedResidual: boolean
  sources: Record<G9DiscBucket, G9DiscAmountSource>
}

/**
 * 写入披露 store；分项合计≈0 且有 residual 时写入「其他」。
 */
export function applyG9DisclosureAmountsToStore(
  rowDefs: G9DisclosureRowDef[],
  prev: Record<string, { currentAmount: number; priorAmount: number; noteText: string }>,
  amounts: G9DiscAmountMap,
  opts?: {
    residualCurrent?: number | null
    residualPrior?: number | null
    sources?: Record<G9DiscBucket, G9DiscAmountSource>
  },
): G9DiscPullApplyResult {
  const next: Record<string, { currentAmount: number; priorAmount: number; noteText: string }> = {
    ...prev,
  }
  const filledBuckets: G9DiscBucket[] = []
  const sources: Record<G9DiscBucket, G9DiscAmountSource> = {
    debt: opts?.sources?.debt ?? 'none',
    equity: opts?.sources?.equity ?? 'none',
    designated: opts?.sources?.designated ?? 'none',
    other: opts?.sources?.other ?? 'none',
  }

  for (const def of rowDefs) {
    const bucket = g9DiscLabelToBucket(def.label)
    if (!bucket) continue
    const cur = next[def.rowKey] ?? { currentAmount: 0, priorAmount: 0, noteText: '' }
    const pair = amounts[bucket]
    next[def.rowKey] = {
      ...cur,
      currentAmount: pair.currentAmount,
      priorAmount: pair.priorAmount,
    }
    if (pairNonZero(pair)) filledBuckets.push(bucket)
  }

  const categoryCurrentSum = calcSubtotal(
    Object.values(amounts).map((p) => p.currentAmount),
  )
  const categoryPriorSum = calcSubtotal(
    Object.values(amounts).map((p) => p.priorAmount),
  )

  let usedResidual = false
  const residualCurrent = opts?.residualCurrent
  const residualPrior = opts?.residualPrior
  if (
    Math.abs(categoryCurrentSum) <= 0.01
    && residualCurrent != null
    && Math.abs(residualCurrent) > 0.01
  ) {
    const otherDef = rowDefs.find((d) => g9DiscLabelToBucket(d.label) === 'other')
    if (otherDef) {
      const cur = next[otherDef.rowKey] ?? { currentAmount: 0, priorAmount: 0, noteText: '' }
      next[otherDef.rowKey] = {
        ...cur,
        currentAmount: residualCurrent,
        priorAmount: residualPrior ?? cur.priorAmount,
      }
      if (!filledBuckets.includes('other')) filledBuckets.push('other')
      sources.other = 'residual'
      usedResidual = true
    }
  }

  return { next, filledBuckets, categoryCurrentSum, categoryPriorSum, usedResidual, sources }
}

export function formatG9DiscPullSummary(
  sources: Record<G9DiscBucket, G9DiscAmountSource>,
  usedResidual: boolean,
): string {
  const labels: Record<G9DiscBucket, string> = {
    debt: '债务',
    equity: '权益',
    designated: '指定',
    other: '其他',
  }
  const srcLabel: Record<G9DiscAmountSource, string> = {
    adj: 'G9-1',
    detail: 'G9-2',
    residual: '残差',
    none: '空',
  }
  const parts = (Object.keys(labels) as G9DiscBucket[]).map(
    (k) => `${labels[k]}←${srcLabel[sources[k]]}`,
  )
  return usedResidual
    ? `${parts.join('；')}（无分项，审定数已写入「其他」，请按种类手工分拆）`
    : parts.join('；')
}
