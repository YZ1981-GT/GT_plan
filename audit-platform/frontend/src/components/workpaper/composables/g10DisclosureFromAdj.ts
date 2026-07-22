/**
 * G10 附注 ← G10-1 账面余额分项 + G10-2 明细（种类/增减）
 * 对齐 Excel：交易性债券/衍生/其他 + 指定债券/其他
 */
import { G10_LIABILITY_LINE_SUFFIXES, G10_ADJUDICATION_ITEMS, type G10LiabilityLineSuffix } from './g10AdjudicationItems'
import { G10_ADJ_ROWS_KEY, parseG10AdjStore, type G10AdjRowStore, g10RowClosingAdjusted, g10RowOpeningAdjusted } from './g10AdjStorage'
import {
  G10_DISC_LINE_SUFFIXES,
  G10_DISC_SUFFIX_TO_MOVEMENT_KEY,
  G10_DISC_SUFFIX_TO_SOE_KEY,
  G10_LISTED_MOVEMENT_ROWS,
  G10_SOE_BALANCE_ROWS,
  g10MaturityDiffPlaceholder,
  type G10DiscLineSuffix,
} from './g10SchemaRows'
import { parseNum, calcAdjustedAmount, calcSubtotal } from './useG10FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export { G10_ADJ_ROWS_KEY }
export const G10_DETAIL_KEY = 'G10-detail-rows'
export const G10_ADJUDICATED_KEY = 'G10-1-adjudicated-amount'
export const G10_CROSS_TOLERANCE = 0.01

export type G10DiscAmountSource = 'adj' | 'detail' | 'residual' | 'none'

export interface G10DiscMovementPair {
  openingAmount: number
  increaseAmount: number
  decreaseAmount: number
  closingAmount: number
}

export interface G10DiscBalancePair {
  currentAmount: number
  priorAmount: number
}

export type G10DiscMovementMap = Record<G10DiscLineSuffix, G10DiscMovementPair>
export type G10DiscBalanceMap = Record<G10DiscLineSuffix, G10DiscBalancePair>

const ADJ_SUFFIX_TO_DISC: Partial<Record<G10LiabilityLineSuffix, G10DiscLineSuffix>> = {
  trading_bond: 'trading_bond',
  derivative_liability: 'derivative',
  other: 'other_trading',
  designated_bond: 'designated_bond',
  hybrid_tool: 'hybrid_tool',
  other_designated: 'other_designated',
}

const LIABILITY_TYPE_TO_DISC: Record<string, G10DiscLineSuffix> = {
  交易性债券: 'trading_bond',
  衍生金融负债: 'derivative',
  卖出回购: 'other_trading',
  融券负债: 'other_trading',
  结构化产品: 'hybrid_tool',
  其他: 'other_trading',
}

/** 明细行 → 附注分项（考虑指定类/交易类） */
function resolveDetailDiscKey(row: {
  liabilityType?: string
  liabilityCategory?: string
  liabilityName?: string
  isDerivative?: boolean
}): G10DiscLineSuffix | null {
  const category = String(row.liabilityCategory ?? '').trim()
  const type = String(row.liabilityType ?? '').trim()
  const text = `${row.liabilityName ?? ''} ${type}`
  if (category === '指定类') {
    if (/债券/.test(text)) return 'designated_bond'
    if (/混合|结构化/.test(text)) return 'hybrid_tool'
    return 'other_designated'
  }
  if (row.isDerivative || type === '衍生金融负债' || /衍生|期权|互换|期货/.test(text)) {
    return 'derivative'
  }
  return LIABILITY_TYPE_TO_DISC[type] ?? (type ? 'other_trading' : null)
}

type G10DetailDiscRow = {
  liabilityType?: string
  liabilityCategory?: string
  liabilityName?: string
  openingAdjusted?: number
  closingAdjusted?: number
  openingBalance?: number
  closingBalance?: number
  openingFairValue?: number
  closingFairValue?: number
  currentIncrease?: number
  currentDecrease?: number
  movementInitialAmount?: number
  movementFvChange?: number
  interestExpense?: number
  isDerivative?: boolean
}

function detailOpening(row: G10DetailDiscRow): number {
  return parseNum(row.openingAdjusted ?? row.openingFairValue ?? row.openingBalance)
}

function detailClosing(row: G10DetailDiscRow): number {
  return parseNum(row.closingAdjusted ?? row.closingFairValue ?? row.closingBalance)
}

function detailIncrease(row: G10DetailDiscRow): number {
  const initial = parseNum(row.movementInitialAmount)
  const fv = parseNum(row.movementFvChange)
  const interest = parseNum(row.interestExpense)
  if (Math.abs(initial) > 0.005 || Math.abs(fv) > 0.005 || Math.abs(interest) > 0.005) {
    return initial + Math.max(0, fv) + Math.max(0, interest)
  }
  const direct = parseNum(row.currentIncrease)
  if (Math.abs(direct) > 0.005) return direct
  const delta = detailClosing(row) - detailOpening(row) + parseNum(row.currentDecrease)
  return delta > 0 ? delta : 0
}

function detailDecrease(row: G10DetailDiscRow): number {
  const direct = parseNum(row.currentDecrease)
  if (Math.abs(direct) > 0.005) return direct
  const delta = detailOpening(row) + detailIncrease(row) - detailClosing(row)
  return delta > 0 ? delta : 0
}

function emptyMovementMap(): G10DiscMovementMap {
  return Object.fromEntries(
    G10_DISC_LINE_SUFFIXES.map((k) => [k, {
      openingAmount: 0,
      increaseAmount: 0,
      decreaseAmount: 0,
      closingAmount: 0,
    }]),
  ) as G10DiscMovementMap
}

function emptyBalanceMap(): G10DiscBalanceMap {
  return Object.fromEntries(
    G10_DISC_LINE_SUFFIXES.map((k) => [k, { currentAmount: 0, priorAmount: 0 }]),
  ) as G10DiscBalanceMap
}

function pairNonZeroMovement(p: G10DiscMovementPair): boolean {
  return Math.abs(p.openingAmount) > 0.005
    || Math.abs(p.increaseAmount) > 0.005
    || Math.abs(p.decreaseAmount) > 0.005
    || Math.abs(p.closingAmount) > 0.005
}

function pairNonZeroBalance(p: G10DiscBalancePair): boolean {
  return Math.abs(p.currentAmount) > 0.005 || Math.abs(p.priorAmount) > 0.005
}

function adjustedPair(raw: G10AdjRowStore[string] | undefined): G10DiscBalancePair {
  return {
    currentAmount: g10RowClosingAdjusted(raw),
    priorAmount: g10RowOpeningAdjusted(raw),
  }
}

/** G10-1 (三)账面余额分项 → 期初/期末 */
export function buildG10DisclosureBalanceFromAdjStore(store: G10AdjRowStore): G10DiscBalanceMap {
  const out = emptyBalanceMap()
  for (const suffix of G10_LIABILITY_LINE_SUFFIXES) {
    const discKey = ADJ_SUFFIX_TO_DISC[suffix]
    if (!discKey || suffix === 'trading_liability' || suffix === 'designated_fvtpl') continue
    const pair = adjustedPair(store[`book_${suffix}`])
    out[discKey].currentAmount += pair.currentAmount
    out[discKey].priorAmount += pair.priorAmount
  }
  return out
}

/** G10-1 → 变动表（期初/期末；增减由明细补全或按差额推导） */
export function buildG10DisclosureMovementFromAdjStore(store: G10AdjRowStore): G10DiscMovementMap {
  const out = emptyMovementMap()
  for (const suffix of G10_LIABILITY_LINE_SUFFIXES) {
    const discKey = ADJ_SUFFIX_TO_DISC[suffix]
    if (!discKey || suffix === 'trading_liability' || suffix === 'designated_fvtpl') continue
    const pair = adjustedPair(store[`book_${suffix}`])
    const net = pair.currentAmount - pair.priorAmount
    out[discKey] = {
      openingAmount: pair.priorAmount,
      closingAmount: pair.currentAmount,
      increaseAmount: net > 0 ? net : 0,
      decreaseAmount: net < 0 ? -net : 0,
    }
  }
  return out
}

/** G10-2 明细 → 分项增减与余额 */
export function buildG10DisclosureMovementFromDetailRows(
  rows: G10DetailDiscRow[],
): G10DiscMovementMap {
  const out = emptyMovementMap()
  for (const r of rows) {
    const discKey = resolveDetailDiscKey(r)
    if (!discKey) continue
    const opening = detailOpening(r)
    const closing = detailClosing(r)
    const increase = detailIncrease(r)
    const decrease = detailDecrease(r)
    out[discKey].openingAmount += opening
    out[discKey].closingAmount += closing
    out[discKey].increaseAmount += increase
    out[discKey].decreaseAmount += decrease
  }
  return out
}

export function buildG10DisclosureBalanceFromDetailRows(
  rows: G10DetailDiscRow[],
): G10DiscBalanceMap {
  const out = emptyBalanceMap()
  for (const r of rows) {
    const discKey = resolveDetailDiscKey(r)
    if (!discKey) continue
    out[discKey].currentAmount += detailClosing(r)
    out[discKey].priorAmount += detailOpening(r)
  }
  return out
}

const DESIGNATED_ADJ_ROWS: Array<{ adjKey: string; label: string }> = [
  { adjKey: 'book_designated_bond', label: '发行的普通债权' },
  { adjKey: 'book_designated_fvtpl', label: '指定为FVTPL的金融负债' },
  { adjKey: 'book_other_designated', label: '其他指定负债' },
  { adjKey: 'book_hybrid_tool', label: '混合工具' },
]

/** G10-1 (三) 指定分项 → 上市附注「指定明细」表 */
export function buildG10DesignatedDetailFromAdjStore(
  store: G10AdjRowStore,
): G10DiscListedStore['designatedDetail'] {
  const out: G10DiscListedStore['designatedDetail'] = {}
  let i = 0
  for (const { adjKey, label } of DESIGNATED_ADJ_ROWS) {
    const pair = adjustedPair(store[adjKey])
    if (Math.abs(pair.currentAmount) <= 0.005 && Math.abs(pair.priorAmount) <= 0.005) continue
    i += 1
    const raw = store[adjKey]
    out[`designated_${i}`] = {
      label,
      openingAmount: pair.priorAmount,
      closingAmount: pair.currentAmount,
      designationReason: String(raw?.reasonAnalysis ?? ''),
    }
  }
  return out
}

function mergeMovement(
  fromAdj: G10DiscMovementMap,
  fromDetail: G10DiscMovementMap,
): { amounts: G10DiscMovementMap; sources: Record<G10DiscLineSuffix, G10DiscAmountSource> } {
  const amounts = emptyMovementMap()
  const sources = {} as Record<G10DiscLineSuffix, G10DiscAmountSource>
  for (const key of G10_DISC_LINE_SUFFIXES) {
    if (pairNonZeroMovement(fromDetail[key])) {
      amounts[key] = { ...fromDetail[key] }
      sources[key] = 'detail'
    } else if (pairNonZeroMovement(fromAdj[key])) {
      amounts[key] = { ...fromAdj[key] }
      sources[key] = 'adj'
    } else {
      sources[key] = 'none'
    }
  }
  return { amounts, sources }
}

function mergeBalance(
  fromAdj: G10DiscBalanceMap,
  fromDetail: G10DiscBalanceMap,
): { amounts: G10DiscBalanceMap; sources: Record<G10DiscLineSuffix, G10DiscAmountSource> } {
  const amounts = emptyBalanceMap()
  const sources = {} as Record<G10DiscLineSuffix, G10DiscAmountSource>
  for (const key of G10_DISC_LINE_SUFFIXES) {
    if (pairNonZeroBalance(fromDetail[key])) {
      amounts[key] = { ...fromDetail[key] }
      sources[key] = 'detail'
    } else if (pairNonZeroBalance(fromAdj[key])) {
      amounts[key] = { ...fromAdj[key] }
      sources[key] = 'adj'
    } else {
      sources[key] = 'none'
    }
  }
  return { amounts, sources }
}

function parseDetailRows(responses: Map<string, ChecklistResponse>): unknown[] {
  try {
    const raw = responses.get(G10_DETAIL_KEY)?.remark
    const arr = raw ? JSON.parse(raw) : []
    return Array.isArray(arr) ? arr : []
  } catch {
    return []
  }
}

export function buildG10DisclosureAmountsFromResponses(responses: Map<string, ChecklistResponse>) {
  const store = parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark)
  const detailRows = parseDetailRows(responses)
  const fromAdjMovement = buildG10DisclosureMovementFromAdjStore(store)
  const fromDetailMovement = buildG10DisclosureMovementFromDetailRows(detailRows as any[])
  const fromAdjBalance = buildG10DisclosureBalanceFromAdjStore(store)
  const fromDetailBalance = buildG10DisclosureBalanceFromDetailRows(detailRows as any[])
  const movement = mergeMovement(fromAdjMovement, fromDetailMovement)
  const balance = mergeBalance(fromAdjBalance, fromDetailBalance)
  return {
    movement: movement.amounts,
    movementSources: movement.sources,
    balance: balance.amounts,
    balanceSources: balance.sources,
    fromAdjMovement,
    fromDetailMovement,
    fromAdjBalance,
    fromDetailBalance,
  }
}

export interface G10DiscListedStore {
  version: 2
  auditYear?: number
  movement: Record<string, G10DiscMovementPair>
  designatedDetail: Record<string, { label?: string; openingAmount: number; closingAmount: number; designationReason: string }>
  fvCreditRisk: Record<string, { label?: string; fvChangeAmount: number; creditRiskCurrent: number; creditRiskCumulative: number }>
  derivativeRows: Array<{ rowKey: string; label: string; currentAmount: number; priorAmount: number }>
  derivativeNote: string
  maturityDiffNote: string
}

export interface G10DiscSoeStore {
  version: 2
  auditYear?: number
  balance: Record<string, G10DiscBalancePair>
  fvCreditRisk: Record<string, { fvChangeAmount: number; creditRiskCurrent: number; creditRiskCumulative: number }>
  maturityDiffNote: string
}

export function defaultG10ListedDiscStore(): G10DiscListedStore {
  const movement = Object.fromEntries(
    Object.values(G10_DISC_SUFFIX_TO_MOVEMENT_KEY).map((k) => [
      k,
      { openingAmount: 0, increaseAmount: 0, decreaseAmount: 0, closingAmount: 0 },
    ]),
  )
  return {
    version: 2,
    movement,
    designatedDetail: {
      designated_1: { label: '发行的普通债权', openingAmount: 0, closingAmount: 0, designationReason: '' },
    },
    fvCreditRisk: {
      fv_1: { label: '发行的普通债权', fvChangeAmount: 0, creditRiskCurrent: 0, creditRiskCumulative: 0 },
    },
    derivativeRows: [],
    derivativeNote: '',
    maturityDiffNote: '',
  }
}

export function defaultG10SoeDiscStore(): G10DiscSoeStore {
  const balance = Object.fromEntries(
    Object.values(G10_DISC_SUFFIX_TO_SOE_KEY).map((k) => [
      k,
      { currentAmount: 0, priorAmount: 0 },
    ]),
  )
  return {
    version: 2,
    balance,
    fvCreditRisk: {
      fv_1: { label: '发行的普通债权', fvChangeAmount: 0, creditRiskCurrent: 0, creditRiskCumulative: 0 },
    },
    maturityDiffNote: '',
  }
}

export function applyG10ListedMovementToStore(
  prev: G10DiscListedStore,
  amounts: G10DiscMovementMap,
  opts?: { residualClosing?: number | null; sources?: Record<G10DiscLineSuffix, G10DiscAmountSource> },
): { next: G10DiscListedStore; filled: G10DiscLineSuffix[]; usedResidual: boolean } {
  const next: G10DiscListedStore = {
    ...prev,
    movement: { ...prev.movement },
  }
  const filled: G10DiscLineSuffix[] = []
  for (const suffix of G10_DISC_LINE_SUFFIXES) {
    const rowKey = G10_DISC_SUFFIX_TO_MOVEMENT_KEY[suffix]
    const pair = amounts[suffix]
    if (pairNonZeroMovement(pair)) filled.push(suffix)
    next.movement[rowKey] = { ...pair }
  }
  const leafSum = calcSubtotal(
    G10_DISC_LINE_SUFFIXES.map((k) => amounts[k].closingAmount),
  )
  let usedResidual = false
  const residual = opts?.residualClosing
  if (Math.abs(leafSum) <= 0.01 && residual != null && Math.abs(residual) > 0.01) {
    const rowKey = G10_DISC_SUFFIX_TO_MOVEMENT_KEY.other_trading
    next.movement[rowKey] = {
      openingAmount: 0,
      increaseAmount: residual > 0 ? residual : 0,
      decreaseAmount: residual < 0 ? -residual : 0,
      closingAmount: residual,
    }
    if (!filled.includes('other_trading')) filled.push('other_trading')
    usedResidual = true
  }
  return { next, filled, usedResidual }
}

export function applyG10SoeBalanceToStore(
  prev: G10DiscSoeStore,
  amounts: G10DiscBalanceMap,
  opts?: { residualCurrent?: number | null; residualPrior?: number | null },
): { next: G10DiscSoeStore; filled: G10DiscLineSuffix[]; usedResidual: boolean } {
  const next: G10DiscSoeStore = {
    ...prev,
    balance: { ...prev.balance },
  }
  const filled: G10DiscLineSuffix[] = []
  for (const suffix of G10_DISC_LINE_SUFFIXES) {
    const rowKey = G10_DISC_SUFFIX_TO_SOE_KEY[suffix]
    const pair = amounts[suffix]
    if (pairNonZeroBalance(pair)) filled.push(suffix)
    next.balance[rowKey] = { ...pair }
  }
  const leafSum = calcSubtotal(
    G10_DISC_LINE_SUFFIXES.map((k) => amounts[k].currentAmount),
  )
  let usedResidual = false
  const residual = opts?.residualCurrent
  if (Math.abs(leafSum) <= 0.01 && residual != null && Math.abs(residual) > 0.01) {
    const rowKey = G10_DISC_SUFFIX_TO_SOE_KEY.other_trading
    next.balance[rowKey] = {
      currentAmount: residual,
      priorAmount: opts?.residualPrior ?? 0,
    }
    if (!filled.includes('other_trading')) filled.push('other_trading')
    usedResidual = true
  }
  return { next, filled, usedResidual }
}

export function buildG10DerivativeRowsFromDetail(
  rows: Array<{
    liabilityName?: string
    liabilityType?: string
    closingAdjusted?: number
    closingBalance?: number
    openingAdjusted?: number
    openingBalance?: number
    isDerivative?: boolean
  }>,
): Array<{ rowKey: string; label: string; currentAmount: number; priorAmount: number }> {
  const out: Array<{ rowKey: string; label: string; currentAmount: number; priorAmount: number }> = []
  rows.forEach((r, i) => {
    const isDeriv = r.isDerivative || String(r.liabilityType ?? '').includes('衍生')
    if (!isDeriv) return
    const label = String(r.liabilityName ?? r.liabilityType ?? `衍生项目${i + 1}`).trim()
    if (!label) return
    out.push({
      rowKey: `deriv_${i + 1}`,
      label,
      currentAmount: parseNum(r.closingAdjusted ?? r.closingBalance),
      priorAmount: parseNum(r.openingAdjusted ?? r.openingBalance),
    })
  })
  return out
}

const DISC_LABELS: Record<G10DiscLineSuffix, string> = {
  trading_bond: '交易性债券',
  derivative: '衍生',
  other_trading: '其他',
  designated_bond: '指定债券',
  hybrid_tool: '混合工具',
  other_designated: '指定其他',
}

const SRC_LABEL: Record<G10DiscAmountSource, string> = {
  adj: 'G10-1',
  detail: 'G10-2',
  residual: '残差',
  none: '空',
}

export function formatG10DiscPullSummary(
  sources: Record<G10DiscLineSuffix, G10DiscAmountSource>,
  usedResidual: boolean,
): string {
  const parts = G10_DISC_LINE_SUFFIXES.map((k) => `${DISC_LABELS[k]}←${SRC_LABEL[sources[k]]}`)
  return usedResidual
    ? `${parts.join('；')}（无分项，审定数已写入「其他」，请按种类手工分拆）`
    : parts.join('；')
}

export function movementClosingSum(store: G10DiscListedStore): number {
  const leafKeys = G10_LISTED_MOVEMENT_ROWS.filter((r) => !r.isParent).map((r) => r.rowKey)
  return calcSubtotal(leafKeys.map((k) => store.movement[k]?.closingAmount ?? 0))
}

export function soeCurrentSum(store: G10DiscSoeStore): number {
  const leafKeys = G10_SOE_BALANCE_ROWS.filter((r) => !r.isParent).map((r) => r.rowKey)
  return calcSubtotal(leafKeys.map((k) => store.balance[k]?.currentAmount ?? 0))
}

export const G10_DISCLOSURE_LISTED_KEY = 'G10-disclosure-listed'
export const G10_DISCLOSURE_SOE_KEY = 'G10-disclosure-soe'

export interface G10DisclosurePullBatchResult {
  listedStore: G10DiscListedStore
  soeStore: G10DiscSoeStore
  usedResidual: boolean
  summary: string
}

function parseListedDiscStore(raw: string | null | undefined): G10DiscListedStore {
  try {
    const parsed = raw ? JSON.parse(raw) : null
    if (parsed?.version === 2) return { ...defaultG10ListedDiscStore(), ...parsed }
  } catch { /* ignore */ }
  return defaultG10ListedDiscStore()
}

function parseSoeDiscStore(raw: string | null | undefined): G10DiscSoeStore {
  try {
    const parsed = raw ? JSON.parse(raw) : null
    if (parsed?.version === 2) return { ...defaultG10SoeDiscStore(), ...parsed }
  } catch { /* ignore */ }
  return defaultG10SoeDiscStore()
}

/** 从 G10-1/G10-2 计算上市附注变动表带入结果（不直接落库） */
export function computeG10ListedDisclosurePull(
  responses: Map<string, ChecklistResponse>,
  prev: G10DiscListedStore,
  auditYear: number | null,
): { next: G10DiscListedStore; usedResidual: boolean; summary: string } {
  const built = buildG10DisclosureAmountsFromResponses(responses)
  const adjRaw = responses.get(G10_ADJUDICATED_KEY)?.conclusion
  const adjudicatedAmount = adjRaw != null && adjRaw !== '' ? parseNum(adjRaw) : 0
  const result = applyG10ListedMovementToStore(prev, built.movement, {
    residualClosing: adjudicatedAmount,
    sources: built.movementSources,
  })
  const detailRows = parseDetailRows(responses)
  const derivRows = buildG10DerivativeRowsFromDetail(detailRows as any[])
  const adjStore = parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark)
  const designated = buildG10DesignatedDetailFromAdjStore(adjStore)
  const maturityNote = prev.maturityDiffNote?.trim()
    ? prev.maturityDiffNote
    : g10MaturityDiffPlaceholder(auditYear)
  const next: G10DiscListedStore = {
    ...result.next,
    derivativeRows: derivRows.length > 0 ? derivRows : result.next.derivativeRows,
    designatedDetail: Object.keys(designated).length > 0
      ? { ...prev.designatedDetail, ...designated }
      : result.next.designatedDetail,
    maturityDiffNote: maturityNote,
    auditYear: auditYear ?? undefined,
  }
  return {
    next,
    usedResidual: result.usedResidual,
    summary: formatG10DiscPullSummary(built.movementSources, result.usedResidual),
  }
}

/** 从 G10-1/G10-2 计算国企附注余额表带入结果（不直接落库） */
export function computeG10SoeDisclosurePull(
  responses: Map<string, ChecklistResponse>,
  prev: G10DiscSoeStore,
  auditYear: number | null,
): { next: G10DiscSoeStore; usedResidual: boolean; summary: string } {
  const built = buildG10DisclosureAmountsFromResponses(responses)
  const adjRaw = responses.get(G10_ADJUDICATED_KEY)?.conclusion
  const adjudicatedAmount = adjRaw != null && adjRaw !== '' ? parseNum(adjRaw) : 0
  const result = applyG10SoeBalanceToStore(prev, built.balance, {
    residualCurrent: adjudicatedAmount,
    residualPrior: null,
  })
  const next: G10DiscSoeStore = {
    ...result.next,
    maturityDiffNote: prev.maturityDiffNote?.trim()
      ? prev.maturityDiffNote
      : g10MaturityDiffPlaceholder(auditYear),
    auditYear: auditYear ?? undefined,
  }
  return {
    next,
    usedResidual: result.usedResidual,
    summary: formatG10DiscPullSummary(built.balanceSources, result.usedResidual),
  }
}

/**
 * G10-2/G10-1 更新后同步两套附注披露 store（上市变动表 + 国企余额表）。
 * 返回汇总说明，供成功/警告提示使用。
 */
export function applyG10DisclosurePullToResponses(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  auditYear: number | null = null,
): G10DisclosurePullBatchResult {
  const listedPrev = parseListedDiscStore(responses.get(G10_DISCLOSURE_LISTED_KEY)?.remark)
  const soePrev = parseSoeDiscStore(responses.get(G10_DISCLOSURE_SOE_KEY)?.remark)
  const listed = computeG10ListedDisclosurePull(responses, listedPrev, auditYear)
  const soe = computeG10SoeDisclosurePull(responses, soePrev, auditYear)

  debouncedSave(G10_DISCLOSURE_LISTED_KEY, { remark: JSON.stringify(listed.next) })
  debouncedSave(G10_DISCLOSURE_SOE_KEY, { remark: JSON.stringify(soe.next) })
  responses.set(G10_DISCLOSURE_LISTED_KEY, {
    item_id: G10_DISCLOSURE_LISTED_KEY,
    conclusion: responses.get(G10_DISCLOSURE_LISTED_KEY)?.conclusion ?? null,
    remark: JSON.stringify(listed.next),
  })
  responses.set(G10_DISCLOSURE_SOE_KEY, {
    item_id: G10_DISCLOSURE_SOE_KEY,
    conclusion: responses.get(G10_DISCLOSURE_SOE_KEY)?.conclusion ?? null,
    remark: JSON.stringify(soe.next),
  })

  const usedResidual = listed.usedResidual || soe.usedResidual
  const summary = `上市：${listed.summary}；国企：${soe.summary}`
  try {
    window.dispatchEvent(new CustomEvent('g10:disclosure-pulled', {
      detail: { usedResidual, summary, timestamp: Date.now() },
    }))
  } catch { /* silent */ }

  return {
    listedStore: listed.next,
    soeStore: soe.next,
    usedResidual,
    summary,
  }
}

export interface G10DisclosureDirectoryVariant {
  code: '附注上市' | '附注国企'
  label: string
  filled: boolean
  closingSum: number
  crossOk: boolean | null
  crossVariance: number | null
}

/** 底稿目录：附注披露编制与审定勾稽状态 */
export function summarizeG10DisclosureDirectoryStatus(
  m: Map<string, { remark?: string; conclusion?: string }>,
): {
  adjudicated: number | null
  variants: G10DisclosureDirectoryVariant[]
} {
  const adjRaw = m.get(G10_ADJUDICATED_KEY)?.conclusion
  const adjudicated = adjRaw != null && String(adjRaw).trim() !== '' ? parseNum(adjRaw) : null
  const variants: G10DisclosureDirectoryVariant[] = []

  function pushVariant(
    code: '附注上市' | '附注国企',
    label: string,
    itemKey: string,
    sumFn: (store: G10DiscListedStore | G10DiscSoeStore) => number,
    filledFn: (store: G10DiscListedStore | G10DiscSoeStore) => boolean,
  ): void {
    let filled = false
    let closingSum = 0
    try {
      const raw = m.get(itemKey)?.remark
      if (raw) {
        const store = JSON.parse(raw) as G10DiscListedStore & G10DiscSoeStore
        closingSum = sumFn(store)
        filled = filledFn(store) || Math.abs(closingSum) > 0.005
      }
    } catch { /* ignore */ }
    const crossVariance = adjudicated != null && filled ? closingSum - adjudicated : null
    const crossOk = crossVariance != null ? Math.abs(crossVariance) <= G10_CROSS_TOLERANCE : null
    variants.push({ code, label, filled, closingSum, crossOk, crossVariance })
  }

  pushVariant(
    '附注上市',
    '上市格式',
    'G10-disclosure-listed',
    (s) => movementClosingSum(s as G10DiscListedStore),
    (s) => Object.values((s as G10DiscListedStore).movement ?? {}).some(pairNonZeroMovement),
  )
  pushVariant(
    '附注国企',
    '国企格式',
    'G10-disclosure-soe',
    (s) => soeCurrentSum(s as G10DiscSoeStore),
    (s) => Object.values((s as G10DiscSoeStore).balance ?? {}).some(pairNonZeroBalance),
  )

  return { adjudicated, variants }
}

export interface G10DisclosureAmountRow {
  rowKey: string
  currentAmount?: number
  priorAmount?: number
  remark?: string
}

/** 从 G10-1 审定表同步附注行金额（按 rowKey 对齐；bookSectionOnly 时仅 (三) 分项） */
export function syncG10DisclosureFromAdjudication<T extends G10DisclosureAmountRow>(
  disclosureRows: T[],
  adjJson: string | null | undefined,
  opts?: { bookSectionOnly?: boolean },
): T[] {
  const store = parseG10AdjStore(adjJson)
  const bookOnly = opts?.bookSectionOnly ?? false
  const adjKeys = new Set(G10_ADJUDICATION_ITEMS.map((d) => d.rowKey))

  return disclosureRows.map((row) => {
    if (row.rowKey === 'total' || !adjKeys.has(row.rowKey)) return row
    if (bookOnly && !row.rowKey.startsWith('book_')) return row
    const adj = store[row.rowKey]
    if (!adj) return row
    const currentAmount = g10RowClosingAdjusted(adj)
    const priorAmount = g10RowOpeningAdjusted(adj)
    if (
      Math.abs(currentAmount) < 0.005
      && Math.abs(priorAmount) < 0.005
      && Math.abs(parseNum(row.currentAmount)) < 0.005
      && Math.abs(parseNum(row.priorAmount)) < 0.005
    ) {
      return row
    }
    return {
      ...row,
      currentAmount,
      priorAmount,
      remark: row.remark || 'G10-1',
    }
  })
}
