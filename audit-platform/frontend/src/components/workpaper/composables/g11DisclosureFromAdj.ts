/**
 * G11 附注 ← G11-1 审定分项 + G11-2 明细（按项目/标签汇总发生额）
 * 损益类：本期/上期发生额；明细有数优先，否则审定；无分项时残差进「其他」。
 */
import { G11_ADJUDICATION_ITEMS } from './g11Constants'
import { parseG11AdjStore, type G11AdjRowStore } from './g11AdjStorage'
import { parseNum, calcAdjustedAmount, calcSubtotal } from './useG11FormulaEngine'
import {
  G11_ADJ_ROWS_KEY,
  G11_ADJUDICATED_KEY,
  G11_CROSS_TOLERANCE,
  G11_DETAIL_KEY,
  G11_DISCLOSURE_LISTED_KEY,
  G11_DISCLOSURE_SOE_KEY,
  G11_LISTED_MAIN_ROW_KEYS,
  G11_LISTED_TRADING_DISPOSE_ROWS,
  G11_SOE_MAIN_ROW_KEYS,
  G11_SOE_REPATRIATION_PLACEHOLDER,
  G11_TRADING_DISPOSE_SUFFIXES,
  g11DisclosureSchema,
  isG11DisclosureLeaf,
  isG11TradingDisposeDetailRow,
  type G11TradingDisposeSuffix,
} from './g11SchemaRows'
import type { ChecklistResponse } from './useF1FormData'

export type G11DiscAmountSource = 'adj' | 'detail' | 'residual' | 'none'

export interface G11DiscAmountPair {
  currentAmount: number
  priorAmount: number
}

/** 按审定/披露主表 rowKey 汇总 */
export type G11DiscAmountMap = Record<string, G11DiscAmountPair>
export type G11DiscSourceMap = Record<string, G11DiscAmountSource>

function emptyMap(): G11DiscAmountMap {
  const out: G11DiscAmountMap = {}
  for (const def of G11_ADJUDICATION_ITEMS) {
    out[def.rowKey] = { currentAmount: 0, priorAmount: 0 }
  }
  return out
}

function pairNonZero(p: G11DiscAmountPair): boolean {
  return Math.abs(p.currentAmount) > 0.005 || Math.abs(p.priorAmount) > 0.005
}

function auditedPair(raw: G11AdjRowStore[string] | undefined): G11DiscAmountPair {
  return {
    currentAmount: calcAdjustedAmount(
      parseNum(raw?.currentUnadjusted),
      parseNum(raw?.currentAdjustment),
    ),
    priorAmount: calcAdjustedAmount(
      parseNum(raw?.priorUnadjusted),
      parseNum(raw?.priorAdjustment),
    ),
  }
}

/** G11-1 分项 → 发生额（审定数） */
export function buildG11DisclosureAmountsFromAdjStore(store: G11AdjRowStore): G11DiscAmountMap {
  const out = emptyMap()
  for (const def of G11_ADJUDICATION_ITEMS) {
    out[def.rowKey] = auditedPair(store[def.rowKey])
  }
  return out
}

/** 明细 itemName → 审定 rowKey */
export function g11DetailItemToRowKey(itemName: string): string | null {
  const name = String(itemName ?? '').trim()
  if (!name) return null
  const exact = G11_ADJUDICATION_ITEMS.find((d) => d.label === name)
  if (exact) return exact.rowKey
  // 上市文案微调：利息收入 ↔ 利息收益；股利收入 ↔ 持有…股利收入
  const aliases: Array<[RegExp, string]> = [
    // 更长/更具体的模式须在前，避免「其他债权…」命中「债权…」
    [/其他债权投资持有期间的利息/, 'oth_debt_hold_interest'],
    [/债权投资持有期间的利息/, 'debt_hold_interest'],
    [/其他权益工具.*股利/, 'oei_dividend'],
    [/其他债权投资处置|处置其他债权/, 'oth_debt_dispose'],
    [/债权投资处置|处置债权投资/, 'debt_dispose'],
    [/处置衍生/, 'derivative_dispose'],
    [/现金流量套期.*无效/, 'hedge_ineffective'],
    [/债务重组/, 'debt_restructuring'],
    [/其他非流动金融资产.*持有|持有其他非流动金融资产/, 'onfa_hold'],
    [/处置其他非流动金融资产/, 'onfa_dispose'],
    [/权益法核算/, 'equity_method'],
    [/处置长期股权投资产生/, 'dispose_lt_equity'],
    [/持有待售.*长期股权/, 'dispose_hfs_lt'],
    [/交易性金融资产持有/, 'trading_hold'],
    [/处置交易性金融资产/, 'trading_dispose'],
    [/取得控制权时/, 'control_fv_gain'],
    [/丧失控制权后.*剩余股权|剩余股权按公允价值/, 'loss_control_fv_gain'],
  ]
  for (const [re, key] of aliases) {
    if (re.test(name)) return key
  }
  const fuzzy = G11_ADJUDICATION_ITEMS.find(
    (d) => name.includes(d.label.slice(0, 8)) || d.label.includes(name.slice(0, 8)),
  )
  return fuzzy?.rowKey ?? null
}

/** G11-2 明细按项目汇总 */
export function buildG11DisclosureAmountsFromDetailRows(
  rows: Array<{
    itemName?: string
    currentAudited?: number
    priorAudited?: number
    currentUnadjusted?: number
    currentAdjustment?: number
    priorUnadjusted?: number
    priorAdjustment?: number
  }>,
): G11DiscAmountMap {
  const out = emptyMap()
  for (const r of rows) {
    const key = g11DetailItemToRowKey(r.itemName ?? '')
    if (!key || !out[key]) continue
    const current = r.currentAudited != null
      ? parseNum(r.currentAudited)
      : calcAdjustedAmount(parseNum(r.currentUnadjusted), parseNum(r.currentAdjustment))
    const prior = r.priorAudited != null
      ? parseNum(r.priorAudited)
      : calcAdjustedAmount(parseNum(r.priorUnadjusted), parseNum(r.priorAdjustment))
    out[key].currentAmount += current
    out[key].priorAmount += prior
  }
  return out
}

/** 各行：明细有数用明细，否则用审定 */
export function mergeG11DisclosureAmounts(
  fromAdj: G11DiscAmountMap,
  fromDetail: G11DiscAmountMap,
): { amounts: G11DiscAmountMap; sources: G11DiscSourceMap } {
  const amounts = emptyMap()
  const sources: G11DiscSourceMap = {}
  for (const def of G11_ADJUDICATION_ITEMS) {
    const key = def.rowKey
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

function parseDetailRows(responses: Map<string, ChecklistResponse>): unknown[] {
  try {
    const raw = responses.get(G11_DETAIL_KEY)?.remark
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function buildG11DisclosureAmountsFromResponses(
  responses: Map<string, ChecklistResponse>,
): {
  amounts: G11DiscAmountMap
  sources: G11DiscSourceMap
  fromAdj: G11DiscAmountMap
  fromDetail: G11DiscAmountMap
} {
  const fromAdj = buildG11DisclosureAmountsFromAdjStore(
    parseG11AdjStore(responses.get(G11_ADJ_ROWS_KEY)?.remark),
  )
  const fromDetail = buildG11DisclosureAmountsFromDetailRows(parseDetailRows(responses) as any[])
  const { amounts, sources } = mergeG11DisclosureAmounts(fromAdj, fromDetail)
  return { amounts, sources, fromAdj, fromDetail }
}

export interface G11DisclosureAmountRow {
  rowKey: string
  label: string
  currentAmount: number
  priorAmount: number
  remark: string
}

export interface G11DiscPullApplyResult<T extends G11DisclosureAmountRow> {
  next: T[]
  filledKeys: string[]
  categoryCurrentSum: number
  categoryPriorSum: number
  usedResidual: boolean
  sources: G11DiscSourceMap
}

/**
 * 写入披露行数组；仅覆盖主表 leaf 行；分项合计≈0 且有 residual 时写入「其他」。
 */
export function applyG11DisclosureAmountsToRows<T extends G11DisclosureAmountRow>(
  rows: T[],
  amounts: G11DiscAmountMap,
  variant: 'listed' | 'soe',
  opts?: {
    residualCurrent?: number | null
    residualPrior?: number | null
    sources?: G11DiscSourceMap
  },
): G11DiscPullApplyResult<T> {
  const mainKeys = variant === 'listed' ? G11_LISTED_MAIN_ROW_KEYS : G11_SOE_MAIN_ROW_KEYS
  const sources: G11DiscSourceMap = { ...(opts?.sources ?? {}) }
  const filledKeys: string[] = []

  const next = rows.map((row) => {
    if (!mainKeys.has(row.rowKey) || !isG11DisclosureLeaf(row.rowKey)) return row
    const pair = amounts[row.rowKey] ?? { currentAmount: 0, priorAmount: 0 }
    if (pairNonZero(pair)) filledKeys.push(row.rowKey)
    const src = sources[row.rowKey]
    const remarkTag = src === 'detail' ? 'G11-2' : src === 'adj' ? 'G11-1' : row.remark
    return {
      ...row,
      currentAmount: pair.currentAmount,
      priorAmount: pair.priorAmount,
      remark: pairNonZero(pair) ? (row.remark?.startsWith('G11-') ? remarkTag : (row.remark || remarkTag)) : row.remark,
    }
  })

  const leafAmounts = [...mainKeys].map((k) => amounts[k] ?? { currentAmount: 0, priorAmount: 0 })
  const categoryCurrentSum = calcSubtotal(leafAmounts.map((p) => p.currentAmount))
  const categoryPriorSum = calcSubtotal(leafAmounts.map((p) => p.priorAmount))

  let usedResidual = false
  const residualCurrent = opts?.residualCurrent
  const residualPrior = opts?.residualPrior
  if (
    Math.abs(categoryCurrentSum) <= G11_CROSS_TOLERANCE
    && residualCurrent != null
    && Math.abs(residualCurrent) > G11_CROSS_TOLERANCE
  ) {
    const otherIdx = next.findIndex((r) => r.rowKey === 'other')
    if (otherIdx >= 0) {
      next[otherIdx] = {
        ...next[otherIdx],
        currentAmount: residualCurrent,
        priorAmount: residualPrior ?? next[otherIdx].priorAmount,
        remark: next[otherIdx].remark || '残差',
      }
      if (!filledKeys.includes('other')) filledKeys.push('other')
      sources.other = 'residual'
      usedResidual = true
    }
  }

  return { next, filledKeys, categoryCurrentSum, categoryPriorSum, usedResidual, sources }
}

const SRC_LABEL: Record<G11DiscAmountSource, string> = {
  adj: 'G11-1',
  detail: 'G11-2',
  residual: '残差',
  none: '空',
}

const SHORT_LABEL: Record<string, string> = {
  equity_method: '权益法',
  dispose_lt_equity: '处置长投',
  trading_hold: '交易性持有',
  trading_dispose: '交易性处置',
  debt_hold_interest: '债权利息',
  oei_dividend: 'OE股利',
  onfa_hold: 'ONFA持有',
  onfa_dispose: 'ONFA处置',
  other: '其他',
}

export function formatG11DiscPullSummary(
  sources: G11DiscSourceMap,
  usedResidual: boolean,
  filledKeys: string[],
): string {
  const keys = filledKeys.length > 0
    ? filledKeys
    : Object.keys(sources).filter((k) => sources[k] !== 'none')
  const parts = keys.slice(0, 8).map((k) => {
    const label = SHORT_LABEL[k] ?? k
    return `${label}←${SRC_LABEL[sources[k] ?? 'none']}`
  })
  const more = keys.length > 8 ? `等${keys.length}项` : ''
  const body = parts.length > 0 ? `${parts.join('；')}${more ? `；${more}` : ''}` : '无分项'
  return usedResidual
    ? `${body}（无分项，审定数已写入「其他」，请按项目手工分拆）`
    : body
}

/** 仅主表 leaf 行合计（排除「其中：」「减：」） */
export function sumG11DisclosureLeafCurrent(
  rows: Array<{ rowKey: string; currentAmount: number }>,
): number {
  return calcSubtotal(
    rows.filter((r) => isG11DisclosureLeaf(r.rowKey)).map((r) => parseNum(r.currentAmount)),
  )
}

export function sumG11DisclosureLeafPrior(
  rows: Array<{ rowKey: string; priorAmount: number }>,
): number {
  return calcSubtotal(
    rows.filter((r) => isG11DisclosureLeaf(r.rowKey)).map((r) => parseNum(r.priorAmount)),
  )
}

export function computeG11DisclosurePull(
  responses: Map<string, ChecklistResponse>,
  rows: G11DisclosureAmountRow[],
  variant: 'listed' | 'soe',
): G11DiscPullApplyResult<G11DisclosureAmountRow> & { summary: string } {
  const built = buildG11DisclosureAmountsFromResponses(responses)
  const adjRaw = responses.get(G11_ADJUDICATED_KEY)?.conclusion
  const residual = adjRaw != null && adjRaw !== '' ? parseNum(adjRaw) : null
  const result = applyG11DisclosureAmountsToRows(rows, built.amounts, variant, {
    residualCurrent: residual,
    residualPrior: null,
    sources: built.sources,
  })
  return {
    ...result,
    summary: formatG11DiscPullSummary(result.sources, result.usedResidual, result.filledKeys),
  }
}

// ─── 上市：处置交易性明细子表 ───

export type G11TradingDisposeMap = Record<G11TradingDisposeSuffix, G11DiscAmountPair>
export type G11TradingDisposeSourceMap = Record<G11TradingDisposeSuffix, G11DiscAmountSource>

function emptyTradingDisposeMap(): G11TradingDisposeMap {
  return Object.fromEntries(
    G11_TRADING_DISPOSE_SUFFIXES.map((k) => [k, { currentAmount: 0, priorAmount: 0 }]),
  ) as G11TradingDisposeMap
}

/** 明细文本 → 处置交易性子类 */
export function g11TradingDisposeSubtype(text: string): G11TradingDisposeSuffix {
  const t = String(text ?? '')
  if (/套期|公允价值套期|有效套期/.test(t)) return 'derivative_hedge'
  if (/衍生|期货|远期|互换|期权/.test(t)) return 'derivative_non_hedge'
  if (/债券|债务工具|债/.test(t) && !/股权|股票|权益/.test(t)) return 'debt_bond'
  if (/股票|权益工具|股权|基金/.test(t)) return 'equity_stock'
  return 'other'
}

/** G11-2 中处置交易性相关行 → 子表明细 */
export function buildG11TradingDisposeFromDetailRows(
  rows: Array<{
    rowKey?: string
    itemName?: string
    investeeName?: string
    tradingDisposeSubtype?: G11TradingDisposeSuffix | '' | null
    currentAudited?: number
    priorAudited?: number
    currentUnadjusted?: number
    currentAdjustment?: number
    priorUnadjusted?: number
    priorAdjustment?: number
  }>,
): { amounts: G11TradingDisposeMap; sources: G11TradingDisposeSourceMap; filled: G11TradingDisposeSuffix[] } {
  const amounts = emptyTradingDisposeMap()
  const sources = Object.fromEntries(
    G11_TRADING_DISPOSE_SUFFIXES.map((k) => [k, 'none' as G11DiscAmountSource]),
  ) as G11TradingDisposeSourceMap
  const filled: G11TradingDisposeSuffix[] = []

  for (const r of rows) {
    if (!isG11TradingDisposeDetailRow(r)) continue
    const explicit = String(r.tradingDisposeSubtype ?? '').trim() as G11TradingDisposeSuffix
    const text = `${r.investeeName ?? ''} ${r.itemName ?? ''}`
    if (
      !explicit
      && r.rowKey === 'trading_dispose'
      && !String(r.investeeName ?? '').trim()
    ) {
      const name = String(r.itemName ?? '').trim()
      if (name === '处置交易性金融资产取得的投资收益' || !/(股票|债券|衍生|套期)/.test(name)) {
        continue
      }
    }
    const key = explicit && G11_TRADING_DISPOSE_SUFFIXES.includes(explicit)
      ? explicit
      : g11TradingDisposeSubtype(text)
    const current = r.currentAudited != null
      ? parseNum(r.currentAudited)
      : calcAdjustedAmount(parseNum(r.currentUnadjusted), parseNum(r.currentAdjustment))
    const prior = r.priorAudited != null
      ? parseNum(r.priorAudited)
      : calcAdjustedAmount(parseNum(r.priorUnadjusted), parseNum(r.priorAdjustment))
    if (Math.abs(current) < 0.005 && Math.abs(prior) < 0.005) continue
    amounts[key].currentAmount += current
    amounts[key].priorAmount += prior
    sources[key] = 'detail'
    if (!filled.includes(key)) filled.push(key)
  }
  return { amounts, sources, filled }
}

export function sumG11TradingDisposeCurrent(map: G11TradingDisposeMap): number {
  return calcSubtotal(G11_TRADING_DISPOSE_SUFFIXES.map((k) => parseNum(map[k]?.currentAmount)))
}

export function tradingDisposeRowsFromMap(
  map: G11TradingDisposeMap,
): Array<{ rowKey: string; label: string; currentAmount: number; priorAmount: number; remark: string }> {
  return G11_LISTED_TRADING_DISPOSE_ROWS.map((def) => ({
    rowKey: def.rowKey,
    label: def.label,
    currentAmount: map[def.rowKey as G11TradingDisposeSuffix]?.currentAmount ?? 0,
    priorAmount: map[def.rowKey as G11TradingDisposeSuffix]?.priorAmount ?? 0,
    remark: '',
  }))
}

// ─── v2 store + 批量同步 ───

export interface G11DiscStoreV2 {
  version: 2
  rows: G11DisclosureAmountRow[]
  tradingDispose?: G11TradingDisposeMap
  repatriationNote?: string
}

export function defaultG11TradingDisposeMap(): G11TradingDisposeMap {
  return emptyTradingDisposeMap()
}

export function defaultG11DiscStore(variant: 'listed' | 'soe'): G11DiscStoreV2 {
  return {
    version: 2,
    rows: g11DisclosureSchema(variant).map((d) => ({
      rowKey: d.rowKey,
      label: d.label,
      currentAmount: 0,
      priorAmount: 0,
      remark: '',
    })),
    tradingDispose: variant === 'listed' ? emptyTradingDisposeMap() : undefined,
    repatriationNote: variant === 'soe' ? G11_SOE_REPATRIATION_PLACEHOLDER : undefined,
  }
}

export function parseG11DiscStore(
  raw: string | null | undefined,
  variant: 'listed' | 'soe',
): G11DiscStoreV2 {
  const base = defaultG11DiscStore(variant)
  if (!raw) return base
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) {
      const byKey = new Map(parsed.map((r: any) => [r.rowKey, r]))
      return {
        ...base,
        rows: base.rows.map((r) => ({
          ...r,
          currentAmount: parseNum(byKey.get(r.rowKey)?.currentAmount),
          priorAmount: parseNum(byKey.get(r.rowKey)?.priorAmount),
          remark: String(byKey.get(r.rowKey)?.remark ?? ''),
        })),
      }
    }
    if (parsed?.version === 2 && Array.isArray(parsed.rows)) {
      const byKey = new Map(parsed.rows.map((r: any) => [r.rowKey, r]))
      const tradingDispose = variant === 'listed'
        ? {
            ...emptyTradingDisposeMap(),
            ...(parsed.tradingDispose ?? {}),
          }
        : undefined
      return {
        version: 2,
        rows: base.rows.map((r) => ({
          ...r,
          currentAmount: parseNum(byKey.get(r.rowKey)?.currentAmount),
          priorAmount: parseNum(byKey.get(r.rowKey)?.priorAmount),
          remark: String(byKey.get(r.rowKey)?.remark ?? ''),
        })),
        tradingDispose,
        repatriationNote: variant === 'soe'
          ? String(parsed.repatriationNote ?? base.repatriationNote ?? '')
          : undefined,
      }
    }
  } catch { /* ignore */ }
  return base
}

export interface G11DisclosurePullBatchResult {
  listedStore: G11DiscStoreV2
  soeStore: G11DiscStoreV2
  usedResidual: boolean
  summary: string
  tradingDisposeFilled: number
}

/**
 * 从 G11-1/G11-2 同步两套附注（主表 + 上市处置交易性子表）。
 */
export function applyG11DisclosurePullToResponses(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
): G11DisclosurePullBatchResult {
  const listedPrev = parseG11DiscStore(responses.get(G11_DISCLOSURE_LISTED_KEY)?.remark, 'listed')
  const soePrev = parseG11DiscStore(responses.get(G11_DISCLOSURE_SOE_KEY)?.remark, 'soe')

  const listedPull = computeG11DisclosurePull(responses, listedPrev.rows, 'listed')
  const soePull = computeG11DisclosurePull(responses, soePrev.rows, 'soe')

  const detailRows = parseDetailRows(responses)
  const td = buildG11TradingDisposeFromDetailRows(detailRows as any[])

  const listedStore: G11DiscStoreV2 = {
    version: 2,
    rows: listedPull.next,
    tradingDispose: td.filled.length > 0 ? td.amounts : (listedPrev.tradingDispose ?? emptyTradingDisposeMap()),
  }
  const soeStore: G11DiscStoreV2 = {
    version: 2,
    rows: soePull.next,
    repatriationNote: soePrev.repatriationNote?.trim()
      ? soePrev.repatriationNote
      : G11_SOE_REPATRIATION_PLACEHOLDER,
  }

  debouncedSave(G11_DISCLOSURE_LISTED_KEY, { remark: JSON.stringify(listedStore) })
  debouncedSave(G11_DISCLOSURE_SOE_KEY, { remark: JSON.stringify(soeStore) })
  responses.set(G11_DISCLOSURE_LISTED_KEY, {
    item_id: G11_DISCLOSURE_LISTED_KEY,
    conclusion: responses.get(G11_DISCLOSURE_LISTED_KEY)?.conclusion ?? null,
    remark: JSON.stringify(listedStore),
  })
  responses.set(G11_DISCLOSURE_SOE_KEY, {
    item_id: G11_DISCLOSURE_SOE_KEY,
    conclusion: responses.get(G11_DISCLOSURE_SOE_KEY)?.conclusion ?? null,
    remark: JSON.stringify(soeStore),
  })

  const usedResidual = listedPull.usedResidual || soePull.usedResidual
  const tdPart = td.filled.length > 0 ? `；处置交易性明细 ${td.filled.length} 类←G11-2` : ''
  const summary = `上市：${listedPull.summary}；国企：${soePull.summary}${tdPart}`

  try {
    window.dispatchEvent(new CustomEvent('g11:disclosure-pulled', {
      detail: { usedResidual, summary, timestamp: Date.now() },
    }))
  } catch { /* silent */ }

  return {
    listedStore,
    soeStore,
    usedResidual,
    summary,
    tradingDisposeFilled: td.filled.length,
  }
}

export { G11_ADJ_ROWS_KEY, G11_DETAIL_KEY, G11_ADJUDICATED_KEY, G11_CROSS_TOLERANCE }

export interface G11DisclosureDirectoryVariant {
  code: '附注上市' | '附注国企'
  label: string
  filled: boolean
  currentSum: number
  crossOk: boolean | null
  crossVariance: number | null
  tradingDisposeCrossOk: boolean | null
}

function discStoreFilled(store: G11DiscStoreV2): boolean {
  const main = store.rows.some(
    (r) => isG11DisclosureLeaf(r.rowKey) && (Math.abs(r.currentAmount) > 0.005 || Math.abs(r.priorAmount) > 0.005),
  )
  const tdMap = store.tradingDispose
  const hasTradingDispose = tdMap
    ? G11_TRADING_DISPOSE_SUFFIXES.some((k) => {
      const p = tdMap[k]
      return Math.abs(p?.currentAmount ?? 0) > 0.005 || Math.abs(p?.priorAmount ?? 0) > 0.005
    })
    : false
  return main || hasTradingDispose
}

/** 底稿目录：附注披露编制与 G11-1 审定勾稽状态 */
export function summarizeG11DisclosureDirectoryStatus(
  m: Map<string, { remark?: string; conclusion?: string }>,
): {
  adjudicated: number | null
  variants: G11DisclosureDirectoryVariant[]
} {
  const adjRaw = m.get(G11_ADJUDICATED_KEY)?.conclusion
  const adjudicated = adjRaw != null && String(adjRaw).trim() !== '' ? parseNum(adjRaw) : null
  const variants: G11DisclosureDirectoryVariant[] = []

  function pushListed(): void {
    let filled = false
    let currentSum = 0
    let tradingDisposeCrossOk: boolean | null = null
    const store = parseG11DiscStore(m.get(G11_DISCLOSURE_LISTED_KEY)?.remark, 'listed')
    currentSum = sumG11DisclosureLeafCurrent(store.rows)
    filled = discStoreFilled(store)
    const main = parseNum(store.rows.find((r) => r.rowKey === 'trading_dispose')?.currentAmount)
    const sub = store.tradingDispose ? sumG11TradingDisposeCurrent(store.tradingDispose) : 0
    if (Math.abs(sub) > G11_CROSS_TOLERANCE) {
      tradingDisposeCrossOk = Math.abs(sub - main) <= G11_CROSS_TOLERANCE
    }
    const crossVariance = adjudicated != null && filled ? currentSum - adjudicated : null
    const crossOk = crossVariance != null ? Math.abs(crossVariance) <= G11_CROSS_TOLERANCE : null
    variants.push({
      code: '附注上市',
      label: '上市格式',
      filled,
      currentSum,
      crossOk,
      crossVariance,
      tradingDisposeCrossOk,
    })
  }

  function pushSoe(): void {
    let filled = false
    let currentSum = 0
    const store = parseG11DiscStore(m.get(G11_DISCLOSURE_SOE_KEY)?.remark, 'soe')
    currentSum = sumG11DisclosureLeafCurrent(store.rows)
    filled = discStoreFilled(store) || !!store.repatriationNote?.trim()
    const crossVariance = adjudicated != null && filled ? currentSum - adjudicated : null
    const crossOk = crossVariance != null ? Math.abs(crossVariance) <= G11_CROSS_TOLERANCE : null
    variants.push({
      code: '附注国企',
      label: '国企格式',
      filled,
      currentSum,
      crossOk,
      crossVariance,
      tradingDisposeCrossOk: null,
    })
  }

  pushListed()
  pushSoe()
  return { adjudicated, variants }
}
