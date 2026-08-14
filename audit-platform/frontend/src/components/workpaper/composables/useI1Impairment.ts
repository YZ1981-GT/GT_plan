/**
 * useI1Impairment — I1-12 减值准备测试 + I1-13 可收回金额(DCF)联动
 *
 * 核心功能（对齐致同 Excel I1-12 + H8-10 编制逻辑）：
 * 1. I1-12：寿命不确定/减值迹象 → 是否测试 → ②账面(原值−摊销)
 *    → ③公允净额 / ④DCF现值 → ⑤=MAX(③,④) → ⑥=MAX(②−⑤,0)
 *    → ⑧=MAX(⑥−⑦,0) / ⑨=MAX(⑦−⑥,0)（⑨仅待查，CAS8 不得转回）
 * 2. I1-13：公允净额 + DCF/WACC → MAX；回写 I1-12 的③④⑤
 * 3. 从 I1-2 带入②；从 I1-12 建 I1-13 组；编制校验；结论草稿
 * 4. 敏感性分析：折现率±1% / 增长率±0.5%
 *
 * 持久化：I1-12-rows / I1-13-rows
 * Spec: .kiro/specs/i1-intangible-assets/ | Req: 12.1-12.4, 13.1-13.5
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'

import { exportMultiSheetData, readSheetObjects } from '@/composables/useExcelIO'
import type { ChecklistItem } from './useI1FormData'
import { calcNetValue } from './useI1FormulaEngine'
import {
  DCF_FORECAST_YEARS,
  defaultFvDisposal,
  defaultWaccParams,
  normalizeFvDisposal,
  normalizeWaccParams,
  calcI1RecoverableResult,
  buildI1ConclusionDraft,
  validateWaccParams,
  buildI113SyncChecks,
  type I1FairValueDisposal,
  type I1WaccParams,
  type I1DcfCalcResult,
  type I113SyncCheck,
} from './i1RecoverableModel'

export type { I1FairValueDisposal, I1WaccParams, I113SyncCheck }
export { DCF_FORECAST_YEARS, buildI1ConclusionDraft, validateWaccParams }

// ─── Types: I1-12 减值准备测试 ───────────────────────────────────────────────

/** I1-12 减值准备测试行（对齐 Excel：类别/寿命/迹象/②~⑨） */
export interface I1ImpairmentTestRow {
  rowId: string
  /** 无形资产类别 */
  category: string
  /** 项目名称 */
  name: string
  /** 使用寿命是否不确定 */
  indefiniteLife: 'Y' | 'N' | ''
  /** 是否存在减值迹象 */
  hasIndication: 'Y' | 'N' | ''
  /** ① 减值迹象描述 */
  indicationDesc: string
  /** 是否进行减值测试（寿命不确定 OR 有迹象） */
  needTest: boolean
  /** 账面原值（从 I1-2 带入，便于追溯） */
  cost: number
  /** 累计摊销（从 I1-2 带入） */
  accAmort: number
  /** 兼容旧字段：已入账减值（归一化时并入⑦） */
  impairmentProvision: number
  /** 兼容旧字段：原「净值」；现 ② 优先用 bookValue */
  netBookValue: number
  /** ② 账面价值 = 原值 − 累计摊销（不含减值） */
  bookValue: number
  /** ③ 公允价值减去处置费用后的净额 */
  fairValueLessDisposal: number
  /** ④ 预计未来现金流量的现值 */
  dcfValue: number
  /** ⑤ 可收回金额 = MAX(③,④)；无需测试时为 0 */
  recoverableAmount: number
  /** ⑥ 累计应计提减值 = MAX(②−⑤, 0) */
  shouldProvision: number
  /** ⑦ 期末账面已计提的减值准备 */
  alreadyProvided: number
  /** ⑧ 本期应补提 = MAX(⑥−⑦, 0) */
  supplement: number
  /** ⑨ 多提待查 = MAX(⑦−⑥, 0)；禁止转回 */
  overProvision: number
  /** Excel ⑧列差值 ⑥−⑦（可为负）；高亮仍看 ⑧/⑨ */
  difference: number
  /** 工作底稿索引号 */
  indexRef: string
  /** 备注 */
  remark: string
  /** 审计结论（适当/需补提/需关注/无需测试） */
  conclusion: string
  /** 是否关联 I1-13 */
  linkedToDcf: boolean
  /** 来源 I1-2 行 id */
  sourceDetailRowId?: string
}

/** I1-12 编制校验 */
export interface I1ImpPrepValidation {
  ok: boolean
  messages: string[]
}

// ─── Types: I1-13 可收回金额测试 (DCF) ──────────────────────────────────────

/** I1-13 可收回金额测试行（对齐 Excel 一/二/三节） */
export interface I1RecoverableTestRow {
  rowId: string
  /** 资产名称（与 I1-12 对应） */
  name: string
  /** 账面净值（对照用，可从 I1-12 带入） */
  bookValue: number
  /** 预测期现金流数组（5年）(Req 13.1) */
  cashFlows: number[]
  /** 手工折现率（小数，WACC 未就绪时回退；如0.08=8%） */
  discountRate: number
  /** 永续增长率 (如0.02=2%) */
  growthRate: number
  /** 增长率确定依据 */
  growthRateBasis: string
  /** CAS8 默认税前 */
  usePreTaxRate: boolean
  /** 公允/处置费用明细 */
  fvDisposal: I1FairValueDisposal
  /** WACC 参数 */
  waccParams: I1WaccParams
  /** 终值 = perpetuityCF / (r - g) */
  terminalValue: number
  /** DCF 使用价值 = PV(预测期) + PV(终值) (Req 13.2) */
  valueInUse: number
  /** 公允价值减去处置费用后的净额 */
  fairValueLessDisposal: number
  /** 可收回金额 = MAX(公允净额, DCF) (Req 13.3) */
  recoverableAmount: number
  /** 各期折现现金流 */
  discountedCashFlows: number[]
  /** 各期折现系数 1/(1+r)^t */
  discountFactors: number[]
  /** 终值折现值 */
  discountedTerminalValue: number
  /** 预测期现值合计 */
  pvForecast: number
  fairValueSource: string
  disposalTotal: number
  recoverableSource: string
  costOfEquity: number
  waccAfterTax: number
  preTaxDiscountRate: number
  effectiveDiscountRate: number
  rateInvalid: boolean
}

/** 敏感性分析结果 (Req 13.5) */
export interface SensitivityResult {
  /** 场景描述 */
  scenario: string
  /** 折现率 */
  discountRate: number
  /** 增长率 */
  growthRate: number
  /** 该场景下的 DCF 使用价值 */
  valueInUse: number
  /** 该场景下的可收回金额 */
  recoverableAmount: number
  /** 与基准值差额 */
  differenceFromBase: number
}

/** I1-12 合计行 */
export interface I1ImpairmentSummary {
  totalBookValue: number
  totalFairValue: number
  totalDcf: number
  totalRecoverable: number
  totalNetBookValue: number
  totalShouldProvision: number
  totalAlreadyProvided: number
  totalSupplement: number
  totalOverProvision: number
  totalDifference: number
}

/** 按类别汇总（对齐 Excel 底部分类合计） */
export interface I1ImpCategorySummary {
  category: string
  bookValue: number
  shouldProvision: number
  alreadyProvided: number
  supplement: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_12_ROWS = 'I1-12-rows'
const ITEM_ID_13_ROWS = 'I1-13-rows'
const ITEM_ID_DETAIL_ROWS = 'I1-2-rows'
const ITEM_ID_12_SUPPLEMENT = 'I1-12-supplement-total'
const ITEM_ID_AMORT_BRANCH = 'I1-amort-branch'
const ITEM_ID_USEFUL_LIFE_ROWS = 'I1-7-rows'
const ITEM_ID_USEFUL_LIFE_PUBLISH = 'I1-7-indefinite-list'

const K11_I1_AMOUNT_CANDIDATES = [
  { id: 'K11-source-I1-amount', label: 'K11-source-I1-amount' },
  { id: 'K11-2-intangible-source-amount', label: 'K11-2-intangible-source-amount' },
  { id: 'K11-2-intangible-occurrence', label: 'K11-2-intangible-occurrence' },
  { id: 'K11-2-detail-rows', label: 'K11-2 明细(无形资产行)' },
]

/** I1-12 ↔ K11 勾稽结果 */
export interface I1K11ReconcileResult {
  i12Supplement: number
  k11Amount: number | null
  diff: number | null
  isMatch: boolean
  source: string
  message: string
}

/** 从 K11 checklist 提取无形资产减值金额 */
export function extractK11IntangibleAmount(list: any[]): { amount: number | null; source: string } {
  const byId = (id: string) => {
    const item = list.find((r) => r.item_id === id)
    if (!item) return null
    const raw = item.remark ?? item.conclusion
    if (raw == null || raw === '') return null
    if (typeof raw === 'string' && raw.trim().startsWith('[')) {
      try {
        const rows = JSON.parse(raw)
        if (!Array.isArray(rows)) return null
        const intang = rows.filter((r: any) => {
          const cat = String(r.assetCategory || r.impairmentItem || r.projectName || r.category || '')
          const wp = String(r.sourceWp || '')
          return wp === 'I1' || cat.includes('无形资产')
        })
        if (!intang.length) return null
        return intang.reduce(
          (s: number, r: any) => s + (Number(r.currentOccurrence ?? r.currentProvision ?? r.sourceAmount) || 0),
          0,
        )
      } catch {
        return null
      }
    }
    const n = Number(raw)
    return Number.isFinite(n) ? n : null
  }
  for (const c of K11_I1_AMOUNT_CANDIDATES) {
    const v = byId(c.id)
    if (v != null) return { amount: v, source: c.label }
  }
  return { amount: null, source: '' }
}

/** 敏感性分析参数 (Req 13.5) */
const SENSITIVITY_DISCOUNT_DELTA = 0.01  // ±1%
const SENSITIVITY_GROWTH_DELTA = 0.005   // ±0.5%

export const I1_IMPAIRMENT_INDICATORS = [
  '资产的市价当期大幅度下跌，其跌幅明显高于因时间的推移或者正常使用而预计的下跌',
  '企业经营所处的经济、技术或者法律等环境以及资产所处的市场在当期或者将在近期发生重大变化，从而对企业产生不利影响',
  '市场利率或者其他市场投资报酬率在当期已经提高，从而影响企业计算资产预计未来现金流量现值的折现率，导致资产可收回金额大幅度降低',
  '有证据表明资产已经陈旧过时或者其实体已经损坏',
  '资产已经或者将被闲置、终止使用或者计划提前处置',
] as const

// ─── Pure helpers (exported for tests) ───────────────────────────────────────

function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

function _genRowId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function _safeParseRows<T>(raw: string | null | undefined): T[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function _yn(val: any): 'Y' | 'N' | '' {
  const s = String(val ?? '').trim().toUpperCase()
  if (s === 'Y' || s === '是' || s === '√' || s === 'TRUE' || s === '1') return 'Y'
  if (s === 'N' || s === '否' || s === '×' || s === 'FALSE' || s === '0') return 'N'
  return ''
}

/** 是否须减值测试：寿命不确定 OR 存在减值迹象（CAS8） */
export function resolveI1NeedTest(
  indefiniteLife: 'Y' | 'N' | '',
  hasIndication: 'Y' | 'N' | '',
): boolean {
  return indefiniteLife === 'Y' || hasIndication === 'Y'
}

/** ② = 原值 − 累计摊销（不含减值） */
export function calcI1ImpairmentBookValue(cost: number, accAmort: number): number {
  return Math.max(_getNum(cost) - _getNum(accAmort), 0)
}

/** ⑤：须测试时 MAX(③,④)，否则 0 */
export function calcI1ImpairmentRecoverable(
  fairValueLessDisposal: number,
  dcfValue: number,
  needTest: boolean,
): number {
  if (!needTest) return 0
  return Math.max(_getNum(fairValueLessDisposal), _getNum(dcfValue))
}

/** ⑥ = MAX(②−⑤, 0)；无须测试时为 0 */
export function calcI1RequiredImpairment(
  bookValue: number,
  recoverableAmount: number,
  needTest: boolean,
): number {
  if (!needTest) return 0
  return Math.max(_getNum(bookValue) - _getNum(recoverableAmount), 0)
}

export function calcI1ImpairmentSupplement(required: number, alreadyProvided: number): number {
  return Math.max(_getNum(required) - _getNum(alreadyProvided), 0)
}

export function calcI1ImpairmentOverProvision(required: number, alreadyProvided: number): number {
  return Math.max(_getNum(alreadyProvided) - _getNum(required), 0)
}

export function suggestI1ImpairmentConclusion(row: Pick<
  I1ImpairmentTestRow,
  'needTest' | 'supplement' | 'overProvision' | 'recoverableAmount' | 'bookValue'
>): string {
  if (!row.needTest) return '无需测试'
  if (row.supplement > 0.005) return '需补提'
  if (row.overProvision > 0.005) return '需关注'
  if (row.bookValue > 0 && row.recoverableAmount <= 0) return '需关注'
  return '适当'
}

export function recomputeI1ImpairmentRow(row: I1ImpairmentTestRow): I1ImpairmentTestRow {
  const indefiniteLife = _yn(row.indefiniteLife)
  const hasIndication = _yn(row.hasIndication)
  const needTest = resolveI1NeedTest(indefiniteLife, hasIndication)
  const cost = _getNum(row.cost)
  const accAmort = _getNum(row.accAmort)
  const bookValue = _getNum(row.bookValue) || calcI1ImpairmentBookValue(cost, accAmort)
  const fairValueLessDisposal = needTest ? _getNum(row.fairValueLessDisposal) : 0
  const dcfValue = needTest ? _getNum(row.dcfValue) : 0
  const recoverableAmount = calcI1ImpairmentRecoverable(fairValueLessDisposal, dcfValue, needTest)
  const shouldProvision = calcI1RequiredImpairment(bookValue, recoverableAmount, needTest)
  const alreadyProvided = _getNum(row.alreadyProvided)
  const supplement = calcI1ImpairmentSupplement(shouldProvision, alreadyProvided)
  const overProvision = calcI1ImpairmentOverProvision(shouldProvision, alreadyProvided)
  const difference = shouldProvision - alreadyProvided
  const indicationDesc = hasIndication === 'N' ? '' : (row.indicationDesc || '')
  const netBookValue = calcNetValue(cost || bookValue + alreadyProvided, accAmort, alreadyProvided)

  return {
    ...row,
    indefiniteLife,
    hasIndication,
    needTest,
    cost,
    accAmort,
    impairmentProvision: alreadyProvided,
    bookValue,
    fairValueLessDisposal,
    dcfValue,
    recoverableAmount,
    shouldProvision,
    alreadyProvided,
    supplement,
    overProvision,
    difference,
    indicationDesc,
    netBookValue,
  }
}

export function emptyI1ImpairmentRow(partial?: Partial<I1ImpairmentTestRow>): I1ImpairmentTestRow {
  return recomputeI1ImpairmentRow({
    rowId: partial?.rowId ?? _genRowId('imp12'),
    category: '',
    name: '',
    indefiniteLife: '',
    hasIndication: '',
    indicationDesc: '',
    needTest: false,
    cost: 0,
    accAmort: 0,
    impairmentProvision: 0,
    netBookValue: 0,
    bookValue: 0,
    fairValueLessDisposal: 0,
    dcfValue: 0,
    recoverableAmount: 0,
    shouldProvision: 0,
    alreadyProvided: 0,
    supplement: 0,
    overProvision: 0,
    difference: 0,
    indexRef: '',
    remark: '',
    conclusion: '',
    linkedToDcf: false,
    ...partial,
  })
}

export function validateI1ImpairmentPrep(rows: I1ImpairmentTestRow[]): I1ImpPrepValidation {
  const messages: string[] = []
  for (const r of rows) {
    if (!r.name && !r.bookValue && !r.needTest) continue
    if (r.indefiniteLife === 'Y' || r.hasIndication === 'Y') {
      if (r.hasIndication === 'Y' && !r.indicationDesc.trim()) {
        messages.push(`「${r.name || r.rowId}」有减值迹象但未填写①迹象描述`)
      }
      if (!/I1-13/i.test(r.indexRef || '')) {
        messages.push(`「${r.name || r.rowId}」须进行减值测试，索引号应含 I1-13`)
      }
      if (r.bookValue > 0 && r.recoverableAmount <= 0) {
        messages.push(`「${r.name || r.rowId}」须测试但⑤可收回金额尚未测算（请完成 I1-13 并联动）`)
      }
    }
    if (r.overProvision > 0.01) {
      messages.push(`「${r.name || r.rowId}」多提待查⑨=${r.overProvision.toFixed(2)}，须查明原因且不得转回`)
    }
  }
  return { ok: messages.length === 0, messages }
}

/** 从 I1-2 明细推导 I1-12 行 */
export function seedRowsFromI12Detail(detailRows: any[]): I1ImpairmentTestRow[] {
  const out: I1ImpairmentTestRow[] = []
  for (const r of detailRows ?? []) {
    const name = String(r?.name || '').trim()
    if (!name) continue
    const cost = _getNum(r.costEnd ?? r.cost)
    const accAmort = _getNum(r.accAmortEnd ?? r.accAmort)
    const alreadyProvided = _getNum(r.impairmentEnd ?? r.impairmentProvision)
    const lifeMonths = _getNum(r.usefulLifeMonths)
    const indefiniteLife: 'Y' | 'N' = lifeMonths <= 0 ? 'Y' : 'N'
    out.push(emptyI1ImpairmentRow({
      category: String(r.category || '').trim(),
      name,
      indefiniteLife,
      hasIndication: '',
      cost,
      accAmort,
      bookValue: calcI1ImpairmentBookValue(cost, accAmort),
      alreadyProvided,
      sourceDetailRowId: String(r.rowId ?? ''),
      indexRef: '',
      remark: '自I1-2带入',
    }))
  }
  return out
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI1Impairment(
  wpId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    /** 保存回调（委托 useI1FormData.saveResponse） */
    onSave?: (itemId: string, value: any) => void
  },
) {

  // ─── State: I1-12 减值准备测试 ─────────────────────────────────────────────

  const impairmentRows = ref<I1ImpairmentTestRow[]>([])

  // ─── State: I1-13 可收回金额测试 ───────────────────────────────────────────

  const recoverableRows = ref<I1RecoverableTestRow[]>([])

  const k11Reconcile = ref<I1K11ReconcileResult>({
    i12Supplement: 0,
    k11Amount: null,
    diff: null,
    isMatch: true,
    source: '',
    message: '尚未核对 K11',
  })

  // ─── Load from allResponses ────────────────────────────────────────────────

  function _loadImpairmentRows(): void {
    const resp = allResponses.value.get(ITEM_ID_12_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    impairmentRows.value = _safeParseRows<any>(raw).map(_normalizeImpairmentRow)
  }

  function _loadRecoverableRows(): void {
    const resp = allResponses.value.get(ITEM_ID_13_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    recoverableRows.value = _safeParseRows<any>(raw).map(_normalizeRecoverableRow)
  }

  function _normalizeImpairmentRow(raw: any): I1ImpairmentTestRow {
    const cost = _getNum(raw.cost)
    const accAmort = _getNum(raw.accAmort)
    const legacyAlready = _getNum(raw.alreadyProvided) || _getNum(raw.impairmentProvision)
    const bookValue = _getNum(raw.bookValue) || calcI1ImpairmentBookValue(cost, accAmort)
      || (_getNum(raw.netBookValue) + legacyAlready)
    // 旧数据仅有单一 recoverableAmount：优先视为④，③为空
    const fairValueLessDisposal = _getNum(raw.fairValueLessDisposal)
    const dcfValue = _getNum(raw.dcfValue) || (
      fairValueLessDisposal > 0 ? 0 : _getNum(raw.recoverableAmount)
    )

    return recomputeI1ImpairmentRow({
      rowId: raw.rowId ?? _genRowId('imp12'),
      category: String(raw.category ?? ''),
      name: String(raw.name ?? ''),
      indefiniteLife: _yn(raw.indefiniteLife),
      hasIndication: _yn(raw.hasIndication),
      indicationDesc: String(raw.indicationDesc ?? ''),
      needTest: false,
      cost,
      accAmort,
      impairmentProvision: legacyAlready,
      netBookValue: _getNum(raw.netBookValue),
      bookValue,
      fairValueLessDisposal,
      dcfValue,
      recoverableAmount: _getNum(raw.recoverableAmount),
      shouldProvision: _getNum(raw.shouldProvision),
      alreadyProvided: legacyAlready,
      supplement: _getNum(raw.supplement),
      overProvision: _getNum(raw.overProvision),
      difference: _getNum(raw.difference),
      indexRef: String(raw.indexRef ?? ''),
      remark: String(raw.remark ?? ''),
      conclusion: String(raw.conclusion ?? ''),
      linkedToDcf: Boolean(raw.linkedToDcf),
      sourceDetailRowId: raw.sourceDetailRowId ? String(raw.sourceDetailRowId) : undefined,
    })
  }

  function _normalizeRecoverableRow(raw: any): I1RecoverableTestRow {
    const cashFlows: number[] = Array.isArray(raw.cashFlows)
      ? raw.cashFlows.slice(0, DCF_FORECAST_YEARS).map(_getNum)
      : new Array(DCF_FORECAST_YEARS).fill(0)
    while (cashFlows.length < DCF_FORECAST_YEARS) cashFlows.push(0)

    const discountRate = _getNum(raw.discountRate) || 0.08
    const growthRate = _getNum(raw.growthRate)
    const fvDisposal = normalizeFvDisposal(raw.fvDisposal)
    const waccParams = normalizeWaccParams(raw.waccParams)
    const usePreTaxRate = raw.usePreTaxRate !== false
    const legacyFairValueNet = _getNum(raw.fairValueLessDisposal)

    const calc = calcI1RecoverableResult({
      cashFlows,
      manualDiscountRate: discountRate,
      growthRate,
      fvDisposal,
      waccParams,
      usePreTaxRate,
      legacyFairValueNet,
    })

    return {
      rowId: raw.rowId ?? _genRowId('dcf13'),
      name: raw.name ?? '',
      bookValue: _getNum(raw.bookValue),
      cashFlows,
      discountRate,
      growthRate,
      growthRateBasis: String(raw.growthRateBasis ?? ''),
      usePreTaxRate,
      fvDisposal,
      waccParams,
      ..._applyCalcToFields(calc),
    }
  }

  function _applyCalcToFields(calc: I1DcfCalcResult): Omit<
    I1RecoverableTestRow,
    | 'rowId' | 'name' | 'bookValue' | 'cashFlows' | 'discountRate' | 'growthRate'
    | 'growthRateBasis' | 'usePreTaxRate' | 'fvDisposal' | 'waccParams'
  > {
    return {
      terminalValue: calc.terminalValue,
      valueInUse: calc.valueInUse,
      fairValueLessDisposal: calc.fairValueLessDisposal,
      recoverableAmount: calc.recoverableAmount,
      discountedCashFlows: calc.discountedCashFlows,
      discountFactors: calc.discountFactors,
      discountedTerminalValue: calc.discountedTerminalValue,
      pvForecast: calc.pvForecast,
      fairValueSource: calc.fairValueSource,
      disposalTotal: calc.disposalTotal,
      recoverableSource: calc.recoverableSource,
      costOfEquity: calc.costOfEquity,
      waccAfterTax: calc.waccAfterTax,
      preTaxDiscountRate: calc.preTaxDiscountRate,
      effectiveDiscountRate: calc.effectiveDiscountRate,
      rateInvalid: calc.rateInvalid,
    }
  }

  // ─── DCF Calculation Core (Req 13.2) ───────────────────────────────────────

  function _calcDcfResult(row: Pick<
    I1RecoverableTestRow,
    'cashFlows' | 'discountRate' | 'growthRate' | 'fvDisposal' | 'waccParams' | 'usePreTaxRate' | 'fairValueLessDisposal'
  >): I1DcfCalcResult {
    return calcI1RecoverableResult({
      cashFlows: row.cashFlows,
      manualDiscountRate: row.discountRate,
      growthRate: row.growthRate,
      fvDisposal: row.fvDisposal ?? defaultFvDisposal(),
      waccParams: row.waccParams ?? defaultWaccParams(),
      usePreTaxRate: row.usePreTaxRate !== false,
      legacyFairValueNet: row.fairValueLessDisposal,
    })
  }

  // ─── I1-12: Recalculation (Req 12.2) ───────────────────────────────────────

  /**
   * 重算单行 I1-12：
   * - needTest = 寿命不确定 OR 有迹象
   * - ②账面 = 原值−摊销（或手工 bookValue）
   * - ⑤ = MAX(③,④)；⑥ = MAX(②−⑤,0)；⑧/⑨ 拆分补提与多提待查
   */
  function _recalcImpairmentRow(row: I1ImpairmentTestRow): void {
    Object.assign(row, recomputeI1ImpairmentRow(row))
  }

  /**
   * 重算所有 I1-12 行。
   */
  function recalcAllImpairment(): void {
    for (const row of impairmentRows.value) {
      _recalcImpairmentRow(row)
    }
    _persistImpairment()
  }

  /**
   * 重算单行 I1-12。
   */
  function recalcImpairmentRow(rowIndex: number): void {
    const row = impairmentRows.value[rowIndex]
    if (!row) return
    _recalcImpairmentRow(row)
    _persistImpairment()
  }

  // ─── I1-13: Recalculation (Req 13.2) ───────────────────────────────────────

  /**
   * 重算单行 I1-13：公允净额 + DCF/WACC → MAX
   */
  function _recalcRecoverableRow(row: I1RecoverableTestRow): void {
    const result = _calcDcfResult(row)
    Object.assign(row, _applyCalcToFields(result))
  }

  /**
   * 重算所有 I1-13 行。
   */
  function recalcAllRecoverable(): void {
    for (const row of recoverableRows.value) {
      _recalcRecoverableRow(row)
    }
    _persistRecoverable()
  }

  /**
   * 重算单行 I1-13。
   */
  function recalcRecoverableRow(rowIndex: number): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    _recalcRecoverableRow(row)
    _persistRecoverable()
  }

  // ─── I1-13 → I1-12 联动 (Req 13.4) ────────────────────────────────────────

  /**
   * 将 I1-13 ③公允 / ④DCF / ⑤可收回 联动填入 I1-12（按名称匹配）。
   */
  function linkRecoverableToImpairment(): { ok: boolean; message: string; count: number } {
    const recoverableMap = new Map<string, I1RecoverableTestRow>()
    for (const row of recoverableRows.value) {
      if (row.name) recoverableMap.set(row.name.trim(), row)
    }

    let count = 0
    for (const row of impairmentRows.value) {
      const key = (row.name || '').trim()
      if (!key || !recoverableMap.has(key)) continue
      const rc = recoverableMap.get(key)!
      const changed =
        row.fairValueLessDisposal !== rc.fairValueLessDisposal
        || row.dcfValue !== rc.valueInUse
        || row.recoverableAmount !== rc.recoverableAmount
        || !row.linkedToDcf
      if (!changed) continue
      row.fairValueLessDisposal = rc.fairValueLessDisposal
      row.dcfValue = rc.valueInUse
      row.recoverableAmount = rc.recoverableAmount
      row.linkedToDcf = true
      if (!/I1-13/i.test(row.indexRef || '')) {
        row.indexRef = row.indexRef ? `${row.indexRef};I1-13` : 'I1-13'
      }
      if (!row.needTest && (rc.recoverableAmount > 0 || rc.valueInUse > 0 || rc.fairValueLessDisposal > 0)) {
        // 已有测算结果时，至少标记有迹象以便公式闸门放行
        if (row.hasIndication !== 'Y' && row.indefiniteLife !== 'Y') {
          row.hasIndication = 'Y'
        }
      }
      _recalcImpairmentRow(row)
      if (!row.conclusion) row.conclusion = suggestI1ImpairmentConclusion(row)
      count++
    }

    if (count > 0) _persistImpairment()
    return {
      ok: count > 0,
      count,
      message: count > 0
        ? `已联动 ${count} 行至 I1-12（③④⑤）`
        : '未找到名称匹配的 I1-12 行（请先在 I1-12 建立同名资产，或从 I1-12 建组）',
    }
  }

  /**
   * 联动单行：I1-13 某行重算后自动填入 I1-12 对应行。
   */
  function linkSingleRecoverableToImpairment(recoverableRowIndex: number): void {
    const rcRow = recoverableRows.value[recoverableRowIndex]
    if (!rcRow?.name) return
    const key = rcRow.name.trim()

    for (const impRow of impairmentRows.value) {
      if ((impRow.name || '').trim() !== key) continue
      impRow.fairValueLessDisposal = rcRow.fairValueLessDisposal
      impRow.dcfValue = rcRow.valueInUse
      impRow.recoverableAmount = rcRow.recoverableAmount
      impRow.linkedToDcf = true
      if (!/I1-13/i.test(impRow.indexRef || '')) {
        impRow.indexRef = impRow.indexRef ? `${impRow.indexRef};I1-13` : 'I1-13'
      }
      if (!impRow.needTest && (rcRow.recoverableAmount > 0 || rcRow.valueInUse > 0)) {
        if (impRow.hasIndication !== 'Y' && impRow.indefiniteLife !== 'Y') {
          impRow.hasIndication = 'Y'
        }
      }
      _recalcImpairmentRow(impRow)
      if (!impRow.conclusion) impRow.conclusion = suggestI1ImpairmentConclusion(impRow)
    }
    _persistImpairment()
  }

  /**
   * 从 I1-12 须测试且有账面的行建立/补齐 I1-13 测算组。
   */
  function seedFromImpairment(): { ok: boolean; message: string; count: number } {
    const existing = new Set(recoverableRows.value.map((r) => (r.name || '').trim()).filter(Boolean))
    let count = 0
    for (const row of impairmentRows.value) {
      const name = (row.name || '').trim()
      if (!name || existing.has(name)) continue
      if (!row.needTest) continue
      if (row.bookValue <= 0 && row.cost <= 0) continue
      addRecoverableRow({
        name,
        bookValue: row.bookValue || row.netBookValue,
        discountRate: 0.08,
        growthRate: 0.02,
        fairValueLessDisposal: row.fairValueLessDisposal,
      })
      existing.add(name)
      count++
    }
    return {
      ok: count > 0,
      count,
      message: count > 0
        ? `已从 I1-12 新建 ${count} 项可收回测算`
        : 'I1-12 无可新建项（须先判定寿命不确定/有迹象，且尚未建组）',
    }
  }

  /**
   * 从 I1-2 明细带入②账面价值（及类别/寿命不确定/⑦已计提）。
   */
  function seedFromDetail(): { ok: boolean; message: string; count: number } {
    const resp = allResponses.value.get(ITEM_ID_DETAIL_ROWS)
    const raw = resp?.remark ?? resp?.conclusion
    let parsed: any[] = []
    if (Array.isArray(raw)) parsed = raw
    else if (typeof raw === 'string') parsed = _safeParseRows<any>(raw)
    else if (raw && typeof raw === 'object') parsed = _safeParseRows<any>(JSON.stringify(raw))

    const seeded = seedRowsFromI12Detail(parsed)
    if (!seeded.length) {
      return { ok: false, count: 0, message: 'I1-2 无明细行可带入' }
    }

    const byName = new Map(impairmentRows.value.map((r) => [(r.name || '').trim(), r]))
    let count = 0
    for (const s of seeded) {
      const key = s.name.trim()
      const prev = byName.get(key)
      if (prev) {
        prev.category = s.category || prev.category
        prev.cost = s.cost
        prev.accAmort = s.accAmort
        prev.bookValue = s.bookValue
        prev.alreadyProvided = s.alreadyProvided || prev.alreadyProvided
        prev.indefiniteLife = s.indefiniteLife || prev.indefiniteLife
        prev.sourceDetailRowId = s.sourceDetailRowId
        _recalcImpairmentRow(prev)
        count++
      } else {
        impairmentRows.value.push(s)
        byName.set(key, s)
        count++
      }
    }
    if (count > 0) _persistImpairment()
    return { ok: count > 0, count, message: `已从 I1-2 带入/更新 ${count} 行` }
  }

  // ─── Sensitivity Analysis (Req 13.5) ───────────────────────────────────────

  /**
   * 敏感性分析：折现率±1% / 增长率±0.5%，产出 5 个场景对比。
   */
  function calcSensitivity(recoverableRowIndex: number): SensitivityResult[] {
    const row = recoverableRows.value[recoverableRowIndex]
    if (!row) return []

    const baseR = row.effectiveDiscountRate || row.discountRate
    const baseG = row.growthRate
    const cfs = row.cashFlows

    const scenarios: Array<{ label: string; r: number; g: number }> = [
      { label: '基准情景', r: baseR, g: baseG },
      { label: `折现率+1% (${((baseR + SENSITIVITY_DISCOUNT_DELTA) * 100).toFixed(1)}%)`, r: baseR + SENSITIVITY_DISCOUNT_DELTA, g: baseG },
      { label: `折现率-1% (${((baseR - SENSITIVITY_DISCOUNT_DELTA) * 100).toFixed(1)}%)`, r: baseR - SENSITIVITY_DISCOUNT_DELTA, g: baseG },
      { label: `增长率+0.5% (${((baseG + SENSITIVITY_GROWTH_DELTA) * 100).toFixed(2)}%)`, r: baseR, g: baseG + SENSITIVITY_GROWTH_DELTA },
      { label: `增长率-0.5% (${((baseG - SENSITIVITY_GROWTH_DELTA) * 100).toFixed(2)}%)`, r: baseR, g: baseG - SENSITIVITY_GROWTH_DELTA },
    ]

    const baseResult = calcI1RecoverableResult({
      cashFlows: cfs,
      manualDiscountRate: baseR,
      growthRate: baseG,
      fvDisposal: row.fvDisposal,
      waccParams: defaultWaccParams(), // 敏感性锁定手工折现率，避免 WACC 覆盖
      usePreTaxRate: true,
      legacyFairValueNet: row.fairValueLessDisposal,
    })

    return scenarios.map((s) => {
      const result = calcI1RecoverableResult({
        cashFlows: cfs,
        manualDiscountRate: s.r,
        growthRate: s.g,
        fvDisposal: row.fvDisposal,
        waccParams: defaultWaccParams(),
        usePreTaxRate: true,
        legacyFairValueNet: row.fairValueLessDisposal,
      })
      return {
        scenario: s.label,
        discountRate: s.r,
        growthRate: s.g,
        valueInUse: result.valueInUse,
        recoverableAmount: result.recoverableAmount,
        differenceFromBase: result.recoverableAmount - baseResult.recoverableAmount,
      }
    })
  }

  function buildConclusionDraft(rowIndex: number): string {
    const row = recoverableRows.value[rowIndex]
    if (!row) return ''
    return buildI1ConclusionDraft({
      assetName: row.name,
      fairValueNet: row.fairValueLessDisposal,
      valueInUse: row.valueInUse,
      recoverableAmount: row.recoverableAmount,
      recoverableSource: row.recoverableSource,
      bookValue: row.bookValue,
      effectiveDiscountRate: row.effectiveDiscountRate,
      growthRate: row.growthRate,
      fromWacc: row.waccAfterTax > 0,
    })
  }

  // ─── Computed: I1-12 合计行 ─────────────────────────────────────────────────

  /** I1-12 合计行 */
  const impairmentSummary: ComputedRef<I1ImpairmentSummary> = computed(() => {
    let totalBookValue = 0
    let totalFairValue = 0
    let totalDcf = 0
    let totalRecoverable = 0
    let totalNetBookValue = 0
    let totalShouldProvision = 0
    let totalAlreadyProvided = 0
    let totalSupplement = 0
    let totalOverProvision = 0
    let totalDifference = 0

    for (const row of impairmentRows.value) {
      totalBookValue += row.bookValue
      totalFairValue += row.fairValueLessDisposal
      totalDcf += row.dcfValue
      totalRecoverable += row.recoverableAmount
      totalNetBookValue += row.netBookValue
      totalShouldProvision += row.shouldProvision
      totalAlreadyProvided += row.alreadyProvided
      totalSupplement += row.supplement
      totalOverProvision += row.overProvision
      totalDifference += row.difference
    }

    return {
      totalBookValue,
      totalFairValue,
      totalDcf,
      totalRecoverable,
      totalNetBookValue,
      totalShouldProvision,
      totalAlreadyProvided,
      totalSupplement,
      totalOverProvision,
      totalDifference,
    }
  })

  const categorySummary: ComputedRef<I1ImpCategorySummary[]> = computed(() => {
    const map = new Map<string, I1ImpCategorySummary>()
    for (const row of impairmentRows.value) {
      const cat = (row.category || '其他').trim() || '其他'
      const cur = map.get(cat) ?? {
        category: cat,
        bookValue: 0,
        shouldProvision: 0,
        alreadyProvided: 0,
        supplement: 0,
      }
      cur.bookValue += row.bookValue
      cur.shouldProvision += row.shouldProvision
      cur.alreadyProvided += row.alreadyProvided
      cur.supplement += row.supplement
      map.set(cat, cur)
    }
    return [...map.values()]
  })

  const prepValidation: ComputedRef<I1ImpPrepValidation> = computed(() =>
    validateI1ImpairmentPrep(impairmentRows.value),
  )

  /** I1-12 ↔ I1-13 回写一致性 */
  const syncChecks: ComputedRef<I113SyncCheck[]> = computed(() =>
    buildI113SyncChecks(impairmentRows.value, recoverableRows.value),
  )

  const staleSyncCount: ComputedRef<number> = computed(() =>
    syncChecks.value.filter((c) => c.status === 'stale' || c.status === 'missing-i13').length,
  )

  /** 须测试但缺 I1-13 / 可收回=0 */
  const missingRecoverableRows: ComputedRef<I1ImpairmentTestRow[]> = computed(() =>
    impairmentRows.value.filter((r) => {
      if (!r.needTest) return false
      const name = (r.name || '').trim()
      if (!name) return false
      const i13 = recoverableRows.value.find((x) => (x.name || '').trim() === name)
      return !i13 || (r.recoverableAmount <= 0 && (i13?.recoverableAmount ?? 0) <= 0)
    }),
  )

  const needTestGatePending: ComputedRef<boolean> = computed(() =>
    missingRecoverableRows.value.length > 0 || staleSyncCount.value > 0,
  )

  function getWaccWarnings(rowIndex: number): string[] {
    const row = recoverableRows.value[rowIndex]
    if (!row?.waccParams) return []
    return validateWaccParams(row.waccParams)
  }

  function buildImpairmentConclusionDraft(): string {
    const need = impairmentRows.value.filter((r) => r.needTest)
    const noNeed = impairmentRows.value.length - need.length
    const supp = impairmentSummary.value.totalSupplement
    const over = impairmentSummary.value.totalOverProvision
    const indefinite = impairmentRows.value.filter((r) => r.indefiniteLife === 'Y').length
    return [
      `经审计：（1）减值迹象识别：须测试 ${need.length} 项（其中寿命不确定 ${indefinite} 项），无须测试 ${noNeed} 项；`,
      `（2）可收回金额：须测试项已按 MAX(公允净额,使用价值) 确定（详见 I1-13）；`,
      `（3）⑧本期应补提合计 ${supp.toFixed(2)} 元；`,
      `（4）⑨多提待查合计 ${over.toFixed(2)} 元${over > 0.005 ? '（须查明原因，禁止转回）' : ''}；`,
      `（5）无形资产减值准备在重大方面${supp < 0.005 && over < 0.005 ? '计提适当' : '尚需关注上述差异'}。`,
    ].join('')
  }

  /**
   * 结论硬闸门：须测试缺 I1-13 / 可收回未回写时禁止定稿。
   * 对齐 CAS8：寿命不确定或有迹象者须完成可收回测算后方可形成结论。
   */
  function assertCanConclude(): { ok: boolean; message: string } {
    if (missingRecoverableRows.value.length > 0) {
      const names = missingRecoverableRows.value.map((r) => r.name).filter(Boolean).slice(0, 5).join('、')
      return {
        ok: false,
        message: `须测试闸门未通过：${missingRecoverableRows.value.length} 项缺 I1-13 可收回测算${names ? `（${names}${missingRecoverableRows.value.length > 5 ? '…' : ''}）` : ''}，禁止定稿结论`,
      }
    }
    if (staleSyncCount.value > 0) {
      return {
        ok: false,
        message: `I1-12↔I1-13 勾稽不一致 ${staleSyncCount.value} 项，请先「从 I1-13 回填」后再定稿`,
      }
    }
    const blocking = prepValidation.value.messages.filter((m) =>
      /I1-13|可收回|迹象描述/.test(m),
    )
    if (blocking.length > 0) {
      return { ok: false, message: `编制校验未通过：${blocking[0]}` }
    }
    return { ok: true, message: '' }
  }

  // ─── Computed: ⑧/⑨≠0 的行红色高亮 (Req 12.4) ─────────────────────────

  /**
   * ⑧应补提或⑨多提待查 ≠0 的行（红色高亮）。
   */
  const highlightedRowIds: ComputedRef<Set<string>> = computed(() => {
    const ids = new Set<string>()
    for (const row of impairmentRows.value) {
      if (Math.abs(row.supplement) > 0.005 || Math.abs(row.overProvision) > 0.005) {
        ids.add(row.rowId)
      }
    }
    return ids
  })

  // ─── Row Management: I1-12 ─────────────────────────────────────────────────

  /**
   * 添加 I1-12 减值测试行。
   */
  function addImpairmentRow(params: {
    name: string
    category?: string
    cost?: number
    accAmort?: number
    bookValue?: number
    impairmentProvision?: number
    alreadyProvided?: number
    recoverableAmount?: number
    fairValueLessDisposal?: number
    dcfValue?: number
    indefiniteLife?: 'Y' | 'N' | ''
    hasIndication?: 'Y' | 'N' | ''
    linkedToDcf?: boolean
  }): I1ImpairmentTestRow {
    const cost = params.cost ?? 0
    const accAmort = params.accAmort ?? 0
    const alreadyProvided = params.alreadyProvided ?? params.impairmentProvision ?? 0
    const bookValue = params.bookValue ?? calcI1ImpairmentBookValue(cost, accAmort)
    const row = emptyI1ImpairmentRow({
      name: params.name,
      category: params.category ?? '',
      cost,
      accAmort,
      bookValue,
      alreadyProvided,
      fairValueLessDisposal: params.fairValueLessDisposal ?? 0,
      dcfValue: params.dcfValue ?? (params.recoverableAmount ?? 0),
      indefiniteLife: params.indefiniteLife ?? '',
      hasIndication: params.hasIndication ?? '',
      linkedToDcf: params.linkedToDcf ?? false,
    })
    impairmentRows.value.push(row)
    _persistImpairment()
    return row
  }

  /**
   * 删除 I1-12 行。
   */
  function removeImpairmentRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= impairmentRows.value.length) return
    impairmentRows.value.splice(rowIndex, 1)
    _persistImpairment()
  }

  /**
   * 更新 I1-12 行的单个字段并重算。
   */
  function updateImpairmentField(
    rowIndex: number,
    field: keyof I1ImpairmentTestRow,
    value: number | string | boolean,
  ): void {
    const row = impairmentRows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value
    if (field === 'cost' || field === 'accAmort') {
      row.bookValue = calcI1ImpairmentBookValue(row.cost, row.accAmort)
    }
    if (field === 'impairmentProvision') {
      row.alreadyProvided = _getNum(value)
    }
    _recalcImpairmentRow(row)
    if (field === 'indefiniteLife' || field === 'hasIndication' || field === 'alreadyProvided'
      || field === 'fairValueLessDisposal' || field === 'dcfValue' || field === 'bookValue') {
      row.conclusion = suggestI1ImpairmentConclusion(row)
    }
    _persistImpairment()
  }

  // ─── Row Management: I1-13 ─────────────────────────────────────────────────

  /**
   * 添加 I1-13 可收回金额测试行。
   */
  function addRecoverableRow(params: {
    name: string
    cashFlows?: number[]
    discountRate?: number
    growthRate?: number
    fairValueLessDisposal?: number
    bookValue?: number
  }): I1RecoverableTestRow {
    const cashFlows = params.cashFlows?.slice(0, DCF_FORECAST_YEARS) ?? new Array(DCF_FORECAST_YEARS).fill(0)
    while (cashFlows.length < DCF_FORECAST_YEARS) cashFlows.push(0)

    const discountRate = params.discountRate ?? 0.08
    const growthRate = params.growthRate ?? 0.02
    const fvDisposal = defaultFvDisposal()
    const waccParams = defaultWaccParams()
    const usePreTaxRate = true
    const legacyFairValueNet = params.fairValueLessDisposal ?? 0

    const calc = calcI1RecoverableResult({
      cashFlows,
      manualDiscountRate: discountRate,
      growthRate,
      fvDisposal,
      waccParams,
      usePreTaxRate,
      legacyFairValueNet,
    })

    const row: I1RecoverableTestRow = {
      rowId: _genRowId('dcf13'),
      name: params.name,
      bookValue: params.bookValue ?? 0,
      cashFlows,
      discountRate,
      growthRate,
      growthRateBasis: '',
      usePreTaxRate,
      fvDisposal,
      waccParams,
      ..._applyCalcToFields(calc),
    }

    recoverableRows.value.push(row)
    _persistRecoverable()
    return row
  }

  /**
   * 删除 I1-13 行。
   */
  function removeRecoverableRow(rowIndex: number): void {
    if (rowIndex < 0 || rowIndex >= recoverableRows.value.length) return
    recoverableRows.value.splice(rowIndex, 1)
    _persistRecoverable()
  }

  /**
   * 更新 I1-13 行的现金流数组某年值。
   */
  function updateCashFlow(rowIndex: number, yearIndex: number, value: number): void {
    const row = recoverableRows.value[rowIndex]
    if (!row || yearIndex < 0 || yearIndex >= DCF_FORECAST_YEARS) return
    row.cashFlows[yearIndex] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  /**
   * 更新 I1-13 行标量字段并重算。
   */
  function updateRecoverableField(
    rowIndex: number,
    field: 'discountRate' | 'growthRate' | 'fairValueLessDisposal' | 'name' | 'bookValue' | 'growthRateBasis' | 'usePreTaxRate',
    value: number | string | boolean,
  ): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    ;(row as any)[field] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  /** 更新公允/处置费用字段 */
  function updateFvField(
    rowIndex: number,
    field: keyof I1FairValueDisposal,
    value: number | string,
  ): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    if (!row.fvDisposal) row.fvDisposal = defaultFvDisposal()
    ;(row.fvDisposal as any)[field] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  /** 更新 WACC 参数 */
  function updateWaccField(
    rowIndex: number,
    field: keyof I1WaccParams,
    value: number,
  ): void {
    const row = recoverableRows.value[rowIndex]
    if (!row) return
    if (!row.waccParams) row.waccParams = defaultWaccParams()
    row.waccParams[field] = value
    _recalcRecoverableRow(row)
    _persistRecoverable()
    linkSingleRecoverableToImpairment(rowIndex)
  }

  /** 持久化整行（名称等 blur 场景） */
  function persistRecoverableRow(rowIndex?: number): void {
    if (rowIndex != null) {
      const row = recoverableRows.value[rowIndex]
      if (row) _recalcRecoverableRow(row)
    }
    _persistRecoverable()
  }

  // ─── Persist ───────────────────────────────────────────────────────────────

  function _publishImpairmentToK11(supplement: number): void {
    try {
      if (typeof window === 'undefined') return
      window.dispatchEvent(new CustomEvent('impairment:calculated', {
        detail: {
          wpCode: 'I1',
          wp_code: 'I1',
          sheetCode: 'I1-12',
          sheet: '减值准备测试表I1-12',
          totalRequiredProvision: supplement,
          amount: supplement,
          label: '本期补提⑧',
          impairmentAmount: impairmentSummary.value.totalShouldProvision,
        },
      }))
    } catch { /* silent */ }
  }

  function _persistImpairment(): void {
    const supp = impairmentSummary.value.totalSupplement
    options?.onSave?.(ITEM_ID_12_ROWS, impairmentRows.value)
    options?.onSave?.(ITEM_ID_12_SUPPLEMENT, supp)
    _publishImpairmentToK11(supp)
  }

  function _persistRecoverable(): void {
    options?.onSave?.(ITEM_ID_13_ROWS, recoverableRows.value)
  }

  /**
   * 有⑧补提时切换摊销分支为含减值（I1-11），并可选回写减值金额。
   */
  function switchAmortToWithImpairment(opts?: {
    alsoPushRows?: boolean
  }): { ok: boolean; message: string; push?: ReturnType<typeof pushToAmortWithImpair> } {
    const supp = impairmentSummary.value.totalSupplement
    if (supp < 0.01 && impairmentSummary.value.totalAlreadyProvided < 0.01) {
      return { ok: false, message: '本期⑧应补提与⑦已计提均为 0，无需切换含减值分支' }
    }
    options?.onSave?.(ITEM_ID_AMORT_BRANCH, 'withImpair')
    const push = opts?.alsoPushRows !== false
      ? pushToAmortWithImpair({ createMissing: true })
      : undefined
    return {
      ok: true,
      push,
      message: push?.ok
        ? `已切换 I1-11 含减值并回写：${push.message}`
        : `已切换摊销分支为「含减值（I1-11）」；请打开 I1-11 写入减值后重算摊销（⑧=${supp.toFixed(2)}）`,
    }
  }

  /**
   * 从 I1-7 使用寿命检查同步「寿命不确定」标记（及可选账面净值提示）。
   * 优先读 I1-7-indefinite-list，其次读 I1-7-rows。
   */
  function syncFromUsefulLife(): { ok: boolean; message: string; count: number } {
    const pub = allResponses.value.get(ITEM_ID_USEFUL_LIFE_PUBLISH)
    const pubRaw = pub?.remark ?? pub?.conclusion
    let indefiniteNames = new Set<string>()
    let lifeByName = new Map<string, { indefinite: boolean; months: number; netBookValue?: number }>()

    const absorbPublish = (raw: any) => {
      let obj = raw
      if (typeof raw === 'string') {
        try { obj = JSON.parse(raw) } catch { return }
      }
      const assets = Array.isArray(obj?.assets) ? obj.assets : []
      for (const a of assets) {
        const name = String(a?.name || '').trim()
        if (!name) continue
        indefiniteNames.add(name)
        lifeByName.set(name, {
          indefinite: true,
          months: 0,
          netBookValue: _getNum(a?.netBookValue),
        })
      }
      const params = Array.isArray(obj?.lifeParams) ? obj.lifeParams : []
      for (const p of params) {
        const name = String(p?.name || '').trim()
        if (!name) continue
        const indefinite = p?.isIndefinite === true || p?.isIndefinite === 'Y' || _getNum(p?.usefulLifeMonths) <= 0
        lifeByName.set(name, {
          indefinite,
          months: _getNum(p?.usefulLifeMonths),
          netBookValue: lifeByName.get(name)?.netBookValue,
        })
        if (indefinite) indefiniteNames.add(name)
        else indefiniteNames.delete(name)
      }
    }

    if (pubRaw) absorbPublish(pubRaw)

    // 补充/覆盖：直接读 I1-7-rows
    const lifeResp = allResponses.value.get(ITEM_ID_USEFUL_LIFE_ROWS)
    const lifeRaw = lifeResp?.remark ?? lifeResp?.conclusion
    let lifeRows: any[] = []
    if (Array.isArray(lifeRaw)) lifeRows = lifeRaw
    else if (typeof lifeRaw === 'string') lifeRows = _safeParseRows<any>(lifeRaw)

    for (const r of lifeRows) {
      const name = String(r?.name || '').trim()
      if (!name) continue
      const months = _getNum(r.usefulLifeMonths)
      const indefinite = r.isIndefinite === 'Y' || r.isIndefinite === true || months <= 0
      lifeByName.set(name, {
        indefinite,
        months,
        netBookValue: _getNum(r.netBookValue),
      })
      if (indefinite) indefiniteNames.add(name)
      else indefiniteNames.delete(name)
    }

    if (!lifeByName.size && !indefiniteNames.size) {
      return { ok: false, count: 0, message: 'I1-7 暂无寿命检查数据可同步（请先在 I1-7 编制或发布不确定清单）' }
    }

    const byName = new Map(impairmentRows.value.map((r) => [(r.name || '').trim(), r]))
    let count = 0

    for (const [name, info] of lifeByName) {
      const prev = byName.get(name)
      if (prev) {
        const nextLife: 'Y' | 'N' = info.indefinite ? 'Y' : 'N'
        if (prev.indefiniteLife !== nextLife) {
          prev.indefiniteLife = nextLife
          count++
        } else if (info.indefinite && prev.indefiniteLife !== 'Y') {
          prev.indefiniteLife = 'Y'
          count++
        }
        _recalcImpairmentRow(prev)
        if (!prev.conclusion) prev.conclusion = suggestI1ImpairmentConclusion(prev)
      } else if (info.indefinite) {
        // 不确定寿命但 I1-12 尚无行：建空行便于后续从 I1-2 补账面
        const row = emptyI1ImpairmentRow({
          name,
          indefiniteLife: 'Y',
          bookValue: info.netBookValue ?? 0,
          remark: '自I1-7不确定寿命清单带入',
          indexRef: 'I1-7',
        })
        impairmentRows.value.push(row)
        byName.set(name, row)
        count++
      }
    }

    if (count > 0) _persistImpairment()
    return {
      ok: count > 0,
      count,
      message: count > 0
        ? `已从 I1-7 同步寿命标记 ${count} 行（不确定 ${indefiniteNames.size} 项）`
        : 'I1-7 与 I1-12 寿命标记已一致，无需更新',
    }
  }

  // ─── Import / Export ───────────────────────────────────────────────────────

  /** 导入 I1-12 行（覆盖） */
  function importImpairmentRows(rows: Partial<I1ImpairmentTestRow>[]): void {
    impairmentRows.value = rows.map(_normalizeImpairmentRow)
    recalcAllImpairment()
  }

  /** 导入 I1-13 行（覆盖） */
  function importRecoverableRows(rows: Partial<I1RecoverableTestRow>[]): void {
    recoverableRows.value = rows.map(_normalizeRecoverableRow)
    recalcAllRecoverable()
    linkRecoverableToImpairment()
  }

  /** 导出 I1-12 行 */
  function exportImpairmentRows(): I1ImpairmentTestRow[] {
    return [...impairmentRows.value]
  }

  /** 导出 I1-13 行 */
  function exportRecoverableRows(): I1RecoverableTestRow[] {
    return [...recoverableRows.value]
  }

  /** 客户端 xlsx 导出（对齐 H8-10） */
  async function exportImpairmentXlsx(kind: 'template' | 'data'): Promise<void> {
    const headers = [
      '类别', '项目名称', '寿命不确定', '有减值迹象', '迹象描述',
      '账面价值②', '公允减处置③', 'DCF现值④', '可收回金额⑤',
      '应计提⑥', '已计提⑦', '本期补提⑧', '多提待查⑨',
      '索引', '结论', '备注',
    ]
    const dataRows = kind === 'template'
      ? []
      : impairmentRows.value
        .filter((r) => r.name || r.bookValue)
        .map((r) => ({
          '类别': r.category || '',
          '项目名称': r.name || '',
          '寿命不确定': r.indefiniteLife || '',
          '有减值迹象': r.hasIndication || '',
          '迹象描述': r.indicationDesc || '',
          '账面价值②': r.bookValue || 0,
          '公允减处置③': r.fairValueLessDisposal || 0,
          'DCF现值④': r.dcfValue || 0,
          '可收回金额⑤': r.recoverableAmount || 0,
          '应计提⑥': r.shouldProvision || 0,
          '已计提⑦': r.alreadyProvided || 0,
          '本期补提⑧': r.supplement || 0,
          '多提待查⑨': r.overProvision || 0,
          '索引': r.indexRef || '',
          '结论': r.conclusion || '',
          '备注': r.remark || '',
        }))
    // 走 useExcelIO 单一入口（B3 批）。模板态 = 只有表头行；数据态 = 表头 + 按 headers
    // 顺序取值 —— json_to_sheet 与 aoa_to_sheet 对缺失字段同样跳过该单元格，故逐格等价。
    await exportMultiSheetData({
      sheets: [
        {
          sheetName: 'I1-12减值测试',
          rows: kind === 'template'
            ? [headers]
            : [headers, ...dataRows.map((r) => headers.map((h) => (r as any)[h]))],
        },
      ],
      fileName: `I1-12_减值准备测试_${kind === 'template' ? '模板' : '数据'}.xlsx`,
      applyStyles: false,
      successMessage: false,
    })
  }

  /** 客户端 xlsx 导入 */
  async function importImpairmentXlsx(file: File, replace = true): Promise<{ imported: number }> {
    // 走 useExcelIO 低层入口（B3 批）。原实现 = read(buffer,{type:'array',cellDates:false})
    // + sheet_to_json(sheet,{defval:''}) + 取第一个 sheet。
    // 🔴 cellDates 与 defval 必须显式透传：前者决定日期是 Date 还是序列号，
    // 后者决定空单元格填 '' 还是被跳过（下游用 ?? / || 取值时两者行为不同）。
    const { rows: rowsRaw } = await readSheetObjects<Record<string, any>>(file, {
      cellDates: false,
      defval: '',
    })
    const mapped = rowsRaw
      .filter((r) => String(r['项目名称'] || r['资产名称'] || '').trim())
      .map((r) => {
        const indefinite = String(r['寿命不确定'] || '').trim().toUpperCase()
        const indication = String(r['有减值迹象'] || '').trim().toUpperCase()
        return emptyI1ImpairmentRow({
          category: String(r['类别'] || ''),
          name: String(r['项目名称'] || r['资产名称'] || '').trim(),
          indefiniteLife: indefinite === 'Y' || indefinite === '是' ? 'Y'
            : indefinite === 'N' || indefinite === '否' ? 'N' : '',
          hasIndication: indication === 'Y' || indication === '是' ? 'Y'
            : indication === 'N' || indication === '否' ? 'N' : '',
          indicationDesc: String(r['迹象描述'] || r['①迹象描述'] || ''),
          bookValue: Number(r['账面价值②'] || r['账面价值'] || 0) || 0,
          fairValueLessDisposal: Number(r['公允减处置③'] || r['公允净额'] || 0) || 0,
          dcfValue: Number(r['DCF现值④'] || r['DCF现值'] || 0) || 0,
          alreadyProvided: Number(r['已计提⑦'] || r['已计提'] || 0) || 0,
          indexRef: String(r['索引'] || r['索引号'] || ''),
          conclusion: String(r['结论'] || ''),
          remark: String(r['备注'] || ''),
        })
      })
    if (replace) {
      impairmentRows.value = mapped
    } else {
      impairmentRows.value.push(...mapped)
    }
    recalcAllImpairment()
    return { imported: mapped.length }
  }

  /**
   * 联动回写 I1-11 含减值摊销：将 ⑦已计提（及 ⑧补提）写入 I1-11-rows。
   * 仅处理 alreadyProvided>0 或 supplement>0 的行。
   */
  function pushToAmortWithImpair(opts?: {
    defaultImpairmentDate?: string
    createMissing?: boolean
  }): { ok: boolean; linked: number; added: number; skipped: number; message: string } {
    const ITEM_I111 = 'I1-11-rows'
    const ITEM_PERIOD = 'I1-amort-period'
    const ITEM_PERIOD_LEGACY = 'I1-11-period'

    const resp = allResponses.value.get(ITEM_I111)
    const raw = resp?.remark ?? resp?.conclusion
    let existing: any[] = []
    if (Array.isArray(raw)) existing = raw
    else if (typeof raw === 'string' && raw) {
      try { existing = JSON.parse(raw) } catch { existing = [] }
    }

    let periodEnd = opts?.defaultImpairmentDate || ''
    if (!periodEnd) {
      const periodItem =
        allResponses.value.get(ITEM_PERIOD) ?? allResponses.value.get(ITEM_PERIOD_LEGACY)
      const pRaw = periodItem?.remark ?? periodItem?.conclusion
      try {
        const p = typeof pRaw === 'string' ? JSON.parse(pRaw || '{}') : pRaw
        periodEnd = p?.periodEnd || ''
      } catch { /* ignore */ }
    }

    const byName = new Map<string, any>()
    for (const r of existing) {
      const n = String(r?.name || '').trim()
      if (n) byName.set(n, r)
    }

    let linked = 0
    let added = 0
    let skipped = 0
    const createMissing = opts?.createMissing !== false

    for (const imp of impairmentRows.value) {
      const name = (imp.name || '').trim()
      if (!name) { skipped++; continue }
      const already = Number(imp.alreadyProvided) || 0
      const supplement = Number(imp.supplement) || 0
      if (already <= 0 && supplement <= 0) { skipped++; continue }

      let row = byName.get(name)
      if (!row) {
        if (!createMissing) { skipped++; continue }
        row = {
          rowId: imp.sourceDetailRowId || `amort-from-i12-${Date.now()}`,
          category: imp.category || '',
          name,
          cost: Number(imp.cost) || 0,
          salvage: 0,
          accAmortBegin: Number(imp.accAmort) || 0,
          bookAccAmortEnd: Number(imp.accAmort) || 0,
          impairment: already + supplement,
          startDate: '',
          usefulLifeYears: 0,
          bookMonthly: 0,
          bookPeriodAmort: 0,
          impairmentDate: supplement > 0 ? periodEnd : '',
          impairmentAmountAtMonth: supplement,
          usefulLifeMonths: 0,
          usedMonths: 0,
          remainingMonths: 0,
          monthlyAmort: [],
          periodAmortization: 0,
          monthlyAmortAmount: 0,
        }
        existing.push(row)
        byName.set(name, row)
        added++
      } else {
        row.impairment = already + (Number(row.impairmentAmountAtMonth) > 0 ? 0 : supplement)
        if (supplement > 0) {
          row.impairment = already + supplement
          row.impairmentAmountAtMonth = supplement
          if (!row.impairmentDate) row.impairmentDate = periodEnd
        } else {
          row.impairment = already
        }
        if (imp.category) row.category = imp.category
        if (imp.cost > 0) row.cost = imp.cost
        if (imp.accAmort != null) {
          row.accAmortBegin = imp.accAmort
          row.bookAccAmortEnd = imp.accAmort
        }
        linked++
      }
    }

    if (linked + added > 0) {
      options?.onSave?.(ITEM_ID_AMORT_BRANCH, 'withImpair')
      options?.onSave?.(ITEM_I111, existing)
    }

    return {
      ok: linked + added > 0,
      linked,
      added,
      skipped,
      message: linked + added > 0
        ? `已回写 I1-11：更新 ${linked} 行${added ? `，新增 ${added} 行` : ''}，并切换含减值分支`
        : '无可回写项（需⑦已计提或⑧应补提>0，且名称可匹配）',
    }
  }

  // ─── Init: watch allResponses 加载数据 ─────────────────────────────────────

  watch(allResponses, () => {
    _loadImpairmentRows()
    _loadRecoverableRows()
  }, { immediate: true })

  /**
   * 核对 I1-12 ⑧应补提 vs K11 无形资产减值金额（对齐 H8 reconcileWithK11）。
   */
  async function reconcileWithK11(projectId: string): Promise<I1K11ReconcileResult> {
    const i12Supplement = impairmentSummary.value.totalSupplement
    const empty: I1K11ReconcileResult = {
      i12Supplement,
      k11Amount: null,
      diff: null,
      isMatch: true,
      source: '',
      message: 'K11 未取到无形资产减值金额',
    }
    if (!projectId) {
      k11Reconcile.value = { ...empty, message: '缺少 projectId，无法核对 K11' }
      return k11Reconcile.value
    }
    try {
      const { api } = await import('@/services/apiProxy')
      const { data: wpList } = await api.get('/api/workpapers', {
        params: { project_id: projectId, wp_code: 'K11' },
      })
      const k11 = Array.isArray(wpList) ? wpList.find((w: any) => w.wp_code === 'K11') : null
      if (!k11?.id) {
        k11Reconcile.value = { ...empty, message: '项目中未找到 K11 底稿' }
        return k11Reconcile.value
      }
      const { data: list } = await api.get(`/api/workpapers/${k11.id}/checklist-responses`)
      const { amount: k11Amount, source } = extractK11IntangibleAmount(Array.isArray(list) ? list : [])
      if (k11Amount == null) {
        k11Reconcile.value = { ...empty, message: 'K11 未取到无形资产减值金额', source }
        return k11Reconcile.value
      }
      const diff = Math.round((i12Supplement - k11Amount) * 100) / 100
      const isMatch = Math.abs(diff) < 0.01
      k11Reconcile.value = {
        i12Supplement,
        k11Amount,
        diff,
        isMatch,
        source,
        message: isMatch
          ? `K11 勾稽通过：⑧本期补提 ${i12Supplement.toFixed(2)} = K11 ${k11Amount.toFixed(2)}（${source}）`
          : `K11 勾稽差异：⑧ ${i12Supplement.toFixed(2)} − K11 ${k11Amount.toFixed(2)} = ${diff.toFixed(2)}（${source}）`,
      }
      return k11Reconcile.value
    } catch (e) {
      k11Reconcile.value = {
        ...empty,
        message: `拉取 K11 失败：${e instanceof Error ? e.message : String(e)}`,
      }
      return k11Reconcile.value
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // ── State ──
    impairmentRows,
    recoverableRows,

    // ── Computed ──
    impairmentSummary,
    categorySummary,
    prepValidation,
    highlightedRowIds,
    syncChecks,
    staleSyncCount,
    missingRecoverableRows,
    needTestGatePending,
    k11Reconcile,

    // ── Constants ──
    DCF_FORECAST_YEARS,
    I1_IMPAIRMENT_INDICATORS,

    // ── Actions: I1-12 减值测试 ──
    recalcAllImpairment,
    recalcImpairmentRow,
    addImpairmentRow,
    removeImpairmentRow,
    updateImpairmentField,
    seedFromDetail,
    syncFromUsefulLife,
    buildImpairmentConclusionDraft,
    assertCanConclude,
    switchAmortToWithImpairment,
    publishToK11: () => _publishImpairmentToK11(impairmentSummary.value.totalSupplement),
    reconcileWithK11,

    // ── Actions: I1-13 可收回金额(DCF) ──
    recalcAllRecoverable,
    recalcRecoverableRow,
    addRecoverableRow,
    removeRecoverableRow,
    updateCashFlow,
    updateRecoverableField,
    updateFvField,
    updateWaccField,
    persistRecoverableRow,
    seedFromImpairment,
    buildConclusionDraft,
    getWaccWarnings,

    // ── Actions: 联动 ──
    linkRecoverableToImpairment,
    linkSingleRecoverableToImpairment,
    pushToAmortWithImpair,

    // ── Actions: 敏感性分析 ──
    calcSensitivity,

    // ── Import/Export ──
    importImpairmentRows,
    importRecoverableRows,
    exportImpairmentRows,
    exportRecoverableRows,
    exportImpairmentXlsx,
    importImpairmentXlsx,
  }
}

export default useI1Impairment
