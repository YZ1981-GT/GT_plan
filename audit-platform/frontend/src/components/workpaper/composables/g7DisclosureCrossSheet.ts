/**
 * G7 附注披露跨底稿取数。
 *
 * 优先从当前底稿 checklist_responses 读取 G7-1 / G7-2 / G7-4 / G7-5；
 * 若缺键，再尝试 cycle_workpapers 中的同循环兄弟底稿。
 */
import { api } from '@/services/apiProxy'
import {
  G7_4_ROWS_KEY,
  G7_14_ROWS_KEY,
  G7_14_SECTION_KEY,
  parseChecklistJson,
} from './g7EquityMethodCrossSheet'
import { rollforwardEnd } from '../g7-long-term-equity-method/calculation/g7EquityMethodCalcModel'
import {
  holdingRatioTotal,
  normalizeG7BasicInfoRow,
  type G7BasicInfoRow,
} from '../g7-long-term-equity-method/info/g7BasicInfoModel'
import {
  normalizeG7DetailRows,
  type G7DetailState,
  type G7EquityRow,
} from './g7DetailModel'
import {
  parseSubsequentPayload,
  type G7NciPurchaseRow,
  type G7PartialDisposalRow,
} from '../g7-long-term-equity-subsidiary/subsequent/g7SubsequentModel'
import type { G7DisclosureRow, G7DisclosureValue } from '../g7-long-term-equity-main/disclosure/g7ListedDisclosureModel'

export const G7_1_ADJ_KEY = 'G7-1-adjudication-data'
export const G7_2_ROWS_KEY = 'G7-2-rows'
export const G7_5_ROWS_KEY = 'G7-5-rows'
export const G7_10_ROWS_KEY = 'G7-10-rows'
export const G7_12_ROWS_KEY = 'G7-12-rows'
export const G7_11_ROWS_KEY = 'G7-11-rows'
export const G7_16_ROWS_KEY = 'G7-16-rows'

export interface G7ClassificationBalances {
  opening: number
  increase: number
  decrease: number
  closing: number
}

export interface G7ClassificationBundle {
  subsidiary: G7ClassificationBalances
  jointVenture: G7ClassificationBalances
  associate: G7ClassificationBalances
  impairment: G7ClassificationBalances
}

export interface G7FinancialInfoMetric {
  investeeName: string
  reportItem: string
  priorAmount: number
  currentAmount: number
}

export interface G7FormerSubsidiaryRow {
  investeeName: string
  registeredPlace: string
  businessNature: string
  holdingRatio: number | null
  votingRights: number | null
  reason: string
}

export interface G7UnrecognizedLossSourceRow {
  investeeName: string
  priorCumulative: number | null
  currentUnrecognized: number | null
  closingCumulative: number | null
}

export interface G7OwnershipImpactTransaction {
  companyName: string
  kind: 'nci' | 'partialDisposal'
  values: Record<string, number | null>
}

/** G7-14 → 披露权益法调节行 */
export interface G7EquityBridgeRow {
  investeeName: string
  shareOfNetAssets: number | null
  adjustments: number | null
  goodwill: number | null
  unrealizedInternal: number | null
  impairment: number | null
  other: number | null
  carrying: number | null
}

export interface G7DisclosureSourceBundle {
  classification: G7ClassificationBundle | null
  detail: G7DetailState | null
  basicInfo: G7BasicInfoRow[]
  financialInfo: G7FinancialInfoMetric[]
  formerSubsidiaries: G7FormerSubsidiaryRow[]
  unrecognizedLoss: G7UnrecognizedLossSourceRow[]
  ownershipImpacts: G7OwnershipImpactTransaction[]
  equityBridge: G7EquityBridgeRow[]
  sourcesHit: string[]
}

export interface G7RefreshResult {
  filledTables: string[]
  sourcesHit: string[]
  message: string
}

export interface G7DisclosureTruncation {
  source: string
  target: string
  total: number
  capacity: number
  omitted: number
  label: string
}

/** 披露取数依赖的源 checklist keys */
export const G7_DISCLOSURE_SOURCE_KEYS = new Set([
  G7_1_ADJ_KEY,
  G7_2_ROWS_KEY,
  G7_4_ROWS_KEY,
  G7_5_ROWS_KEY,
  G7_10_ROWS_KEY,
  G7_11_ROWS_KEY,
  G7_12_ROWS_KEY,
  G7_14_SECTION_KEY,
  G7_14_ROWS_KEY,
  G7_16_ROWS_KEY,
])

export const G7_SOURCE_SAVED_EVENT = 'g7:source-rows-saved'

export function emitG7SourceRowsSaved(detail: {
  projectId?: string
  wpId?: string
  itemIds: string[]
}): void {
  const itemIds = [...new Set(detail.itemIds.filter(Boolean))]
  const relevant = itemIds.filter(id => G7_DISCLOSURE_SOURCE_KEYS.has(id))
  if (!relevant.length) return
  window.dispatchEvent(new CustomEvent(G7_SOURCE_SAVED_EVENT, {
    detail: {
      projectId: detail.projectId || '',
      wpId: detail.wpId || '',
      itemIds: relevant,
      timestamp: Date.now(),
    },
  }))
}

export function collectDisclosureTruncations(
  bundle: G7DisclosureSourceBundle,
  variant: 'listed' | 'soe',
): G7DisclosureTruncation[] {
  const out: G7DisclosureTruncation[] = []
  const push = (
    source: string,
    target: string,
    label: string,
    total: number,
    capacity: number,
  ) => {
    if (total <= capacity) return
    out.push({
      source,
      target,
      total,
      capacity,
      omitted: total - capacity,
      label,
    })
  }

  const jv = bundle.basicInfo.filter(r => r.groupType === 'joint_venture')
  const assoc = bundle.basicInfo.filter(r => r.groupType === 'associate')
  const bridgeJv = bundle.equityBridge.filter(r => groupTypeOf(r.investeeName, bundle.basicInfo) === 'joint_venture')
  const bridgeAssoc = bundle.equityBridge.filter(r => groupTypeOf(r.investeeName, bundle.basicInfo) === 'associate')
  const bridgeUntyped = !bridgeJv.length && !bridgeAssoc.length ? bundle.equityBridge : []

  if (variant === 'listed') {
    push('G7-4', 'important-associate-balance', '重要联营企业', assoc.length, 3)
    push('G7-10', 'ownership-change-impact', '所有权变动交易', bundle.ownershipImpacts.length, 6)
    push('G7-14', 'important-associate-balance', '权益法调节联营', Math.max(bridgeAssoc.length, bridgeUntyped.slice(1).length), 3)
  } else {
    push('G7-4', 'important-jv-fs', '重要合营企业', jv.length, 2)
    push('G7-4', 'important-associate-fs', '重要联营企业', assoc.length, 2)
    push('G7-10', 'ownership-change-impact', '所有权变动交易', bundle.ownershipImpacts.length, 3)
    push('G7-14', 'important-associate-fs', '权益法调节联营', Math.max(bridgeAssoc.length, bridgeUntyped.slice(1).length), 2)
  }
  return out
}

export function formatTruncationHint(truncations: G7DisclosureTruncation[]): string {
  if (!truncations.length) return ''
  const parts = truncations.map(t => `${t.omitted} 家${t.label}`)
  return `另有 ${parts.join('、')} 超过披露列容量，未自动带入`
}

function n(value: unknown): number {
  const num = Number(value)
  return Number.isFinite(num) ? num : 0
}

function emptyBalances(): G7ClassificationBalances {
  return { opening: 0, increase: 0, decrease: 0, closing: 0 }
}

function sumGroupRows(rows: any[] | undefined): G7ClassificationBalances {
  const balances = emptyBalances()
  if (!Array.isArray(rows)) return balances
  for (const row of rows) {
    if (row?._isSubtotal) continue
    balances.opening += n(row.openingAdjusted ?? row.opening_adjusted)
    balances.increase += n(row.debitAmount ?? row.debit_amount)
    balances.decrease += n(row.creditAmount ?? row.credit_amount)
    balances.closing += n(row.closingAdjusted ?? row.closing_adjusted)
  }
  return balances
}

/** 解析 G7-1 审定表 remark → 分类余额 */
export function parseG71Classification(raw: unknown): G7ClassificationBundle | null {
  const parsed = parseChecklistJson(raw)
  if (!parsed || typeof parsed !== 'object') return null
  const groups = Array.isArray(parsed.groups) ? parsed.groups : []
  const byId = new Map<string, any>()
  for (const group of groups) {
    const id = String(group?.id ?? group?.groupType ?? '')
    if (id) byId.set(id, group)
  }
  return {
    subsidiary: sumGroupRows(byId.get('subsidiary')?.rows),
    jointVenture: sumGroupRows(byId.get('joint_venture')?.rows),
    associate: sumGroupRows(byId.get('associate')?.rows),
    impairment: sumGroupRows(byId.get('impairment')?.rows),
  }
}

export function parseG74BasicInfo(raw: unknown): G7BasicInfoRow[] {
  const parsed = parseChecklistJson(raw)
  const list = Array.isArray(parsed) ? parsed : parsed?.rows
  if (!Array.isArray(list)) return []
  return list.map((item, index) => normalizeG7BasicInfoRow(item as Record<string, unknown>, index))
}

function isEmptyValue(value: G7DisclosureValue | undefined): boolean {
  return value == null || value === ''
}

function writeValue(
  target: Record<string, G7DisclosureValue>,
  key: string,
  next: G7DisclosureValue,
  force: boolean,
): boolean {
  if (next == null || next === '') return false
  if (!force && !isEmptyValue(target[key])) return false
  if (target[key] === next) return false
  target[key] = next
  return true
}

function writeLabel(row: G7DisclosureRow, label: string, force: boolean): boolean {
  if (!label.trim()) return false
  if (!force && row.label.trim()) return false
  if (row.label === label) return false
  row.label = label
  return true
}

function dataSlots(rows: G7DisclosureRow[], prefix: string): G7DisclosureRow[] {
  return rows.filter(row => row.kind === 'data' && row.id.startsWith(prefix))
}

function ensureDataSlots(
  rows: G7DisclosureRow[],
  prefix: string,
  needed: number,
  insertBeforeId: string | undefined,
  makeRow: (index: number) => G7DisclosureRow,
): G7DisclosureRow[] {
  let slots = dataSlots(rows, prefix)
  while (slots.length < needed) {
    const next = makeRow(slots.length)
    const insertAt = insertBeforeId
      ? rows.findIndex(row => row.id === insertBeforeId)
      : -1
    if (insertAt >= 0) rows.splice(insertAt, 0, next)
    else rows.push(next)
    const subtotal = rows.find(row => row.id === insertBeforeId)
    if (subtotal?.sumRows && !subtotal.sumRows.includes(next.id)) {
      subtotal.sumRows.push(next.id)
    }
    slots = dataSlots(rows, prefix)
  }
  return slots
}

/** 国企：lte-classification ← G7-1 */
export function applySoeClassificationFromG71(
  rows: G7DisclosureRow[],
  classification: G7ClassificationBundle,
  force = false,
): boolean {
  const mapping: Array<[string, G7ClassificationBalances]> = [
    ['lte-sub', classification.subsidiary],
    ['lte-jv', classification.jointVenture],
    ['lte-assoc', classification.associate],
    ['lte-impairment', classification.impairment],
  ]
  let changed = false
  for (const [rowId, balances] of mapping) {
    const row = rows.find(item => item.id === rowId)
    if (!row) continue
    changed = writeValue(row.values, 'opening', balances.opening, force) || changed
    changed = writeValue(row.values, 'increase', balances.increase, force) || changed
    changed = writeValue(row.values, 'decrease', balances.decrease, force) || changed
    changed = writeValue(row.values, 'closing', balances.closing, force) || changed
  }
  return changed
}

/** 上市：subsidiary-composition ← G7-4 子公司 */
export function applyListedSubsidiaryCompositionFromG74(
  rows: G7DisclosureRow[],
  basicInfo: G7BasicInfoRow[],
  force = false,
): boolean {
  const subsidiaries = basicInfo.filter(row => row.groupType === 'subsidiary' && row.investeeName.trim())
  if (!subsidiaries.length) return false
  const slots = ensureDataSlots(
    rows,
    'subsidiary-',
    subsidiaries.length,
    undefined,
    index => ({
      id: `subsidiary-manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: '被投资单位基本信息G7-4',
    }),
  )
  let changed = false
  subsidiaries.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'principalPlace', source.principalPlace, force) || changed
    changed = writeValue(row.values, 'registeredPlace', source.registeredPlace, force) || changed
    changed = writeValue(row.values, 'businessNature', source.businessNature, force) || changed
    changed = writeValue(row.values, 'directHolding', source.directHoldingRatio, force) || changed
    changed = writeValue(row.values, 'indirectHolding', source.indirectHoldingRatio, force) || changed
    changed = writeValue(row.values, 'acquisitionMethod', source.acquisitionMethod, force) || changed
  })
  return changed
}

/** 国企：subsidiary-basic ← G7-4 子公司（投资额可补 G7-2） */
export function applySoeSubsidiaryBasicFromG74(
  rows: G7DisclosureRow[],
  basicInfo: G7BasicInfoRow[],
  detail: G7DetailState | null,
  force = false,
): boolean {
  const subsidiaries = basicInfo.filter(row => row.groupType === 'subsidiary' && row.investeeName.trim())
  if (!subsidiaries.length) return false
  const amountByName = new Map<string, number>()
  for (const row of detail?.costRows ?? []) {
    if (row.investeeName.trim()) amountByName.set(row.investeeName.trim(), row.auditedClosingAmount)
  }
  const slots = ensureDataSlots(
    rows,
    'subsidiary-basic-',
    subsidiaries.length,
    undefined,
    index => ({
      id: `subsidiary-basic-manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: '被投资单位基本信息G7-4；投资额←明细表G7-2',
    }),
  )
  let changed = false
  subsidiaries.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'level', source.level, force) || changed
    changed = writeValue(row.values, 'enterpriseType', source.enterpriseType, force) || changed
    changed = writeValue(row.values, 'registeredPlace', source.registeredPlace, force) || changed
    changed = writeValue(row.values, 'principalPlace', source.principalPlace, force) || changed
    changed = writeValue(row.values, 'businessNature', source.businessNature, force) || changed
    changed = writeValue(row.values, 'paidInCapital', source.registeredCapital, force) || changed
    changed = writeValue(row.values, 'subscribedRatio', source.directHoldingRatio, force) || changed
    changed = writeValue(row.values, 'paidInRatio', source.directHoldingRatio, force) || changed
    changed = writeValue(row.values, 'votingRights', source.votingRatio, force) || changed
    const amount = source.investmentAmount ?? amountByName.get(source.investeeName.trim()) ?? null
    changed = writeValue(row.values, 'investmentAmount', amount, force) || changed
    changed = writeValue(row.values, 'acquisitionMethod', source.acquisitionMethod, force) || changed
  })
  return changed
}

function applyEquityMovementSlots(
  rows: G7DisclosureRow[],
  equityRows: G7EquityRow[],
  prefix: string,
  subtotalId: string,
  force: boolean,
  style: 'listed' | 'soe',
): boolean {
  const sources = equityRows.filter(row => row.investeeName.trim())
  if (!sources.length) return false
  const slots = ensureDataSlots(
    rows,
    prefix,
    sources.length,
    subtotalId,
    index => ({
      id: `${prefix}manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: '明细表G7-2',
    }),
  )
  let changed = false
  sources.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    const opening = source.auditedOpeningAmount
    const addition = source.auditedCostIncrease
    const reduction = source.auditedCostDecrease
    const equityProfit = source.auditedProfitLoss
    const oci = source.auditedOci
    const otherEquity = source.auditedOtherEquity
    const dividend = source.auditedDividend
    const closing = source.auditedClosingAmount
    const other = source.auditedOtherIncrease || source.auditedOtherDecrease
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'addition', addition, force) || changed
    changed = writeValue(row.values, 'reduction', reduction, force) || changed
    changed = writeValue(row.values, 'equityProfit', equityProfit, force) || changed
    changed = writeValue(row.values, 'oci', oci, force) || changed
    changed = writeValue(row.values, 'otherEquity', otherEquity, force) || changed
    changed = writeValue(row.values, 'dividend', dividend, force) || changed
    changed = writeValue(row.values, 'other', other, force) || changed
    if (style === 'listed') {
      changed = writeValue(row.values, 'openingBook', opening, force) || changed
      changed = writeValue(row.values, 'closingBook', closing, force) || changed
    } else {
      changed = writeValue(row.values, 'investmentCost', source.initialInvestmentCost, force) || changed
      changed = writeValue(row.values, 'opening', opening, force) || changed
      changed = writeValue(row.values, 'closing', closing, force) || changed
    }
  })
  return changed
}

/** 上市：investment-movement ← G7-2 权益法行 */
export function applyListedMovementFromG72(
  rows: G7DisclosureRow[],
  detail: G7DetailState,
  force = false,
): boolean {
  const jv = detail.equityRows.filter(row => row.relationship === 'joint_venture')
  const assoc = detail.equityRows.filter(row => row.relationship === 'associate')
  let changed = applyEquityMovementSlots(rows, jv, 'joint-venture-', 'joint-venture-subtotal', force, 'listed')
  changed = applyEquityMovementSlots(rows, assoc, 'associate-', 'associate-subtotal', force, 'listed') || changed
  return changed
}

/** 国企：lte-movement ← G7-2 权益法行 */
export function applySoeMovementFromG72(
  rows: G7DisclosureRow[],
  detail: G7DetailState,
  force = false,
): boolean {
  const jv = detail.equityRows.filter(row => row.relationship === 'joint_venture')
  const assoc = detail.equityRows.filter(row => row.relationship === 'associate')
  let changed = applyEquityMovementSlots(rows, jv, 'mv-jv-', 'mv-assoc-group', force, 'soe')
  const total = rows.find(row => row.id === 'mv-total')
  if (total) {
    total.sumRows = dataSlots(rows, 'mv-').map(row => row.id)
  }
  changed = applyEquityMovementSlots(rows, assoc, 'mv-assoc-', 'mv-total', force, 'soe') || changed
  if (total) {
    total.sumRows = [...dataSlots(rows, 'mv-jv-'), ...dataSlots(rows, 'mv-assoc-')].map(row => row.id)
  }
  return changed
}

/** 上市：important-jv-associate / joint-operations ← G7-4 */
export function applyListedInvesteeNamesFromG74(
  rows: G7DisclosureRow[],
  basicInfo: G7BasicInfoRow[],
  options: { prefix: string; groups: Array<G7BasicInfoRow['groupType']>; force?: boolean },
): boolean {
  const sources = basicInfo.filter(
    row => options.groups.includes(row.groupType) && row.investeeName.trim(),
  )
  if (!sources.length) return false
  const slots = ensureDataSlots(
    rows,
    options.prefix,
    sources.length,
    undefined,
    index => ({
      id: `${options.prefix}manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: '被投资单位基本信息G7-4',
    }),
  )
  let changed = false
  sources.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    changed = writeLabel(row, source.investeeName, !!options.force) || changed
    changed = writeValue(row.values, 'principalPlace', source.principalPlace, !!options.force) || changed
    changed = writeValue(row.values, 'registeredPlace', source.registeredPlace, !!options.force) || changed
    changed = writeValue(row.values, 'businessNature', source.businessNature, !!options.force) || changed
    changed = writeValue(row.values, 'directShare', source.directHoldingRatio, !!options.force) || changed
    changed = writeValue(row.values, 'indirectShare', source.indirectHoldingRatio, !!options.force) || changed
    changed = writeValue(row.values, 'directHolding', source.directHoldingRatio, !!options.force) || changed
    changed = writeValue(row.values, 'indirectHolding', source.indirectHoldingRatio, !!options.force) || changed
    changed = writeValue(row.values, 'votingRights', source.votingRatio, !!options.force) || changed
    changed = writeValue(row.values, 'accountingMethod', source.accountingMethod, !!options.force) || changed
  })
  return changed
}

/** 国企：表决权例外表 ← G7-4 */
export function applySoeControlExceptionsFromG74(
  belowHalfRows: G7DisclosureRow[],
  aboveHalfRows: G7DisclosureRow[],
  basicInfo: G7BasicInfoRow[],
  force = false,
): boolean {
  const below = basicInfo.filter(
    row => row.groupType === 'subsidiary'
      && row.investeeName.trim()
      && row.votingRatio != null
      && row.votingRatio < 50,
  )
  const above = basicInfo.filter(
    row => (row.groupType === 'joint_venture' || row.groupType === 'associate')
      && row.investeeName.trim()
      && row.votingRatio != null
      && row.votingRatio >= 50,
  )
  let changed = false

  const fillException = (
    targetRows: G7DisclosureRow[],
    sources: G7BasicInfoRow[],
    prefix: string,
  ) => {
    if (!sources.length) return
    const slots = ensureDataSlots(
      targetRows,
      prefix,
      sources.length,
      undefined,
      index => ({
        id: `${prefix}manual-${Date.now()}-${index + 1}`,
        label: '',
        values: {},
        kind: 'data',
        source: 'G7-4 条件筛选',
      }),
    )
    sources.forEach((source, index) => {
      const row = slots[index]
      if (!row) return
      changed = writeLabel(row, source.investeeName, force) || changed
      changed = writeValue(row.values, 'subscribedRatio', source.directHoldingRatio, force) || changed
      changed = writeValue(row.values, 'votingRights', source.votingRatio, force) || changed
      changed = writeValue(row.values, 'registeredCapital', source.registeredCapital, force) || changed
      changed = writeValue(row.values, 'investmentAmount', source.investmentAmount, force) || changed
      changed = writeValue(row.values, 'level', source.level, force) || changed
      const reason = source.lessThanHalfControlReason || source.majorityNoControlReason || ''
      changed = writeValue(row.values, 'reason', reason, force) || changed
    })
  }

  fillException(belowHalfRows, below, 'control-below-half-')
  const jv = above.filter(row => row.groupType === 'joint_venture')
  const assoc = above.filter(row => row.groupType === 'associate')
  fillException(aboveHalfRows, jv, 'nc-jv-')
  fillException(aboveHalfRows, assoc, 'nc-assoc-')
  return changed
}

/** 国企：本期新纳入 ← G7-4 newlyConsolidated=是 */
export function applySoeNewlyConsolidatedFromG74(
  rows: G7DisclosureRow[],
  basicInfo: G7BasicInfoRow[],
  force = false,
): boolean {
  const sources = basicInfo.filter(
    row => row.newlyConsolidated === '是' && row.investeeName.trim(),
  )
  if (!sources.length) return false
  const slots = ensureDataSlots(
    rows,
    'new-entity-',
    sources.length,
    undefined,
    index => ({
      id: `new-entity-manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: 'G7-4「本期新增=是」',
    }),
  )
  let changed = false
  sources.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'closingNetAssets', source.endingNetAssets, force) || changed
    changed = writeValue(row.values, 'currentNetProfit', source.currentNetProfit, force) || changed
  })
  return changed
}

/** G7-5 reportItem → 披露表行标签别名 */
const G75_LABEL_ALIASES: Record<string, string[]> = {
  流动资产: ['流动资产'],
  非流动资产: ['非流动资产'],
  总资产: ['资产合计', '总资产'],
  流动负债: ['流动负债'],
  非流动负债: ['非流动负债'],
  总负债: ['负债合计', '总负债'],
  '所有者权益（净资产）': ['净资产', '所有者权益（净资产）', '所有者权益'],
  营业收入: ['营业收入'],
  净利润: ['净利润'],
  其他综合收益: ['其他综合收益'],
  综合收益总额: ['综合收益总额'],
  财务费用: ['财务费用'],
  所得税费用: ['所得税费用'],
  营业成本: ['营业成本'],
}

function normalizeReportLabel(reportItem: string): string[] {
  const key = reportItem.trim()
  return G75_LABEL_ALIASES[key] ?? [key]
}

export function parseG75FinancialInfo(raw: unknown): G7FinancialInfoMetric[] {
  const parsed = parseChecklistJson(raw)
  if (!parsed) return []
  const metrics: G7FinancialInfoMetric[] = []
  const pushRow = (row: any, fallbackName = '') => {
    const investeeName = String(row?.investeeName ?? fallbackName ?? '').trim()
    const reportItem = String(row?.reportItem ?? '').trim()
    if (!investeeName || !reportItem) return
    metrics.push({
      investeeName,
      reportItem,
      priorAmount: n(row.priorAmount),
      currentAmount: n(row.currentAmount),
    })
  }
  if (Array.isArray(parsed.groups)) {
    for (const group of parsed.groups) {
      const name = String(group?.investeeName ?? '').trim()
      for (const row of group?.rows ?? []) pushRow(row, name)
    }
  }
  const flat = Array.isArray(parsed) ? parsed : parsed.rows
  if (Array.isArray(flat)) {
    for (const row of flat) pushRow(row)
  }
  return metrics
}

export function parseG712FormerSubsidiaries(raw: unknown): G7FormerSubsidiaryRow[] {
  const parsed = parseChecklistJson(raw)
  const list = Array.isArray(parsed) ? parsed : parsed?.rows
  if (!Array.isArray(list)) return []
  return list
    .map((row: any) => ({
      investeeName: String(row.investeeName ?? '').trim(),
      registeredPlace: String(row.registeredPlace ?? '').trim(),
      businessNature: String(row.businessNature ?? '').trim(),
      holdingRatio: row.originalShareholdingRatio != null
        ? n(row.originalShareholdingRatio)
        : (row.holdingRatio != null
          ? n(row.holdingRatio)
          : (row.disposalRatio != null ? n(row.disposalRatio) : null)),
      votingRights: row.votingRatio != null ? n(row.votingRatio) : (row.votingRights != null ? n(row.votingRights) : null),
      reason: String(
        row.disposalReason
        ?? row.reason
        ?? (row.disposalDate ? `处置日 ${row.disposalDate}` : ''),
      ).trim(),
    }))
    .filter(row => row.investeeName)
}

export function parseG716UnrecognizedLoss(raw: unknown): G7UnrecognizedLossSourceRow[] {
  const parsed = parseChecklistJson(raw)
  const list = Array.isArray(parsed) ? parsed : parsed?.rows
  if (!Array.isArray(list)) return []
  return list
    .map((row: any) => {
      const investeeName = String(row.investeeName ?? '').trim()
      if (!investeeName) return null
      const current = row.currentChange != null && row.currentChange !== ''
        ? n(row.currentChange)
        : (row.unrecognizedLoss != null ? n(row.unrecognizedLoss) : null)
      const closing = row.unrecognizedLoss != null ? n(row.unrecognizedLoss) : current
      const prior = row.priorCumulative != null
        ? n(row.priorCumulative)
        : (closing != null && current != null ? Math.round((closing - current) * 100) / 100 : null)
      return {
        investeeName,
        priorCumulative: prior,
        currentUnrecognized: current,
        closingCumulative: closing,
      } as G7UnrecognizedLossSourceRow
    })
    .filter((row): row is G7UnrecognizedLossSourceRow => !!row)
}

function normalizeImpactLabel(label: string): string {
  return label.replace(/[：:\/、\s]/g, '').trim()
}

/** 从 G7-10 NCI / 不丧失控制权处置行提取披露口径金额 */
export function parseG710OwnershipImpacts(raw: unknown): G7OwnershipImpactTransaction[] {
  const { rows } = parseSubsequentPayload(raw)
  const out: G7OwnershipImpactTransaction[] = []
  for (const row of rows) {
    if (row.section === 'nci') {
      const nci = row as G7NciPurchaseRow
      const name = String(nci.companyName ?? '').trim()
      if (!name) continue
      out.push({
        companyName: name,
        kind: 'nci',
        values: {
          现金: nci.costCash,
          非现金资产的公允价值: nci.costNonCashFV,
          发行或承担的债务的账面价值: nci.costDebtBV,
          发行的权益性证券的面值: nci.costEquityFace,
          或有对价: nci.costContingent,
          购买成本处置对价合计: nci.purchaseCost,
          减按取得处置股权比例计算的子公司净资产份额: nci.shareOfNetAssets,
          减按取得处置的股权比例计算的子公司净资产份额: nci.shareOfNetAssets,
          差额: nci.equityAdjustment,
          其中调整资本公积: nci.adjCapitalReserve,
          调整资本公积: nci.adjCapitalReserve,
          调整盈余公积: nci.adjSurplusReserve,
          调整未分配利润: nci.adjRetainedEarnings,
        },
      })
    } else if (row.section === 'partialDisposal') {
      const disp = row as G7PartialDisposalRow
      const name = String(disp.companyName ?? '').trim()
      if (!name) continue
      out.push({
        companyName: name,
        kind: 'partialDisposal',
        values: {
          现金: disp.considerationCash,
          非现金资产的公允价值: disp.considerationNonCashFV,
          发行或承担的债务的账面价值: disp.considerationDebtBV,
          发行的权益性证券的面值: disp.considerationEquityFace,
          或有对价: disp.considerationContingent,
          购买成本处置对价合计: disp.consideration,
          减按取得处置股权比例计算的子公司净资产份额: disp.consolShare,
          减按取得处置的股权比例计算的子公司净资产份额: disp.consolShare,
          差额: disp.consolEquityAdj,
          其中调整资本公积: disp.adjCapitalReserve,
          调整资本公积: disp.adjCapitalReserve,
          调整盈余公积: disp.adjSurplusReserve,
          调整未分配利润: disp.adjRetainedEarnings,
        },
      })
    }
  }
  return out
}

export function applyOwnershipChangeImpactFromG710(
  rows: G7DisclosureRow[],
  transactions: G7OwnershipImpactTransaction[],
  maxCompanies: number,
  force = false,
): boolean {
  if (!transactions.length) return false
  const limited = transactions.slice(0, maxCompanies)
  let changed = false
  for (let i = 0; i < limited.length; i++) {
    const tx = limited[i]
    const colKey = `company${i + 1}`
    for (const row of rows) {
      if (row.kind && row.kind !== 'data') continue
      const key = normalizeImpactLabel(row.label)
      if (!key || key === '购买成本处置对价') continue
      const value = tx.values[key]
      if (value == null) continue
      changed = writeValue(row.values, colKey, value, force) || changed
    }
  }
  return changed
}

/** 不重要合营/联营汇总：账面价值 + 按持股比例份额 ← G7-2 / (G7-5×比例) */
export function applyAggregateSummaryFromSources(
  rows: G7DisclosureRow[],
  detail: G7DetailState | null,
  financialInfo: G7FinancialInfoMetric[],
  basicInfo: G7BasicInfoRow[],
  options: {
    excludeNames?: Iterable<string>
    jv: { carryingId: string; profitId: string; ociId: string; comprehensiveId: string }
    assoc: { carryingId: string; profitId: string; ociId: string; comprehensiveId: string }
    force?: boolean
  },
): boolean {
  const exclude = new Set(
    [...(options.excludeNames ?? [])].map(name => String(name).trim()).filter(Boolean),
  )
  const jvNames = new Set(basicInfo.filter(r => r.groupType === 'joint_venture').map(r => r.investeeName.trim()))
  const assocNames = new Set(basicInfo.filter(r => r.groupType === 'associate').map(r => r.investeeName.trim()))

  const buckets = {
    jv: { priorCarrying: 0, currentCarrying: 0, profit: 0, oci: 0, hasG72: false },
    assoc: { priorCarrying: 0, currentCarrying: 0, profit: 0, oci: 0, hasG72: false },
  }

  if (detail) {
    for (const row of detail.equityRows) {
      const name = row.investeeName.trim()
      if (!name || exclude.has(name)) continue
      const isJv = jvNames.has(name) || (!jvNames.size && row.relationship === 'joint_venture')
      const isAssoc = assocNames.has(name) || (!assocNames.size && row.relationship === 'associate')
      if (!isJv && !isAssoc) continue
      const bucket = isJv ? buckets.jv : buckets.assoc
      bucket.priorCarrying += row.auditedOpeningAmount
      bucket.currentCarrying += row.auditedClosingAmount
      bucket.profit += row.auditedProfitLoss
      bucket.oci += row.auditedOci
      bucket.hasG72 = true
    }
  }

  const writeShareFallback = (
    names: string[],
    ids: { profitId: string; ociId: string; comprehensiveId: string },
  ): boolean => {
    let changed = false
    let profitCurrent = 0
    let profitPrior = 0
    let ociCurrent = 0
    let ociPrior = 0
    let compCurrent = 0
    let compPrior = 0
    let hit = false
    for (const name of names) {
      if (exclude.has(name)) continue
      const ratioPct = (() => {
        const info = basicInfo.find(r => r.investeeName.trim() === name)
        if (!info) return null
        const total = holdingRatioTotal(info)
        return total == null ? null : total / 100
      })()
      if (ratioPct == null) continue
      const profit = metricLookup(financialInfo, [name], '净利润')
      const oci = metricLookup(financialInfo, [name], '其他综合收益')
      const comp = metricLookup(financialInfo, [name], '综合收益总额')
      if (profit) {
        profitCurrent += profit.current * ratioPct
        profitPrior += profit.prior * ratioPct
        hit = true
      }
      if (oci) {
        ociCurrent += oci.current * ratioPct
        ociPrior += oci.prior * ratioPct
        hit = true
      }
      if (comp) {
        compCurrent += comp.current * ratioPct
        compPrior += comp.prior * ratioPct
        hit = true
      } else if (profit || oci) {
        compCurrent += (profit?.current ?? 0) * ratioPct + (oci?.current ?? 0) * ratioPct
        compPrior += (profit?.prior ?? 0) * ratioPct + (oci?.prior ?? 0) * ratioPct
        hit = true
      }
    }
    if (!hit) return false
    const force = !!options.force
    const profitRow = rows.find(r => r.id === ids.profitId)
    const ociRow = rows.find(r => r.id === ids.ociId)
    const compRow = rows.find(r => r.id === ids.comprehensiveId)
    if (profitRow) {
      changed = writeValue(profitRow.values, 'current', round2(profitCurrent), force) || changed
      changed = writeValue(profitRow.values, 'prior', round2(profitPrior), force) || changed
    }
    if (ociRow) {
      changed = writeValue(ociRow.values, 'current', round2(ociCurrent), force) || changed
      changed = writeValue(ociRow.values, 'prior', round2(ociPrior), force) || changed
    }
    if (compRow) {
      changed = writeValue(compRow.values, 'current', round2(compCurrent), force) || changed
      changed = writeValue(compRow.values, 'prior', round2(compPrior), force) || changed
    }
    return changed
  }

  const writeBucket = (
    bucket: typeof buckets.jv,
    ids: { carryingId: string; profitId: string; ociId: string; comprehensiveId: string },
    names: string[],
  ): boolean => {
    let changed = false
    const force = !!options.force
    const carryingRow = rows.find(r => r.id === ids.carryingId)
    if (carryingRow && (bucket.currentCarrying || bucket.priorCarrying || force)) {
      changed = writeValue(carryingRow.values, 'current', bucket.currentCarrying, force) || changed
      changed = writeValue(carryingRow.values, 'prior', bucket.priorCarrying, force) || changed
    }
    if (bucket.hasG72) {
      const profitRow = rows.find(r => r.id === ids.profitId)
      const ociRow = rows.find(r => r.id === ids.ociId)
      const compRow = rows.find(r => r.id === ids.comprehensiveId)
      if (profitRow) {
        changed = writeValue(profitRow.values, 'current', bucket.profit, force) || changed
      }
      if (ociRow) {
        changed = writeValue(ociRow.values, 'current', bucket.oci, force) || changed
      }
      if (compRow) {
        changed = writeValue(compRow.values, 'current', round2(bucket.profit + bucket.oci), force) || changed
      }
    } else if (financialInfo.length) {
      changed = writeShareFallback(names, ids) || changed
    }
    return changed
  }

  const jvNameList = jvNames.size
    ? [...jvNames]
    : detail?.equityRows.filter(r => r.relationship === 'joint_venture').map(r => r.investeeName.trim()) ?? []
  const assocNameList = assocNames.size
    ? [...assocNames]
    : detail?.equityRows.filter(r => r.relationship === 'associate').map(r => r.investeeName.trim()) ?? []

  let changed = writeBucket(buckets.jv, options.jv, jvNameList)
  changed = writeBucket(buckets.assoc, options.assoc, assocNameList) || changed
  return changed
}

/** @deprecated 使用 applyAggregateSummaryFromSources */
export function applyAggregateCarryingFromG72(
  rows: G7DisclosureRow[],
  detail: G7DetailState | null,
  basicInfo: G7BasicInfoRow[],
  options: { jvCarryingId: string; assocCarryingId: string; force?: boolean },
): boolean {
  return applyAggregateSummaryFromSources(rows, detail, [], basicInfo, {
    jv: {
      carryingId: options.jvCarryingId,
      profitId: '',
      ociId: '',
      comprehensiveId: '',
    },
    assoc: {
      carryingId: options.assocCarryingId,
      profitId: '',
      ociId: '',
      comprehensiveId: '',
    },
    force: options.force,
  })
}

function round2(value: number): number {
  return Math.round(value * 100) / 100
}

function nullableAmount(value: unknown): number | null {
  if (value == null || value === '') return null
  const num = Number(value)
  return Number.isFinite(num) ? num : null
}

/** 解析 G7-14 权益法测算 → 披露调节行 */
export function parseG714EquityBridge(raw: unknown): G7EquityBridgeRow[] {
  const parsed = parseChecklistJson(raw)
  if (!parsed) return []
  const list = Array.isArray(parsed) ? parsed : parsed.rows
  if (!Array.isArray(list)) return []
  const adjList = Array.isArray(parsed?.netAssetAdjustments)
    ? parsed.netAssetAdjustments
    : (Array.isArray(parsed?.net_asset_adjustments) ? parsed.net_asset_adjustments : [])
  const elimByName = new Map<string, number>()
  for (const adj of adjList) {
    const name = String(adj?.investeeName ?? adj?.investee_name ?? '').trim()
    if (!name) continue
    const elim = adj?.unrealizedInternalElim ?? adj?.unrealized_internal_elim
    if (elim && typeof elim === 'object') {
      elimByName.set(name, rollforwardEnd({
        begin: n(elim.begin),
        increase: n(elim.increase),
        decrease: n(elim.decrease),
      }))
    }
  }
  return list
    .map((row: any) => {
      const investeeName = String(row.investeeName ?? row.investee_name ?? '').trim()
      if (!investeeName) return null
      const fv = nullableAmount(row.cumulativeFvAdj ?? row.cumulative_fv_adj)
      const unexplained = nullableAmount(row.unexplainedVariance ?? row.unexplained_variance)
      const other = fv != null || unexplained != null
        ? n(fv) + n(unexplained)
        : null
      return {
        investeeName,
        shareOfNetAssets: nullableAmount(row.shareOfAuditedNetAssets ?? row.share_of_audited_net_assets),
        adjustments: nullableAmount(row.netAssetShareVariance ?? row.net_asset_share_variance),
        goodwill: nullableAmount(row.goodwill),
        unrealizedInternal: elimByName.has(investeeName)
          ? elimByName.get(investeeName)!
          : nullableAmount(row.unrealizedInternalElim ?? row.unrealized_internal_elim),
        impairment: nullableAmount(row.impairment),
        other,
        carrying: nullableAmount(row.lteiBookBalance ?? row.ltei_book_balance ?? row.closingBalance),
      } as G7EquityBridgeRow
    })
    .filter((row): row is G7EquityBridgeRow => !!row)
}

const LISTED_BRIDGE_LABELS: Array<[string, keyof G7EquityBridgeRow]> = [
  ['按持股比例计算的净资产份额', 'shareOfNetAssets'],
  ['调整事项', 'adjustments'],
  ['其中：商誉', 'goodwill'],
  ['未实现内部交易损益', 'unrealizedInternal'],
  ['减值准备', 'impairment'],
  ['其他', 'other'],
  ['对合营企业权益投资的账面价值', 'carrying'],
  ['对联营企业权益投资的账面价值', 'carrying'],
]

const SOE_BRIDGE_LABELS: Array<[string, keyof G7EquityBridgeRow]> = [
  ['按持股比例计算的净资产份额', 'shareOfNetAssets'],
  ['调整事项', 'adjustments'],
  ['对合营企业权益投资的账面价值', 'carrying'],
  ['对联营企业权益投资的账面价值', 'carrying'],
]

function writeBridgeFields(
  rows: G7DisclosureRow[],
  source: G7EquityBridgeRow,
  currentKey: string,
  labels: Array<[string, keyof G7EquityBridgeRow]>,
  force: boolean,
): boolean {
  let changed = false
  for (const row of rows) {
    if (row.kind && row.kind !== 'data') continue
    const field = labels.find(([label]) => label === row.label)?.[1]
    if (!field) continue
    const value = source[field]
    if (typeof value !== 'number') continue
    changed = writeValue(row.values, currentKey, value, force) || changed
    if (row.source !== '权益法测算G7-14') {
      row.source = '权益法测算G7-14'
      changed = true
    }
  }
  return changed
}

function partitionBridgeRows(
  bridge: G7EquityBridgeRow[],
  basicInfo: G7BasicInfoRow[],
): { jv: G7EquityBridgeRow[]; assoc: G7EquityBridgeRow[] } {
  const jv: G7EquityBridgeRow[] = []
  const assoc: G7EquityBridgeRow[] = []
  for (const row of bridge) {
    const type = groupTypeOf(row.investeeName, basicInfo)
    if (type === 'joint_venture') jv.push(row)
    else if (type === 'associate') assoc.push(row)
  }
  if (!jv.length && !assoc.length) {
    // 无 G7-4 分类时：全部当作联营矩阵/合营表可分别取前若干家
    return { jv: bridge.slice(0, 1), assoc: bridge.slice(1) }
  }
  return { jv, assoc }
}

/** 上市：重要合营/联营权益法调节 ← G7-14 */
export function applyListedEquityBridgeFromG714(
  tables: Record<string, G7DisclosureRow[]>,
  bridge: G7EquityBridgeRow[],
  basicInfo: G7BasicInfoRow[],
  force = false,
): string[] {
  if (!bridge.length) return []
  const { jv, assoc } = partitionBridgeRows(bridge, basicInfo)
  const filled: string[] = []
  if (tables['important-jv-balance'] && jv[0]
    && writeBridgeFields(tables['important-jv-balance'], jv[0], 'current', LISTED_BRIDGE_LABELS, force)) {
    filled.push('important-jv-balance')
  }
  if (tables['important-associate-balance'] && assoc.length) {
    let changed = false
    assoc.slice(0, 3).forEach((source, index) => {
      changed = writeBridgeFields(
        tables['important-associate-balance'],
        source,
        `company${index + 1}Current`,
        LISTED_BRIDGE_LABELS,
        force,
      ) || changed
    })
    if (changed) filled.push('important-associate-balance')
  }
  return filled
}

/** 国企：重要合营/联营 FS 权益法调节 ← G7-14 */
export function applySoeEquityBridgeFromG714(
  tables: Record<string, G7DisclosureRow[]>,
  bridge: G7EquityBridgeRow[],
  basicInfo: G7BasicInfoRow[],
  force = false,
): string[] {
  if (!bridge.length) return []
  const { jv, assoc } = partitionBridgeRows(bridge, basicInfo)
  const filled: string[] = []
  if (tables['important-jv-fs'] && jv[0]
    && writeBridgeFields(tables['important-jv-fs'], jv[0], 'current', SOE_BRIDGE_LABELS, force)) {
    filled.push('important-jv-fs')
  }
  if (tables['important-associate-fs']) {
    const slots: Array<{ source: G7EquityBridgeRow; key: string }> = []
    if (jv[1]) slots.push({ source: jv[1], key: 'jv2Current' })
    assoc.slice(0, 2).forEach((source, index) => {
      slots.push({ source, key: `a${index + 1}Current` })
    })
    let changed = false
    for (const slot of slots) {
      changed = writeBridgeFields(
        tables['important-associate-fs'],
        slot.source,
        slot.key,
        SOE_BRIDGE_LABELS,
        force,
      ) || changed
    }
    if (changed) filled.push('important-associate-fs')
  }
  return filled
}

function groupTypeOf(name: string, basicInfo: G7BasicInfoRow[]): G7BasicInfoRow['groupType'] | null {
  const hit = basicInfo.find(row => row.investeeName.trim() === name)
  return hit?.groupType ?? null
}

function metricLookup(
  financialInfo: G7FinancialInfoMetric[],
  investeeNames: string[],
  disclosureLabel: string,
): { current: number; prior: number } | null {
  const aliases = new Set(
    Object.entries(G75_LABEL_ALIASES)
      .filter(([, labels]) => labels.includes(disclosureLabel))
      .map(([key]) => key),
  )
  aliases.add(disclosureLabel)
  let current = 0
  let prior = 0
  let hit = false
  for (const name of investeeNames) {
    for (const metric of financialInfo) {
      if (metric.investeeName !== name) continue
      if (!aliases.has(metric.reportItem) && !normalizeReportLabel(metric.reportItem).includes(disclosureLabel)) continue
      current += metric.currentAmount
      prior += metric.priorAmount
      hit = true
    }
  }
  return hit ? { current, prior } : null
}

function applyCurrentPriorMetrics(
  rows: G7DisclosureRow[],
  financialInfo: G7FinancialInfoMetric[],
  investeeNames: string[],
  force: boolean,
): boolean {
  if (!investeeNames.length) return false
  let changed = false
  for (const row of rows) {
    if (row.kind && row.kind !== 'data') continue
    const amounts = metricLookup(financialInfo, investeeNames, row.label)
    if (!amounts) continue
    changed = writeValue(row.values, 'current', amounts.current, force) || changed
    changed = writeValue(row.values, 'prior', amounts.prior, force) || changed
  }
  return changed
}

function applyMatrixMetrics(
  rows: G7DisclosureRow[],
  financialInfo: G7FinancialInfoMetric[],
  slots: Array<{ name: string; currentKey: string; priorKey: string }>,
  force: boolean,
): boolean {
  if (!slots.length) return false
  let changed = false
  for (const row of rows) {
    if (row.kind && row.kind !== 'data') continue
    for (const slot of slots) {
      const amounts = metricLookup(financialInfo, [slot.name], row.label)
      if (!amounts) continue
      changed = writeValue(row.values, slot.currentKey, amounts.current, force) || changed
      changed = writeValue(row.values, slot.priorKey, amounts.prior, force) || changed
    }
  }
  return changed
}

export function applyFinancialInfoFromG75(
  tables: Record<string, G7DisclosureRow[]>,
  financialInfo: G7FinancialInfoMetric[],
  basicInfo: G7BasicInfoRow[],
  force: boolean,
  variant: 'listed' | 'soe',
): string[] {
  if (!financialInfo.length) return []
  const jvFromBasic = basicInfo.filter(r => r.groupType === 'joint_venture').map(r => r.investeeName.trim()).filter(Boolean)
  const assocFromBasic = basicInfo.filter(r => r.groupType === 'associate').map(r => r.investeeName.trim()).filter(Boolean)
  const jv = jvFromBasic.length
    ? jvFromBasic
    : [...new Set(financialInfo.map(m => m.investeeName))].filter(name => !assocFromBasic.includes(name))
  const assoc = assocFromBasic.length
    ? assocFromBasic
    : []

  const filled: string[] = []
  if (variant === 'listed') {
    if (tables['important-jv-balance'] && applyCurrentPriorMetrics(tables['important-jv-balance'], financialInfo, jv, force)) {
      filled.push('important-jv-balance')
    }
    if (tables['important-jv-results'] && applyCurrentPriorMetrics(tables['important-jv-results'], financialInfo, jv, force)) {
      filled.push('important-jv-results')
    }
    if (tables['important-associate-balance']) {
      const slots = assoc.slice(0, 3).map((name, index) => ({
        name,
        currentKey: `company${index + 1}Current`,
        priorKey: `company${index + 1}Prior`,
      }))
      if (applyMatrixMetrics(tables['important-associate-balance'], financialInfo, slots, force)) {
        filled.push('important-associate-balance')
      }
    }
    if (tables['important-associate-results']) {
      const slots = assoc.slice(0, 3).map((name, index) => ({
        name,
        currentKey: `company${index + 1}Current`,
        priorKey: `company${index + 1}Prior`,
      }))
      if (applyMatrixMetrics(tables['important-associate-results'], financialInfo, slots, force)) {
        filled.push('important-associate-results')
      }
    }
  } else {
    if (tables['important-jv-fs'] && applyCurrentPriorMetrics(tables['important-jv-fs'], financialInfo, jv, force)) {
      filled.push('important-jv-fs')
    }
    if (tables['important-jv-pl'] && applyCurrentPriorMetrics(tables['important-jv-pl'], financialInfo, jv, force)) {
      filled.push('important-jv-pl')
    }
    if (tables['important-associate-fs'] || tables['important-associate-pl']) {
      const slots = [
        ...(jv[1] ? [{ name: jv[1], currentKey: 'jv2Current', priorKey: 'jv2Prior' }] : []),
        ...assoc.slice(0, 2).map((name, index) => ({
          name,
          currentKey: `a${index + 1}Current`,
          priorKey: `a${index + 1}Prior`,
        })),
      ]
      if (tables['important-associate-fs'] && applyMatrixMetrics(tables['important-associate-fs'], financialInfo, slots, force)) {
        filled.push('important-associate-fs')
      }
      if (tables['important-associate-pl'] && applyMatrixMetrics(tables['important-associate-pl'], financialInfo, slots, force)) {
        filled.push('important-associate-pl')
      }
    }
  }
  return filled
}

export function applyFormerSubsidiaryBasicFromG712(
  rows: G7DisclosureRow[],
  former: G7FormerSubsidiaryRow[],
  force = false,
): boolean {
  const sources = former.filter(row => row.investeeName.trim())
  if (!sources.length) return false
  const slots = ensureDataSlots(
    rows,
    'former-sub-',
    sources.length,
    undefined,
    index => ({
      id: `former-sub-manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: '处置子公司测试表G7-12',
    }),
  )
  let changed = false
  sources.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'registeredPlace', source.registeredPlace, force) || changed
    changed = writeValue(row.values, 'businessNature', source.businessNature, force) || changed
    changed = writeValue(row.values, 'holdingRatio', source.holdingRatio, force) || changed
    changed = writeValue(row.values, 'votingRights', source.votingRights, force) || changed
    changed = writeValue(row.values, 'reason', source.reason, force) || changed
  })
  return changed
}

function applyUnrecognizedLossSlots(
  rows: G7DisclosureRow[],
  sources: G7UnrecognizedLossSourceRow[],
  prefix: string,
  subtotalId: string | undefined,
  columnKeys: { prior: string; current: string; closing: string },
  force: boolean,
): boolean {
  if (!sources.length) return false
  const slots = ensureDataSlots(
    rows,
    prefix,
    sources.length,
    subtotalId,
    index => ({
      id: `${prefix}manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: '未确认投资损失测试表G7-16',
    }),
  )
  let changed = false
  sources.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, columnKeys.prior, source.priorCumulative, force) || changed
    changed = writeValue(row.values, columnKeys.current, source.currentUnrecognized, force) || changed
    changed = writeValue(row.values, columnKeys.closing, source.closingCumulative, force) || changed
  })
  return changed
}

export function applyUnrecognizedLossFromG716(
  rows: G7DisclosureRow[],
  unrecognized: G7UnrecognizedLossSourceRow[],
  basicInfo: G7BasicInfoRow[],
  options: {
    jvPrefix: string
    assocPrefix: string
    jvSubtotalId?: string
    assocSubtotalId?: string
    columnKeys: { prior: string; current: string; closing: string }
    force?: boolean
  },
): boolean {
  if (!unrecognized.length) return false
  const jvNames = new Set(basicInfo.filter(r => r.groupType === 'joint_venture').map(r => r.investeeName.trim()))
  const assocNames = new Set(basicInfo.filter(r => r.groupType === 'associate').map(r => r.investeeName.trim()))
  let jv = unrecognized.filter(r => jvNames.has(r.investeeName))
  let assoc = unrecognized.filter(r => assocNames.has(r.investeeName))
  if (!jv.length && !assoc.length) {
    // No G7-4 typing: first half → JV, rest → associate (stable fallback)
    const mid = Math.ceil(unrecognized.length / 2)
    jv = unrecognized.slice(0, mid)
    assoc = unrecognized.slice(mid)
  }
  let changed = applyUnrecognizedLossSlots(
    rows, jv, options.jvPrefix, options.jvSubtotalId, options.columnKeys, !!options.force,
  )
  changed = applyUnrecognizedLossSlots(
    rows, assoc, options.assocPrefix, options.assocSubtotalId, options.columnKeys, !!options.force,
  ) || changed
  return changed
}

function findChecklistValue(
  items: Array<{ item_id?: string; conclusion?: unknown; remark?: unknown }>,
  key: string,
): unknown {
  const item = items.find(entry => entry.item_id === key)
  if (!item) return null
  return item.remark || item.conclusion || null
}

export function buildSourceBundleFromChecklistItems(
  items: Array<{ item_id?: string; conclusion?: unknown; remark?: unknown }>,
): G7DisclosureSourceBundle {
  const sourcesHit: string[] = []
  const adjRaw = findChecklistValue(items, G7_1_ADJ_KEY)
  const classification = parseG71Classification(adjRaw)
  if (classification) sourcesHit.push('G7-1')

  const detailRaw = findChecklistValue(items, G7_2_ROWS_KEY)
  const detailParsed = parseChecklistJson(detailRaw) ?? detailRaw
  const detail = detailParsed ? normalizeG7DetailRows(detailParsed) : null
  if (detail && (detail.costRows.length || detail.equityRows.length)) sourcesHit.push('G7-2')

  const basicRaw = findChecklistValue(items, G7_4_ROWS_KEY)
  const basicInfo = parseG74BasicInfo(basicRaw)
  if (basicInfo.length) sourcesHit.push('G7-4')

  const financialInfo = parseG75FinancialInfo(findChecklistValue(items, G7_5_ROWS_KEY))
  if (financialInfo.length) sourcesHit.push('G7-5')

  let formerSubsidiaries = parseG712FormerSubsidiaries(findChecklistValue(items, G7_12_ROWS_KEY))
  if (formerSubsidiaries.length) sourcesHit.push('G7-12')
  else {
    formerSubsidiaries = parseG712FormerSubsidiaries(findChecklistValue(items, G7_11_ROWS_KEY))
    if (formerSubsidiaries.length) sourcesHit.push('G7-11')
  }

  const unrecognizedLoss = parseG716UnrecognizedLoss(findChecklistValue(items, G7_16_ROWS_KEY))
  if (unrecognizedLoss.length) sourcesHit.push('G7-16')

  const ownershipImpacts = parseG710OwnershipImpacts(findChecklistValue(items, G7_10_ROWS_KEY))
  if (ownershipImpacts.length) sourcesHit.push('G7-10')

  let equityBridge = parseG714EquityBridge(findChecklistValue(items, G7_14_SECTION_KEY))
  if (!equityBridge.length) {
    equityBridge = parseG714EquityBridge(findChecklistValue(items, G7_14_ROWS_KEY))
  }
  if (equityBridge.length) sourcesHit.push('G7-14')

  return {
    classification,
    detail,
    basicInfo,
    financialInfo,
    formerSubsidiaries,
    unrecognizedLoss,
    ownershipImpacts,
    equityBridge,
    sourcesHit,
  }
}

export function refreshListedTablesFromSources(
  tables: Record<string, G7DisclosureRow[]>,
  bundle: G7DisclosureSourceBundle,
  force = false,
): string[] {
  const filled: string[] = []
  if (bundle.detail && tables['investment-movement']) {
    if (applyListedMovementFromG72(tables['investment-movement'], bundle.detail, force)) {
      filled.push('investment-movement')
    }
  }
  if (bundle.basicInfo.length) {
    if (tables['subsidiary-composition']
      && applyListedSubsidiaryCompositionFromG74(tables['subsidiary-composition'], bundle.basicInfo, force)) {
      filled.push('subsidiary-composition')
    }
    if (tables['important-jv-associate']
      && applyListedInvesteeNamesFromG74(tables['important-jv-associate'], bundle.basicInfo, {
        prefix: 'important-jv-associate-',
        groups: ['joint_venture', 'associate'],
        force,
      })) {
      filled.push('important-jv-associate')
    }
    if (tables['joint-operations']
      && applyListedInvesteeNamesFromG74(tables['joint-operations'], bundle.basicInfo, {
        prefix: 'joint-operation-',
        groups: ['joint_operation'],
        force,
      })) {
      filled.push('joint-operations')
    }
  }
  filled.push(...applyFinancialInfoFromG75(tables, bundle.financialInfo, bundle.basicInfo, force, 'listed'))
  filled.push(...applyListedEquityBridgeFromG714(tables, bundle.equityBridge, bundle.basicInfo, force))
  if (tables['unimportant-aggregate']) {
    const jv = bundle.basicInfo.filter(r => r.groupType === 'joint_venture').map(r => r.investeeName.trim())
    const assoc = bundle.basicInfo.filter(r => r.groupType === 'associate').map(r => r.investeeName.trim())
    const exclude = [...jv.slice(0, 1), ...assoc.slice(0, 3)]
    if (applyAggregateSummaryFromSources(
      tables['unimportant-aggregate'],
      bundle.detail,
      bundle.financialInfo,
      bundle.basicInfo,
      {
        excludeNames: exclude,
        jv: {
          carryingId: 'ua-jv-carrying',
          profitId: 'ua-jv-profit',
          ociId: 'ua-jv-oci',
          comprehensiveId: 'ua-jv-comprehensive',
        },
        assoc: {
          carryingId: 'ua-assoc-carrying',
          profitId: 'ua-assoc-profit',
          ociId: 'ua-assoc-oci',
          comprehensiveId: 'ua-assoc-comprehensive',
        },
        force,
      },
    )) {
      filled.push('unimportant-aggregate')
    }
  }
  if (tables['ownership-change-impact'] && bundle.ownershipImpacts.length) {
    if (applyOwnershipChangeImpactFromG710(tables['ownership-change-impact'], bundle.ownershipImpacts, 6, force)) {
      filled.push('ownership-change-impact')
    }
  }
  if (tables['excess-losses'] && bundle.unrecognizedLoss.length) {
    if (applyUnrecognizedLossFromG716(tables['excess-losses'], bundle.unrecognizedLoss, bundle.basicInfo, {
      jvPrefix: 'el-jv-',
      assocPrefix: 'el-assoc-',
      jvSubtotalId: 'el-jv-subtotal',
      assocSubtotalId: 'el-assoc-subtotal',
      columnKeys: {
        prior: 'priorUnrecognised',
        current: 'currentUnrecognised',
        closing: 'closingUnrecognised',
      },
      force,
    })) {
      filled.push('excess-losses')
    }
  }
  return [...new Set(filled)]
}

export function refreshSoeTablesFromSources(
  tables: Record<string, G7DisclosureRow[]>,
  bundle: G7DisclosureSourceBundle,
  force = false,
): string[] {
  const filled: string[] = []
  if (bundle.classification && tables['lte-classification']) {
    if (applySoeClassificationFromG71(tables['lte-classification'], bundle.classification, force)) {
      filled.push('lte-classification')
    }
  }
  if (bundle.detail && tables['lte-movement']) {
    if (applySoeMovementFromG72(tables['lte-movement'], bundle.detail, force)) {
      filled.push('lte-movement')
    }
  }
  if (bundle.basicInfo.length) {
    if (tables['subsidiary-basic']
      && applySoeSubsidiaryBasicFromG74(tables['subsidiary-basic'], bundle.basicInfo, bundle.detail, force)) {
      filled.push('subsidiary-basic')
    }
    if (tables['control-below-half'] && tables['no-control-above-half']
      && applySoeControlExceptionsFromG74(
        tables['control-below-half'],
        tables['no-control-above-half'],
        bundle.basicInfo,
        force,
      )) {
      filled.push('control-below-half', 'no-control-above-half')
    }
    if (tables['newly-consolidated']
      && applySoeNewlyConsolidatedFromG74(tables['newly-consolidated'], bundle.basicInfo, force)) {
      filled.push('newly-consolidated')
    }
  }
  filled.push(...applyFinancialInfoFromG75(tables, bundle.financialInfo, bundle.basicInfo, force, 'soe'))
  filled.push(...applySoeEquityBridgeFromG714(tables, bundle.equityBridge, bundle.basicInfo, force))
  if (tables['insignificant-aggregate']) {
    const jv = bundle.basicInfo.filter(r => r.groupType === 'joint_venture').map(r => r.investeeName.trim())
    const assoc = bundle.basicInfo.filter(r => r.groupType === 'associate').map(r => r.investeeName.trim())
    const exclude = [...jv.slice(0, 2), ...assoc.slice(0, 2)]
    if (applyAggregateSummaryFromSources(
      tables['insignificant-aggregate'],
      bundle.detail,
      bundle.financialInfo,
      bundle.basicInfo,
      {
        excludeNames: exclude,
        jv: {
          carryingId: 'agg-jv-carrying',
          profitId: 'agg-jv-profit',
          ociId: 'agg-jv-oci',
          comprehensiveId: 'agg-jv-comprehensive',
        },
        assoc: {
          carryingId: 'agg-assoc-carrying',
          profitId: 'agg-assoc-profit',
          ociId: 'agg-assoc-oci',
          comprehensiveId: 'agg-assoc-comprehensive',
        },
        force,
      },
    )) {
      filled.push('insignificant-aggregate')
    }
  }
  if (tables['ownership-change-impact'] && bundle.ownershipImpacts.length) {
    if (applyOwnershipChangeImpactFromG710(tables['ownership-change-impact'], bundle.ownershipImpacts, 3, force)) {
      filled.push('ownership-change-impact')
    }
  }
  if (tables['former-subsidiary-basic'] && bundle.formerSubsidiaries.length) {
    if (applyFormerSubsidiaryBasicFromG712(tables['former-subsidiary-basic'], bundle.formerSubsidiaries, force)) {
      filled.push('former-subsidiary-basic')
    }
  }
  if (tables['unrecognized-losses'] && bundle.unrecognizedLoss.length) {
    if (applyUnrecognizedLossFromG716(tables['unrecognized-losses'], bundle.unrecognizedLoss, bundle.basicInfo, {
      jvPrefix: 'ul-jv-',
      assocPrefix: 'ul-assoc-',
      jvSubtotalId: 'ul-jv-subtotal',
      assocSubtotalId: 'ul-assoc-subtotal',
      columnKeys: {
        prior: 'priorCumulative',
        current: 'currentUnrecognized',
        closing: 'closingCumulative',
      },
      force,
    })) {
      filled.push('unrecognized-losses')
    }
  }
  return [...new Set(filled)]
}

type ChecklistItem = { item_id?: string; conclusion?: unknown; remark?: unknown }

async function fetchChecklistItems(wpId: string): Promise<ChecklistItem[]> {
  const response = await api.get(
    `/api/workpapers/${wpId}/checklist-responses`,
    { _silent: true } as any,
  )
  return Array.isArray(response) ? response : (response as any)?.data ?? []
}

function mergeChecklistItems(target: ChecklistItem[], extra: ChecklistItem[]): ChecklistItem[] {
  const map = new Map<string, ChecklistItem>()
  for (const item of [...target, ...extra]) {
    const id = String(item.item_id || '')
    if (!id) continue
    const existing = map.get(id)
    if (!existing) {
      map.set(id, item)
      continue
    }
    // 本底稿已有非空载荷时，不让兄弟底稿覆盖
    const existingHas = !!(existing.remark || existing.conclusion)
    const nextHas = !!(item.remark || item.conclusion)
    if (!existingHas && nextHas) map.set(id, item)
  }
  return [...map.values()]
}

/** 加载 G7-1/2/4/5/10/12/14/16 源数据：本底稿 + cycle_workpapers 兄弟底稿。 */
export async function loadG7DisclosureSources(options: {
  wpId: string
  htmlData?: Record<string, unknown> | null
}): Promise<G7DisclosureSourceBundle> {
  let items = await fetchChecklistItems(options.wpId)
  const cycle = options.htmlData?.cycle_workpapers
  if (Array.isArray(cycle)) {
    for (const entry of cycle) {
      const siblingId = String((entry as any)?.wp_id || '')
      if (!siblingId || siblingId === options.wpId) continue
      try {
        const siblingItems = await fetchChecklistItems(siblingId)
        items = mergeChecklistItems(items, siblingItems)
      } catch {
        // 兄弟底稿不可用时跳过
      }
    }
  }
  const bundle = buildSourceBundleFromChecklistItems(items)
  const html = options.htmlData ?? {}

  // htmlData 兜底（导入种子 / 未写 checklist 的场景）
  if (!bundle.classification) {
    const fromHtml = parseG71Classification(html.adjudication ?? html.adjudicationData ?? null)
    if (fromHtml) {
      bundle.classification = fromHtml
      bundle.sourcesHit.push('G7-1')
    }
  }
  if (!bundle.detail || !(bundle.detail.costRows.length || bundle.detail.equityRows.length)) {
    const detailRaw = (html.detail as any)?.rows ?? html.detail ?? html.g72Rows ?? null
    const fromHtml = detailRaw ? normalizeG7DetailRows(detailRaw) : null
    if (fromHtml && (fromHtml.costRows.length || fromHtml.equityRows.length)) {
      bundle.detail = fromHtml
      bundle.sourcesHit.push('G7-2')
    }
  }
  if (!bundle.basicInfo.length) {
    const fromHtml = parseG74BasicInfo(html.basicInfo ?? html.basic_info ?? null)
    if (fromHtml.length) {
      bundle.basicInfo = fromHtml
      bundle.sourcesHit.push('G7-4')
    }
  }
  if (!bundle.financialInfo.length) {
    const fromHtml = parseG75FinancialInfo(html.financialInfo ?? null)
    if (fromHtml.length) {
      bundle.financialInfo = fromHtml
      bundle.sourcesHit.push('G7-5')
    }
  }
  if (!bundle.ownershipImpacts.length) {
    const fromHtml = parseG710OwnershipImpacts(
      html.subsequentMeasurement
      ?? html.subsequent_measurement
      ?? html.subsequentRows
      ?? html.subsequent
      ?? html.g710Rows
      ?? null,
    )
    if (fromHtml.length) {
      bundle.ownershipImpacts = fromHtml
      bundle.sourcesHit.push('G7-10')
    }
  }
  if (!bundle.equityBridge.length) {
    const fromHtml = parseG714EquityBridge(
      html.equityMethodCalc ?? html.equity_method_calc ?? html.g714Rows ?? html.g714 ?? null,
    )
    if (fromHtml.length) {
      bundle.equityBridge = fromHtml
      bundle.sourcesHit.push('G7-14')
    }
  }
  if (!bundle.unrecognizedLoss.length) {
    const fromHtml = parseG716UnrecognizedLoss(html.unrecognizedLoss ?? null)
    if (fromHtml.length) {
      bundle.unrecognizedLoss = fromHtml
      bundle.sourcesHit.push('G7-16')
    }
  }
  if (!bundle.formerSubsidiaries.length) {
    const pkg = html.disposalPackage as any
    const single = html.disposalSingle as any
    const fromHtml = parseG712FormerSubsidiaries(pkg ?? single ?? null)
    if (fromHtml.length) {
      bundle.formerSubsidiaries = fromHtml
      bundle.sourcesHit.push(pkg ? 'G7-12' : 'G7-11')
    }
  }
  return bundle
}
