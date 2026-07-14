/** E1-14 货币资金分析：源模板七区段、八项比例及旧 JSON 兼容。 */
import { computed, onBeforeUnmount, ref, watch, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { calcChange, calcChangeRate, exceedsThreshold, parseNum } from './useE1FormulaEngine'

export interface AnalysisRow {
  itemKey: string
  itemName: string
  endingAmount: number
  openingAmount: number
  priorAmount: number
  changeAmount: number
  changeRate: number | ''
  priorChangeAmount: number
  priorChangeRate: number | ''
  varianceNote: string
}

export type AnalysisPeriod = 'current' | 'prior' | 'prior2'
export interface YearValues { current: number; prior: number; prior2: number }
export interface OtherFundRow extends YearValues { key: string; name: string; reason: string }
export interface MonthlyFundRow {
  month: number; opening: number; increase: number; decrease: number
  ending: number; average: number; note: string
}
export interface BankStructureRow {
  key: string; name: string; accountCount: number; ending: number
  ratio: number; opening: number; change: number; note: string
}
export interface FundQualityRow {
  key: string; name: string; ending: number; ratio: number; opening: number; conclusion: string
}
export interface AnalysisAnomalyRow {
  id: string; item: string; amount: number; reason: string; risk: string; response: string
}
export interface RatioRow {
  key: string; name: string; current: number | ''; prior: number | ''; prior2: number | ''
  currentChange: number | ''; priorChange: number | ''; reason: string
}

const LEGACY_KEY = 'E1-analysis-rows'
const STRUCTURED_KEY = 'E1-analysis-structured'
const CHANGE_RATE_THRESHOLD = 0.3
const ANALYSIS_ITEMS = [
  { itemKey: 'cash', itemName: '库存现金', crossKey: 'E1-adj-total-1001' },
  { itemKey: 'bank', itemName: '银行存款', crossKey: 'E1-adj-total-1002' },
  { itemKey: 'other', itemName: '其他货币资金', crossKey: 'E1-adj-total-1012' },
] as const
const OTHER_FUND_ITEMS = [
  ['draft', '银行汇票存款'], ['cashier', '银行本票存款'], ['lc', '信用证保证金存款'],
  ['outport', '外埠存款'], ['investment', '存出投资款'], ['creditCard', '信用卡存款'],
  ['platform', '支付宝、微信及其他'],
] as const
const METRIC_ITEMS = [
  ['assetTotal', '资产总额'], ['loanTotal', '贷款总额'], ['termDeposit', '定期存款'],
  ['largeCd', '大额存单'], ['restrictedFunds', '受限货币资金'], ['financeCompanyFunds', '存放财务公司款项'],
] as const
const BANK_TYPES = ['国有银行', '股份制银行', '城商行', '农商行', '外资银行', '其他'] as const
const QUALITY_ITEMS = [
  ['available', '正常可用资金'], ['restricted', '受限资金'], ['pledged', '其中：质押资金'],
  ['frozen', '其中：冻结资金'], ['otherRestricted', '其中：其他受限'],
] as const
const RATIO_ITEMS = [
  ['bankAsset', '银行存款÷资产总额'], ['termBank', '定期存款÷银行存款'],
  ['termCdBank', '（定期存款+大额存单）÷银行存款'], ['restrictedCash', '受限货币资金÷货币资金'],
  ['financeCash', '存放财务公司款项÷货币资金'], ['cashLoan', '货币资金÷贷款总额'],
  ['termLoan', '定期存款÷贷款总额'], ['bankCash', '银行存款÷货币资金（集中度）'],
] as const

interface StoredLegacy {
  openingAmount: number; priorAmount: number; priorChangeAmount: number
  priorChangeRate: number | ''; varianceNote: string
}
interface StructuredState {
  metrics: Record<string, YearValues>
  otherFunds: Record<string, YearValues & { reason: string }>
  monthly: MonthlyFundRow[]
  banks: Record<string, Omit<BankStructureRow, 'key' | 'name' | 'ratio' | 'change'>>
  quality: Record<string, Omit<FundQualityRow, 'key' | 'name' | 'ratio'>>
  anomalies: AnalysisAnomalyRow[]
  ratioReasons: Record<string, string>
  cashThreshold: number
  loanThreshold: number
  concentrationThreshold: number
}

function years(): YearValues { return { current: 0, prior: 0, prior2: 0 } }
function id(prefix: string): string {
  return `${prefix}-${typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random()}`}`
}
function defaultState(): StructuredState {
  return {
    metrics: Object.fromEntries(METRIC_ITEMS.map(([key]) => [key, years()])),
    otherFunds: Object.fromEntries(OTHER_FUND_ITEMS.map(([key]) => [key, { ...years(), reason: '' }])),
    monthly: Array.from({ length: 12 }, (_, i) => ({ month: i + 1, opening: 0, increase: 0, decrease: 0, ending: 0, average: 0, note: '' })),
    banks: Object.fromEntries(BANK_TYPES.map(name => [name, { accountCount: 0, ending: 0, opening: 0, note: '' }])),
    quality: Object.fromEntries(QUALITY_ITEMS.map(([key]) => [key, { ending: 0, opening: 0, conclusion: '' }])),
    anomalies: [{ id: id('anomaly'), item: '', amount: 0, reason: '', risk: '', response: '' }],
    ratioReasons: {}, cashThreshold: 0, loanThreshold: 0, concentrationThreshold: 0.6,
  }
}
function normalizeState(raw: any): StructuredState {
  const base = defaultState()
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return base
  for (const [key] of METRIC_ITEMS) {
    const value = raw.metrics?.[key] || {}
    base.metrics[key] = { current: parseNum(value.current), prior: parseNum(value.prior), prior2: parseNum(value.prior2) }
  }
  for (const [key] of OTHER_FUND_ITEMS) {
    const value = raw.otherFunds?.[key] || {}
    base.otherFunds[key] = { current: parseNum(value.current), prior: parseNum(value.prior), prior2: parseNum(value.prior2), reason: String(value.reason || '') }
  }
  if (Array.isArray(raw.monthly)) {
    base.monthly = base.monthly.map((fallback, index) => {
      const value = raw.monthly[index] || {}
      const opening = parseNum(value.opening); const increase = parseNum(value.increase); const decrease = parseNum(value.decrease)
      const ending = value.ending == null ? opening + increase - decrease : parseNum(value.ending)
      return { ...fallback, opening, increase, decrease, ending, average: value.average == null ? (opening + ending) / 2 : parseNum(value.average), note: String(value.note || '') }
    })
  }
  for (const name of BANK_TYPES) {
    const value = raw.banks?.[name] || {}
    base.banks[name] = { accountCount: parseNum(value.accountCount), ending: parseNum(value.ending), opening: parseNum(value.opening), note: String(value.note || '') }
  }
  for (const [key] of QUALITY_ITEMS) {
    const value = raw.quality?.[key] || {}
    base.quality[key] = { ending: parseNum(value.ending), opening: parseNum(value.opening), conclusion: String(value.conclusion || '') }
  }
  if (Array.isArray(raw.anomalies) && raw.anomalies.length) {
    base.anomalies = raw.anomalies.map((value: any) => ({ id: String(value.id || id('anomaly')), item: String(value.item || ''), amount: parseNum(value.amount), reason: String(value.reason || ''), risk: String(value.risk || ''), response: String(value.response || '') }))
  }
  base.ratioReasons = typeof raw.ratioReasons === 'object' && raw.ratioReasons ? raw.ratioReasons : {}
  base.cashThreshold = parseNum(raw.cashThreshold)
  base.loanThreshold = parseNum(raw.loanThreshold)
  base.concentrationThreshold = parseNum(raw.concentrationThreshold) || 0.6
  return base
}

export function useE1Analysis(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options
  const isLoading = ref(false)
  const storedMap = ref<Record<string, StoredLegacy>>({})
  const structured = ref<StructuredState>(defaultState())

  function loadFromResponses(): void {
    try {
      const parsed = JSON.parse(allResponses.value.get(LEGACY_KEY)?.remark || '[]')
      const map: Record<string, StoredLegacy> = {}
      if (Array.isArray(parsed)) parsed.forEach((row: any) => {
        if (!row.itemKey) return
        map[row.itemKey] = {
          openingAmount: parseNum(row.openingAmount), priorAmount: parseNum(row.priorAmount),
          priorChangeAmount: parseNum(row.priorChangeAmount), priorChangeRate: row.priorChangeRate === '' ? '' : parseNum(row.priorChangeRate),
          varianceNote: String(row.varianceNote || ''),
        }
      })
      storedMap.value = map
    } catch { storedMap.value = {} }
    try { structured.value = normalizeState(JSON.parse(allResponses.value.get(STRUCTURED_KEY)?.remark || '{}')) }
    catch { structured.value = defaultState() }
  }
  loadFromResponses()
  watch(() => [allResponses.value.get(LEGACY_KEY)?.remark, allResponses.value.get(STRUCTURED_KEY)?.remark], loadFromResponses)

  function getEnding(crossKey: string): number { return parseNum(allResponses.value.get(crossKey)?.remark) }
  const rows: ComputedRef<AnalysisRow[]> = computed(() => ANALYSIS_ITEMS.map(item => {
    const saved = storedMap.value[item.itemKey] || { openingAmount: 0, priorAmount: 0, priorChangeAmount: 0, priorChangeRate: '', varianceNote: '' }
    const endingAmount = getEnding(item.crossKey)
    const changeAmount = calcChange(endingAmount, saved.openingAmount)
    return { ...item, endingAmount, ...saved, changeAmount, changeRate: calcChangeRate(changeAmount, saved.openingAmount) }
  }))
  const totalByPeriod = (period: AnalysisPeriod): number => rows.value.reduce((sum, row) => sum + (period === 'current' ? row.endingAmount : period === 'prior' ? row.openingAmount : row.priorAmount), 0)
  const bankByPeriod = (period: AnalysisPeriod): number => {
    const row = rows.value.find(item => item.itemKey === 'bank')
    return row ? (period === 'current' ? row.endingAmount : period === 'prior' ? row.openingAmount : row.priorAmount) : 0
  }
  const metricValue = (key: string, period: AnalysisPeriod): number => structured.value.metrics[key]?.[period] || 0
  const divide = (a: number, b: number): number | '' => b ? a / b : ''
  function ratioValue(key: string, period: AnalysisPeriod): number | '' {
    const cash = totalByPeriod(period); const bank = bankByPeriod(period)
    const term = metricValue('termDeposit', period); const loan = metricValue('loanTotal', period)
    const formulas: Record<string, () => number | ''> = {
      bankAsset: () => divide(bank, metricValue('assetTotal', period)), termBank: () => divide(term, bank),
      termCdBank: () => divide(term + metricValue('largeCd', period), bank), restrictedCash: () => divide(metricValue('restrictedFunds', period), cash),
      financeCash: () => divide(metricValue('financeCompanyFunds', period), cash), cashLoan: () => divide(cash, loan),
      termLoan: () => divide(term, loan), bankCash: () => divide(bank, cash),
    }
    return formulas[key]?.() ?? ''
  }
  const otherFundRows = computed<OtherFundRow[]>(() => OTHER_FUND_ITEMS.map(([key, name]) => ({ key, name, ...structured.value.otherFunds[key] })))
  const ratioRows = computed<RatioRow[]>(() => RATIO_ITEMS.map(([key, name]) => {
    const current = ratioValue(key, 'current'); const prior = ratioValue(key, 'prior'); const prior2 = ratioValue(key, 'prior2')
    return { key, name, current, prior, prior2, currentChange: current === '' || prior === '' ? '' : current - prior, priorChange: prior === '' || prior2 === '' ? '' : prior - prior2, reason: structured.value.ratioReasons[key] || '' }
  }))
  const monthlyRows = computed(() => structured.value.monthly)
  const totalBankEnding = computed(() => Object.values(structured.value.banks).reduce((sum, row) => sum + row.ending, 0))
  const bankRows = computed<BankStructureRow[]>(() => BANK_TYPES.map(name => {
    const row = structured.value.banks[name]
    return { key: name, name, ...row, ratio: totalBankEnding.value ? row.ending / totalBankEnding.value : 0, change: row.ending - row.opening }
  }))
  const qualityTotal = computed(() => structured.value.quality.available.ending + structured.value.quality.restricted.ending)
  const qualityRows = computed<FundQualityRow[]>(() => QUALITY_ITEMS.map(([key, name]) => {
    const row = structured.value.quality[key]
    return { key, name, ...row, ratio: qualityTotal.value ? row.ending / qualityTotal.value : 0 }
  }))
  const anomalyRows = computed(() => structured.value.anomalies)
  const metricRows = computed(() => METRIC_ITEMS.map(([key, name]) => ({ key, name, ...structured.value.metrics[key] })))
  const totalEnding = computed(() => totalByPeriod('current'))
  const currentLoanTotal = computed(() => metricValue('loanTotal', 'current'))
  const bankConcentration = computed(() => divide(bankByPeriod('current'), totalEnding.value) || 0)
  const showDualHighWarning = computed(() => structured.value.cashThreshold > 0 && structured.value.loanThreshold > 0 && totalEnding.value >= structured.value.cashThreshold && currentLoanTotal.value >= structured.value.loanThreshold)
  const showConcentrationConcern = computed(() => bankConcentration.value >= structured.value.concentrationThreshold)

  function serializeLegacy(): string { return JSON.stringify(ANALYSIS_ITEMS.map(item => ({ itemKey: item.itemKey, ...(storedMap.value[item.itemKey] || {}) }))) }
  function serializeStructured(): string { return JSON.stringify(structured.value) }
  let timer: ReturnType<typeof setTimeout> | null = null
  function persist(): void {
    const legacy = serializeLegacy(); const detail = serializeStructured()
    const items: ChecklistItem[] = [
      { item_id: LEGACY_KEY, conclusion: null, remark: legacy },
      { item_id: STRUCTURED_KEY, conclusion: null, remark: detail },
    ]
    allResponses.value.set(LEGACY_KEY, items[0]); allResponses.value.set(STRUCTURED_KEY, items[1])
    void saveImmediate(items)
  }
  function scheduleSave(): void { if (timer) clearTimeout(timer); timer = setTimeout(() => { timer = null; persist() }, 1200) }
  function mutable(): boolean { return !isReadonly.value }
  function updateCell(itemKey: string, field: string, value: number | string): void {
    if (!mutable()) return
    const saved = storedMap.value[itemKey] || { openingAmount: 0, priorAmount: 0, priorChangeAmount: 0, priorChangeRate: '', varianceNote: '' }
    const next: any = { ...saved }
    next[field] = field === 'varianceNote' ? String(value) : value === '' ? '' : parseNum(value)
    storedMap.value = { ...storedMap.value, [itemKey]: next }; scheduleSave()
  }
  function updateMetric(key: string, period: AnalysisPeriod, value: number): void {
    if (!mutable()) return
    structured.value.metrics[key] = { ...structured.value.metrics[key], [period]: parseNum(value) }; scheduleSave()
  }
  function updateOtherFund(key: string, field: AnalysisPeriod | 'reason', value: number | string): void {
    if (!mutable()) return
    structured.value.otherFunds[key] = { ...structured.value.otherFunds[key], [field]: field === 'reason' ? String(value) : parseNum(value) } as any; scheduleSave()
  }
  function updateRatioReason(key: string, value: string): void { if (mutable()) { structured.value.ratioReasons[key] = value; scheduleSave() } }
  function updateMonthly(month: number, field: keyof MonthlyFundRow, value: number | string): void {
    if (!mutable()) return
    const index = month - 1; const row: any = { ...structured.value.monthly[index], [field]: field === 'note' ? String(value) : parseNum(value) }
    if (['opening', 'increase', 'decrease'].includes(field)) row.ending = row.opening + row.increase - row.decrease
    if (['opening', 'increase', 'decrease', 'ending'].includes(field)) row.average = (row.opening + row.ending) / 2
    structured.value.monthly[index] = row; scheduleSave()
  }
  function updateBank(key: string, field: string, value: number | string): void {
    if (!mutable()) return
    structured.value.banks[key] = { ...structured.value.banks[key], [field]: field === 'note' ? String(value) : parseNum(value) }; scheduleSave()
  }
  function updateQuality(key: string, field: string, value: number | string): void {
    if (!mutable()) return
    structured.value.quality[key] = { ...structured.value.quality[key], [field]: field === 'conclusion' ? String(value) : parseNum(value) }; scheduleSave()
  }
  function addAnomaly(): void { if (mutable()) { structured.value.anomalies.push({ id: id('anomaly'), item: '', amount: 0, reason: '', risk: '', response: '' }); scheduleSave() } }
  function updateAnomaly(rowId: string, field: keyof AnalysisAnomalyRow, value: number | string): void {
    if (!mutable()) return
    const row = structured.value.anomalies.find(item => item.id === rowId); if (!row) return
    ;(row as any)[field] = field === 'amount' ? parseNum(value) : String(value); scheduleSave()
  }
  function removeAnomaly(rowId: string): void { if (mutable()) { structured.value.anomalies = structured.value.anomalies.filter(row => row.id !== rowId); scheduleSave() } }
  function updateThreshold(field: 'cashThreshold' | 'loanThreshold' | 'concentrationThreshold', value: number): void { if (mutable()) { structured.value[field] = parseNum(value); scheduleSave() } }
  function hydrate(): void { isLoading.value = true; try { loadFromResponses() } finally { isLoading.value = false } }
  onBeforeUnmount(() => { if (timer) { clearTimeout(timer); persist() } })

  return {
    rows, otherFundRows, metricRows, ratioRows, monthlyRows, bankRows, qualityRows, anomalyRows,
    totalEnding, currentLoanTotal, bankConcentration, showDualHighWarning, showConcentrationConcern,
    cashThreshold: computed(() => structured.value.cashThreshold), loanThreshold: computed(() => structured.value.loanThreshold),
    concentrationThreshold: computed(() => structured.value.concentrationThreshold), isLoading,
    isRateExceeding: (row: AnalysisRow) => exceedsThreshold(row.changeRate, CHANGE_RATE_THRESHOLD),
    updateCell, updateMetric, updateOtherFund, updateRatioReason, updateMonthly, updateBank, updateQuality,
    addAnomaly, updateAnomaly, removeAnomaly, updateThreshold, hydrate,
  }
}
