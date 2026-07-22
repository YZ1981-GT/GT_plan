/**
 * useH1Impairment — H1-14~15 减值 composable
 *
 * H1-14：减值迹象6项判断 + 测算表
 * H1-15：多资产组切换 + 公允净额 + DCF/WACC + 可收回金额MAX
 *       + 敏感性矩阵 + 终值单独敏感轴 + H1-4闲置清单带入账面
 *
 * Spec: .kiro/specs/h1-fixed-assets/
 * Task: 3.14
 * Requirements: 13.1-13.10 / 17.1
 */
import { ref, computed, watch, type Ref } from 'vue'
import type { ChecklistItem } from './useH1FormData'
import { calcDcfPresentValue, calcTerminalValue } from './useH1DepreciationEngine'
import { calcSubtotal } from './useH1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ImpairmentIndication {
  key: string
  description: string
  result: 'Y' | 'N' | 'NA' | ''
  explanation: string
}

/** 源模板 H1-14 固定资产类别（分类汇总行） */
export const H1_14_ASSET_CATEGORIES = [
  '房屋及建筑物',
  '机器设备',
  '运输设备',
  '办公设备',
  '其他设备',
] as const

export type H1_14_AssetCategory = (typeof H1_14_ASSET_CATEGORIES)[number] | string

export interface ImpairmentCalcRow {
  rowId: string
  /** 固定资产类别（用于分类汇总） */
  category: H1_14_AssetCategory
  /** 项目名称 / 资产组名称 */
  assetGroup: string
  /** 行级：是否存在减值迹象 */
  hasIndication: 'Y' | 'N' | ''
  /** ① 减值迹象描述 */
  indicationDesc: string
  /** ② 账面价值（原值−累计折旧，未扣减值） */
  bookValue: number
  /** ③ 公允价值减处置费用净额 */
  fairValueLessDisposal: number
  /** ④ 预计未来现金流量现值 */
  dcfValue: number
  /** ⑤ 可收回金额 = MAX(③,④) */
  recoverableAmount: number
  /** ⑥ 期末应计提减值 = MAX(②−⑤, 0) */
  impairmentAmount: number
  /** ⑦ 期末账面已计提减值准备 */
  alreadyProvided: number
  /**
   * 原始差异 ⑥−⑦（可为负，用于发现多提/潜在转回）
   * 展示「⑧本期应补提」时取 MAX(difference, 0)
   */
  difference: number
  /** 工作底稿索引号（如 H1-15 / 评估报告） */
  indexRef: string
  remark: string
}

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
  categorySumImpairment: number
  grandImpairment: number
  categorySumAlready: number
  grandAlready: number
}

/** H1-14 行 vs H1-15 ④DCF 回写校验 */
export interface DcfSyncCheck {
  rowId: string
  assetGroup: string
  h14Dcf: number
  h15Dcf: number
  h14Fv: number
  h15Fv: number
  /** 是否在 H1-15 找到同名资产组 */
  hasH15Group: boolean
  /** |h14Dcf - h15Dcf| < 0.01 */
  dcfSynced: boolean
  /** |h14Fv - h15Fv| < 0.01 */
  fvSynced: boolean
  status: 'synced' | 'stale' | 'missing-h15' | 'no-test'
}

export interface K11ReconcileResult {
  h14Supplement: number
  k11Amount: number | null
  diff: number | null
  isMatch: boolean
  source: string
  message: string
}

export interface DcfModelParams {
  discountRate: number
  forecastPeriod: number
  perpetualGrowthRate: number
  cashFlows: number[]
  terminalCashFlow: number
  revenues: number[]
  costs: number[]
  growthRateBasis: string
  industryGrowthRate: number
  marketGrowthRate: number
  countryGrowthRate: number
  usePreTaxRate: boolean
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
  auditNote: string
}

/** H1-15 可收回金额测试资产组（多组切换） */
export interface RecoverableGroup {
  groupId: string
  name: string
  bookValue: number
  /** 来源 H1-4 闲置行 rowId（导入去重） */
  sourceIdleRowId?: string
  alreadyProvided: number
  dcfParams: DcfModelParams
  waccParams: WaccParams
  fvDisposal: FairValueDisposal
  note: string
  conclusion: string
}

export interface SensitivityCell {
  discountRate: number
  growthRate: number
  recoverableAmount: number
}

/** 终值单独敏感轴数据点 */
export interface TerminalSensitivityPoint {
  paramLabel: string
  paramValue: number
  terminalValue: number
  terminalValueDiscounted: number
  forecastPv: number
  totalDcf: number
  recoverableAmount: number
  invalid: boolean
}

/** H1-4 闲置资产（供导入） */
export interface IdleAssetImport {
  rowId: string
  name: string
  netValue: number
  impairmentAmount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_PREFIX_14 = 'H1-14'
const ITEM_PREFIX_15 = 'H1-15'

const INDICATION_DEFINITIONS: Pick<ImpairmentIndication, 'key' | 'description'>[] = [
  { key: 'market_decline', description: '资产的市价当期大幅度下跌，其跌幅明显高于因时间的推移或者正常使用而预计的下跌' },
  { key: 'tech_change', description: '企业经营所处的经济、技术或者法律等环境以及资产所处的市场在当期或者将在近期发生重大变化' },
  { key: 'rate_increase', description: '市场利率或者其他市场投资报酬率在当期已经提高，从而影响企业计算资产预计未来现金流量现值的折现率' },
  { key: 'obsolescence', description: '有证据表明资产已经陈旧过时或者其实体已经损坏' },
  { key: 'idle_abandoned', description: '资产已经或者将被闲置、终止使用或者计划提前处置' },
  { key: 'underperform', description: '企业内部报告的证据表明资产的经济绩效已经低于或者将低于预期' },
]

function _newId(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 6)}`
}

function _defaultDcfParams(): DcfModelParams {
  return {
    discountRate: 10,
    forecastPeriod: 5,
    perpetualGrowthRate: 2,
    cashFlows: [0, 0, 0, 0, 0],
    terminalCashFlow: 0,
    revenues: [0, 0, 0, 0, 0],
    costs: [0, 0, 0, 0, 0],
    growthRateBasis: '',
    industryGrowthRate: 0,
    marketGrowthRate: 0,
    countryGrowthRate: 0,
    usePreTaxRate: true,
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
    auditNote: '',
  }
}

function _defaultGroup(name = '资产组-1'): RecoverableGroup {
  return {
    groupId: _newId('cgu'),
    name,
    bookValue: 0,
    alreadyProvided: 0,
    dcfParams: _defaultDcfParams(),
    waccParams: _defaultWaccParams(),
    fvDisposal: _defaultFvDisposal(name),
    note: '',
    conclusion: '',
  }
}

// ─── Pure helpers ────────────────────────────────────────────────────────────

export function calcCostOfEquity(rf: number, beta: number, rm: number): number {
  return rf + beta * (rm - rf)
}

export function calcWaccAfterTax(
  totalDebt: number,
  totalEquity: number,
  costOfEquity: number,
  costOfDebt: number,
  taxRate: number,
): number {
  const total = totalDebt + totalEquity
  if (total <= 0) return 0
  const eRatio = totalEquity / total
  const dRatio = totalDebt / total
  const t = taxRate / 100
  return eRatio * costOfEquity + dRatio * costOfDebt * (1 - t)
}

export function calcPreTaxDiscountRate(waccAfterTax: number, taxRate: number): number {
  const t = taxRate / 100
  if (t >= 1) return waccAfterTax
  return waccAfterTax / (1 - t)
}

export function resolveFairValue(fv: FairValueDisposal): { value: number; source: string } {
  if (fv.salesAgreementPrice > 0) return { value: fv.salesAgreementPrice, source: '销售协议价格' }
  if (fv.activeMarketPrice > 0) return { value: fv.activeMarketPrice, source: '活跃市场价格' }
  if (fv.estimatedPrice > 0) return { value: fv.estimatedPrice, source: '估计价格' }
  return { value: 0, source: '未确定' }
}

export function calcDisposalTotal(fv: FairValueDisposal): number {
  return (fv.legalFees || 0) + (fv.relatedTaxes || 0) + (fv.transportCosts || 0)
    + (fv.directCosts || 0) + (fv.otherCosts || 0)
}

/**
 * 终值单独敏感轴：固定另一参数，对折现率或增长率做单轴扰动，只观察终值现值变化。
 * @param axis 'rate' | 'growth'
 * @param offsets 百分数偏移（如 [-2,-1,0,1,2] 表示百分点）
 */
export function calcTerminalSensitivityAxis(opts: {
  cashFlows: number[]
  baseRatePct: number
  baseGrowthPct: number
  terminalCashFlow: number
  fairValueLessDisposal: number
  axis: 'rate' | 'growth'
  offsetsPct: number[]
}): TerminalSensitivityPoint[] {
  const { cashFlows, baseRatePct, baseGrowthPct, terminalCashFlow, fairValueLessDisposal, axis, offsetsPct } = opts
  const lastCf = cashFlows.length > 0 ? cashFlows[cashFlows.length - 1] : 0
  const n = cashFlows.length

  return offsetsPct.map((off) => {
    const ratePct = axis === 'rate' ? baseRatePct + off : baseRatePct
    const growthPct = axis === 'growth' ? baseGrowthPct + off : baseGrowthPct
    const r = ratePct / 100
    const g = growthPct / 100
    const invalid = r <= g || r <= 0
    const forecastPv = invalid ? 0 : calcDcfPresentValue(cashFlows, r)
    const termCF = terminalCashFlow > 0 ? terminalCashFlow : lastCf * (1 + g)
    const tv = !invalid && termCF > 0 ? calcTerminalValue(termCF, r, g) : 0
    const tvDisc = !invalid && n > 0 ? tv / Math.pow(1 + r, n) : 0
    const totalDcf = forecastPv + tvDisc
    return {
      paramLabel: axis === 'rate' ? `折现率 ${ratePct.toFixed(1)}%` : `增长率 ${growthPct.toFixed(1)}%`,
      paramValue: axis === 'rate' ? ratePct : growthPct,
      terminalValue: tv,
      terminalValueDiscounted: tvDisc,
      forecastPv,
      totalDcf,
      recoverableAmount: Math.max(fairValueLessDisposal, totalDcf),
      invalid,
    }
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH1Impairment(
  wpId: Ref<string>,
  projectId: Ref<string>,
  allResponses: Ref<Map<string, ChecklistItem>>,
  options?: {
    crossSheetIdleAssets?: Ref<Array<{ name: string; netValue: number }>>
    onSave?: (itemId: string, value: any) => void
  },
) {
  const indications = ref<ImpairmentIndication[]>([])
  const calcRows = ref<ImpairmentCalcRow[]>([])

  /** 多资产组（H1-15 核心状态） */
  const groups = ref<RecoverableGroup[]>([_defaultGroup()])
  const activeGroupId = ref(groups.value[0].groupId)

  const auditNote = ref('')
  const auditConclusion = ref('')

  // ─── Active group aliases（兼容既有 UI 绑定） ─────────────────────────────

  const activeGroup = computed(() => {
    const g = groups.value.find((x) => x.groupId === activeGroupId.value)
    return g ?? groups.value[0] ?? _defaultGroup()
  })

  const dcfParams = computed(() => activeGroup.value.dcfParams)
  const waccParams = computed(() => activeGroup.value.waccParams)
  const fvDisposal = computed(() => activeGroup.value.fvDisposal)
  const bookValue = computed({
    get: () => activeGroup.value.bookValue,
    set: (v: number) => { activeGroup.value.bookValue = v },
  })
  const recoverableNote = computed({
    get: () => activeGroup.value.note,
    set: (v: string) => { activeGroup.value.note = v },
  })
  const recoverableConclusion = computed({
    get: () => activeGroup.value.conclusion,
    set: (v: string) => { activeGroup.value.conclusion = v },
  })

  // ─── Load / Persist helpers ────────────────────────────────────────────────

  function _parseJson<T>(raw: string | null | undefined, fallback: T): T {
    if (!raw) return fallback
    try {
      const parsed = JSON.parse(raw)
      return parsed ?? fallback
    } catch {
      return fallback
    }
  }

  function _getString(itemId: string): string {
    const item = allResponses.value.get(itemId)
    return (item?.remark ?? item?.conclusion ?? '') as string
  }

  function _normalizeForecastLength(params: DcfModelParams): void {
    const n = Math.max(3, Math.min(10, Number(params.forecastPeriod) || 5))
    params.forecastPeriod = n
    params.revenues = [...(params.revenues || [])]
    params.costs = [...(params.costs || [])]
    params.cashFlows = [...(params.cashFlows || [])]
    while (params.revenues.length < n) params.revenues.push(0)
    while (params.costs.length < n) params.costs.push(0)
    params.revenues = params.revenues.slice(0, n)
    params.costs = params.costs.slice(0, n)
    const hasRevCost = params.revenues.some((v) => v !== 0) || params.costs.some((v) => v !== 0)
    if (hasRevCost || !params.cashFlows.length) {
      params.cashFlows = params.revenues.map((r, i) => (Number(r) || 0) - (Number(params.costs[i]) || 0))
    } else {
      while (params.cashFlows.length < n) params.cashFlows.push(0)
      params.cashFlows = params.cashFlows.slice(0, n)
    }
  }

  function _normalizeGroup(raw: any): RecoverableGroup {
    const name = raw.name ?? raw.fvDisposal?.assetName ?? '资产组'
    const dcf = { ..._defaultDcfParams(), ...(raw.dcfParams || {}) }
    _normalizeForecastLength(dcf)
    return {
      groupId: raw.groupId ?? _newId('cgu'),
      name,
      bookValue: Number(raw.bookValue) || 0,
      sourceIdleRowId: raw.sourceIdleRowId,
      alreadyProvided: Number(raw.alreadyProvided) || 0,
      dcfParams: dcf,
      waccParams: { ..._defaultWaccParams(), ...(raw.waccParams || {}) },
      fvDisposal: { ..._defaultFvDisposal(name), ...(raw.fvDisposal || {}), assetName: raw.fvDisposal?.assetName || name },
      note: raw.note ?? '',
      conclusion: raw.conclusion ?? '',
    }
  }

  function _migrateLegacySingleGroup(): RecoverableGroup {
    const g = _defaultGroup()
    const dcfItem = allResponses.value.get(`${ITEM_PREFIX_15}-dcf-params`)
    if (dcfItem?.remark) {
      Object.assign(g.dcfParams, _parseJson(dcfItem.remark as string, {}))
      _normalizeForecastLength(g.dcfParams)
    }
    const waccItem = allResponses.value.get(`${ITEM_PREFIX_15}-wacc-params`)
    if (waccItem?.remark) Object.assign(g.waccParams, _parseJson(waccItem.remark as string, {}))
    const fvItem = allResponses.value.get(`${ITEM_PREFIX_15}-fv-disposal`)
    if (fvItem?.remark) Object.assign(g.fvDisposal, _parseJson(fvItem.remark as string, {}))
    const bvItem = allResponses.value.get(`${ITEM_PREFIX_15}-book-value`)
    if (bvItem?.remark != null && bvItem.remark !== '') {
      const n = Number(bvItem.remark)
      if (Number.isFinite(n)) g.bookValue = n
    }
    g.note = _getString(`${ITEM_PREFIX_15}-audit-note`)
    g.conclusion = _getString(`${ITEM_PREFIX_15}-audit-conclusion`)
    if (g.fvDisposal.assetName) g.name = g.fvDisposal.assetName
    return g
  }

  function _loadData(): void {
    const indItem = allResponses.value.get(`${ITEM_PREFIX_14}-indications`)
    if (indItem?.remark) {
      const parsed = _parseJson<ImpairmentIndication[] | null>(indItem.remark, null)
      indications.value = Array.isArray(parsed) ? parsed : _buildDefaultIndications()
    } else {
      indications.value = _buildDefaultIndications()
    }

    const calcItem = allResponses.value.get(`${ITEM_PREFIX_14}-calc-rows`)
    if (calcItem?.remark) {
      const parsed = _parseJson<any[] | null>(calcItem.remark, null)
      calcRows.value = Array.isArray(parsed) ? parsed.map(_normalizeCalcRow) : []
    } else {
      calcRows.value = []
    }

    const groupsItem = allResponses.value.get(`${ITEM_PREFIX_15}-groups`)
    if (groupsItem?.remark) {
      const parsed = _parseJson<any[] | null>(groupsItem.remark as string, null)
      if (Array.isArray(parsed) && parsed.length > 0) {
        groups.value = parsed.map(_normalizeGroup)
      } else {
        groups.value = [_migrateLegacySingleGroup()]
      }
    } else {
      groups.value = [_migrateLegacySingleGroup()]
      // 若测算表有多行且遗留单组为空名，用测算表补建组
      if (calcRows.value.length > 1 && !groups.value[0].bookValue) {
        groups.value = calcRows.value.map((row) => {
          const g = _defaultGroup(row.assetGroup || '资产组')
          g.bookValue = row.bookValue
          g.alreadyProvided = row.alreadyProvided
          g.fvDisposal.assetName = row.assetGroup
          return g
        })
      }
    }

    const activeItem = allResponses.value.get(`${ITEM_PREFIX_15}-active-group`)
    const savedActive = activeItem?.remark as string | undefined
    if (savedActive && groups.value.some((g) => g.groupId === savedActive)) {
      activeGroupId.value = savedActive
    } else {
      activeGroupId.value = groups.value[0].groupId
    }

    auditNote.value = _getString(`${ITEM_PREFIX_14}-audit-note`)
    auditConclusion.value = _getString(`${ITEM_PREFIX_14}-audit-conclusion`)
  }

  function _buildDefaultIndications(): ImpairmentIndication[] {
    return INDICATION_DEFINITIONS.map((def) => ({
      ...def,
      result: '' as const,
      explanation: '',
    }))
  }

  /** 按源模板公式重算 ⑤⑥⑧（⑧展示用 MAX(⑥−⑦,0)，difference 保留原始差） */
  function _recalcCalcRow(row: ImpairmentCalcRow): void {
    row.recoverableAmount = Math.max(Number(row.fairValueLessDisposal) || 0, Number(row.dcfValue) || 0)
    row.impairmentAmount = Math.max((Number(row.bookValue) || 0) - row.recoverableAmount, 0)
    row.difference = row.impairmentAmount - (Number(row.alreadyProvided) || 0)
  }

  /** 从 H1-15 资产组计算 ③公允净额 / ④DCF（与 syncAllGroups 同口径） */
  function _calcGroupRecoverable(g: RecoverableGroup): { fvNet: number; dcf: number } {
    const fvResolved = resolveFairValue(g.fvDisposal)
    const disp = calcDisposalTotal(g.fvDisposal)
    const fvNet = Math.max(fvResolved.value - disp, 0)
    const ke = calcCostOfEquity(g.waccParams.riskFreeRate, g.waccParams.beta, g.waccParams.marketReturn)
    const waccAt = calcWaccAfterTax(
      g.waccParams.totalDebt,
      g.waccParams.totalEquity,
      ke,
      g.waccParams.costOfDebt,
      g.waccParams.taxRate,
    )
    const ratePct = waccAt > 0
      ? (g.dcfParams.usePreTaxRate ? calcPreTaxDiscountRate(waccAt, g.waccParams.taxRate) : waccAt)
      : g.dcfParams.discountRate
    const r = ratePct / 100
    const gr = g.dcfParams.perpetualGrowthRate / 100
    const cfs = g.dcfParams.cashFlows
    const pv = calcDcfPresentValue(cfs, r)
    const termCF = g.dcfParams.terminalCashFlow > 0
      ? g.dcfParams.terminalCashFlow
      : (cfs.length ? cfs[cfs.length - 1] * (1 + gr) : 0)
    const tv = termCF > 0 && r > gr ? calcTerminalValue(termCF, r, gr) / Math.pow(1 + r, cfs.length) : 0
    return { fvNet, dcf: pv + tv }
  }

  function _findGroupForCalcRow(row: ImpairmentCalcRow): RecoverableGroup | undefined {
    const name = (row.assetGroup || '').trim()
    if (!name) return undefined
    return groups.value.find((g) => (g.name || '').trim() === name)
  }

  function _normalizeCalcRow(raw: any): ImpairmentCalcRow {
    const book = Number(raw.bookValue) || 0
    const fairVLD = Number(raw.fairValueLessDisposal) || 0
    const dcfVal = Number(raw.dcfValue) || 0
    const already = Number(raw.alreadyProvided) || 0
    const row: ImpairmentCalcRow = {
      rowId: raw.rowId ?? _newId('imp'),
      category: raw.category ?? '',
      assetGroup: raw.assetGroup ?? '',
      hasIndication: raw.hasIndication === 'Y' || raw.hasIndication === 'N' ? raw.hasIndication : '',
      indicationDesc: raw.indicationDesc ?? '',
      bookValue: book,
      fairValueLessDisposal: fairVLD,
      dcfValue: dcfVal,
      recoverableAmount: 0,
      impairmentAmount: 0,
      alreadyProvided: already,
      difference: 0,
      indexRef: raw.indexRef ?? '',
      remark: raw.remark ?? '',
    }
    _recalcCalcRow(row)
    return row
  }

  function _persistGroups(): void {
    options?.onSave?.(`${ITEM_PREFIX_15}-groups`, groups.value)
    options?.onSave?.(`${ITEM_PREFIX_15}-active-group`, activeGroupId.value)
  }

  // ─── H1-4 闲置解析 ─────────────────────────────────────────────────────────

  function parseIdleAssetsFromH4(): IdleAssetImport[] {
    // 优先外部注入
    const injected = options?.crossSheetIdleAssets?.value
    if (injected && injected.length > 0) {
      return injected.map((a, i) => ({
        rowId: `injected-${i}-${a.name}`,
        name: a.name,
        netValue: a.netValue,
        impairmentAmount: 0,
      }))
    }
    const item = allResponses.value.get('H1-4-rows')
    if (!item?.remark) return []
    const rows = _parseJson<any[]>(item.remark as string, [])
    if (!Array.isArray(rows)) return []
    return rows
      .map((row) => ({
        rowId: String(row.rowId ?? ''),
        name: String(row.name || '未命名资产'),
        netValue: Number(row.netValue) || 0,
        impairmentAmount: Number(row.impairmentAmount) || 0,
      }))
      .filter((r) => r.netValue > 0)
  }

  const idleAssetsAvailable = computed(() => parseIdleAssetsFromH4())

  // ─── Computed: WACC / FV / DCF（基于当前资产组） ───────────────────────────

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
      return dcfParams.value.usePreTaxRate ? preTaxDiscountRate.value : waccAfterTax.value
    }
    return dcfParams.value.discountRate
  })

  const fairValueResolved = computed(() => resolveFairValue(fvDisposal.value))
  const disposalTotal = computed(() => calcDisposalTotal(fvDisposal.value))
  const fairValueLessDisposal = computed(() =>
    Math.max(fairValueResolved.value.value - disposalTotal.value, 0),
  )

  const cashFlowRows = computed(() => {
    const r = effectiveDiscountRate.value / 100
    const cfs = dcfParams.value.cashFlows
    return cfs.map((fcf, i) => {
      const year = i + 1
      const df = r <= -1 ? 0 : 1 / Math.pow(1 + r, year)
      return {
        year,
        yearLabel: `第${year}年`,
        revenue: dcfParams.value.revenues[i] ?? 0,
        cost: dcfParams.value.costs[i] ?? 0,
        fcf: fcf ?? 0,
        discountFactor: df,
        presentValue: (fcf ?? 0) * df,
      }
    })
  })

  const dcfResult = computed(() => {
    const r = effectiveDiscountRate.value / 100
    const g = dcfParams.value.perpetualGrowthRate / 100
    const cfs = dcfParams.value.cashFlows.filter((v) => v != null)
    const pvCashFlows = calcDcfPresentValue(cfs, r)
    const termCF = dcfParams.value.terminalCashFlow > 0
      ? dcfParams.value.terminalCashFlow
      : (cfs.length > 0 ? cfs[cfs.length - 1] * (1 + g) : 0)
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

  const recoverableAmount = computed(() =>
    Math.max(fairValueLessDisposal.value, dcfResult.value.totalPV),
  )

  const recoverableSource = computed(() => {
    if (recoverableAmount.value <= 0) return '未测算'
    return recoverableAmount.value === dcfResult.value.totalPV
      ? '预计未来现金流量现值(DCF)'
      : '公允价值减处置费用净额'
  })

  const impliedImpairment = computed(() =>
    Math.max(bookValue.value - recoverableAmount.value, 0),
  )

  // ─── 敏感性：二维矩阵（可收回金额） ───────────────────────────────────────

  const sensitivityMatrix = computed<SensitivityCell[]>(() => {
    const baseRate = effectiveDiscountRate.value / 100
    const baseGrowth = dcfParams.value.perpetualGrowthRate / 100
    const cfs = dcfParams.value.cashFlows
    const lastCf = cfs.length > 0 ? cfs[cfs.length - 1] : 0
    const results: SensitivityCell[] = []
    const rateOffsets = [-0.02, -0.01, 0, 0.01, 0.02]
    const growthOffsets = [-0.01, -0.005, 0, 0.005, 0.01]

    for (const rOff of rateOffsets) {
      for (const gOff of growthOffsets) {
        const r = baseRate + rOff
        const g = baseGrowth + gOff
        if (r <= g || r <= 0) {
          results.push({ discountRate: r * 100, growthRate: g * 100, recoverableAmount: 0 })
          continue
        }
        const pv = calcDcfPresentValue(cfs, r)
        const termCF = dcfParams.value.terminalCashFlow > 0
          ? dcfParams.value.terminalCashFlow
          : lastCf * (1 + g)
        const tv = termCF > 0 ? calcTerminalValue(termCF, r, g) / Math.pow(1 + r, cfs.length) : 0
        results.push({
          discountRate: r * 100,
          growthRate: g * 100,
          recoverableAmount: Math.max(fairValueLessDisposal.value, pv + tv),
        })
      }
    }
    return results
  })

  const sensitivityGrid = computed(() => {
    const rates = [...new Set(sensitivityMatrix.value.map((c) => +c.discountRate.toFixed(2)))].sort((a, b) => a - b)
    const growths = [...new Set(sensitivityMatrix.value.map((c) => +c.growthRate.toFixed(2)))].sort((a, b) => a - b)
    const lookup = new Map(
      sensitivityMatrix.value.map((c) => [`${c.discountRate.toFixed(2)}_${c.growthRate.toFixed(2)}`, c.recoverableAmount]),
    )
    const rows = rates.map((r) => {
      const cells: Record<string, number> = {}
      for (const g of growths) {
        cells[`g_${g}`] = lookup.get(`${r.toFixed(2)}_${g.toFixed(2)}`) ?? 0
      }
      return { label: `${r.toFixed(1)}%`, rate: r, cells }
    })
    return { rates, growths, rows }
  })

  // ─── 终值单独敏感轴 ────────────────────────────────────────────────────────

  const terminalSensitivityByRate = computed(() =>
    calcTerminalSensitivityAxis({
      cashFlows: dcfParams.value.cashFlows,
      baseRatePct: effectiveDiscountRate.value,
      baseGrowthPct: dcfParams.value.perpetualGrowthRate,
      terminalCashFlow: dcfParams.value.terminalCashFlow,
      fairValueLessDisposal: fairValueLessDisposal.value,
      axis: 'rate',
      offsetsPct: [-2, -1, 0, 1, 2],
    }),
  )

  const terminalSensitivityByGrowth = computed(() =>
    calcTerminalSensitivityAxis({
      cashFlows: dcfParams.value.cashFlows,
      baseRatePct: effectiveDiscountRate.value,
      baseGrowthPct: dcfParams.value.perpetualGrowthRate,
      terminalCashFlow: dcfParams.value.terminalCashFlow,
      fairValueLessDisposal: fairValueLessDisposal.value,
      axis: 'growth',
      offsetsPct: [-1, -0.5, 0, 0.5, 1],
    }),
  )

  const hasIndication = computed(() =>
    indications.value.some((ind) => ind.result === 'Y'),
  )

  const rowsNeedingImpairment = computed(() =>
    calcRows.value.filter((r) => r.impairmentAmount > 0 && r.difference > 0.01),
  )

  const impairmentTotal = computed(() => calcSubtotal(calcRows.value.map((r) => r.impairmentAmount)))
  const alreadyProvidedTotal = computed(() => calcSubtotal(calcRows.value.map((r) => r.alreadyProvided)))
  /** 原始合计差 ⑥−⑦（可为负） */
  const totalDiff = computed(() => impairmentTotal.value - alreadyProvidedTotal.value)
  /** ⑧ 本期应补提合计 = MAX(⑥−⑦, 0)（对齐源模板 ⑧≥0） */
  const supplementTotal = computed(() => Math.max(totalDiff.value, 0))
  const overProvisionTotal = computed(() => Math.max(-totalDiff.value, 0))
  const hasOverProvision = computed(() =>
    calcRows.value.some((r) => Number(r.difference) < -0.01),
  )

  /** 按固定资产类别分类汇总（源模板合计下分项） */
  const categoryTotals = computed<ImpCategoryTotal[]>(() => {
    const map = new Map<string, ImpCategoryTotal>()
    const ensure = (cat: string) => {
      if (!map.has(cat)) {
        map.set(cat, {
          category: cat,
          bookValue: 0,
          recoverableAmount: 0,
          impairmentAmount: 0,
          alreadyProvided: 0,
          supplement: 0,
          overProvision: 0,
          rowCount: 0,
        })
      }
      return map.get(cat)!
    }
    for (const cat of H1_14_ASSET_CATEGORIES) ensure(cat)
    for (const row of calcRows.value) {
      const cat = row.category && String(row.category).trim()
        ? String(row.category).trim()
        : '未分类'
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
      (t) => t.rowCount > 0 || (H1_14_ASSET_CATEGORIES as readonly string[]).includes(t.category),
    )
  })

  /** 编制校验：分类汇总之和 = 明细合计；迹象与测算行勾稽 */
  const prepValidation = computed<ImpPrepValidation>(() => {
    const messages: string[] = []
    const categorySumImpairment = calcSubtotal(
      categoryTotals.value
        .filter((t) => t.category !== '未分类')
        .map((t) => t.impairmentAmount),
    ) + (categoryTotals.value.find((t) => t.category === '未分类')?.impairmentAmount ?? 0)
    const categorySumAlready = calcSubtotal(categoryTotals.value.map((t) => t.alreadyProvided))
    const grandImpairment = impairmentTotal.value
    const grandAlready = alreadyProvidedTotal.value
    if (Math.abs(categorySumImpairment - grandImpairment) > 0.01) {
      messages.push(`分类⑥合计(${categorySumImpairment.toFixed(2)})≠明细⑥合计(${grandImpairment.toFixed(2)})`)
    }
    if (Math.abs(categorySumAlready - grandAlready) > 0.01) {
      messages.push(`分类⑦合计(${categorySumAlready.toFixed(2)})≠明细⑦合计(${grandAlready.toFixed(2)})`)
    }
    const unclassified = calcRows.value.filter((r) => !r.category || !String(r.category).trim()).length
    if (unclassified > 0) messages.push(`${unclassified} 行未填固定资产类别`)
    const needTest = indications.value.some((i) => i.result === 'Y')
    const tested = calcRows.value.filter((r) => r.hasIndication === 'Y').length
    if (needTest && calcRows.value.length === 0) {
      messages.push('六项迹象已勾选「有」，但测算表无行——请新增资产组或自 H1-4 引入')
    }
    if (needTest && tested === 0 && calcRows.value.length > 0) {
      messages.push('六项迹象存在「有」，但测算行均未勾选行级「有迹象」')
    }
    for (const r of calcRows.value) {
      if (r.hasIndication === 'Y' && r.recoverableAmount <= 0 && r.bookValue > 0) {
        messages.push(`「${r.assetGroup || '未命名'}」有迹象但可收回金额未测算（请完成 H1-15）`)
        break
      }
    }
    if (hasOverProvision.value) {
      messages.push('存在⑦>⑥（已计提超过应计提）——核查是否处置结转；CAS8第17条不得转回损益')
    }
    const staleDcf = dcfSyncChecks.value.filter((c) => c.status === 'stale')
    if (staleDcf.length > 0) {
      messages.push(`${staleDcf.length} 行④DCF 与 H1-15 不一致，请强制回写`)
    }
    const missingH15 = dcfSyncChecks.value.filter((c) => c.status === 'missing-h15')
    if (missingH15.length > 0) {
      messages.push(`${missingH15.length} 行有迹象但 H1-15 无同名资产组`)
    }
    return {
      ok: messages.length === 0,
      messages,
      categorySumImpairment,
      grandImpairment,
      categorySumAlready,
      grandAlready,
    }
  })

  /** 逐行：H1-14 ④/③ vs H1-15 测算结果 */
  const dcfSyncChecks = computed<DcfSyncCheck[]>(() => {
    return calcRows.value.map((row) => {
      const needTest = row.hasIndication === 'Y' || (Number(row.bookValue) || 0) > 0
      const g = _findGroupForCalcRow(row)
      if (!g) {
        return {
          rowId: row.rowId,
          assetGroup: row.assetGroup,
          h14Dcf: Number(row.dcfValue) || 0,
          h15Dcf: 0,
          h14Fv: Number(row.fairValueLessDisposal) || 0,
          h15Fv: 0,
          hasH15Group: false,
          dcfSynced: false,
          fvSynced: false,
          status: needTest && row.hasIndication === 'Y' ? 'missing-h15' : 'no-test',
        }
      }
      const { fvNet, dcf } = _calcGroupRecoverable(g)
      const h14Dcf = Number(row.dcfValue) || 0
      const h14Fv = Number(row.fairValueLessDisposal) || 0
      const dcfSynced = Math.abs(h14Dcf - dcf) < 0.01
      const fvSynced = Math.abs(h14Fv - fvNet) < 0.01
      let status: DcfSyncCheck['status'] = 'synced'
      if (row.hasIndication === 'Y' || h14Dcf > 0 || dcf > 0) {
        status = dcfSynced ? 'synced' : 'stale'
      } else {
        status = 'no-test'
      }
      return {
        rowId: row.rowId,
        assetGroup: row.assetGroup,
        h14Dcf,
        h15Dcf: dcf,
        h14Fv,
        h15Fv: fvNet,
        hasH15Group: true,
        dcfSynced,
        fvSynced,
        status,
      }
    })
  })

  const dcfSyncSummary = computed(() => {
    const checks = dcfSyncChecks.value
    const stale = checks.filter((c) => c.status === 'stale').length
    const missing = checks.filter((c) => c.status === 'missing-h15').length
    const synced = checks.filter((c) => c.status === 'synced').length
    return {
      stale,
      missing,
      synced,
      ok: stale === 0 && missing === 0,
      message: stale || missing
        ? `④回写校验：${stale} 行过期，${missing} 行缺 H1-15`
        : (synced > 0 ? `④已与 H1-15 一致（${synced} 行）` : '暂无④回写校验项'),
    }
  })

  const k11Reconcile = ref<K11ReconcileResult>({
    h14Supplement: 0,
    k11Amount: null,
    diff: null,
    isMatch: true,
    source: '',
    message: '尚未核对 K11',
  })

  /** 按源模板结论栏生成可编辑草稿 */
  function buildConclusionDraft(): string {
    const signOk = indications.value.every((i) => i.result === 'Y' || i.result === 'N' || i.result === 'NA')
    const yCount = indications.value.filter((i) => i.result === 'Y').length
    const groupCount = calcRows.value.length
    const req = impairmentTotal.value
    const booked = alreadyProvidedTotal.value
    const supp = supplementTotal.value
    const over = overProvisionTotal.value
    let handle = '差额不重大/无需调整'
    if (supp > 0.01) handle = '已建议调整补提'
    else if (over > 0.01) handle = '已计提大于应计提，需核查不得转回'
    const lines = [
      `（1）减值迹象识别：六项判断${signOk ? '已完成' : '尚未完成'}，其中「有」${yCount}项，识别${yCount > 0 || groupCount > 0 ? '充分' : '待确认'}。`,
      `（2）共测试资产组/单项 ${groupCount} 个；应计提⑥ ${req.toFixed(2)}，已计提⑦ ${booked.toFixed(2)}，本期应补提⑧ ${supp.toFixed(2)}${over > 0.01 ? `，多提 ${over.toFixed(2)}` : ''}。`,
      `（3）差异处理：${handle}。`,
      `（4）CAS8第17条：${over > 0.01 ? '已关注多提/潜在转回，详见审计说明' : '未发现不当转回损益情形'}。`,
      `（5）固定资产减值准备在重大方面${supp < 0.01 && over < 0.01 ? '公允反映' : '存在需关注事项/错报风险'}。`,
    ]
    return lines.join('\n')
  }

  // ─── 资产组 CRUD ───────────────────────────────────────────────────────────

  function setActiveGroup(groupId: string): void {
    if (!groups.value.some((g) => g.groupId === groupId)) return
    activeGroupId.value = groupId
    options?.onSave?.(`${ITEM_PREFIX_15}-active-group`, groupId)
  }

  function addRecoverableGroup(name?: string): RecoverableGroup {
    const g = _defaultGroup(name || `资产组-${groups.value.length + 1}`)
    groups.value.push(g)
    activeGroupId.value = g.groupId
    _persistGroups()
    return g
  }

  function removeRecoverableGroup(groupId: string): void {
    if (groups.value.length <= 1) return
    const idx = groups.value.findIndex((g) => g.groupId === groupId)
    if (idx < 0) return
    groups.value.splice(idx, 1)
    if (activeGroupId.value === groupId) {
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

  /**
   * 从 H1-4 闲置清单导入：为每个净值>0 的闲置资产创建 H1-15 资产组，
   * 并同步写入 H1-14 测算行（账面=净值，已计提=闲置表减值金额）。
   */
  function importFromIdleAssets(): { added: number; skipped: number; total: number } {
    const idle = parseIdleAssetsFromH4()
    let added = 0
    let skipped = 0
    for (const asset of idle) {
      const exists = groups.value.some(
        (g) =>
          (asset.rowId && g.sourceIdleRowId === asset.rowId)
          || g.name === asset.name,
      )
      if (exists) {
        // 已存在则刷新账面
        const g = groups.value.find(
          (x) => (asset.rowId && x.sourceIdleRowId === asset.rowId) || x.name === asset.name,
        )
        if (g) {
          g.bookValue = asset.netValue
          g.alreadyProvided = asset.impairmentAmount
          g.sourceIdleRowId = asset.rowId || g.sourceIdleRowId
        }
        const calc = calcRows.value.find((r) => r.assetGroup === asset.name)
        if (calc) {
          calc.bookValue = asset.netValue
          calc.alreadyProvided = asset.impairmentAmount
          if (!calc.hasIndication) calc.hasIndication = 'Y'
          if (!calc.indicationDesc) calc.indicationDesc = '闲置/拟处置（来源H1-4）'
          _recalcCalcRow(calc)
        }
        skipped++
        continue
      }

      const g = _defaultGroup(asset.name)
      g.bookValue = asset.netValue
      g.alreadyProvided = asset.impairmentAmount
      g.sourceIdleRowId = asset.rowId
      g.fvDisposal.assetName = asset.name
      groups.value.push(g)

      if (!calcRows.value.some((r) => r.assetGroup === asset.name)) {
        const row: ImpairmentCalcRow = {
          rowId: _newId('imp'),
          category: '其他设备',
          assetGroup: asset.name,
          hasIndication: 'Y',
          indicationDesc: '闲置/拟处置（来源H1-4）',
          bookValue: asset.netValue,
          fairValueLessDisposal: 0,
          dcfValue: 0,
          recoverableAmount: 0,
          impairmentAmount: 0,
          alreadyProvided: asset.impairmentAmount,
          difference: 0,
          indexRef: 'H1-4→H1-15',
          remark: '来源H1-4闲置',
        }
        _recalcCalcRow(row)
        calcRows.value.push(row)
      }
      added++
    }

    // 去掉占位空组（仅当导入成功且原组无账面无名称意义）
    if (added > 0) {
      const placeholder = groups.value.find(
        (g) => !g.sourceIdleRowId && g.bookValue === 0 && (!g.name || g.name.startsWith('资产组-')),
      )
      if (placeholder && groups.value.length > 1) {
        const idx = groups.value.findIndex((g) => g.groupId === placeholder.groupId)
        if (idx >= 0) groups.value.splice(idx, 1)
      }
      activeGroupId.value = groups.value.find((g) => g.sourceIdleRowId)?.groupId
        ?? groups.value[0].groupId
    }

    _persistGroups()
    _persistCalcRows()
    // 自动勾选闲置迹象
    if (added > 0 || (skipped > 0 && idle.length > 0)) {
      const idleInd = indications.value.find((i) => i.key === 'idle_abandoned')
      if (idleInd && idleInd.result !== 'Y') {
        idleInd.result = 'Y'
        idleInd.explanation = idleInd.explanation || `已从H1-4引入${idle.length}项闲置资产`
        _persistIndications()
      }
    }
    return { added, skipped, total: idle.length }
  }

  // ─── H1-14 CRUD ────────────────────────────────────────────────────────────

  function updateIndication(key: string, field: keyof ImpairmentIndication, value: any): void {
    const ind = indications.value.find((i) => i.key === key)
    if (!ind) return
    ;(ind as any)[field] = value
    _persistIndications()
  }

  function updateCalcRow(rowId: string, field: keyof ImpairmentCalcRow, value: any): void {
    const row = calcRows.value.find((r) => r.rowId === rowId)
    if (!row) return
    // ④ DCF 强制自 H1-15 回写，禁止手工改数
    if (field === 'dcfValue') return
    ;(row as any)[field] = value
    // 行级勾选「有迹象」时，自动带出六项中已勾选 Y 的摘要
    if (field === 'hasIndication' && value === 'Y' && !row.indicationDesc) {
      const ys = indications.value.filter((i) => i.result === 'Y').map((i) => i.description.slice(0, 20))
      if (ys.length) row.indicationDesc = ys.join('；')
    }
    _recalcCalcRow(row)
    _persistCalcRows()
  }

  function addCalcRow(assetGroup: string, category = ''): void {
    const row: ImpairmentCalcRow = {
      rowId: _newId('imp'),
      category,
      assetGroup,
      hasIndication: hasIndication.value ? 'Y' : '',
      indicationDesc: '',
      bookValue: 0,
      fairValueLessDisposal: 0,
      dcfValue: 0,
      recoverableAmount: 0,
      impairmentAmount: 0,
      alreadyProvided: 0,
      difference: 0,
      indexRef: 'H1-15',
      remark: '',
    }
    calcRows.value.push(row)
    _persistCalcRows()
  }

  function removeCalcRow(rowId: string): void {
    const idx = calcRows.value.findIndex((r) => r.rowId === rowId)
    if (idx >= 0) {
      calcRows.value.splice(idx, 1)
      _persistCalcRows()
    }
  }

  function updateDcfParams(params: Partial<DcfModelParams>): void {
    Object.assign(activeGroup.value.dcfParams, params)
    if (params.forecastPeriod != null || params.revenues || params.costs) {
      _normalizeForecastLength(activeGroup.value.dcfParams)
    }
    if (waccAfterTax.value > 0) {
      activeGroup.value.dcfParams.discountRate = +effectiveDiscountRate.value.toFixed(4)
    }
    _persistGroups()
  }

  function updateCashFlowYear(yearIndex: number, field: 'revenue' | 'cost' | 'fcf', value: number): void {
    const dp = activeGroup.value.dcfParams
    const n = dp.forecastPeriod
    if (yearIndex < 0 || yearIndex >= n) return
    if (field === 'revenue') {
      dp.revenues[yearIndex] = value
      dp.cashFlows[yearIndex] = value - (dp.costs[yearIndex] || 0)
    } else if (field === 'cost') {
      dp.costs[yearIndex] = value
      dp.cashFlows[yearIndex] = (dp.revenues[yearIndex] || 0) - value
    } else {
      dp.cashFlows[yearIndex] = value
    }
    const last = dp.cashFlows[n - 1] || 0
    if (dp.terminalCashFlow === 0 || field !== 'fcf') {
      dp.terminalCashFlow = last * (1 + dp.perpetualGrowthRate / 100)
    }
    _persistGroups()
  }

  function updateWaccParams(params: Partial<WaccParams>): void {
    Object.assign(activeGroup.value.waccParams, params)
    if (waccAfterTax.value > 0) {
      activeGroup.value.dcfParams.discountRate = +effectiveDiscountRate.value.toFixed(4)
    }
    _persistGroups()
  }

  function updateFvDisposal(params: Partial<FairValueDisposal>): void {
    Object.assign(activeGroup.value.fvDisposal, params)
    if (params.assetName != null) activeGroup.value.name = params.assetName
    _persistGroups()
  }

  function updateBookValue(val: number): void {
    activeGroup.value.bookValue = val
    _persistGroups()
  }

  /** 将当前资产组测算结果回写至 H1-14（按名称匹配，否则新增） */
  function syncToImpairmentCalc(targetRowId?: string): void {
    const g = activeGroup.value
    const { fvNet, dcf } = _calcGroupRecoverable(g)
    let row = targetRowId
      ? calcRows.value.find((r) => r.rowId === targetRowId)
      : calcRows.value.find((r) => r.assetGroup === g.name)
    if (!row) {
      addCalcRow(g.name || '资产组-1')
      row = calcRows.value[calcRows.value.length - 1]
    }
    row.assetGroup = g.name || row.assetGroup
    if (g.bookValue > 0) row.bookValue = g.bookValue
    if (g.alreadyProvided > 0 && row.alreadyProvided === 0) row.alreadyProvided = g.alreadyProvided
    row.fairValueLessDisposal = fvNet
    row.dcfValue = dcf
    if (!row.hasIndication) row.hasIndication = 'Y'
    if (!row.indexRef) row.indexRef = 'H1-15'
    _recalcCalcRow(row)
    _persistCalcRows()
  }

  /** 回写全部资产组到 H1-14 */
  function syncAllGroupsToImpairmentCalc(): void {
    for (const g of groups.value) {
      const { fvNet, dcf } = _calcGroupRecoverable(g)
      let row = calcRows.value.find((x) => x.assetGroup === g.name)
      if (!row) {
        addCalcRow(g.name)
        row = calcRows.value[calcRows.value.length - 1]
      }
      row.bookValue = g.bookValue
      if (g.alreadyProvided > 0) row.alreadyProvided = g.alreadyProvided
      row.fairValueLessDisposal = fvNet
      row.dcfValue = dcf
      if (!row.hasIndication) row.hasIndication = 'Y'
      if (!row.indexRef) row.indexRef = 'H1-15'
      _recalcCalcRow(row)
    }
    _persistCalcRows()
  }

  /**
   * 强制自 H1-15 回写 ③/④（④为主校验项）。
   * @returns 更新行数
   */
  function forceSyncFromH15(): { updated: number; created: number; unmatched: string[] } {
    let updated = 0
    let created = 0
    const unmatched: string[] = []
    const matchedNames = new Set<string>()

    for (const g of groups.value) {
      const { fvNet, dcf } = _calcGroupRecoverable(g)
      let row = calcRows.value.find((x) => (x.assetGroup || '').trim() === (g.name || '').trim())
      if (!row) {
        addCalcRow(g.name || '资产组')
        row = calcRows.value[calcRows.value.length - 1]
        created++
      } else {
        updated++
      }
      if (g.bookValue > 0) row.bookValue = g.bookValue
      if (g.alreadyProvided > 0) row.alreadyProvided = g.alreadyProvided
      row.fairValueLessDisposal = fvNet
      row.dcfValue = dcf
      if (!row.hasIndication) row.hasIndication = 'Y'
      row.indexRef = row.indexRef || 'H1-15'
      _recalcCalcRow(row)
      matchedNames.add((g.name || '').trim())
    }

    for (const row of calcRows.value) {
      if (row.hasIndication === 'Y' && !matchedNames.has((row.assetGroup || '').trim())) {
        unmatched.push(row.assetGroup || row.rowId)
      }
    }
    _persistCalcRows()
    return { updated, created, unmatched }
  }

  function _persistIndications(): void {
    options?.onSave?.(`${ITEM_PREFIX_14}-indications`, indications.value)
  }

  function _persistCalcRows(): void {
    options?.onSave?.(`${ITEM_PREFIX_14}-calc-rows`, calcRows.value)
    // 语义合计：供 K11 / 一致性门禁 / =WP 消费
    const supp = calcSubtotal(calcRows.value.map((r) => Math.max(Number(r.difference) || 0, 0)))
    const req = calcSubtotal(calcRows.value.map((r) => Number(r.impairmentAmount) || 0))
    options?.onSave?.(`${ITEM_PREFIX_14}-supplement-total`, supp)
    options?.onSave?.(`${ITEM_PREFIX_14}-本期减值合计`, supp)
    options?.onSave?.(`${ITEM_PREFIX_14}-应计提合计`, req)
    _publishImpairmentToK11(supp)
  }

  /** 发布本期补提 → K11（对齐 F2 impairment:calculated 约定） */
  function _publishImpairmentToK11(supplement: number): void {
    try {
      if (typeof window === 'undefined') return
      window.dispatchEvent(new CustomEvent('impairment:calculated', {
        detail: {
          wpCode: 'H1',
          wp_code: 'H1',
          sheetCode: 'H1-14',
          sheet: '减值测算表H1-14',
          totalRequiredProvision: supplement,
          amount: supplement,
          label: '本期补提⑧',
          impairmentAmount: calcSubtotal(calcRows.value.map((r) => Number(r.impairmentAmount) || 0)),
        },
      }))
    } catch { /* silent */ }
  }

  /**
   * 拉取 K11 固定资产减值本期发生额，与 H1-14 ⑧本期补提交叉核对。
   */
  async function reconcileWithK11(projectId: string): Promise<K11ReconcileResult> {
    const h14Supplement = supplementTotal.value
    const empty: K11ReconcileResult = {
      h14Supplement,
      k11Amount: null,
      diff: null,
      isMatch: true,
      source: '',
      message: 'K11 未取到固定资产减值金额',
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
      const byId = (id: string) => {
        const item = list.find((r) => r.item_id === id)
        if (!item) return null
        const raw = item.remark ?? item.conclusion
        if (raw == null || raw === '') return null
        // 明细行 JSON
        if (typeof raw === 'string' && raw.trim().startsWith('[')) {
          try {
            const rows = JSON.parse(raw)
            if (!Array.isArray(rows)) return null
            const fa = rows.filter((r: any) => {
              const cat = String(r.assetCategory || r.impairmentItem || '')
              const wp = String(r.sourceWp || '')
              return wp === 'H1' || cat.includes('固定资产')
            })
            if (!fa.length) return null
            return fa.reduce((s: number, r: any) => s + (Number(r.currentOccurrence ?? r.currentProvision) || 0), 0)
          } catch { return null }
        }
        const n = Number(raw)
        return Number.isFinite(n) ? n : null
      }

      const candidates = [
        { id: 'K11-2-fixed-asset-occurrence', label: 'K11-2-fixed-asset-occurrence' },
        { id: 'K11-source-H1-amount', label: 'K11-source-H1-amount' },
        { id: 'K11-2-detail-rows', label: 'K11-2 明细(固定资产行)' },
      ]
      let k11Amount: number | null = null
      let source = ''
      for (const c of candidates) {
        const v = byId(c.id)
        if (v != null) {
          k11Amount = v
          source = c.label
          break
        }
      }

      if (k11Amount == null) {
        k11Reconcile.value = empty
        return k11Reconcile.value
      }
      const diff = h14Supplement - k11Amount
      const isMatch = Math.abs(diff) < 0.01
      k11Reconcile.value = {
        h14Supplement,
        k11Amount,
        diff,
        isMatch,
        source,
        message: isMatch
          ? `K11 勾稽通过：⑧本期补提 ${h14Supplement.toFixed(2)} = K11 ${k11Amount.toFixed(2)}（${source}）`
          : `K11 勾稽差异：⑧ ${h14Supplement.toFixed(2)} − K11 ${k11Amount.toFixed(2)} = ${diff.toFixed(2)}（${source}）`,
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

  function saveNote(note: string): void {
    auditNote.value = note
    options?.onSave?.(`${ITEM_PREFIX_14}-audit-note`, note)
  }

  function saveConclusion(conclusion: string): void {
    auditConclusion.value = conclusion
    options?.onSave?.(`${ITEM_PREFIX_14}-audit-conclusion`, conclusion)
  }

  function saveRecoverableNote(note: string): void {
    activeGroup.value.note = note
    _persistGroups()
  }

  function saveRecoverableConclusion(conclusion: string): void {
    activeGroup.value.conclusion = conclusion
    _persistGroups()
  }

  watch(allResponses, () => _loadData(), { immediate: true })

  return {
    // State
    indications,
    calcRows,
    groups,
    activeGroupId,
    activeGroup,
    dcfParams,
    waccParams,
    fvDisposal,
    bookValue,
    auditNote,
    auditConclusion,
    recoverableNote,
    recoverableConclusion,
    idleAssetsAvailable,
    // Computed
    costOfEquity,
    waccAfterTax,
    preTaxDiscountRate,
    effectiveDiscountRate,
    fairValueResolved,
    disposalTotal,
    fairValueLessDisposal,
    cashFlowRows,
    dcfResult,
    recoverableAmount,
    recoverableSource,
    impliedImpairment,
    sensitivityMatrix,
    sensitivityGrid,
    terminalSensitivityByRate,
    terminalSensitivityByGrowth,
    hasIndication,
    rowsNeedingImpairment,
    impairmentTotal,
    alreadyProvidedTotal,
    totalDiff,
    supplementTotal,
    overProvisionTotal,
    hasOverProvision,
    categoryTotals,
    prepValidation,
    dcfSyncChecks,
    dcfSyncSummary,
    k11Reconcile,
    // Actions
    updateIndication,
    updateCalcRow,
    addCalcRow,
    removeCalcRow,
    updateDcfParams,
    updateCashFlowYear,
    updateWaccParams,
    updateFvDisposal,
    updateBookValue,
    syncToImpairmentCalc,
    syncAllGroupsToImpairmentCalc,
    forceSyncFromH15,
    reconcileWithK11,
    setActiveGroup,
    addRecoverableGroup,
    removeRecoverableGroup,
    renameActiveGroup,
    importFromIdleAssets,
    parseIdleAssetsFromH4,
    buildConclusionDraft,
    saveNote,
    saveConclusion,
    saveRecoverableNote,
    saveRecoverableConclusion,
    INDICATION_DEFINITIONS,
    H1_14_ASSET_CATEGORIES,
  }
}

export default useH1Impairment
