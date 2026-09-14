/**
 * useH3Impairment — H3-10/H3-11 减值组 composable（仅成本模式）
 *
 * H3-10：减值迹象判断 + 减值测算表
 * H3-11：多物业/资产组 + 可收回金额 = MAX(公允净额, DCF)
 *        + WACC/CAPM + 终值敏感轴 + H3-8/H3-14 取数 + 回写 H3-10
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem } from './useH3FormData'
import { calcSubtotal, calcDcfPresentValue, calcTerminalValue } from './useH3FormulaEngine'
import {
  H3_10_CATEGORY_BUILDING,
  H3_10_CATEGORY_LAND,
  H3_10_CATEGORY_CIP,
  ITEM_H310_STOCKTAKE_CONCERNS,
  ITEM_H310_SUPPLEMENT_TOTAL,
  parseH32CostDetailRows,
  parseStocktakeConcernPayload,
  extractK11InvestmentPropertyAmount,
  type K11ReconcileResult,
  type StocktakeImpairmentConcern,
} from './h3ImpairmentCrossSheet'
import {
  calcCostOfEquity,
  calcWaccAfterTax,
  calcPreTaxDiscountRate,
  resolveFairValue,
  calcDisposalTotal,
  calcTerminalSensitivityAxis,
  type TerminalSensitivityPoint,
} from './useH1Impairment'

export type { K11ReconcileResult, StocktakeImpairmentConcern }

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ImpairmentSign {
  id: string
  indicator: string
  exists: string
  evidence: string
}

export interface ImpairmentCalcRow {
  rowId: string
  /** 投资性房地产类别 */
  category: string
  /** 项目名称 */
  assetName: string
  hasIndication: 'Y' | 'N' | ''
  indicationDesc: string
  bookValue: number
  fairValueLessDisposal: number
  dcfValue: number
  recoverableAmount: number
  impairmentAmount: number
  /** @deprecated 兼容旧字段 */
  impairmentLoss: number
  alreadyProvided: number
  difference: number
  indexRef: string
  remark: string
}

/** 源模板 H3-10 投资性房地产类别 */
export const H3_10_ASSET_CATEGORIES = [
  H3_10_CATEGORY_BUILDING,
  H3_10_CATEGORY_LAND,
  H3_10_CATEGORY_CIP,
] as const

export interface ImpCategoryTotal {
  category: string
  bookValue: number
  recoverableAmount: number
  impairmentAmount: number
  alreadyProvided: number
  supplement: number
  overProvision: number
  rowCount: number
}

export interface ImpPrepValidation {
  ok: boolean
  messages: string[]
}

export interface DcfSyncCheck {
  rowId: string
  assetName: string
  h10Dcf: number
  h11Dcf: number
  h10Fv: number
  h11Fv: number
  hasH11Group: boolean
  dcfSynced: boolean
  fvSynced: boolean
  status: 'synced' | 'stale' | 'missing-h11' | 'no-test'
}

export interface FairValueDisposal {
  assetName: string
  salesAgreementPrice: number
  salesAgreementNote: string
  activeMarketPrice: number
  activeMarketNote: string
  estimatedPrice: number
  estimatedNote: string
  legalFees: number
  relatedTaxes: number
  transportCosts: number
  directCosts: number
  otherCosts: number
  remark: string
}

export interface WaccParams {
  taxRate: number
  totalDebt: number
  totalEquity: number
  costOfDebt: number
  riskFreeRate: number
  beta: number
  marketReturn: number
}

export interface DcfAssumptions {
  discountRate: number
  forecastYears: number
  terminalGrowth: number
  annualRent: number
  annualCost: number
  residualValue: number
  growthRateBasis: string
  industryGrowthRate: number
  marketGrowthRate: number
  countryGrowthRate: number
  usePreTaxRate: boolean
}

/** H3-11 可收回金额测试资产组（多物业切换） */
export interface RecoverableGroup {
  groupId: string
  name: string
  bookValue: number
  sourceH38RowId?: string
  sourceH14RowId?: string
  dcfAssumptions: DcfAssumptions
  waccParams: WaccParams
  fvDisposal: FairValueDisposal
}

export interface FairValueSourceRow {
  rowId: string
  assetName: string
  appraisalValue: number
  marketRef: number
  bookValue: number
  discountRate: number
  rentAssumption: number
}

export interface RentalSourceRow {
  rowId: string
  assetName: string
  expectedRent: number
  annualRent: number
  monthlyRent: number
}

export interface CashFlowRow {
  year: number
  yearLabel: string
  revenue: number
  cost: number
  netCashFlow: number
  discountFactor: number
  presentValue: number
}

export interface DcfResult {
  pvCashFlows: number
  terminalCashFlow: number
  terminalValue: number
  terminalValueDiscounted: number
  totalPV: number
  rateInvalid: boolean
}

const ITEM_SIGNS = 'H3-10-signs'
const ITEM_CALC = 'H3-10-calc-rows'
const ITEM_GROUPS = 'H3-11-groups'
const ITEM_ACTIVE = 'H3-11-active-group'
/** 遗留单组键（迁移用） */
const ITEM_DCF_LEGACY = 'H3-11-dcf-assumptions'
const ITEM_FV_LEGACY = 'H3-11-fv-disposal'
const ITEM_WACC_LEGACY = 'H3-11-wacc-params'
const ITEM_H38_ROWS = 'H3-8-calc-rows'
const ITEM_H14_ROWS = 'H3-14-contract-rows'
const ITEM_H14_ROWS_LEGACY = 'H3-14-rental-rows'

/** CAS8 六项减值迹象 */
const CAS8_SIGN_DEFINITIONS: { id: string; indicator: string }[] = [
  { id: 'market_decline', indicator: '资产的市价当期大幅度下跌，其跌幅明显高于因时间的推移或者正常使用而预计的下跌' },
  { id: 'env_change', indicator: '企业经营所处的经济、技术或者法律等环境以及资产所处的市场在当期或者将在近期发生重大变化' },
  { id: 'rate_increase', indicator: '市场利率或者其他市场投资报酬率在当期已经提高，从而影响企业计算资产预计未来现金流量现值的折现率' },
  { id: 'physical_damage', indicator: '有证据表明资产已经陈旧过时或者其实体已经损坏' },
  { id: 'idle_disposal', indicator: '资产已经或者将被闲置、终止使用或者计划提前处置（如长期空置、停租）' },
  { id: 'underperform', indicator: '企业内部报告的证据表明资产的经济绩效已经低于或者将低于预期（如租金收益率持续下降）' },
]

function _recalcCalcRow(row: ImpairmentCalcRow): void {
  row.recoverableAmount = Math.max(Number(row.fairValueLessDisposal) || 0, Number(row.dcfValue) || 0)
  row.impairmentAmount = Math.max((Number(row.bookValue) || 0) - row.recoverableAmount, 0)
  row.impairmentLoss = row.impairmentAmount
  row.difference = row.impairmentAmount - (Number(row.alreadyProvided) || 0)
}

function _normCalc(raw: any): ImpairmentCalcRow {
  const book = Number(raw.bookValue) || 0
  const fvNet = Number(raw.fairValueLessDisposal) || 0
  const dcf = Number(raw.dcfValue) || 0
  const legacyRecoverable = Number(raw.recoverableAmount) || 0
  const already = Number(raw.alreadyProvided) || 0
  const row: ImpairmentCalcRow = {
    rowId: raw.rowId ?? _newId('imp'),
    category: raw.category ?? '',
    assetName: raw.assetName ?? '',
    hasIndication: raw.hasIndication === 'Y' || raw.hasIndication === 'N' ? raw.hasIndication : '',
    indicationDesc: raw.indicationDesc ?? '',
    bookValue: book,
    fairValueLessDisposal: fvNet,
    dcfValue: dcf,
    recoverableAmount: 0,
    impairmentAmount: 0,
    impairmentLoss: 0,
    alreadyProvided: already,
    difference: 0,
    indexRef: raw.indexRef ?? '',
    remark: raw.remark ?? '',
  }
  if (legacyRecoverable > 0 && fvNet === 0 && dcf === 0) {
    row.recoverableAmount = legacyRecoverable
    row.impairmentAmount = Math.max(book - legacyRecoverable, 0)
    row.impairmentLoss = row.impairmentAmount
    row.difference = row.impairmentAmount - already
  } else {
    _recalcCalcRow(row)
  }
  if (raw.impairmentLoss != null && row.impairmentAmount === 0) {
    row.impairmentAmount = Number(raw.impairmentLoss) || 0
    row.impairmentLoss = row.impairmentAmount
    row.difference = row.impairmentAmount - already
  }
  return row
}

function _defaultCalcRows(): ImpairmentCalcRow[] {
  return H3_10_ASSET_CATEGORIES.map((cat) => _normCalc({
    rowId: _newId('imp'),
    category: cat,
    assetName: cat,
  }))
}

function _newId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

function _defaultFvDisposal(name = ''): FairValueDisposal {
  return {
    assetName: name,
    salesAgreementPrice: 0,
    salesAgreementNote: '',
    activeMarketPrice: 0,
    activeMarketNote: '',
    estimatedPrice: 0,
    estimatedNote: '',
    legalFees: 0,
    relatedTaxes: 0,
    transportCosts: 0,
    directCosts: 0,
    otherCosts: 0,
    remark: '',
  }
}

function _defaultWaccParams(): WaccParams {
  return {
    taxRate: 25,
    totalDebt: 0,
    totalEquity: 0,
    costOfDebt: 5,
    riskFreeRate: 2.5,
    beta: 1,
    marketReturn: 10,
  }
}

function _defaultDcfAssumptions(): DcfAssumptions {
  return {
    discountRate: 10,
    forecastYears: 5,
    terminalGrowth: 2,
    annualRent: 0,
    annualCost: 0,
    residualValue: 0,
    growthRateBasis: '',
    industryGrowthRate: 0,
    marketGrowthRate: 0,
    countryGrowthRate: 0,
    usePreTaxRate: true,
  }
}

function _defaultGroup(name = '物业-1'): RecoverableGroup {
  return {
    groupId: _newId('h3cgu'),
    name,
    bookValue: 0,
    dcfAssumptions: _defaultDcfAssumptions(),
    waccParams: _defaultWaccParams(),
    fvDisposal: _defaultFvDisposal(name),
  }
}

function _normFv(raw: any, name = ''): FairValueDisposal {
  const base = _defaultFvDisposal(name)
  if (!raw || typeof raw !== 'object') return base
  return {
    assetName: raw.assetName ?? name ?? base.assetName,
    salesAgreementPrice: Number(raw.salesAgreementPrice) || 0,
    salesAgreementNote: raw.salesAgreementNote ?? '',
    activeMarketPrice: Number(raw.activeMarketPrice) || 0,
    activeMarketNote: raw.activeMarketNote ?? '',
    estimatedPrice: Number(raw.estimatedPrice) || 0,
    estimatedNote: raw.estimatedNote ?? '',
    legalFees: Number(raw.legalFees) || 0,
    relatedTaxes: Number(raw.relatedTaxes) || 0,
    transportCosts: Number(raw.transportCosts) || 0,
    directCosts: Number(raw.directCosts) || 0,
    otherCosts: Number(raw.otherCosts) || 0,
    remark: raw.remark ?? '',
  }
}

function _normWacc(raw: any): WaccParams {
  const base = _defaultWaccParams()
  if (!raw || typeof raw !== 'object') return base
  return {
    taxRate: Number(raw.taxRate) ?? base.taxRate,
    totalDebt: Number(raw.totalDebt) || 0,
    totalEquity: Number(raw.totalEquity) || 0,
    costOfDebt: Number(raw.costOfDebt) ?? base.costOfDebt,
    riskFreeRate: Number(raw.riskFreeRate) ?? base.riskFreeRate,
    beta: Number(raw.beta) ?? base.beta,
    marketReturn: Number(raw.marketReturn) ?? base.marketReturn,
  }
}

function _normDcf(raw: any): DcfAssumptions {
  const base = _defaultDcfAssumptions()
  if (!raw || typeof raw !== 'object') return base
  return {
    discountRate: Number(raw.discountRate) ?? base.discountRate,
    forecastYears: Number(raw.forecastYears) || 5,
    terminalGrowth: Number(raw.terminalGrowth) ?? base.terminalGrowth,
    annualRent: Number(raw.annualRent) || 0,
    annualCost: Number(raw.annualCost) || 0,
    residualValue: Number(raw.residualValue) || 0,
    growthRateBasis: raw.growthRateBasis ?? '',
    industryGrowthRate: Number(raw.industryGrowthRate) || 0,
    marketGrowthRate: Number(raw.marketGrowthRate) || 0,
    countryGrowthRate: Number(raw.countryGrowthRate) || 0,
    usePreTaxRate: raw.usePreTaxRate !== false,
  }
}

function _normalizeGroup(raw: any): RecoverableGroup {
  const name = raw.name ?? raw.fvDisposal?.assetName ?? '物业'
  return {
    groupId: raw.groupId ?? _newId('h3cgu'),
    name,
    bookValue: Number(raw.bookValue) || 0,
    sourceH38RowId: raw.sourceH38RowId,
    sourceH14RowId: raw.sourceH14RowId,
    dcfAssumptions: _normDcf(raw.dcfAssumptions ?? raw.dcfParams),
    waccParams: _normWacc(raw.waccParams),
    fvDisposal: _normFv(raw.fvDisposal, name),
  }
}

function _parseCrossSheetRows(getValue: (id: string) => any, primary: string, legacy?: string): any[] {
  let raw = getValue(primary)
  if (!Array.isArray(raw) && legacy) raw = getValue(legacy)
  return Array.isArray(raw) ? raw : []
}

function _matchName(a: string, b: string): boolean {
  const x = a.trim()
  const y = b.trim()
  return x.length > 0 && x === y
}

export function useH3Impairment(params: {
  allResponses: Ref<Map<string, ChecklistItem>>
  wpId: Ref<string>
  getValue: (id: string) => any
  setValue: (id: string, value: any) => void
  saveImmediate: (id: string, value: any) => Promise<void>
}) {
  const { allResponses, getValue, setValue } = params

  const signs = ref<ImpairmentSign[]>([])
  const calcRows = ref<ImpairmentCalcRow[]>([])
  const groups = ref<RecoverableGroup[]>([_defaultGroup()])
  const activeGroupId = ref(groups.value[0].groupId)

  function _migrateLegacySingleGroup(): RecoverableGroup {
    const g = _defaultGroup()
    const dcf = getValue(ITEM_DCF_LEGACY)
    const fv = getValue(ITEM_FV_LEGACY)
    const wacc = getValue(ITEM_WACC_LEGACY)
    if (dcf) g.dcfAssumptions = _normDcf(dcf)
    if (fv) g.fvDisposal = _normFv(fv, g.name)
    if (wacc) g.waccParams = _normWacc(wacc)
    if (g.fvDisposal.assetName) g.name = g.fvDisposal.assetName
    return g
  }

  function _persistGroups(): void {
    setValue(ITEM_GROUPS, groups.value)
    setValue(ITEM_ACTIVE, activeGroupId.value)
  }

  function loadData(): void {
    const rawSigns = getValue(ITEM_SIGNS)
    signs.value = Array.isArray(rawSigns) && rawSigns.length > 0
      ? rawSigns.map(_normSign)
      : CAS8_SIGN_DEFINITIONS.map((s) => ({ id: s.id, indicator: s.indicator, exists: '', evidence: '' }))

    const rawCalc = getValue(ITEM_CALC)
    const hadSavedCalc = Array.isArray(rawCalc) && rawCalc.length > 0
    const rawGroups = getValue(ITEM_GROUPS)
    const hadSavedGroups = Array.isArray(rawGroups) && rawGroups.length > 0

    if (hadSavedCalc) {
      calcRows.value = rawCalc.map(_normCalc)
    } else if (!hadSavedGroups) {
      calcRows.value = _defaultCalcRows()
    } else {
      calcRows.value = []
    }

    if (hadSavedGroups) {
      groups.value = rawGroups.map(_normalizeGroup)
    } else {
      groups.value = [_migrateLegacySingleGroup()]
      if (hadSavedCalc && calcRows.value.length > 1) {
        groups.value = calcRows.value.map((row) => {
          const g = _defaultGroup(row.assetName || '物业')
          g.bookValue = row.bookValue
          g.fvDisposal.assetName = row.assetName
          return g
        })
      }
    }

    const savedActive = getValue(ITEM_ACTIVE)
    if (typeof savedActive === 'string' && groups.value.some((g) => g.groupId === savedActive)) {
      activeGroupId.value = savedActive
    } else {
      activeGroupId.value = groups.value[0]?.groupId ?? activeGroupId.value
    }
  }

  function _normSign(raw: any): ImpairmentSign {
    return {
      id: raw.id ?? '',
      indicator: raw.indicator ?? raw.description ?? '',
      exists: typeof raw.exists === 'string' ? raw.exists : (raw.exists ? '是' : ''),
      evidence: raw.evidence ?? '',
    }
  }

  const hasImpairmentSigns = computed(() => signs.value.some((s) => s.exists === '是'))
  const signYesCount = computed(() => signs.value.filter((s) => s.exists === '是').length)
  const totalImpairment = computed(() => calcSubtotal(calcRows.value.map((r) => r.impairmentAmount)))
  const alreadyProvidedTotal = computed(() => calcSubtotal(calcRows.value.map((r) => r.alreadyProvided)))
  const supplementTotal = computed(() =>
    calcSubtotal(calcRows.value.map((r) => Math.max(Number(r.difference) || 0, 0))),
  )
  const overProvisionTotal = computed(() =>
    calcSubtotal(calcRows.value.map((r) => Math.max(-(Number(r.difference) || 0), 0))),
  )
  const hasOverProvision = computed(() =>
    calcRows.value.some((r) => Number(r.difference) < -0.01),
  )

  const categoryTotals = computed<ImpCategoryTotal[]>(() => {
    const map = new Map<string, ImpCategoryTotal>()
    const ensure = (cat: string) => {
      if (!map.has(cat)) {
        map.set(cat, {
          category: cat, bookValue: 0, recoverableAmount: 0, impairmentAmount: 0,
          alreadyProvided: 0, supplement: 0, overProvision: 0, rowCount: 0,
        })
      }
      return map.get(cat)!
    }
    for (const cat of H3_10_ASSET_CATEGORIES) ensure(cat)
    for (const row of calcRows.value) {
      const cat = row.category?.trim() || '未分类'
      const t = ensure(cat)
      t.bookValue += Number(row.bookValue) || 0
      t.recoverableAmount += Number(row.recoverableAmount) || 0
      t.impairmentAmount += Number(row.impairmentAmount) || 0
      t.alreadyProvided += Number(row.alreadyProvided) || 0
      t.supplement += Math.max(Number(row.difference) || 0, 0)
      t.overProvision += Math.max(-(Number(row.difference) || 0), 0)
      t.rowCount += 1
    }
    return [...map.values()].filter(
      (t) => t.rowCount > 0 || (H3_10_ASSET_CATEGORIES as readonly string[]).includes(t.category),
    )
  })

  function _calcGroupRecoverableParts(g: RecoverableGroup): { fvNet: number; dcf: number; recoverable: number } {
    const fvResolved = resolveFairValue(g.fvDisposal as any)
    const disp = calcDisposalTotal(g.fvDisposal as any)
    const fvNet = Math.max(fvResolved.value - disp, 0)
    const ke = calcCostOfEquity(g.waccParams.riskFreeRate, g.waccParams.beta, g.waccParams.marketReturn)
    const waccAt = calcWaccAfterTax(
      g.waccParams.totalDebt, g.waccParams.totalEquity, ke,
      g.waccParams.costOfDebt, g.waccParams.taxRate,
    )
    const ratePct = waccAt > 0
      ? (g.dcfAssumptions.usePreTaxRate ? calcPreTaxDiscountRate(waccAt, g.waccParams.taxRate) : waccAt)
      : g.dcfAssumptions.discountRate
    const r = ratePct / 100
    const gr = g.dcfAssumptions.terminalGrowth / 100
    const years = Math.max(0, Math.floor(g.dcfAssumptions.forecastYears) || 0)
    const baseNet = g.dcfAssumptions.annualRent - g.dcfAssumptions.annualCost
    const cfs: number[] = []
    for (let y = 1; y <= years; y++) {
      cfs.push(baseNet + (y === years ? g.dcfAssumptions.residualValue : 0))
    }
    const pv = calcDcfPresentValue(cfs, r)
    let dcf = pv
    if (r > gr && years > 0) {
      dcf += calcTerminalValue(baseNet * (1 + gr), r, gr) / Math.pow(1 + r, years)
    }
    return { fvNet, dcf, recoverable: Math.max(fvNet, dcf) }
  }

  const dcfSyncChecks = computed<DcfSyncCheck[]>(() => {
    const groupByName = new Map(groups.value.map((g) => [(g.name || g.fvDisposal.assetName || '').trim(), g]))
    return calcRows.value.map((row) => {
      const needTest = row.hasIndication === 'Y' || (Number(row.bookValue) || 0) > 0
      const rowName = (row.assetName || '').trim()
      const g = groupByName.get(rowName)
      const h10Dcf = Number(row.dcfValue) || 0
      const h10Fv = Number(row.fairValueLessDisposal) || 0
      if (!g) {
        return {
          rowId: row.rowId, assetName: row.assetName,
          h10Dcf, h11Dcf: 0, h10Fv, h11Fv: 0,
          hasH11Group: false, dcfSynced: false, fvSynced: false,
          status: needTest && row.hasIndication === 'Y' ? 'missing-h11' as const : 'no-test' as const,
        }
      }
      const { fvNet, dcf } = _calcGroupRecoverableParts(g)
      const dcfSynced = Math.abs(h10Dcf - dcf) < 0.01
      const fvSynced = Math.abs(h10Fv - fvNet) < 0.01
      let status: DcfSyncCheck['status'] = 'no-test'
      if (row.hasIndication === 'Y' || h10Dcf > 0 || dcf > 0) {
        status = dcfSynced && fvSynced ? 'synced' : 'stale'
      }
      return {
        rowId: row.rowId, assetName: row.assetName,
        h10Dcf, h11Dcf: dcf, h10Fv, h11Fv: fvNet,
        hasH11Group: true, dcfSynced, fvSynced, status,
      }
    })
  })

  const dcfSyncSummary = computed(() => {
    const checks = dcfSyncChecks.value
    const stale = checks.filter((c) => c.status === 'stale').length
    const missing = checks.filter((c) => c.status === 'missing-h11').length
    const synced = checks.filter((c) => c.status === 'synced').length
    return {
      stale, missing, synced,
      ok: stale === 0 && missing === 0,
      message: stale || missing
        ? `④回写校验：${stale} 行过期，${missing} 行缺 H3-11`
        : (synced > 0 ? `④已与 H3-11 一致（${synced} 行）` : '暂无④回写校验项'),
    }
  })

  const stocktakeConcernItems = computed<StocktakeImpairmentConcern[]>(() => {
    const raw = getValue(ITEM_H310_STOCKTAKE_CONCERNS)
    if (raw && typeof raw === 'object' && !Array.isArray(raw)) {
      return parseStocktakeConcernPayload(raw)
    }
    if (typeof raw === 'string') {
      try {
        return parseStocktakeConcernPayload(JSON.parse(raw))
      } catch {
        return []
      }
    }
    return []
  })

  const prepValidation = computed<ImpPrepValidation>(() => {
    const messages: string[] = []
    if (hasImpairmentSigns.value && calcRows.value.every((r) => r.hasIndication !== 'Y')) {
      messages.push('CAS8 迹象存在「是」，但测算行均未勾选行级「有迹象」')
    }
    for (const r of calcRows.value) {
      if (r.hasIndication === 'Y' && r.recoverableAmount <= 0 && r.bookValue > 0) {
        messages.push(`「${r.assetName || r.category || '未命名'}」有迹象但可收回金额未测算（请完成 H3-11）`)
        break
      }
    }
    if (hasOverProvision.value) {
      messages.push('存在⑦>⑥——核查是否处置结转；CAS8第17条不得转回损益')
    }
    const staleDcf = dcfSyncChecks.value.filter((c) => c.status === 'stale')
    if (staleDcf.length > 0) messages.push(`${staleDcf.length} 行④DCF 与 H3-11 不一致，请强制回写`)
    const missingH11 = dcfSyncChecks.value.filter((c) => c.status === 'missing-h11')
    if (missingH11.length > 0) messages.push(`${missingH11.length} 行有迹象但 H3-11 无同名物业组`)
    if (stocktakeConcernItems.value.length > 0 && calcRows.value.every((r) => r.hasIndication !== 'Y')) {
      messages.push(`H3-9 推送减值关注 ${stocktakeConcernItems.value.length} 项，请「自 H3-9 引入」`)
    }
    const unclassified = calcRows.value.filter((r) => !r.category?.trim()).length
    if (unclassified > 0) messages.push(`${unclassified} 行未填投资性房地产类别`)
    return { ok: messages.length === 0, messages }
  })

  function buildConclusionDraft(): string {
    const yCount = signYesCount.value
    const groupCount = calcRows.value.length
    const req = totalImpairment.value
    const booked = alreadyProvidedTotal.value
    const supp = supplementTotal.value
    const over = overProvisionTotal.value
    let handle = '差额不重大/无需调整'
    if (supp > 0.01) handle = '已建议调整补提'
    else if (over > 0.01) handle = '已计提大于应计提，需核查不得转回'
    return [
      `（1）减值迹象识别：CAS8 六项判断已完成，其中「是」${yCount}项。`,
      `（2）共测试 ${groupCount} 个项目；应计提⑥ ${req.toFixed(2)}，已计提⑦ ${booked.toFixed(2)}，本期应补提⑧ ${supp.toFixed(2)}${over > 0.01 ? `，多提 ${over.toFixed(2)}` : ''}。`,
      `（3）差异处理：${handle}。`,
      `（4）CAS8第17条：${over > 0.01 ? '已关注多提/潜在转回，详见审计说明' : '未发现不当转回损益情形'}。`,
      `（5）投资性房地产减值准备在重大方面${supp < 0.01 && over < 0.01 ? '公允反映' : '存在需关注事项/错报风险'}。`,
    ].join('\n')
  }

  const activeGroup: ComputedRef<RecoverableGroup> = computed(() =>
    groups.value.find((g) => g.groupId === activeGroupId.value) ?? groups.value[0] ?? _defaultGroup(),
  )

  const assumptions = computed(() => activeGroup.value.dcfAssumptions)
  const fvDisposal = computed(() => activeGroup.value.fvDisposal)
  const waccParams = computed(() => activeGroup.value.waccParams)
  const bookValue = computed({
    get: () => activeGroup.value.bookValue,
    set: (v: number) => {
      activeGroup.value.bookValue = v
      _persistGroups()
    },
  })

  // ─── Active group aliases ────────────────────────────────────────────────────

  const fairValueSourcesAvailable = computed<FairValueSourceRow[]>(() =>
    _parseCrossSheetRows(getValue, ITEM_H38_ROWS)
      .map((r) => ({
        rowId: r.rowId ?? '',
        assetName: r.assetName ?? '',
        appraisalValue: Number(r.appraisalValue ?? r.assessedValue) || 0,
        marketRef: Number(r.marketRef) || 0,
        bookValue: Number(r.bookValue) || 0,
        discountRate: Number(r.discountRate) || 0,
        rentAssumption: Number(r.rentAssumption ?? r.rentalAssumption) || 0,
      }))
      .filter((r) => r.assetName || r.appraisalValue > 0),
  )

  const rentalSourcesAvailable = computed<RentalSourceRow[]>(() =>
    _parseCrossSheetRows(getValue, ITEM_H14_ROWS, ITEM_H14_ROWS_LEGACY)
      .map((r) => ({
        rowId: r.rowId ?? '',
        assetName: r.assetName ?? '',
        expectedRent: Number(r.expectedRent) || 0,
        annualRent: Number(r.annualRent) || (Number(r.monthlyRent) || 0) * 12,
        monthlyRent: Number(r.monthlyRent) || 0,
      }))
      .filter((r) => r.assetName),
  )

  // ─── H3-10 ops ───────────────────────────────────────────────────────────────

  const k11Reconcile = ref<K11ReconcileResult>({
    h10Supplement: 0,
    k11Amount: null,
    diff: null,
    isMatch: true,
    source: '',
    message: '尚未核对 K11',
  })

  function _publishImpairmentToK11(supplement: number): void {
    try {
      if (typeof window === 'undefined') return
      window.dispatchEvent(new CustomEvent('impairment:calculated', {
        detail: {
          wpCode: 'H3',
          wp_code: 'H3',
          sheetCode: 'H3-10',
          sheet: '减值测算表H3-10',
          totalRequiredProvision: supplement,
          amount: supplement,
          label: '本期补提⑧',
          impairmentAmount: totalImpairment.value,
        },
      }))
    } catch { /* silent */ }
  }

  function _persistCalcRows(): void {
    setValue(ITEM_CALC, calcRows.value)
    const supp = supplementTotal.value
    setValue(ITEM_H310_SUPPLEMENT_TOTAL, supp)
    _publishImpairmentToK11(supp)
  }

  function updateSign(_index: number, _row?: any): void {
    setValue(ITEM_SIGNS, signs.value)
  }

  function addCalcRow(assetName?: string, category = ''): void {
    calcRows.value.push(_normCalc({
      assetName: assetName ?? '',
      category: category || assetName || '',
      rowId: _newId('imp'),
    }))
    _persistCalcRows()
  }

  function removeCalcRow(rowId: string): void {
    const idx = calcRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      calcRows.value.splice(idx, 1)
      _persistCalcRows()
    }
  }

  function updateCalcRow(index: number, field?: keyof ImpairmentCalcRow): void {
    const row = calcRows.value[index]
    if (!row) return
    if (field === 'dcfValue') return
    row.bookValue = Number(row.bookValue) || 0
    row.fairValueLessDisposal = Number(row.fairValueLessDisposal) || 0
    row.alreadyProvided = Number(row.alreadyProvided) || 0
    if (field === 'hasIndication' && row.hasIndication === 'Y' && !row.indicationDesc) {
      const ys = signs.value.filter((s) => s.exists === '是').map((s) => s.indicator.slice(0, 24))
      if (ys.length) row.indicationDesc = ys.join('；')
    }
    _recalcCalcRow(row)
    _persistCalcRows()
  }

  function _applyH11ToCalcRow(row: ImpairmentCalcRow, g: RecoverableGroup): void {
    const { fvNet, dcf, recoverable } = _calcGroupRecoverableParts(g)
    row.fairValueLessDisposal = fvNet
    row.dcfValue = dcf
    row.recoverableAmount = recoverable
    if (g.bookValue > 0 && !row.bookValue) row.bookValue = g.bookValue
    if (!row.indexRef) row.indexRef = 'H3-11'
    if (!row.hasIndication && hasImpairmentSigns.value) row.hasIndication = 'Y'
    _recalcCalcRow(row)
  }

  /** 强制自 H3-11 全部物业组回写 ③/④ 至 H3-10 */
  function forceSyncFromH11(): { updated: number; created: number; unmatched: string[] } {
    let updated = 0
    let created = 0
    const unmatched: string[] = []
    const matchedNames = new Set<string>()

    for (const g of groups.value) {
      const name = (g.name || g.fvDisposal.assetName || '').trim()
      if (!name) continue
      let row = calcRows.value.find((r) => _matchName(r.assetName, name))
      if (!row) {
        addCalcRow(name, H3_10_ASSET_CATEGORIES[0])
        row = calcRows.value[calcRows.value.length - 1]
        created++
      } else {
        updated++
      }
      _applyH11ToCalcRow(row, g)
      matchedNames.add(name)
    }

    for (const row of calcRows.value) {
      if (row.hasIndication === 'Y' && !matchedNames.has((row.assetName || '').trim())) {
        unmatched.push(row.assetName || row.category)
      }
    }
    _persistCalcRows()
    return { updated, created, unmatched }
  }

  /** 从 H3-2 成本明细带入 ②账面价值、⑦已计提（按资产名称匹配） */
  function importBookValuesFromH32(): { updated: number; created: number; skipped: number; message: string } {
    const seeds = parseH32CostDetailRows(getValue)
    if (!seeds.length) {
      return { updated: 0, created: 0, skipped: 0, message: 'H3-2 成本明细无数据，请先编制 H3-2 明细表' }
    }
    let updated = 0
    let created = 0
    let skipped = 0
    for (const s of seeds) {
      if (s.bookValue <= 0 && s.alreadyProvided <= 0) {
        skipped++
        continue
      }
      let row = calcRows.value.find((r) => _matchName(r.assetName, s.assetName))
      if (!row) {
        calcRows.value.push(_normCalc({
          assetName: s.assetName,
          category: s.category,
          rowId: _newId('imp'),
          bookValue: s.bookValue,
          alreadyProvided: s.alreadyProvided,
          indexRef: 'H3-2',
        }))
        row = calcRows.value[calcRows.value.length - 1]
        created++
      } else {
        if (s.bookValue > 0) row.bookValue = s.bookValue
        if (s.alreadyProvided > 0) row.alreadyProvided = s.alreadyProvided
        if (!row.category) row.category = s.category
        if (!row.indexRef) row.indexRef = 'H3-2'
        _recalcCalcRow(row)
        updated++
      }
    }
    _persistCalcRows()
    return {
      updated,
      created,
      skipped,
      message: `已从 H3-2 带入：更新 ${updated}、新增 ${created}${skipped ? `、跳过 ${skipped}` : ''}`,
    }
  }

  /** 自 H3-9 推送的减值关注引入测算行 */
  function importFromStocktakeConcerns(): { added: number; refreshed: number; message: string } {
    const concerns = stocktakeConcernItems.value
    if (!concerns.length) {
      return { added: 0, refreshed: 0, message: 'H3-9 暂无减值关注线索，请先在 H3-9 执行「推送减值关注」' }
    }
    let added = 0
    let refreshed = 0
    const idleSign = signs.value.find((s) => s.id === 'idle_disposal')
    if (idleSign && idleSign.exists !== '是') {
      idleSign.exists = '是'
      idleSign.evidence = idleSign.evidence || `H3-9 推送 ${concerns.length} 项减值关注`
      setValue(ITEM_SIGNS, signs.value)
    }
    for (const c of concerns) {
      let row = calcRows.value.find((r) => _matchName(r.assetName, c.assetName))
      if (!row) {
        calcRows.value.push(_normCalc({
          assetName: c.assetName,
          rowId: _newId('imp'),
          hasIndication: 'Y',
          indicationDesc: c.reason,
          bookValue: c.bookValue,
          indexRef: 'H3-9',
          remark: `来源H3-9/${c.checkRowId}`,
        }))
        added++
      } else {
        row.hasIndication = 'Y'
        row.indicationDesc = row.indicationDesc || c.reason
        if (c.bookValue > 0 && !row.bookValue) row.bookValue = c.bookValue
        if (!row.indexRef) row.indexRef = 'H3-9'
        row.remark = row.remark || `来源H3-9/${c.checkRowId}`
        _recalcCalcRow(row)
        refreshed++
      }
    }
    _persistCalcRows()
    return {
      added,
      refreshed,
      message: `自 H3-9 引入：新增 ${added}、刷新 ${refreshed}，共 ${concerns.length} 项`,
    }
  }

  /** 与 K11 投资性房地产减值本期发生额交叉核对 */
  async function reconcileWithK11(projectId: string): Promise<K11ReconcileResult> {
    const h10Supplement = supplementTotal.value
    const empty: K11ReconcileResult = {
      h10Supplement,
      k11Amount: null,
      diff: null,
      isMatch: true,
      source: '',
      message: 'K11 未取到投资性房地产减值金额',
    }
    if (!projectId) {
      k11Reconcile.value = { ...empty, message: '缺少 projectId，无法核对 K11' }
      return k11Reconcile.value
    }
    try {
      const { api } = await import('@/services/apiProxy')
      const idRes = await api.get<{ wp_id: string }>('/api/custom-query/wp-id-by-code', {
        params: { project_id: projectId, wp_code: 'K11' },
        _silent: true,
      } as any)
      const k11WpId = (idRes as any)?.wp_id ?? (idRes as any)?.data?.wp_id
      if (!k11WpId) {
        k11Reconcile.value = { ...empty, message: '项目中未找到 K11 底稿' }
        return k11Reconcile.value
      }
      const res = await api.get(`/api/workpapers/${k11WpId}/checklist-responses`, { _silent: true } as any)
      const list: any[] = Array.isArray(res) ? res : (res?.data ?? [])
      const { amount: k11Amount, source } = extractK11InvestmentPropertyAmount(list)
      if (k11Amount == null) {
        k11Reconcile.value = empty
        return k11Reconcile.value
      }
      const diff = h10Supplement - k11Amount
      const isMatch = Math.abs(diff) < 0.01
      k11Reconcile.value = {
        h10Supplement,
        k11Amount,
        diff,
        isMatch,
        source,
        message: isMatch
          ? `K11 勾稽通过：⑧本期补提 ${h10Supplement.toFixed(2)} = K11 ${k11Amount.toFixed(2)}（${source}）`
          : `K11 勾稽差异：⑧ ${h10Supplement.toFixed(2)} − K11 ${k11Amount.toFixed(2)} = ${diff.toFixed(2)}（${source}）`,
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

  // ─── H3-11 group CRUD ────────────────────────────────────────────────────────

  function setActiveGroup(groupId: string): void {
    if (!groups.value.some((g) => g.groupId === groupId)) return
    activeGroupId.value = groupId
    _persistGroups()
  }

  function addRecoverableGroup(name?: string): RecoverableGroup {
    const g = _defaultGroup(name || `物业-${groups.value.length + 1}`)
    groups.value.push(g)
    activeGroupId.value = g.groupId
    _persistGroups()
    return g
  }

  function removeRecoverableGroup(groupId?: string): void {
    const id = groupId ?? activeGroupId.value
    if (groups.value.length <= 1) return
    const idx = groups.value.findIndex((g) => g.groupId === id)
    if (idx < 0) return
    groups.value.splice(idx, 1)
    if (activeGroupId.value === id) {
      activeGroupId.value = groups.value[Math.max(0, idx - 1)].groupId
    }
    _persistGroups()
  }

  function renameActiveGroup(name: string): void {
    const g = activeGroup.value
    g.name = name
    g.fvDisposal.assetName = name
    _persistGroups()
  }

  /** 从 H3-10 减值测算表同步资产组（按资产名称） */
  function syncGroupsFromH10(): { added: number; updated: number } {
    let added = 0
    let updated = 0
    for (const row of calcRows.value) {
      const name = (row.assetName || '').trim()
      if (!name) continue
      let g = groups.value.find((x) => _matchName(x.name, name))
      if (!g) {
        g = _defaultGroup(name)
        g.bookValue = row.bookValue
        groups.value.push(g)
        added++
      } else {
        g.bookValue = row.bookValue
        updated++
      }
    }
    _persistGroups()
    return { added, updated }
  }

  // ─── H3-8 / H3-14 import ───────────────────────────────────────────────────

  function importFairValueFromH38(rowId?: string): { ok: boolean; message: string } {
    const sources = fairValueSourcesAvailable.value
    if (!sources.length) {
      return { ok: false, message: 'H3-8 无公允价值复核数据，请先编制 H3-8 公允价值复核表' }
    }
    let src = rowId ? sources.find((r) => r.rowId === rowId) : undefined
    if (!src) {
      src = sources.find((r) => _matchName(r.assetName, activeGroup.value.name))
    }
    if (!src) src = sources[0]

    const g = activeGroup.value
    if (src.appraisalValue > 0) {
      g.fvDisposal.activeMarketPrice = src.appraisalValue
      g.fvDisposal.activeMarketNote = `来自 H3-8 评估值（索引 H3-8）`
    }
    if (src.marketRef > 0) {
      g.fvDisposal.estimatedPrice = src.marketRef
      g.fvDisposal.estimatedNote = '来自 H3-8 市场参考价'
    }
    if (src.discountRate > 0) {
      g.dcfAssumptions.discountRate = src.discountRate
    }
    if (src.rentAssumption > 0) {
      g.dcfAssumptions.annualRent = src.rentAssumption * 12
    }
    if (src.bookValue > 0 && !g.bookValue) {
      g.bookValue = src.bookValue
    }
    if (!g.name.trim() || g.name.startsWith('物业-')) {
      g.name = src.assetName
      g.fvDisposal.assetName = src.assetName
    }
    g.sourceH38RowId = src.rowId
    _persistGroups()
    return {
      ok: true,
      message: `已从 H3-8 带入「${src.assetName}」评估值 ${src.appraisalValue.toLocaleString('zh-CN')}`,
    }
  }

  function importRentalFromH14(rowId?: string): { ok: boolean; message: string } {
    const sources = rentalSourcesAvailable.value
    if (!sources.length) {
      return { ok: false, message: 'H3-14 无租金合同数据，请先编制 H3-14 租金收入测算表' }
    }
    let src = rowId ? sources.find((r) => r.rowId === rowId) : undefined
    if (!src) {
      src = sources.find((r) => _matchName(r.assetName, activeGroup.value.name))
    }
    if (!src) src = sources[0]

    const g = activeGroup.value
    const annual = src.expectedRent > 0 ? src.expectedRent : src.annualRent
    if (annual <= 0) {
      return { ok: false, message: `「${src.assetName}」H3-14 应计租金为零，请检查合同行` }
    }
    g.dcfAssumptions.annualRent = annual
    if (!g.name.trim() || g.name.startsWith('物业-')) {
      g.name = src.assetName
      g.fvDisposal.assetName = src.assetName
    }
    g.sourceH14RowId = src.rowId
    _persistGroups()
    return {
      ok: true,
      message: `已从 H3-14 带入「${src.assetName}」年租金 ${annual.toLocaleString('zh-CN')}`,
    }
  }

  /** 批量：为 H3-8 每行创建/更新资产组并带入公允价值 */
  function importAllGroupsFromH38(): { ok: boolean; message: string; count: number } {
    const sources = fairValueSourcesAvailable.value
    if (!sources.length) {
      return { ok: false, message: 'H3-8 无数据', count: 0 }
    }
    let count = 0
    for (const src of sources) {
      let g = groups.value.find((x) => _matchName(x.name, src.assetName))
      if (!g) {
        g = _defaultGroup(src.assetName || `物业-${groups.value.length + 1}`)
        groups.value.push(g)
      }
      if (src.appraisalValue > 0) {
        g.fvDisposal.activeMarketPrice = src.appraisalValue
        g.fvDisposal.activeMarketNote = '来自 H3-8 评估值'
      }
      if (src.marketRef > 0) {
        g.fvDisposal.estimatedPrice = src.marketRef
      }
      if (src.bookValue > 0) g.bookValue = src.bookValue
      g.sourceH38RowId = src.rowId
      count++
    }
    _persistGroups()
    return { ok: true, message: `已从 H3-8 同步 ${count} 个物业`, count }
  }

  // ─── H3-11 WACC / DCF computed（基于当前资产组） ─────────────────────────────

  const costOfEquity = computed(() =>
    calcCostOfEquity(waccParams.value.riskFreeRate, waccParams.value.beta, waccParams.value.marketReturn),
  )

  const waccAfterTax = computed(() =>
    calcWaccAfterTax(
      waccParams.value.totalDebt,
      waccParams.value.totalEquity,
      costOfEquity.value,
      waccParams.value.costOfDebt,
      waccParams.value.taxRate,
    ),
  )

  const preTaxDiscountRate = computed(() =>
    calcPreTaxDiscountRate(waccAfterTax.value, waccParams.value.taxRate),
  )

  const effectiveDiscountRate = computed(() => {
    if (waccAfterTax.value > 0) {
      return assumptions.value.usePreTaxRate ? preTaxDiscountRate.value : waccAfterTax.value
    }
    return assumptions.value.discountRate
  })

  const fairValueResolved = computed(() => resolveFairValue(fvDisposal.value as any))
  const disposalTotal = computed(() => calcDisposalTotal(fvDisposal.value as any))
  const fairValueLessDisposal = computed(() =>
    Math.max(fairValueResolved.value.value - disposalTotal.value, 0),
  )

  const cashFlowRows = computed<CashFlowRow[]>(() => {
    const a = assumptions.value
    const years = Math.max(0, Math.floor(Number(a.forecastYears) || 0))
    const r = effectiveDiscountRate.value / 100
    const revenue = Number(a.annualRent) || 0
    const cost = Number(a.annualCost) || 0
    const residual = Number(a.residualValue) || 0
    const out: CashFlowRow[] = []
    for (let y = 1; y <= years; y++) {
      const net = revenue - cost + (y === years ? residual : 0)
      const df = r <= -1 ? 0 : 1 / Math.pow(1 + r, y)
      out.push({
        year: y,
        yearLabel: y === years && residual > 0 ? `第${y}年+残值` : `第${y}年`,
        revenue,
        cost,
        netCashFlow: net,
        discountFactor: df,
        presentValue: net * df,
      })
    }
    return out
  })

  const dcfResult = computed<DcfResult>(() => {
    const a = assumptions.value
    const r = effectiveDiscountRate.value / 100
    const g = (Number(a.terminalGrowth) || 0) / 100
    const cfs = cashFlowRows.value.map((row) => row.netCashFlow)
    const baseNet = (Number(a.annualRent) || 0) - (Number(a.annualCost) || 0)
    const pvCashFlows = calcDcfPresentValue(cfs, r)
    const termCF = cfs.length > 0 ? baseNet * (1 + g) : 0
    const tv = termCF > 0 && r > g ? calcTerminalValue(termCF, r, g) : 0
    const tvDiscounted = cfs.length > 0 ? tv / Math.pow(1 + r, cfs.length) : 0
    return {
      pvCashFlows,
      terminalCashFlow: termCF,
      terminalValue: tv,
      terminalValueDiscounted: tvDiscounted,
      totalPV: pvCashFlows + tvDiscounted,
      rateInvalid: r <= g || r <= 0,
    }
  })

  const dcfTotal = computed(() => dcfResult.value.totalPV)

  const recoverableAmount = computed(() =>
    Math.max(fairValueLessDisposal.value, dcfResult.value.totalPV),
  )

  const recoverableSource = computed(() => {
    if (recoverableAmount.value <= 0) return '未测算'
    if (dcfResult.value.totalPV > fairValueLessDisposal.value) return '预计未来现金流量现值(DCF)'
    if (fairValueLessDisposal.value > dcfResult.value.totalPV) return '公允价值减处置费用净额'
    return '两者相等'
  })

  const impliedImpairment = computed(() =>
    Math.max(bookValue.value - recoverableAmount.value, 0),
  )

  function _computeRecoverableAt(discountRatePct: number, growthPct: number): number {
    const a = assumptions.value
    const years = Math.max(0, Math.floor(Number(a.forecastYears) || 0))
    const r = (discountRatePct || 0) / 100
    const g = (growthPct || 0) / 100
    const revenue = Number(a.annualRent) || 0
    const cost = Number(a.annualCost) || 0
    const residual = Number(a.residualValue) || 0
    const baseNet = revenue - cost
    if (years <= 0 || r <= 0) return Math.max(fairValueLessDisposal.value, 0)

    const cfs: number[] = []
    for (let y = 1; y <= years; y++) {
      cfs.push(baseNet + (y === years ? residual : 0))
    }
    const pv = calcDcfPresentValue(cfs, r)
    let totalDcf = pv
    if (r > g) {
      const terminal = calcTerminalValue(baseNet * (1 + g), r, g)
      totalDcf += terminal / Math.pow(1 + r, years)
    }
    return Math.max(fairValueLessDisposal.value, totalDcf)
  }

  const sensitivityCols = computed<string[]>(() => {
    const g = Number(assumptions.value.terminalGrowth) || 0
    return [g - 1, g, g + 1].map((x) => x.toFixed(1))
  })

  const sensitivityRows = computed(() => {
    const dr = effectiveDiscountRate.value || Number(assumptions.value.discountRate) || 0
    return [dr - 1, dr, dr + 1].map((d) => {
      const row: Record<string, number | string> = { label: `${d.toFixed(1)}%` }
      for (const col of sensitivityCols.value) {
        row[col] = _computeRecoverableAt(d, parseFloat(col))
      }
      return row
    })
  })

  const terminalSensitivityByRate = computed<TerminalSensitivityPoint[]>(() =>
    calcTerminalSensitivityAxis({
      cashFlows: cashFlowRows.value.map((r) => r.netCashFlow),
      baseRatePct: effectiveDiscountRate.value,
      baseGrowthPct: assumptions.value.terminalGrowth,
      terminalCashFlow: dcfResult.value.terminalCashFlow,
      fairValueLessDisposal: fairValueLessDisposal.value,
      axis: 'rate',
      offsetsPct: [-2, -1, 0, 1, 2],
    }),
  )

  const terminalSensitivityByGrowth = computed<TerminalSensitivityPoint[]>(() =>
    calcTerminalSensitivityAxis({
      cashFlows: cashFlowRows.value.map((r) => r.netCashFlow),
      baseRatePct: effectiveDiscountRate.value,
      baseGrowthPct: assumptions.value.terminalGrowth,
      terminalCashFlow: dcfResult.value.terminalCashFlow,
      fairValueLessDisposal: fairValueLessDisposal.value,
      axis: 'growth',
      offsetsPct: [-1, -0.5, 0, 0.5, 1],
    }),
  )

  function updateAssumptions(_a?: any): void {
    _persistGroups()
  }

  function updateFvDisposal(): void {
    _persistGroups()
  }

  function updateWaccParams(): void {
    _persistGroups()
  }

  function _calcGroupRecoverable(g: RecoverableGroup): number {
    return _calcGroupRecoverableParts(g).recoverable
  }

  function pushRecoverableToH10(assetName?: string): { ok: boolean; message: string } {
    const name = assetName || activeGroup.value.name || fvDisposal.value.assetName || '投资性房地产'
    const { fvNet, dcf, recoverable } = _calcGroupRecoverableParts(activeGroup.value)
    if (recoverable <= 0) {
      return { ok: false, message: '可收回金额尚未测算，请先完成公允净额或 DCF 测算' }
    }
    let idx = calcRows.value.findIndex((r) => _matchName(r.assetName, name))
    if (idx < 0) {
      idx = calcRows.value.findIndex((r) => !r.assetName || r.assetName === r.category)
    }
    if (idx < 0) {
      addCalcRow(name, H3_10_ASSET_CATEGORIES[0])
      idx = calcRows.value.length - 1
    }
    const row = calcRows.value[idx]
    if (!row.assetName || row.assetName === row.category) row.assetName = name
    row.fairValueLessDisposal = fvNet
    row.dcfValue = dcf
    row.recoverableAmount = recoverable
    if (!row.indexRef) row.indexRef = 'H3-11'
    if (!row.hasIndication && hasImpairmentSigns.value) row.hasIndication = 'Y'
    _recalcCalcRow(row)
    _persistCalcRows()
    return {
      ok: true,
      message: `已回写「${name}」③=${fvNet.toLocaleString('zh-CN')} ④=${dcf.toLocaleString('zh-CN')} ⑤=${recoverable.toLocaleString('zh-CN')} 至 H3-10`,
    }
  }

  function pushAllGroupsToH10(): { ok: boolean; message: string; count: number } {
    let count = 0
    for (const g of groups.value) {
      const { fvNet, dcf, recoverable } = _calcGroupRecoverableParts(g)
      if (recoverable <= 0) continue
      const name = g.name || g.fvDisposal.assetName
      if (!name) continue
      let idx = calcRows.value.findIndex((r) => _matchName(r.assetName, name))
      if (idx < 0) {
        addCalcRow(name, H3_10_ASSET_CATEGORIES[0])
        idx = calcRows.value.length - 1
      }
      const row = calcRows.value[idx]
      row.bookValue = row.bookValue || g.bookValue
      row.fairValueLessDisposal = fvNet
      row.dcfValue = dcf
      row.recoverableAmount = recoverable
      if (!row.indexRef) row.indexRef = 'H3-11'
      _recalcCalcRow(row)
      count++
    }
    _persistCalcRows()
    return {
      ok: count > 0,
      message: count > 0 ? `已回写 ${count} 个物业 ③④⑤ 至 H3-10` : '无可回写数据',
      count,
    }
  }

  watch(allResponses, () => loadData(), { immediate: true })

  return {
    signs, calcRows,
    impairmentSigns: signs,
    impairmentCalcRows: calcRows,
    hasImpairmentSigns, signYesCount, totalImpairment,
    alreadyProvidedTotal, supplementTotal, overProvisionTotal, hasOverProvision,
    categoryTotals, prepValidation, dcfSyncChecks, dcfSyncSummary,
    H3_10_ASSET_CATEGORIES,
    updateSign, addCalcRow, removeCalcRow, updateCalcRow,
    forceSyncFromH11, buildConclusionDraft,
    importBookValuesFromH32, importFromStocktakeConcerns, reconcileWithK11,
    stocktakeConcernItems, k11Reconcile,
    groups, activeGroupId, activeGroup, bookValue,
    assumptions, fvDisposal, waccParams,
    fairValueSourcesAvailable, rentalSourcesAvailable,
    cashFlowRows, dcfResult, dcfTotal,
    costOfEquity, waccAfterTax, preTaxDiscountRate, effectiveDiscountRate,
    fairValueResolved, disposalTotal, fairValueLessDisposal,
    recoverableAmount, recoverableSource, impliedImpairment,
    sensitivityRows, sensitivityCols,
    terminalSensitivityByRate, terminalSensitivityByGrowth,
    setActiveGroup, addRecoverableGroup, removeRecoverableGroup, renameActiveGroup,
    syncGroupsFromH10,
    importFairValueFromH38, importRentalFromH14, importAllGroupsFromH38,
    updateAssumptions, updateFvDisposal, updateWaccParams,
    pushRecoverableToH10, pushAllGroupsToH10,
    loadData,
  }
}

export default useH3Impairment
