/**
 * G7 附注披露跨底稿取数。
 *
 * 优先从当前底稿 checklist_responses 读取 G7-1/2/4/5/8/9/10/11·12/14/16/17；
 * 若缺键，再尝试 cycle_workpapers 中的同循环兄弟底稿。
 */
import { api } from '@/services/apiProxy'
import {
  G7_4_ROWS_KEY,
  G7_14_ROWS_KEY,
  G7_14_SECTION_KEY,
  G7_17_ROWS_KEY,
  G7_17_SECTION_KEY,
  parseChecklistJson,
} from './g7EquityMethodCrossSheet'
import {
  buildG7ControlConclusion,
  listG7ControlDecisions,
} from './g7ControlJudgmentModel'
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
export const G7_6_ROWS_KEY = 'G7-6-rows'
export const G7_7_CONTROL_KEY = 'G7-7-control-judgment-data'
export const G7_7_CONCLUSION_KEY = 'G7-7-control-judgment-audit-conclusion'
export const G7_8_ROWS_KEY = 'G7-8-rows'
export const G7_9_ROWS_KEY = 'G7-9-rows'
export const G7_10_ROWS_KEY = 'G7-10-rows'
export const G7_12_ROWS_KEY = 'G7-12-rows'
export const G7_11_ROWS_KEY = 'G7-11-rows'
export const G7_16_ROWS_KEY = 'G7-16-rows'

/**
 * 超额亏损分担额表的数据列 key（listed / soe **共用一套**）。
 *
 * 🔴 单一真源：改造前两变体各写一套字面量 —— listed 用英式 `priorUnrecognised` /
 * `currentUnrecognised` / `closingUnrecognised`，soe 用美式 `priorCumulative` /
 * `currentUnrecognized` / `closingCumulative`。同一张披露表在两变体下列语义完全相同，
 * 分两套拼写没有业务依据，只会让 seed 侧被迫也维护两份（G7 列对齐 spec C 类偏差之一）。
 *
 * 收敛到**美式**的依据：美式是平台主流（`g7UnrecognizedLossModel` /
 * `useG7EquityMethodFormData` / `G7TabUnrecognizedLoss.vue` / J3 / G6 共 40+ 处引用），
 * 英式仅 listed 披露这 3 列在用。改名零数据风险 —— 量化闸
 * （`diagnose_g7_seed_key_impact.py`）实测 listed `七、1` 全章节
 * `SAFE_TO_RENAME_SEED`（该章节记录均无 `sub_table_data`，从未推送过）。
 */
export const G7_EXCESS_LOSS_KEYS = {
  prior: 'priorCumulative',
  current: 'currentUnrecognized',
  closing: 'closingCumulative',
} as const

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
  /** 叙述用：丧失控制权日 / 依据 / 剩余股权重计量（G7-12） */
  lossOfControlDate?: string
  lossOfControlBasis?: string
  residualFairValue?: number | null
  remeasurementGain?: number | null
  remainingShareholdingRatio?: number | null
  residualFairValueMethod?: string
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

/** G7-17 减值测试 → 披露/勾稽源 */
export interface G717ImpairmentSourceRow {
  investeeName: string
  impairmentAmount: number
  openingImpairment: number
  hasImpairmentSign?: boolean
  bookValue?: number | null
  recoverableAmount?: number | null
  fvLessDisposalCost?: number | null
  valueInUse?: number | null
}

/** G7-8 同控合并 → 披露行 */
export interface G78CommonControlSourceRow {
  investeeName: string
  consolidationDate: string
  bookNetAssets: number | null
  consideration: number | null
  ultimateController: string
  basisNote: string
}

/** G7-9 非同控合并 → 披露行 */
export interface G79NonCommonControlSourceRow {
  investeeName: string
  purchaseDate: string
  purchaseDateBasis: string
  preHolding: number | null
  atCombinationHolding: number | null
  fvIdentifiable: number | null
  fvMethod: string
  consideration: number | null
  goodwill: number | null
  notes: string
}

/** G7-6 会计政策不一致 → 披露叙述草稿 */
export interface G7PolicyDifferenceSourceRow {
  investeeName: string
  policyItem: string
  adjustmentAmount: number | null
  adjustmentNote: string
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
  impairmentTests?: G717ImpairmentSourceRow[]
  commonControlMergers?: G78CommonControlSourceRow[]
  nonCommonControlMergers?: G79NonCommonControlSourceRow[]
  policyDifferences?: G7PolicyDifferenceSourceRow[]
  /** G7-7 控制判断叙述草稿（综合结论或决策摘要） */
  controlJudgmentNarrative?: string
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
  G7_6_ROWS_KEY,
  G7_7_CONTROL_KEY,
  G7_8_ROWS_KEY,
  G7_9_ROWS_KEY,
  G7_10_ROWS_KEY,
  G7_11_ROWS_KEY,
  G7_12_ROWS_KEY,
  G7_14_SECTION_KEY,
  G7_14_ROWS_KEY,
  G7_16_ROWS_KEY,
  G7_17_SECTION_KEY,
  G7_17_ROWS_KEY,
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

  const minoritySubs = minoritySubsidiarySources(bundle.basicInfo)

  if (variant === 'listed') {
    push('G7-4', 'important-associate-balance', '重要联营企业', assoc.length, 3)
    push('G7-4', 'important-minority-subsidiaries', '重要非全资子公司', minoritySubs.length, 5)
    push('G7-10', 'ownership-change-impact', '所有权变动交易', bundle.ownershipImpacts.length, 6)
    push('G7-14', 'important-associate-balance', '权益法调节联营', Math.max(bridgeAssoc.length, bridgeUntyped.slice(1).length), 3)
  } else {
    push('G7-4', 'important-jv-fs', '重要合营企业', jv.length, 2)
    push('G7-4', 'important-associate-fs', '重要联营企业', assoc.length, 2)
    push('G7-4', 'minority-financials', '重要非全资子公司', minoritySubs.length, 5)
    push('G7-11/12', 'former-subsidiary-position', '出售日子公司财务状况', bundle.formerSubsidiaries.length, 2)
    push('G7-11/12', 'former-subsidiary-results', '出售日子公司经营成果', bundle.formerSubsidiaries.length, 5)
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

/** 国企：lte-classification 减值行 ← G7-17（优先于仅 G7-1 空壳） */
export function applySoeImpairmentFromG717(
  rows: G7DisclosureRow[],
  tests: G717ImpairmentSourceRow[],
  force = false,
): boolean {
  if (!tests.length) return false
  const row = rows.find(item => item.id === 'lte-impairment')
  if (!row) return false
  const opening = tests.reduce((s, t) => s + n(t.openingImpairment), 0)
  const increase = tests.reduce((s, t) => s + n(t.impairmentAmount), 0)
  const closing = Math.round((opening + increase) * 100) / 100
  if (!force && opening === 0 && increase === 0) return false
  // G7-17 有测算结果时优先覆盖减值行（与「源键刷新」契约一致）
  const prefer = true
  let changed = false
  if (opening !== 0 || force) {
    changed = writeValue(row.values, 'opening', opening, prefer) || changed
  }
  changed = writeValue(row.values, 'increase', increase, prefer) || changed
  changed = writeValue(row.values, 'closing', closing, prefer) || changed
  if (changed) row.source = '减值测试G7-17'
  return changed
}

/** 解析 G7-17 减值测试行 */
export function parseG717Impairment(raw: unknown): G717ImpairmentSourceRow[] {
  const parsed = parseChecklistJson(raw) ?? raw
  if (!parsed) return []
  const list = Array.isArray(parsed)
    ? parsed
    : (Array.isArray((parsed as any).rows) ? (parsed as any).rows : [])
  if (!Array.isArray(list)) return []
  return list
    .map((row: any) => {
      const investeeName = String(row?.investeeName ?? row?.investee_name ?? '').trim()
      if (!investeeName) return null
      const signRaw = row.hasImpairmentSign ?? row.has_impairment_sign
      return {
        investeeName,
        impairmentAmount: n(row.impairmentAmount ?? row.impairment_amount),
        openingImpairment: n(row.openingImpairment ?? row.opening_impairment),
        hasImpairmentSign: signRaw === true || signRaw === '是' || signRaw === 'true' || signRaw === 1,
        bookValue: nullableMoney(row.bookValue ?? row.book_value),
        recoverableAmount: nullableMoney(row.recoverableAmount ?? row.recoverable_amount),
        fvLessDisposalCost: nullableMoney(
          row.fvLessDisposalCost ?? row.fv_less_disposal_cost ?? row.fairValueLessCosts,
        ),
        valueInUse: nullableMoney(row.valueInUse ?? row.value_in_use),
      } as G717ImpairmentSourceRow
    })
    .filter((row): row is G717ImpairmentSourceRow => !!row)
}

/** 用 G7-17 覆盖/补全权益桥减值准备列 */
export function mergeG717IntoEquityBridge(
  bridge: G7EquityBridgeRow[],
  tests: G717ImpairmentSourceRow[],
): G7EquityBridgeRow[] {
  if (!tests.length) return bridge
  const byName = new Map(tests.map(t => [t.investeeName.trim(), t]))
  const out = bridge.map((b) => {
    const t = byName.get(b.investeeName.trim())
    if (!t) return b
    return { ...b, impairment: t.impairmentAmount }
  })
  for (const t of tests) {
    if (out.some(b => b.investeeName.trim() === t.investeeName.trim())) continue
    out.push({
      investeeName: t.investeeName,
      shareOfNetAssets: null,
      adjustments: null,
      goodwill: null,
      unrealizedInternal: null,
      impairment: t.impairmentAmount,
      other: null,
      carrying: null,
    })
  }
  return out
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
  经营活动现金流量: ['经营活动现金流量', '经营活动产生的现金流量净额'],
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
  const toPercent = (v: number | null): number | null => {
    if (v == null || Number.isNaN(v)) return null
    // UI 存小数 0~1；披露附注一般用百分数
    if (Math.abs(v) <= 1) return Math.round(v * 10000) / 100
    return v
  }
  return list
    .map((row: any) => {
      const lossDate = String(row.lossOfControlDate ?? row.disposalDate ?? '').trim()
      const residualFv = nullableMoney(row.residualFairValue ?? row.lossDateResidualFV ?? row.remainingInvestmentFV)
      const remainingRatioRaw = row.remainingShareholdingRatio ?? row.remaining_shareholding_ratio
      let remainingShareholdingRatio: number | null = null
      if (remainingRatioRaw != null && remainingRatioRaw !== '') {
        const v = Number(remainingRatioRaw)
        if (Number.isFinite(v)) {
          remainingShareholdingRatio = Math.abs(v) <= 1 ? Math.round(v * 10000) / 100 : Math.round(v * 100) / 100
        }
      }
      const residualBook = nullableMoney(row.residualBookValue ?? row.residual_book_value)
      const remeasurementGain = residualFv != null && residualBook != null
        ? Math.round((residualFv - residualBook) * 100) / 100
        : nullableMoney(row.remeasurementGain ?? row.remeasurement_gain ?? row.individualRemeasurementGain)
      return {
        investeeName: String(row.investeeName ?? '').trim(),
        registeredPlace: String(row.registeredPlace ?? '').trim(),
        businessNature: String(row.businessNature ?? '').trim(),
        holdingRatio: toPercent(
          row.originalShareholdingRatio != null
            ? n(row.originalShareholdingRatio)
            : (row.holdingRatio != null ? n(row.holdingRatio) : null),
        ),
        votingRights: toPercent(
          row.votingRatio != null ? n(row.votingRatio) : (row.votingRights != null ? n(row.votingRights) : null),
        ),
        reason: String(
          row.disposalReason
          ?? row.reason
          ?? (lossDate ? `处置日 ${lossDate}` : ''),
        ).trim(),
        lossOfControlDate: lossDate,
        lossOfControlBasis: String(row.lossOfControlBasis ?? row.loss_of_control_basis ?? '').trim(),
        residualFairValue: residualFv,
        remeasurementGain,
        remainingShareholdingRatio,
        residualFairValueMethod: String(
          row.residualFairValueMethod ?? row.residual_fair_value_method ?? '',
        ).trim(),
      }
    })
    .filter(row => row.investeeName)
}

/**
 * G7-11 非一揽子处置 → 披露「本期不再纳入合并」基本信息。
 * 不用 disposalRatio 冒充持股比例（处置比例 ≠ 原持股）。
 */
export function parseG711FormerSubsidiaries(raw: unknown): G7FormerSubsidiaryRow[] {
  const parsed = parseChecklistJson(raw)
  const list = Array.isArray(parsed) ? parsed : parsed?.rows
  if (!Array.isArray(list)) return []
  const toPercent = (v: number | null): number | null => {
    if (v == null || Number.isNaN(v)) return null
    if (Math.abs(v) <= 1) return Math.round(v * 10000) / 100
    return v
  }
  return list
    .map((row: any) => {
      const name = String(row.investeeName ?? '').trim()
      if (!name) return null
      const date = String(row.disposalDate ?? row.lossOfControlDate ?? '').trim()
      const ratio = row.disposalRatio != null ? n(row.disposalRatio) : null
      const ratioPct = ratio != null ? toPercent(ratio) : null
      const reasonParts = [
        date ? `处置日 ${date}` : '',
        ratioPct != null ? `处置比例 ${ratioPct}%` : '',
        String(row.auditConclusion ?? row.reason ?? '').trim(),
      ].filter(Boolean)
      return {
        investeeName: name,
        registeredPlace: String(row.registeredPlace ?? '').trim(),
        businessNature: String(row.businessNature ?? '').trim(),
        // 无原持股字段时不回填 holdingRatio，避免把处置比例误作持股
        holdingRatio: row.originalShareholdingRatio != null
          ? toPercent(n(row.originalShareholdingRatio))
          : (row.holdingRatio != null ? toPercent(n(row.holdingRatio)) : null),
        votingRights: toPercent(
          row.votingRatio != null ? n(row.votingRatio) : (row.votingRights != null ? n(row.votingRights) : null),
        ),
        reason: reasonParts.join('；'),
      } as G7FormerSubsidiaryRow
    })
    .filter((row): row is G7FormerSubsidiaryRow => !!row)
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
          : nullableAmount(
            row.unrealizedInternalElim
            ?? row.unrealized_internal_elim
            // G7-15 同步写入的「内部交易抵销」列
            ?? row.internalTransactionAdj
            ?? row.internal_transaction_adj,
          ),
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
  sourceLabel = '处置子公司测试表G7-12',
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
      source: sourceLabel,
    }),
  )
  let changed = false
  sources.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    if (!row.source || force) row.source = sourceLabel
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


/** 小数持股 → 披露百分数；已是百分数则保持 */
function ratioToPercentDisplay(raw: unknown): number | null {
  if (raw == null || raw === '') return null
  const v = Number(raw)
  if (!Number.isFinite(v)) return null
  if (Math.abs(v) <= 1.0000001) return Math.round(v * 10000) / 100
  return Math.round(v * 100) / 100
}

function nullableMoney(raw: unknown): number | null {
  if (raw == null || raw === '') return null
  const v = Number(raw)
  return Number.isFinite(v) ? Math.round(v * 100) / 100 : null
}

/** 解析 G7-8 同控初始计量 → 披露用合并行 */
export function parseG78CommonControlMergers(raw: unknown): G78CommonControlSourceRow[] {
  const parsed = parseChecklistJson(raw) ?? raw
  const list = Array.isArray(parsed)
    ? parsed
    : (Array.isArray((parsed as any)?.rows) ? (parsed as any).rows : [])
  if (!Array.isArray(list)) return []
  const out: G78CommonControlSourceRow[] = []
  for (const row of list) {
    if (String(row?.section || '') !== 'merger') continue
    const investeeName = String(row?.investeeName ?? row?.investee_name ?? '').trim()
    if (!investeeName) continue
    const notes: string[] = []
    const policy = String(row?.accountingPolicyConsistent ?? '').trim()
    if (policy) notes.push(`会计政策一致：${policy}`)
    const policyNote = String(row?.accountingPolicyNote ?? '').trim()
    if (policyNote) notes.push(policyNote)
    const treatment = String(row?.adjustmentTreatment ?? '').trim()
    if (treatment) notes.push(`差额处理：${treatment}`)
    const idx = String(row?.indexRef ?? '').trim()
    if (idx) notes.push(`索引：${idx}`)
    out.push({
      investeeName,
      consolidationDate: String(row?.acquisitionDate ?? row?.acquisition_date ?? '').trim(),
      bookNetAssets: nullableMoney(row?.ownerEquityBookValue ?? row?.owner_equity_book_value),
      consideration: nullableMoney(row?.totalConsideration ?? row?.total_consideration),
      ultimateController: String(row?.finalController ?? row?.final_controller ?? '').trim(),
      basisNote: notes.join('；'),
    })
  }
  return out
}

/** 解析 G7-9 非同控初始计量 → 披露用合并行 */
export function parseG79NonCommonControlMergers(raw: unknown): G79NonCommonControlSourceRow[] {
  const parsed = parseChecklistJson(raw) ?? raw
  const list = Array.isArray(parsed)
    ? parsed
    : (Array.isArray((parsed as any)?.rows) ? (parsed as any).rows : [])
  if (!Array.isArray(list)) return []
  const out: G79NonCommonControlSourceRow[] = []
  for (const row of list) {
    if (String(row?.section || '') !== 'merger') continue
    const investeeName = String(row?.investeeName ?? row?.investee_name ?? '').trim()
    if (!investeeName) continue
    const notes: string[] = []
    const goodwill = nullableMoney(row?.goodwill)
    if (goodwill != null && goodwill < -0.005) {
      const reviewed = String(row?.bargainPurchaseReviewed ?? '').trim()
      const amt = Math.abs(goodwill).toFixed(2)
      notes.push(reviewed ? `廉价购买利得 ${amt}（复核：${reviewed}）` : `廉价购买利得 ${amt}`)
      const bargainNote = String(row?.bargainPurchaseReviewNote ?? '').trim()
      if (bargainNote) notes.push(bargainNote)
    }
    const contingent = nullableMoney(row?.contingentConsiderationFV ?? row?.contingent_consideration_fv)
    if (contingent != null && Math.abs(contingent) > 0.005) {
      notes.push(`或有对价FV ${contingent.toFixed(2)}`)
    }
    const idx = String(row?.indexRef ?? '').trim()
    if (idx) notes.push(`索引：${idx}`)
    out.push({
      investeeName,
      purchaseDate: String(row?.acquisitionDate ?? row?.acquisition_date ?? '').trim(),
      purchaseDateBasis: String(
        row?.acquisitionDateEvidenceRef ?? row?.acquisition_date_evidence_ref ?? '',
      ).trim(),
      preHolding: null,
      atCombinationHolding: ratioToPercentDisplay(row?.ownershipRatio ?? row?.ownership_ratio),
      fvIdentifiable: nullableMoney(
        row?.acquireeIdentifiableNetAssetsFV ?? row?.acquiree_identifiable_net_assets_fv,
      ),
      fvMethod: String(row?.valuationReportRef ?? row?.valuation_report_ref ?? '').trim(),
      consideration: nullableMoney(row?.totalConsiderationFV ?? row?.total_consideration_fv),
      goodwill,
      notes: notes.join('；'),
    })
  }
  return out
}

/** 解析 G7-6「不一致」事项 → 披露政策差异草稿源 */
export function parseG76PolicyDifferences(raw: unknown): G7PolicyDifferenceSourceRow[] {
  const parsed = parseChecklistJson(raw) ?? raw
  const out: G7PolicyDifferenceSourceRow[] = []

  const pushRow = (investeeName: string, row: any) => {
    const name = String(investeeName || '').trim()
    if (!name || name === '未分组') return
    const consistent = String(row?.isConsistent ?? row?.is_consistent ?? '').trim()
    if (consistent !== '不一致') return
    const amountRaw = row?.adjustmentAmount ?? row?.adjustment_amount
    const amount = amountRaw == null || amountRaw === '' ? null : Number(amountRaw)
    out.push({
      investeeName: name,
      policyItem: String(row?.policyItem ?? row?.policy_item ?? '').trim(),
      adjustmentAmount: Number.isFinite(amount as number) ? (amount as number) : null,
      adjustmentNote: String(row?.adjustmentNote ?? row?.adjustment_note ?? '').trim(),
    })
  }

  if (parsed && typeof parsed === 'object' && Array.isArray((parsed as any).groups)) {
    for (const g of (parsed as any).groups) {
      const name = String(g?.investeeName ?? g?.investee_name ?? '').trim()
      const rows = Array.isArray(g?.rows) ? g.rows : []
      for (const r of rows) pushRow(name, r)
    }
  } else {
    const list = Array.isArray(parsed)
      ? parsed
      : (Array.isArray((parsed as any)?.rows) ? (parsed as any).rows : [])
    for (const r of list) {
      pushRow(String(r?.investeeName ?? r?.investee_name ?? ''), r)
    }
  }
  return out
}

/** 由 G7-6 不一致行生成附注叙述草稿 */
export function buildG76PolicyDifferenceNarrative(rows: G7PolicyDifferenceSourceRow[]): string {
  if (!rows.length) return ''
  const byName = new Map<string, G7PolicyDifferenceSourceRow[]>()
  for (const row of rows) {
    const list = byName.get(row.investeeName) || []
    list.push(row)
    byName.set(row.investeeName, list)
  }
  const blocks: string[] = [
    '经核对合营/联营企业会计政策，下列事项与本公司存在重大差异，已按投资方政策调整（来源 G7-6）：',
  ]
  for (const [name, items] of byName) {
    const parts = items.map((item) => {
      const bits: string[] = []
      if (item.policyItem) bits.push(item.policyItem)
      if (item.adjustmentAmount != null && Number.isFinite(item.adjustmentAmount)) {
        bits.push(`调整 ${item.adjustmentAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} 元`)
      }
      if (item.adjustmentNote) bits.push(item.adjustmentNote)
      return bits.join('，') || '政策差异'
    })
    blocks.push(`【${name}】${parts.join('；')}`)
  }
  blocks.push('上述调整已（或应）计入 G7-14「会计政策调整」列；公允价值/可辨认净资产差异见 G7-13。')
  return blocks.join('\n')
}

/** G7-7 控制判断 → 披露叙述草稿（优先综合结论，否则决策摘要） */
export function parseG77ControlJudgmentNarrative(
  controlRaw: unknown,
  conclusionRaw: unknown,
): string {
  const parsed = parseChecklistJson(controlRaw) ?? controlRaw
  const root = (parsed as any)?.controlJudgment ?? parsed
  const overallFromData = root && typeof root === 'object'
    ? String((root as any).overallConclusion ?? '').trim()
    : ''
  if (overallFromData) return overallFromData

  let conclusion = ''
  if (conclusionRaw != null && conclusionRaw !== '') {
    if (typeof conclusionRaw === 'string') {
      conclusion = conclusionRaw.trim()
    } else if (typeof conclusionRaw === 'object') {
      const obj = conclusionRaw as Record<string, unknown>
      conclusion = String(obj.conclusion ?? obj.content ?? obj.text ?? obj.remark ?? '').trim()
    }
  }
  if (conclusion) return conclusion

  const decisions = listG7ControlDecisions(controlRaw)
  return decisions
    .filter(d => d.investeeName.trim() || d.relationshipType)
    .map(d => buildG7ControlConclusion(d))
    .join('\n')
}

/** G7-5 单户单项目本期金额（无则 null） */
function g75CurrentAmount(
  financialInfo: G7FinancialInfoMetric[],
  investeeName: string,
  label: string,
): number | null {
  const amounts = metricLookup(financialInfo, [investeeName], label)
  if (!amounts) return null
  return amounts.current
}

/** 按少数股东比例分摊 G7-5 金额 */
function nciShareOf(
  financialInfo: G7FinancialInfoMetric[],
  investeeName: string,
  label: string,
  nciPercent: number | null,
): number | null {
  if (nciPercent == null || !Number.isFinite(nciPercent)) return null
  const base = g75CurrentAmount(financialInfo, investeeName, label)
  if (base == null) return null
  return Math.round(base * (nciPercent / 100) * 100) / 100
}

/** 用 G7-5 补同控表未接列（收入/净利润/经营现金流；不臆造现金净增加额） */
function enrichCommonControlPlFromG75(
  row: G7DisclosureRow,
  investeeName: string,
  financialInfo: G7FinancialInfoMetric[],
  force: boolean,
): boolean {
  if (!financialInfo.length) return false
  let changed = false
  const revenue = g75CurrentAmount(financialInfo, investeeName, '营业收入')
  const profit = g75CurrentAmount(financialInfo, investeeName, '净利润')
  const ocf = g75CurrentAmount(financialInfo, investeeName, '经营活动现金流量')
  if (revenue != null) changed = writeValue(row.values, 'revenue', revenue, force) || changed
  if (profit != null) changed = writeValue(row.values, 'netProfit', profit, force) || changed
  if (ocf != null) changed = writeValue(row.values, 'operatingCashFlow', ocf, force) || changed
  return changed
}

/** 用 G7-5 补非同控「购买日至期末」列（全期代理，有数才填） */
function enrichNonCommonControlPlFromG75(
  row: G7DisclosureRow,
  investeeName: string,
  financialInfo: G7FinancialInfoMetric[],
  force: boolean,
): boolean {
  if (!financialInfo.length) return false
  let changed = false
  const revenue = g75CurrentAmount(financialInfo, investeeName, '营业收入')
  const profit = g75CurrentAmount(financialInfo, investeeName, '净利润')
  const ocf = g75CurrentAmount(financialInfo, investeeName, '经营活动现金流量')
  if (revenue != null) changed = writeValue(row.values, 'postRevenue', revenue, force) || changed
  if (profit != null) changed = writeValue(row.values, 'postProfit', profit, force) || changed
  if (ocf != null) changed = writeValue(row.values, 'postCashFlow', ocf, force) || changed
  return changed
}

function enrichMinorityNciAmounts(
  row: G7DisclosureRow,
  investeeName: string,
  nciPercent: number | null,
  financialInfo: G7FinancialInfoMetric[],
  force: boolean,
): boolean {
  if (!financialInfo.length || nciPercent == null) return false
  let changed = false
  const profit = nciShareOf(financialInfo, investeeName, '净利润', nciPercent)
  const equity = nciShareOf(financialInfo, investeeName, '所有者权益', nciPercent)
    ?? nciShareOf(financialInfo, investeeName, '净资产', nciPercent)
  if (profit != null) changed = writeValue(row.values, 'currentProfit', profit, force) || changed
  if (equity != null) changed = writeValue(row.values, 'closingEquity', equity, force) || changed
  return changed
}

/** G7-4 → 持股/表决权差异、控制例外叙述 */
export function buildControlJudgementNarrative(
  basicInfo: G7BasicInfoRow[],
  scope: 'subsidiary' | 'jv-associate' | 'all' = 'all',
): string {
  const lines: string[] = []
  for (const row of basicInfo) {
    const name = row.investeeName.trim()
    if (!name) continue
    if (scope === 'subsidiary' && row.groupType !== 'subsidiary') continue
    if (scope === 'jv-associate'
      && row.groupType !== 'joint_venture'
      && row.groupType !== 'associate') continue
    const bits: string[] = []
    if (row.holdingVotingDifferenceReason.trim()) {
      bits.push(`持股与表决权差异：${row.holdingVotingDifferenceReason.trim()}`)
    }
    if (row.lessThanHalfControlReason.trim()) {
      bits.push(`半数以下表决权仍控制：${row.lessThanHalfControlReason.trim()}`)
    }
    if (row.majorityNoControlReason.trim()) {
      bits.push(`半数以上不控制：${row.majorityNoControlReason.trim()}`)
    }
    if (!bits.length) continue
    lines.push(`【${name}】${bits.join('；')}`)
  }
  if (!lines.length) return ''
  return ['根据被投资单位基本信息（G7-4），控制/重大影响相关判断如下：', ...lines].join('\n')
}

export function buildJointControlBasisNarrative(basicInfo: G7BasicInfoRow[]): string {
  const jvs = basicInfo.filter(r => r.groupType === 'joint_venture' && r.investeeName.trim())
  if (!jvs.length) return ''
  const lines = jvs.map((row) => {
    const bits = [`【${row.investeeName.trim()}】`]
    const holding = holdingRatioTotal(row)
    if (holding != null) bits.push(`持股合计 ${holding}%`)
    if (row.votingRatio != null) bits.push(`表决权 ${row.votingRatio}%`)
    if (row.holdingVotingDifferenceReason.trim()) bits.push(row.holdingVotingDifferenceReason.trim())
    return bits.join('；')
  })
  return ['对下列合营企业具有共同控制（来源 G7-4）：', ...lines].join('\n')
}

export function buildJointOperationBasisNarrative(basicInfo: G7BasicInfoRow[]): string {
  const ops = basicInfo.filter(r => r.groupType === 'joint_operation' && r.investeeName.trim())
  if (!ops.length) return ''
  const lines = ops.map((row) => {
    const bits = [`【${row.investeeName.trim()}】`]
    if (row.principalPlace) bits.push(`主要经营地 ${row.principalPlace}`)
    if (row.registeredPlace) bits.push(`注册地 ${row.registeredPlace}`)
    if (row.holdingVotingDifferenceReason.trim()) bits.push(row.holdingVotingDifferenceReason.trim())
    return bits.join('；')
  })
  return ['共同经营判断依据（来源 G7-4）：', ...lines].join('\n')
}

export function buildOwnershipChangeNarrative(impacts: G7OwnershipImpactTransaction[]): string {
  if (!impacts.length) return ''
  const lines = impacts.map((tx) => {
    const kindLabel = tx.kind === 'nci' ? '购买少数股权' : '不丧失控制权处置'
    const consideration = tx.values['购买成本处置对价合计']
    const diff = tx.values['差额']
    const bits = [`【${tx.companyName}】${kindLabel}`]
    if (consideration != null) bits.push(`对价合计 ${consideration}`)
    if (diff != null) bits.push(`差额 ${diff}`)
    return bits.join('；')
  })
  return ['未丧失控制权的所有者权益份额变动（来源 G7-10）：', ...lines].join('\n')
}

export function buildImpairmentMethodNarrative(tests: G717ImpairmentSourceRow[]): string {
  const relevant = tests.filter(t =>
    t.hasImpairmentSign || (t.impairmentAmount != null && Math.abs(t.impairmentAmount) > 0.005),
  )
  if (!relevant.length) return ''
  const lines = relevant.map((t) => {
    const bits = [`【${t.investeeName}】`]
    if (t.bookValue != null) bits.push(`账面价值 ${t.bookValue}`)
    if (t.recoverableAmount != null) bits.push(`可收回金额 ${t.recoverableAmount}`)
    if (t.impairmentAmount != null && Math.abs(t.impairmentAmount) > 0.005) {
      bits.push(`本期计提减值 ${t.impairmentAmount}`)
    }
    const methodBits: string[] = []
    if (t.fvLessDisposalCost != null && Math.abs(t.fvLessDisposalCost) > 0.005) {
      methodBits.push(`公允价值减处置费用净额 ${t.fvLessDisposalCost}`)
    }
    if (t.valueInUse != null && Math.abs(t.valueInUse) > 0.005) {
      methodBits.push(`预计未来现金流量现值 ${t.valueInUse}`)
    }
    if (methodBits.length) bits.push(`确定方法：${methodBits.join(' / ')}`)
    return bits.join('；')
  })
  return ['长期股权投资减值测试说明（来源 G7-17）：', ...lines].join('\n')
}

export function buildSaleDateMethodNarrative(former: G7FormerSubsidiaryRow[]): string {
  const lines = former
    .filter(r => r.investeeName.trim() && (r.lossOfControlDate || r.lossOfControlBasis))
    .map((r) => {
      const bits = [`【${r.investeeName}】`]
      if (r.lossOfControlDate) bits.push(`丧失控制权日 ${r.lossOfControlDate}`)
      if (r.lossOfControlBasis) bits.push(`依据：${r.lossOfControlBasis}`)
      return bits.join('；')
    })
  if (!lines.length) return ''
  return ['出售日/丧失控制权日确定方法（来源 G7-12/11）：', ...lines].join('\n')
}

export function buildRemainingEquityRemeasurementNarrative(former: G7FormerSubsidiaryRow[]): string {
  const lines = former
    .filter(r => r.investeeName.trim() && (
      r.residualFairValue != null
      || r.remeasurementGain != null
      || r.remainingShareholdingRatio != null
    ))
    .map((r) => {
      const bits = [`【${r.investeeName}】`]
      if (r.remainingShareholdingRatio != null) bits.push(`剩余持股 ${r.remainingShareholdingRatio}%`)
      if (r.residualFairValue != null) bits.push(`剩余股权公允价值 ${r.residualFairValue}`)
      if (r.remeasurementGain != null) bits.push(`重新计量损益 ${r.remeasurementGain}`)
      if (r.residualFairValueMethod) bits.push(`确定方法：${r.residualFairValueMethod}`)
      return bits.join('；')
    })
  if (!lines.length) return ''
  return ['丧失控制权日剩余股权公允价值及重新计量损益（来源 G7-12）：', ...lines].join('\n')
}

/** 国企：同一控制下企业合并 ← G7-8（P&L/现金流有 G7-5 时补列，不改表结构） */
export function applySoeCommonControlFromG78(
  rows: G7DisclosureRow[],
  sources: G78CommonControlSourceRow[],
  force = false,
  financialInfo: G7FinancialInfoMetric[] = [],
): boolean {
  const list = sources.filter(s => s.investeeName.trim())
  if (!list.length) return false
  const slots = ensureDataSlots(
    rows,
    'common-control-',
    list.length,
    undefined,
    index => ({
      id: `common-control-manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: '同一控制下企业合并测试表G7-8',
    }),
  )
  let changed = false
  list.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    if (!row.source || force) {
      row.source = financialInfo.length
        ? '同一控制下企业合并测试表G7-8；损益/现金流←财务信息G7-5（全期代理）'
        : '同一控制下企业合并测试表G7-8'
    }
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'consolidationDate', source.consolidationDate, force) || changed
    changed = writeValue(row.values, 'bookNetAssets', source.bookNetAssets, force) || changed
    changed = writeValue(row.values, 'consideration', source.consideration, force) || changed
    changed = writeValue(row.values, 'ultimateController', source.ultimateController, force) || changed
    changed = enrichCommonControlPlFromG75(row, source.investeeName, financialInfo, force) || changed
  })
  return changed
}

/** 国企：非同一控制下企业合并 ← G7-9 */
export function applySoeNonCommonControlFromG79(
  rows: G7DisclosureRow[],
  sources: G79NonCommonControlSourceRow[],
  force = false,
  financialInfo: G7FinancialInfoMetric[] = [],
): boolean {
  const list = sources.filter(s => s.investeeName.trim())
  if (!list.length) return false
  const slots = ensureDataSlots(
    rows,
    'non-common-control-',
    list.length,
    undefined,
    index => ({
      id: `non-common-control-manual-${Date.now()}-${index + 1}`,
      label: '',
      values: {},
      kind: 'data',
      source: '非同一控制下企业合并测试表G7-9',
    }),
  )
  let changed = false
  list.forEach((source, index) => {
    const row = slots[index]
    if (!row) return
    if (!row.source || force) {
      row.source = financialInfo.length
        ? '非同一控制下企业合并测试表G7-9；购买日至期末←财务信息G7-5（全期代理）'
        : '非同一控制下企业合并测试表G7-9'
    }
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'purchaseDate', source.purchaseDate, force) || changed
    changed = writeValue(row.values, 'purchaseDateBasis', source.purchaseDateBasis, force) || changed
    changed = writeValue(row.values, 'preHolding', source.preHolding, force) || changed
    changed = writeValue(row.values, 'atCombinationHolding', source.atCombinationHolding, force) || changed
    changed = writeValue(row.values, 'fvIdentifiable', source.fvIdentifiable, force) || changed
    changed = writeValue(row.values, 'fvMethod', source.fvMethod, force) || changed
    changed = writeValue(row.values, 'consideration', source.consideration, force) || changed
    changed = writeValue(row.values, 'goodwill', source.goodwill, force) || changed
    changed = enrichNonCommonControlPlFromG75(row, source.investeeName, financialInfo, force) || changed
  })
  return changed
}

function appendNarrativeIfEmpty(
  texts: Record<string, string> | undefined,
  key: string,
  draft: string,
  force: boolean,
): boolean {
  if (!texts || !draft.trim()) return false
  const prev = String(texts[key] || '').trim()
  if (!force && prev) return false
  if (prev === draft.trim()) return false
  texts[key] = force && prev && !prev.includes(draft.trim())
    ? `${prev}\n${draft.trim()}`
    : draft.trim()
  return true
}

function minoritySubsidiarySources(basicInfo: G7BasicInfoRow[]): G7BasicInfoRow[] {
  return basicInfo.filter((row) => {
    if (row.groupType !== 'subsidiary') return false
    if (!row.investeeName.trim()) return false
    const holding = holdingRatioTotal(row)
    return holding != null && holding > 0 && holding < 99.999
  })
}

/** 国企：重要非全资子公司少数股东表 ← G7-4；损益/权益有 G7-5 时按 NCI% 分摊 */
export function applySoeMinorityShareholdersFromG74(
  rows: G7DisclosureRow[],
  basicInfo: G7BasicInfoRow[],
  force = false,
  financialInfo: G7FinancialInfoMetric[] = [],
): boolean {
  const sources = minoritySubsidiarySources(basicInfo)
  if (!sources.length) return false
  const slots = ensureDataSlots(
    rows,
    'minority-',
    sources.length,
    undefined,
    index => ({
      id: `minority-manual-${Date.now()}-${index + 1}`,
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
    if (!row.source || force) {
      row.source = financialInfo.length
        ? '被投资单位基本信息G7-4；少数股东损益/权益←财务信息G7-5×NCI%'
        : '被投资单位基本信息G7-4'
    }
    const holding = holdingRatioTotal(source)
    const nci = holding != null ? Math.round((100 - holding) * 100) / 100 : null
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'holdingRatio', nci, force) || changed
    changed = enrichMinorityNciAmounts(row, source.investeeName, nci, financialInfo, force) || changed
  })
  return changed
}

/** 上市：重要的非全资子公司 ← G7-4（少数股东持股比例=100−持股合计） */
export function applyListedMinoritySubsidiariesFromG74(
  rows: G7DisclosureRow[],
  basicInfo: G7BasicInfoRow[],
  force = false,
  financialInfo: G7FinancialInfoMetric[] = [],
): boolean {
  const sources = minoritySubsidiarySources(basicInfo)
  if (!sources.length) return false
  const slots = ensureDataSlots(
    rows,
    'minority-subsidiary-',
    sources.length,
    undefined,
    index => ({
      id: `minority-subsidiary-manual-${Date.now()}-${index + 1}`,
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
    if (!row.source || force) {
      row.source = financialInfo.length
        ? '被投资单位基本信息G7-4；少数股东损益/权益←财务信息G7-5×NCI%'
        : '被投资单位基本信息G7-4'
    }
    const holding = holdingRatioTotal(source)
    const nci = holding != null ? Math.round((100 - holding) * 100) / 100 : null
    changed = writeLabel(row, source.investeeName, force) || changed
    changed = writeValue(row.values, 'holdingRatio', nci, force) || changed
    changed = enrichMinorityNciAmounts(row, source.investeeName, nci, financialInfo, force) || changed
  })
  return changed
}

const LISTED_MINORITY_BALANCE_FIELDS: Array<{ key: string; label: string }> = [
  { key: 'currentAssets', label: '流动资产' },
  { key: 'nonCurrentAssets', label: '非流动资产' },
  { key: 'totalAssets', label: '资产合计' },
  { key: 'currentLiabilities', label: '流动负债' },
  { key: 'nonCurrentLiabilities', label: '非流动负债' },
  { key: 'totalLiabilities', label: '负债合计' },
]

const LISTED_MINORITY_RESULT_FIELDS: Array<{ key: string; label: string; which: 'current' | 'prior' }> = [
  { key: 'currentRevenue', label: '营业收入', which: 'current' },
  { key: 'currentProfit', label: '净利润', which: 'current' },
  { key: 'currentComprehensive', label: '综合收益总额', which: 'current' },
  { key: 'currentCashFlow', label: '经营活动现金流量', which: 'current' },
  { key: 'priorRevenue', label: '营业收入', which: 'prior' },
  { key: 'priorProfit', label: '净利润', which: 'prior' },
  { key: 'priorComprehensive', label: '综合收益总额', which: 'prior' },
  { key: 'priorCashFlow', label: '经营活动现金流量', which: 'prior' },
]

/**
 * 上市：重要非全资子公司主要财务信息（期末/期初/发生额三表）← G7-5。
 * 行=公司（与 important-minority-subsidiaries 对齐），列=报表项目金额。
 */
export function applyListedMinorityFsFromG75(
  tables: {
    closing?: G7DisclosureRow[]
    opening?: G7DisclosureRow[]
    results?: G7DisclosureRow[]
  },
  financialInfo: G7FinancialInfoMetric[],
  basicInfo: G7BasicInfoRow[],
  force = false,
): string[] {
  if (!financialInfo.length) return []
  const names = minoritySubsidiarySources(basicInfo).map(r => r.investeeName.trim()).slice(0, 5)
  if (!names.length) return []
  const filled: string[] = []
  const sourceTag = '财务信息G7-5'

  const fillBalance = (
    rows: G7DisclosureRow[] | undefined,
    prefix: string,
    which: 'current' | 'prior',
    tableId: string,
  ) => {
    if (!rows) return
    const slots = ensureDataSlots(
      rows,
      prefix,
      names.length,
      undefined,
      index => ({
        id: `${prefix}manual-${Date.now()}-${index + 1}`,
        label: '',
        values: {},
        kind: 'data',
        source: sourceTag,
      }),
    )
    let changed = false
    names.forEach((name, index) => {
      const row = slots[index]
      if (!row) return
      if (!row.source || force) row.source = sourceTag
      changed = writeLabel(row, name, force) || changed
      for (const field of LISTED_MINORITY_BALANCE_FIELDS) {
        const amounts = metricLookup(financialInfo, [name], field.label)
        if (!amounts) continue
        const value = which === 'current' ? amounts.current : amounts.prior
        changed = writeValue(row.values, field.key, value, force) || changed
      }
    })
    if (changed) filled.push(tableId)
  }

  fillBalance(tables.closing, 'minority-closing-', 'current', 'minority-closing-balance')
  fillBalance(tables.opening, 'minority-opening-', 'prior', 'minority-opening-balance')

  if (tables.results) {
    const slots = ensureDataSlots(
      tables.results,
      'minority-results-',
      names.length,
      undefined,
      index => ({
        id: `minority-results-manual-${Date.now()}-${index + 1}`,
        label: '',
        values: {},
        kind: 'data',
        source: sourceTag,
      }),
    )
    let changed = false
    names.forEach((name, index) => {
      const row = slots[index]
      if (!row) return
      if (!row.source || force) row.source = sourceTag
      changed = writeLabel(row, name, force) || changed
      for (const field of LISTED_MINORITY_RESULT_FIELDS) {
        const amounts = metricLookup(financialInfo, [name], field.label)
        if (!amounts) continue
        const value = field.which === 'current' ? amounts.current : amounts.prior
        changed = writeValue(row.values, field.key, value, force) || changed
      }
    })
    if (changed) filled.push('minority-results')
  }

  return filled
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
  let formerSource: 'G7-12' | 'G7-11' | null = formerSubsidiaries.length ? 'G7-12' : null
  if (!formerSubsidiaries.length) {
    formerSubsidiaries = parseG711FormerSubsidiaries(findChecklistValue(items, G7_11_ROWS_KEY))
    if (formerSubsidiaries.length) formerSource = 'G7-11'
  }
  if (formerSource) sourcesHit.push(formerSource)

  const unrecognizedLoss = parseG716UnrecognizedLoss(findChecklistValue(items, G7_16_ROWS_KEY))
  if (unrecognizedLoss.length) sourcesHit.push('G7-16')

  const ownershipImpacts = parseG710OwnershipImpacts(findChecklistValue(items, G7_10_ROWS_KEY))
  if (ownershipImpacts.length) sourcesHit.push('G7-10')

  let equityBridge = parseG714EquityBridge(findChecklistValue(items, G7_14_SECTION_KEY))
  if (!equityBridge.length) {
    equityBridge = parseG714EquityBridge(findChecklistValue(items, G7_14_ROWS_KEY))
  }
  if (equityBridge.length) sourcesHit.push('G7-14')

  let impairmentTests = parseG717Impairment(findChecklistValue(items, G7_17_ROWS_KEY))
  if (!impairmentTests.length) {
    impairmentTests = parseG717Impairment(findChecklistValue(items, G7_17_SECTION_KEY))
  }
  if (impairmentTests.length) {
    sourcesHit.push('G7-17')
    equityBridge = mergeG717IntoEquityBridge(equityBridge, impairmentTests)
  }

  const commonControlMergers = parseG78CommonControlMergers(findChecklistValue(items, G7_8_ROWS_KEY))
  if (commonControlMergers.length) sourcesHit.push('G7-8')

  const nonCommonControlMergers = parseG79NonCommonControlMergers(findChecklistValue(items, G7_9_ROWS_KEY))
  if (nonCommonControlMergers.length) sourcesHit.push('G7-9')

  const policyDifferences = parseG76PolicyDifferences(findChecklistValue(items, G7_6_ROWS_KEY))
  if (policyDifferences.length) sourcesHit.push('G7-6')

  const controlJudgmentNarrative = parseG77ControlJudgmentNarrative(
    findChecklistValue(items, G7_7_CONTROL_KEY),
    findChecklistValue(items, G7_7_CONCLUSION_KEY),
  )
  if (controlJudgmentNarrative) sourcesHit.push('G7-7')

  return {
    classification,
    detail,
    basicInfo,
    financialInfo,
    formerSubsidiaries,
    unrecognizedLoss,
    ownershipImpacts,
    equityBridge,
    impairmentTests,
    commonControlMergers,
    nonCommonControlMergers,
    policyDifferences,
    controlJudgmentNarrative,
    sourcesHit,
  }
}

export function refreshListedTablesFromSources(
  tables: Record<string, G7DisclosureRow[]>,
  bundle: G7DisclosureSourceBundle,
  force = false,
  texts?: Record<string, string>,
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
    if (tables['important-minority-subsidiaries']
      && applyListedMinoritySubsidiariesFromG74(
        tables['important-minority-subsidiaries'],
        bundle.basicInfo,
        force,
        bundle.financialInfo,
      )) {
      filled.push('important-minority-subsidiaries')
    }
  }
  filled.push(...applyFinancialInfoFromG75(tables, bundle.financialInfo, bundle.basicInfo, force, 'listed'))
  filled.push(...applyListedMinorityFsFromG75(
    {
      closing: tables['minority-closing-balance'],
      opening: tables['minority-opening-balance'],
      results: tables['minority-results'],
    },
    bundle.financialInfo,
    bundle.basicInfo,
    force,
  ))
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
      columnKeys: G7_EXCESS_LOSS_KEYS,
      force,
    })) {
      filled.push('excess-losses')
    }
  }
  const policyDraft = buildG76PolicyDifferenceNarrative(bundle.policyDifferences ?? [])
  if (appendNarrativeIfEmpty(texts, 'policy-differences', policyDraft, force)) {
    filled.push('policy-differences')
  }
  // 优先 G7-7 综合叙述；否则用 G7-4 原因字段拼草稿
  const controlDraft = String(bundle.controlJudgmentNarrative || '').trim()
    || buildControlJudgementNarrative(bundle.basicInfo, 'subsidiary')
  if (appendNarrativeIfEmpty(texts, 'subsidiary-control-judgement', controlDraft, force)) {
    filled.push('subsidiary-control-judgement')
  }
  const jvJudgeDraft = buildControlJudgementNarrative(bundle.basicInfo, 'jv-associate')
    || (
      /共同控制|重大影响/.test(String(bundle.controlJudgmentNarrative || ''))
        ? String(bundle.controlJudgmentNarrative || '').trim()
        : ''
    )
  if (appendNarrativeIfEmpty(texts, 'jv-associate-judgement', jvJudgeDraft, force)) {
    filled.push('jv-associate-judgement')
  }
  const ownershipDraft = buildOwnershipChangeNarrative(bundle.ownershipImpacts)
  if (appendNarrativeIfEmpty(texts, 'ownership-change-description', ownershipDraft, force)) {
    filled.push('ownership-change-description')
  }
  const impairmentDraft = buildImpairmentMethodNarrative(bundle.impairmentTests ?? [])
  if (appendNarrativeIfEmpty(texts, 'impairment-method', impairmentDraft, force)) {
    filled.push('impairment-method')
  }
  const joDraft = buildJointOperationBasisNarrative(bundle.basicInfo)
  if (appendNarrativeIfEmpty(texts, 'joint-operation-basis', joDraft, force)) {
    filled.push('joint-operation-basis')
  }
  return [...new Set(filled)]
}

export function refreshSoeTablesFromSources(
  tables: Record<string, G7DisclosureRow[]>,
  bundle: G7DisclosureSourceBundle,
  force = false,
  texts?: Record<string, string>,
): string[] {
  const filled: string[] = []
  if (bundle.classification && tables['lte-classification']) {
    if (applySoeClassificationFromG71(tables['lte-classification'], bundle.classification, force)) {
      filled.push('lte-classification')
    }
  }
  if (bundle.impairmentTests?.length && tables['lte-classification']) {
    if (applySoeImpairmentFromG717(tables['lte-classification'], bundle.impairmentTests, force)) {
      if (!filled.includes('lte-classification')) filled.push('lte-classification')
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
    if (tables['minority-shareholders']
      && applySoeMinorityShareholdersFromG74(
        tables['minority-shareholders'],
        bundle.basicInfo,
        force,
        bundle.financialInfo,
      )) {
      filled.push('minority-shareholders')
    }
  }
  filled.push(...applyFinancialInfoFromG75(tables, bundle.financialInfo, bundle.basicInfo, force, 'soe'))

  if (tables['minority-financials'] && bundle.financialInfo.length && bundle.basicInfo.length) {
    const minorityNames = minoritySubsidiarySources(bundle.basicInfo)
      .map(r => r.investeeName.trim())
      .slice(0, 5)
    const slots = minorityNames.map((name, index) => ({
      name,
      currentKey: `c${index + 1}Current`,
      priorKey: `c${index + 1}Prior`,
    }))
    if (applyMatrixMetrics(tables['minority-financials'], bundle.financialInfo, slots, force)) {
      filled.push('minority-financials')
    }
  }

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
    const sourceLabel = bundle.sourcesHit.includes('G7-12')
      ? '处置子公司测试表G7-12'
      : '处置子公司测试表G7-11'
    if (applyFormerSubsidiaryBasicFromG712(
      tables['former-subsidiary-basic'],
      bundle.formerSubsidiaries,
      force,
      sourceLabel,
    )) {
      filled.push('former-subsidiary-basic')
    }
  }

  if (bundle.formerSubsidiaries.length && bundle.financialInfo.length) {
    const names = bundle.formerSubsidiaries.map(r => r.investeeName.trim()).filter(Boolean)
    if (tables['former-subsidiary-position']) {
      const slots = names.slice(0, 2).map((name, index) => ({
        name,
        currentKey: `c${index + 1}SaleDate`,
        priorKey: `c${index + 1}Opening`,
      }))
      if (applyMatrixMetrics(tables['former-subsidiary-position'], bundle.financialInfo, slots, force)) {
        filled.push('former-subsidiary-position')
      }
    }
    if (tables['former-subsidiary-results']) {
      const letters = ['a', 'b', 'c', 'd', 'e']
      const slots = names.slice(0, 5).map((name, index) => ({
        name,
        currentKey: `${letters[index]}Current`,
        priorKey: `${letters[index]}Prior`,
      }))
      if (applyMatrixMetrics(tables['former-subsidiary-results'], bundle.financialInfo, slots, force)) {
        filled.push('former-subsidiary-results')
      }
    }
  }

  if (tables['common-control-combination'] && bundle.commonControlMergers?.length) {
    if (applySoeCommonControlFromG78(
      tables['common-control-combination'],
      bundle.commonControlMergers,
      force,
      bundle.financialInfo,
    )) {
      filled.push('common-control-combination')
    }
    const draft = bundle.commonControlMergers
      .map((s) => {
        const bits = [`【${s.investeeName}】`]
        if (s.consolidationDate) bits.push(`合并日 ${s.consolidationDate}`)
        if (s.basisNote) bits.push(s.basisNote)
        return bits.join('：')
      })
      .filter(Boolean)
      .join('\n')
    if (appendNarrativeIfEmpty(texts, 'common-control-basis', draft, force)) {
      filled.push('common-control-basis')
    }
  }

  if (tables['non-common-control-combination'] && bundle.nonCommonControlMergers?.length) {
    if (applySoeNonCommonControlFromG79(
      tables['non-common-control-combination'],
      bundle.nonCommonControlMergers,
      force,
      bundle.financialInfo,
    )) {
      filled.push('non-common-control-combination')
    }
    const draft = bundle.nonCommonControlMergers
      .map((s) => {
        const bits = [`【${s.investeeName}】`]
        if (s.purchaseDate) bits.push(`购买日 ${s.purchaseDate}`)
        if (s.purchaseDateBasis) bits.push(`依据：${s.purchaseDateBasis}`)
        if (s.notes) bits.push(s.notes)
        return bits.join('；')
      })
      .filter(Boolean)
      .join('\n')
    if (appendNarrativeIfEmpty(texts, 'non-common-control-notes', draft, force)) {
      filled.push('non-common-control-notes')
    }
  }

  if (tables['unrecognized-losses'] && bundle.unrecognizedLoss.length) {
    if (applyUnrecognizedLossFromG716(tables['unrecognized-losses'], bundle.unrecognizedLoss, bundle.basicInfo, {
      jvPrefix: 'ul-jv-',
      assocPrefix: 'ul-assoc-',
      jvSubtotalId: 'ul-jv-subtotal',
      assocSubtotalId: 'ul-assoc-subtotal',
      columnKeys: G7_EXCESS_LOSS_KEYS,
      force,
    })) {
      filled.push('unrecognized-losses')
    }
  }
  const policyDraft = buildG76PolicyDifferenceNarrative(bundle.policyDifferences ?? [])
  if (appendNarrativeIfEmpty(texts, 'policy-estimate-differences', policyDraft, force)) {
    filled.push('policy-estimate-differences')
  }
  const holdingVotingDraft = buildControlJudgementNarrative(bundle.basicInfo, 'subsidiary')
    || String(bundle.controlJudgmentNarrative || '').trim()
  if (appendNarrativeIfEmpty(texts, 'holding-voting-diff', holdingVotingDraft, force)) {
    filled.push('holding-voting-diff')
  }
  const lteHoldingDraft = buildControlJudgementNarrative(bundle.basicInfo, 'jv-associate')
  if (appendNarrativeIfEmpty(texts, 'lte-holding-voting-diff', lteHoldingDraft, force)) {
    filled.push('lte-holding-voting-diff')
  }
  const jointControlDraft = buildJointControlBasisNarrative(bundle.basicInfo)
  if (appendNarrativeIfEmpty(texts, 'joint-control-basis', jointControlDraft, force)) {
    filled.push('joint-control-basis')
  }
  const ownershipDraft = buildOwnershipChangeNarrative(bundle.ownershipImpacts)
  if (appendNarrativeIfEmpty(texts, 'ownership-change-description', ownershipDraft, force)) {
    filled.push('ownership-change-description')
  }
  const saleDateDraft = buildSaleDateMethodNarrative(bundle.formerSubsidiaries)
  if (appendNarrativeIfEmpty(texts, 'sale-date-method', saleDateDraft, force)) {
    filled.push('sale-date-method')
  }
  const remMeasureDraft = buildRemainingEquityRemeasurementNarrative(bundle.formerSubsidiaries)
  if (appendNarrativeIfEmpty(texts, 'remaining-equity-remeasurement', remMeasureDraft, force)) {
    filled.push('remaining-equity-remeasurement')
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

/** 加载 G7-1/2/4/5/8/9/10/12/14/16 源数据：本底稿 + cycle_workpapers 兄弟底稿。 */
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
  if (!(bundle.policyDifferences?.length)) {
    const fromHtml = parseG76PolicyDifferences(
      html.accountingPolicy ?? html.accounting_policy ?? html.g76Rows ?? null,
    )
    if (fromHtml.length) {
      bundle.policyDifferences = fromHtml
      bundle.sourcesHit.push('G7-6')
    }
  }
  if (!bundle.controlJudgmentNarrative) {
    const fromHtml = parseG77ControlJudgmentNarrative(
      html.controlJudgment ?? html.control_judgment ?? html.g77 ?? null,
    )
    if (fromHtml) {
      bundle.controlJudgmentNarrative = fromHtml
      bundle.sourcesHit.push('G7-7')
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
  if (!bundle.impairmentTests?.length) {
    const fromHtml = parseG717Impairment(
      html.impairmentTest ?? html.impairment_test ?? html.g717Rows ?? html.g717 ?? null,
    )
    if (fromHtml.length) {
      bundle.impairmentTests = fromHtml
      bundle.sourcesHit.push('G7-17')
      bundle.equityBridge = mergeG717IntoEquityBridge(bundle.equityBridge, fromHtml)
    }
  }
  if (!bundle.formerSubsidiaries.length) {
    const pkg = html.disposalPackage as any
    const single = html.disposalSingle as any
    if (pkg) {
      const fromHtml = parseG712FormerSubsidiaries(pkg)
      if (fromHtml.length) {
        bundle.formerSubsidiaries = fromHtml
        bundle.sourcesHit.push('G7-12')
      }
    }
    if (!bundle.formerSubsidiaries.length && single) {
      const fromHtml = parseG711FormerSubsidiaries(single)
      if (fromHtml.length) {
        bundle.formerSubsidiaries = fromHtml
        bundle.sourcesHit.push('G7-11')
      }
    }
  }
  if (!bundle.commonControlMergers?.length) {
    const fromHtml = parseG78CommonControlMergers(
      html.sameControlMeasurement ?? html.same_control ?? html.g78Rows ?? html.g78 ?? null,
    )
    if (fromHtml.length) {
      bundle.commonControlMergers = fromHtml
      bundle.sourcesHit.push('G7-8')
    }
  }
  if (!bundle.nonCommonControlMergers?.length) {
    const fromHtml = parseG79NonCommonControlMergers(
      html.notSameControlMeasurement ?? html.not_same_control ?? html.g79Rows ?? html.g79 ?? null,
    )
    if (fromHtml.length) {
      bundle.nonCommonControlMergers = fromHtml
      bundle.sourcesHit.push('G7-9')
    }
  }
  return bundle
}
