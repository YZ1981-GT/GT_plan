/** E1-15 账户配置+月度矩阵；E1-20 应计利息兼容。 */
import { computed, onBeforeUnmount, ref, watch } from 'vue'
import { ElMessageBox } from 'element-plus'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { calcAccruedInterest, calcFxConvert, parseNum } from './useE1FormulaEngine'

export type InterestCalcVariant = 'monthly' | 'accrued'
export type DepositType = '活期存款' | '七天通知存款' | '大额存单'
export type AccruedInterestCategory = 'finance' | 'bank' | 'other' | 'digital'

/** 旧版12行模型，保留导出以兼容历史调用与 JSON 迁移。 */
export interface MonthlyInterestRow {
  id: string; month: number; monthlyAvgBalance: number; monthlyRate: number; calculatedInterest: number
}
export interface MonthlySummary { totalCalculated: number; bookInterest: number; diff: number }
export interface MonthlyAccount {
  id: string
  depositType: DepositType
  bank: string
  accountNo: string
  annualRate: number
  balances: number[]
  bookInterests: number[]
}
export interface MonthlyMatrixRow {
  month: number
  accounts: Record<string, { balance: number; bookInterest: number; calculatedInterest: number }>
  totalBalance: number
  totalCalculated: number
  totalBook: number
  diff: number
}
export interface InterestStructureRow {
  key: string; name: string; current: number; prior: number; change: number; changeRate: number | ''; note: string
}
export interface MarketRateRow {
  key: string; name: string; actualRate: number; marketRate: number; diff: number; diffRate: number | ''; note: string
}
export interface InterestAnomalyRow { key: string; item: string; amount: number; reason: string; risk: string; response: string }
export interface AccruedInterestRow {
  id: string; bank: string; accountNo: string; usage: string; category: AccruedInterestCategory
  currency: string; fcAmount: number; settleDate: string; cutoffDate: string; days: number
  dailyRate: number; accruedFc: number; fxRate: number; accruedRmb: number; note: string
}

const MONTHLY_KEY = 'E1-interest-monthly-rows'
const ACCRUED_KEY = 'E1-accrued-interest-rows'
const SUMMARY_KEY = `${MONTHLY_KEY}-summary`
const DEPOSIT_TYPES: DepositType[] = ['活期存款', '七天通知存款', '大额存单']
const ACCRUED_CATEGORIES: AccruedInterestCategory[] = ['finance', 'bank', 'other', 'digital']
const MARKET_TYPES = ['活期存款', '七天通知存款', '3个月定期', '6个月定期', '1年期定期', '2年期定期', '大额存单'] as const
const ANOMALY_ITEMS = ['利息收入异常高', '利息收入异常低', '利率异常', '其他异常'] as const
const ACCRUED_FIELDS = ['id', 'bank', 'accountNo', 'usage', 'category', 'currency', 'fcAmount', 'settleDate', 'cutoffDate', 'dailyRate', 'fxRate', 'note']

interface MonthlyAnalysisData {
  structurePrior: Record<string, number>
  structureNotes: Record<string, string>
  marketRates: Record<string, number>
  marketNotes: Record<string, string>
  anomalies: InterestAnomalyRow[]
}
function uid(prefix: string): string {
  return `${prefix}-${typeof crypto !== 'undefined' && crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`}`
}
function twelve(): number[] { return Array.from({ length: 12 }, () => 0) }
function createAccount(accountNo = '默认账户'): MonthlyAccount {
  return { id: uid('account'), depositType: '活期存款', bank: '', accountNo, annualRate: 0, balances: twelve(), bookInterests: twelve() }
}
function defaultMonthlyAnalysis(): MonthlyAnalysisData {
  return {
    structurePrior: Object.fromEntries(DEPOSIT_TYPES.map(key => [key, 0])),
    structureNotes: {}, marketRates: Object.fromEntries(MARKET_TYPES.map(key => [key, 0])), marketNotes: {},
    anomalies: ANOMALY_ITEMS.map((item, index) => ({ key: `anomaly-${index}`, item, amount: 0, reason: '', risk: '', response: '' })),
  }
}
function calcDaysBetween(start: string, end: string): number {
  if (!start || !end) return 0
  const d1 = new Date(start); const d2 = new Date(end)
  if (Number.isNaN(d1.getTime()) || Number.isNaN(d2.getTime())) return 0
  return Math.max(0, Math.round((d2.getTime() - d1.getTime()) / 86400000))
}
function normalizeAccruedCategory(value: unknown): AccruedInterestCategory {
  const category = String(value) as AccruedInterestCategory
  return ACCRUED_CATEGORIES.includes(category) ? category : 'bank'
}
function recalcAccrued(row: AccruedInterestRow): AccruedInterestRow {
  const days = calcDaysBetween(row.settleDate, row.cutoffDate)
  const accruedFc = calcAccruedInterest(row.fcAmount, days, row.dailyRate)
  return { ...row, days, accruedFc, accruedRmb: calcFxConvert(accruedFc, row.fxRate) }
}
function emptyAccrued(): AccruedInterestRow {
  return recalcAccrued({ id: uid('accrued'), bank: '', accountNo: '', usage: '', category: 'bank', currency: '人民币', fcAmount: 0, settleDate: '', cutoffDate: '', days: 0, dailyRate: 0, accruedFc: 0, fxRate: 1, accruedRmb: 0, note: '' })
}
function normalizeAccount(raw: any): MonthlyAccount {
  const account = createAccount(String(raw.accountNo || '默认账户'))
  const type = String(raw.depositType || '活期存款') as DepositType
  account.id = String(raw.id || uid('account'))
  account.depositType = DEPOSIT_TYPES.includes(type) ? type : '活期存款'
  account.bank = String(raw.bank || '')
  account.annualRate = parseNum(raw.annualRate)
  account.balances = Array.from({ length: 12 }, (_, i) => parseNum(raw.balances?.[i]))
  account.bookInterests = Array.from({ length: 12 }, (_, i) => parseNum(raw.bookInterests?.[i]))
  return account
}
function migrateLegacyRows(rows: any[], legacyBookInterest: number): MonthlyAccount[] {
  const account = createAccount('旧版月度数据迁入')
  account.id = 'legacy-monthly-account'
  account.balances = Array.from({ length: 12 }, (_, i) => parseNum(rows.find(row => parseNum(row.month) === i + 1)?.monthlyAvgBalance))
  const rates = rows.map(row => parseNum(row.monthlyRate)).filter(Boolean)
  const calculated = account.balances.map((balance, i) => balance * parseNum(rows.find(row => parseNum(row.month) === i + 1)?.monthlyRate))
  const total = calculated.reduce((sum, value) => sum + value, 0)
  const totalBalance = account.balances.reduce((sum, value) => sum + value, 0)
  account.annualRate = totalBalance
    ? total / totalBalance * 12
    : rates.length ? rates.reduce((sum, value) => sum + value, 0) / rates.length * 12 : 0
  account.bookInterests = total
    ? calculated.map(value => legacyBookInterest * value / total)
    : Array.from({ length: 12 }, (_, i) => i === 11 ? legacyBookInterest : 0)
  return [account]
}

export function useE1InterestCalc(options: UseE1BaseOptions & { variant: InterestCalcVariant }) {
  const { allResponses, saveImmediate, isReadonly, variant } = options
  const storageKey = variant === 'monthly' ? MONTHLY_KEY : ACCRUED_KEY
  const rows = ref<Array<MonthlyAccount | AccruedInterestRow>>([])
  const monthlyAnalysis = ref<MonthlyAnalysisData>(defaultMonthlyAnalysis())
  const monthlySummary = ref<MonthlySummary>({ totalCalculated: 0, bookInterest: 0, diff: 0 })
  const isLoading = ref(false)

  function parseSummary(): any {
    try { return JSON.parse(allResponses.value.get(SUMMARY_KEY)?.remark || '{}') } catch { return {} }
  }
  function loadMonthly(): void {
    const summary = parseSummary()
    try {
      const parsed = JSON.parse(allResponses.value.get(MONTHLY_KEY)?.remark || '[]')
      if (Array.isArray(parsed) && parsed.length && 'month' in parsed[0] && !('balances' in parsed[0])) {
        rows.value = migrateLegacyRows(parsed, parseNum(summary.bookInterest))
      } else if (Array.isArray(parsed) && parsed.length) {
        rows.value = parsed.map(normalizeAccount)
      } else rows.value = [createAccount()]
    } catch { rows.value = [createAccount()] }
    const defaults = defaultMonthlyAnalysis()
    monthlyAnalysis.value = {
      structurePrior: { ...defaults.structurePrior, ...(summary.structurePrior || {}) },
      structureNotes: { ...(summary.structureNotes || {}) },
      marketRates: { ...defaults.marketRates, ...(summary.marketRates || {}) },
      marketNotes: { ...(summary.marketNotes || {}) },
      anomalies: Array.isArray(summary.anomalies) && summary.anomalies.length
        ? summary.anomalies.map((row: any, index: number) => ({ key: String(row.key || `anomaly-${index}`), item: String(row.item || ANOMALY_ITEMS[index] || '其他异常'), amount: parseNum(row.amount), reason: String(row.reason || ''), risk: String(row.risk || ''), response: String(row.response || '') }))
        : defaults.anomalies,
    }
  }
  function loadAccrued(): void {
    try {
      const parsed = JSON.parse(allResponses.value.get(ACCRUED_KEY)?.remark || '[]')
      rows.value = Array.isArray(parsed) && parsed.length ? parsed.map((raw: any) => recalcAccrued({
        id: String(raw.id || uid('accrued')), bank: String(raw.bank || ''), accountNo: String(raw.accountNo || ''), usage: String(raw.usage || ''),
        category: normalizeAccruedCategory(raw.category), currency: String(raw.currency || '人民币'),
        fcAmount: parseNum(raw.fcAmount), settleDate: String(raw.settleDate || ''), cutoffDate: String(raw.cutoffDate || ''), days: 0, dailyRate: parseNum(raw.dailyRate), accruedFc: 0,
        fxRate: parseNum(raw.fxRate) || 1, accruedRmb: 0, note: String(raw.note || ''),
      })) : [emptyAccrued()]
    } catch { rows.value = [emptyAccrued()] }
  }
  function loadFromResponses(): void { variant === 'monthly' ? loadMonthly() : loadAccrued() }
  loadFromResponses()
  watch(() => allResponses.value.get(storageKey)?.remark, (next, previous) => { if (next !== previous && next !== serializeRows()) loadFromResponses() })

  const accounts = computed(() => variant === 'monthly' ? rows.value as MonthlyAccount[] : [])
  const monthlyMatrix = computed<MonthlyMatrixRow[]>(() => Array.from({ length: 12 }, (_, index) => {
    const accountValues: MonthlyMatrixRow['accounts'] = {}
    accounts.value.forEach(account => {
      const balance = account.balances[index] || 0
      accountValues[account.id] = { balance, bookInterest: account.bookInterests[index] || 0, calculatedInterest: balance * account.annualRate / 12 }
    })
    const values = Object.values(accountValues)
    const totalBalance = values.reduce((sum, value) => sum + value.balance, 0)
    const totalCalculated = values.reduce((sum, value) => sum + value.calculatedInterest, 0)
    const totalBook = values.reduce((sum, value) => sum + value.bookInterest, 0)
    return { month: index + 1, accounts: accountValues, totalBalance, totalCalculated, totalBook, diff: totalCalculated - totalBook }
  }))
  const totalCalculated = computed(() => variant === 'monthly'
    ? monthlyMatrix.value.reduce((sum, row) => sum + row.totalCalculated, 0)
    : 0)
  const totalBookInterest = computed(() => monthlyMatrix.value.reduce((sum, row) => sum + row.totalBook, 0))
  watch([totalCalculated, totalBookInterest], ([calculated, book]) => { monthlySummary.value = { totalCalculated: calculated, bookInterest: book, diff: calculated - book } }, { immediate: true })

  const interestStructureRows = computed<InterestStructureRow[]>(() => DEPOSIT_TYPES.map(type => {
    const current = accounts.value.filter(account => account.depositType === type).reduce((sum, account) => sum + account.balances.reduce((subtotal, balance) => subtotal + balance * account.annualRate / 12, 0), 0)
    const prior = parseNum(monthlyAnalysis.value.structurePrior[type]); const change = current - prior
    return { key: type, name: `${type}利息`, current, prior, change, changeRate: prior ? change / prior : '', note: monthlyAnalysis.value.structureNotes[type] || '' }
  }))
  const marketRateRows = computed<MarketRateRow[]>(() => MARKET_TYPES.map(name => {
    const matching = accounts.value.filter(account => account.depositType === name)
    const actualRate = matching.length ? matching.reduce((sum, account) => sum + account.annualRate, 0) / matching.length : 0
    const marketRate = parseNum(monthlyAnalysis.value.marketRates[name]); const diff = actualRate - marketRate
    return { key: name, name, actualRate, marketRate, diff, diffRate: marketRate ? diff / marketRate : '', note: monthlyAnalysis.value.marketNotes[name] || '' }
  }))
  const anomalyRows = computed(() => monthlyAnalysis.value.anomalies)
  const accruedRows = computed(() => variant === 'accrued' ? rows.value as AccruedInterestRow[] : [])
  const accruedCategoryTotals = computed<Record<AccruedInterestCategory, number>>(() => {
    const totals: Record<AccruedInterestCategory, number> = { finance: 0, bank: 0, other: 0, digital: 0 }
    for (const row of accruedRows.value) totals[row.category] += parseNum(row.accruedRmb)
    return totals
  })
  function serializeRows(): string {
    if (variant === 'monthly') return JSON.stringify(accounts.value)
    return JSON.stringify((rows.value as AccruedInterestRow[]).map(row => Object.fromEntries(ACCRUED_FIELDS.map(field => [field, (row as any)[field]]))))
  }
  function summaryJson(): string { return JSON.stringify({ ...monthlySummary.value, ...monthlyAnalysis.value, version: 2 }) }
  let timer: ReturnType<typeof setTimeout> | null = null
  function persist(): void {
    const remark = serializeRows(); const items: ChecklistItem[] = [{ item_id: storageKey, conclusion: null, remark }]
    allResponses.value.set(storageKey, items[0])
    if (variant === 'monthly') {
      const summaryRemark = summaryJson(); const summaryItem = { item_id: SUMMARY_KEY, conclusion: null, remark: summaryRemark }
      allResponses.value.set(SUMMARY_KEY, summaryItem); items.push(summaryItem)
    }
    void saveImmediate(items)
  }
  function scheduleSave(): void { if (timer) clearTimeout(timer); timer = setTimeout(() => { timer = null; persist() }, 1200) }
  async function addAccount(): Promise<void> {
    if (isReadonly.value || variant !== 'monthly') return
    try {
      const { value } = await ElMessageBox.prompt('请输入银行账号或账户名称', '新增存款账户', { confirmButtonText: '添加', cancelButtonText: '取消', inputPattern: /\S+/, inputErrorMessage: '账户名称不能为空' })
      rows.value = [...rows.value, createAccount(value.trim())]; scheduleSave()
    } catch { /* cancelled */ }
  }
  function addRow(): void {
    if (isReadonly.value || variant === 'monthly') return
    rows.value = [...rows.value, emptyAccrued()]; scheduleSave()
  }
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    if (variant === 'monthly' && accounts.value.length <= 1) return
    rows.value = rows.value.filter(row => row.id !== rowId); scheduleSave()
  }
  function updateAccount(rowId: string, field: 'depositType' | 'bank' | 'accountNo' | 'annualRate', value: number | string): void {
    if (isReadonly.value || variant !== 'monthly') return
    const account = accounts.value.find(row => row.id === rowId); if (!account) return
    ;(account as any)[field] = field === 'annualRate' ? parseNum(value) : String(value); rows.value = [...rows.value]; scheduleSave()
  }
  function updateMonthlyCell(rowId: string, month: number, field: 'balance' | 'bookInterest', value: number): void {
    if (isReadonly.value || variant !== 'monthly') return
    const account = accounts.value.find(row => row.id === rowId); if (!account || month < 1 || month > 12) return
    const target = field === 'balance' ? account.balances : account.bookInterests
    target[month - 1] = parseNum(value); rows.value = [...rows.value]; scheduleSave()
  }
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value || variant === 'monthly') return
    const index = rows.value.findIndex(row => row.id === rowId); if (index < 0) return
    const raw: any = { ...(rows.value[index] as AccruedInterestRow) }
    if (field === 'category') raw.category = normalizeAccruedCategory(value)
    else raw[field] = ['fcAmount', 'dailyRate', 'fxRate'].includes(field) ? parseNum(value) : String(value)
    rows.value[index] = recalcAccrued(raw); rows.value = [...rows.value]; scheduleSave()
  }
  function updateSummary(_field: keyof MonthlySummary, _value: number): void { /* 账面利息改由各账户逐月录入 */ }
  function updateStructure(key: string, field: 'prior' | 'note', value: number | string): void {
    if (isReadonly.value) return
    if (field === 'prior') monthlyAnalysis.value.structurePrior[key] = parseNum(value)
    else monthlyAnalysis.value.structureNotes[key] = String(value)
    scheduleSave()
  }
  function updateMarketRate(key: string, field: 'marketRate' | 'note', value: number | string): void {
    if (isReadonly.value) return
    if (field === 'marketRate') monthlyAnalysis.value.marketRates[key] = parseNum(value)
    else monthlyAnalysis.value.marketNotes[key] = String(value)
    scheduleSave()
  }
  function updateAnomaly(key: string, field: keyof InterestAnomalyRow, value: number | string): void {
    if (isReadonly.value) return
    const row = monthlyAnalysis.value.anomalies.find(item => item.key === key); if (!row) return
    ;(row as any)[field] = field === 'amount' ? parseNum(value) : String(value); scheduleSave()
  }
  function hydrate(): void { isLoading.value = true; try { loadFromResponses() } finally { isLoading.value = false } }
  onBeforeUnmount(() => { if (timer) { clearTimeout(timer); persist() } })

  return {
    rows, accounts, monthlyMatrix, monthlySummary, totalCalculated, totalBookInterest,
    interestStructureRows, marketRateRows, anomalyRows, accruedRows, accruedCategoryTotals, isLoading,
    addAccount, addRow, removeRow, updateAccount, updateMonthlyCell, updateCell, updateSummary,
    updateStructure, updateMarketRate, updateAnomaly, hydrate,
  }
}
