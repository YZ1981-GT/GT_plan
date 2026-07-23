/**
 * useE1Reconciliation — E1-6 银行存款余额调节表
 *
 * 每个银行账户维护四类逐笔未达账项；旧版四个汇总金额字段会迁移为占位明细。
 * 企业账面侧 = bookBalance + 银行已收企业未收 - 银行已付企业未付
 * 银行对账单侧 = statementBalance + 企业已收银行未收 - 企业已付银行未付
 */
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'

export type OutstandingItemCategory =
  | 'bankReceivedCompanyUnreceivedItems'
  | 'bankPaidCompanyUnpaidItems'
  | 'companyReceivedBankUnreceivedItems'
  | 'companyPaidBankUnpaidItems'

export interface OutstandingItem {
  id: string
  bankDate: string
  amount: number
  postedAfterPeriod: boolean
  postingDate: string
  voucherNo: string
  description: string
  counterAccount: string
  statementDate: string
  accountingCorrect: boolean | null
  adjustmentRequired: boolean | null
  note: string
}

export interface ReconciliationRow {
  id: string
  bankName: string
  accountNo: string
  bookBalance: number
  statementBalance: number
  bankReceivedCompanyUnreceivedItems: OutstandingItem[]
  bankPaidCompanyUnpaidItems: OutstandingItem[]
  companyReceivedBankUnreceivedItems: OutstandingItem[]
  companyPaidBankUnpaidItems: OutstandingItem[]
  bankReceived: number
  bankPaid: number
  companyReceived: number
  companyPaid: number
  reconciledBook: number
  reconciledStatement: number
  diff: number
  diffReason: string
}

const STORAGE_KEY = 'E1-reconciliation-rows'
const TOLERANCE = 0.005
export const LARGE_AMOUNT_THRESHOLD = 100_000

export const OUTSTANDING_ITEM_CATEGORIES: Array<{
  key: OutstandingItemCategory
  label: string
  shortLabel: string
  side: 'book' | 'statement'
  operator: '+' | '-'
}> = [
  { key: 'bankReceivedCompanyUnreceivedItems', label: '银行已收企业未收', shortLabel: '银收企未收', side: 'book', operator: '+' },
  { key: 'bankPaidCompanyUnpaidItems', label: '银行已付企业未付', shortLabel: '银付企未付', side: 'book', operator: '-' },
  { key: 'companyReceivedBankUnreceivedItems', label: '企业已收银行未收', shortLabel: '企收银未收', side: 'statement', operator: '+' },
  { key: 'companyPaidBankUnpaidItems', label: '企业已付银行未付', shortLabel: '企付银未付', side: 'statement', operator: '-' },
]

function generateId(prefix: string): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) return `${prefix}-${crypto.randomUUID()}`
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createEmptyItem(overrides: Partial<OutstandingItem> = {}): OutstandingItem {
  return {
    id: generateId('recon-item'),
    bankDate: '',
    amount: 0,
    postedAfterPeriod: false,
    postingDate: '',
    voucherNo: '',
    description: '',
    counterAccount: '',
    statementDate: '',
    accountingCorrect: null,
    adjustmentRequired: null,
    note: '',
    ...overrides,
  }
}

function normalizeNullableBoolean(value: unknown): boolean | null {
  if (value === true || value === 'true' || value === '是') return true
  if (value === false || value === 'false' || value === '否') return false
  return null
}

function normalizeItem(raw: unknown): OutstandingItem {
  const item = raw && typeof raw === 'object' ? raw as Record<string, unknown> : {}
  return createEmptyItem({
    id: String(item.id || generateId('recon-item')),
    bankDate: String(item.bankDate || ''),
    amount: parseNum(item.amount),
    postedAfterPeriod: normalizeNullableBoolean(item.postedAfterPeriod) === true,
    postingDate: String(item.postingDate || ''),
    voucherNo: String(item.voucherNo || ''),
    description: String(item.description || ''),
    counterAccount: String(item.counterAccount || ''),
    statementDate: String(item.statementDate || ''),
    accountingCorrect: normalizeNullableBoolean(item.accountingCorrect),
    adjustmentRequired: normalizeNullableBoolean(item.adjustmentRequired),
    note: String(item.note || ''),
  })
}

function legacyPlaceholder(amount: unknown, label: string): OutstandingItem[] {
  const parsed = parseNum(amount)
  if (Math.abs(parsed) <= TOLERANCE) return []
  return [createEmptyItem({
    amount: parsed,
    description: `${label}（旧汇总金额迁移）`,
    note: '由旧版汇总金额自动迁移，请补充日期、凭证及入账情况。',
  })]
}

function normalizeItems(
  raw: Record<string, unknown>,
  key: OutstandingItemCategory,
  legacyField: keyof Pick<ReconciliationRow, 'bankReceived' | 'bankPaid' | 'companyReceived' | 'companyPaid'>,
  label: string,
): OutstandingItem[] {
  const value = raw[key]
  if (Array.isArray(value)) return value.map(normalizeItem)
  return legacyPlaceholder(raw[legacyField], label)
}

function sumItems(items: OutstandingItem[]): number {
  return items.reduce((total, item) => total + parseNum(item.amount), 0)
}

function recalcRow(row: ReconciliationRow): ReconciliationRow {
  const companyReceived = sumItems(row.bankReceivedCompanyUnreceivedItems)
  const companyPaid = sumItems(row.bankPaidCompanyUnpaidItems)
  const bankReceived = sumItems(row.companyReceivedBankUnreceivedItems)
  const bankPaid = sumItems(row.companyPaidBankUnpaidItems)
  const reconciledBook = parseNum(row.bookBalance) + companyReceived - companyPaid
  const reconciledStatement = parseNum(row.statementBalance) + bankReceived - bankPaid
  return {
    ...row,
    bankReceived,
    bankPaid,
    companyReceived,
    companyPaid,
    reconciledBook,
    reconciledStatement,
    diff: reconciledBook - reconciledStatement,
  }
}

function createEmptyRow(): ReconciliationRow {
  return recalcRow({
    id: generateId('recon'),
    bankName: '',
    accountNo: '',
    bookBalance: 0,
    statementBalance: 0,
    bankReceivedCompanyUnreceivedItems: [],
    bankPaidCompanyUnpaidItems: [],
    companyReceivedBankUnreceivedItems: [],
    companyPaidBankUnpaidItems: [],
    bankReceived: 0,
    bankPaid: 0,
    companyReceived: 0,
    companyPaid: 0,
    reconciledBook: 0,
    reconciledStatement: 0,
    diff: 0,
    diffReason: '',
  })
}

function normalizeRow(rawValue: unknown): ReconciliationRow {
  const raw = rawValue && typeof rawValue === 'object' ? rawValue as Record<string, unknown> : {}
  return recalcRow({
    id: String(raw.id || generateId('recon')),
    bankName: String(raw.bankName || ''),
    accountNo: String(raw.accountNo || ''),
    bookBalance: parseNum(raw.bookBalance),
    statementBalance: parseNum(raw.statementBalance),
    bankReceivedCompanyUnreceivedItems: normalizeItems(raw, 'bankReceivedCompanyUnreceivedItems', 'companyReceived', '银行已收企业未收'),
    bankPaidCompanyUnpaidItems: normalizeItems(raw, 'bankPaidCompanyUnpaidItems', 'companyPaid', '银行已付企业未付'),
    companyReceivedBankUnreceivedItems: normalizeItems(raw, 'companyReceivedBankUnreceivedItems', 'bankReceived', '企业已收银行未收'),
    companyPaidBankUnpaidItems: normalizeItems(raw, 'companyPaidBankUnpaidItems', 'bankPaid', '企业已付银行未付'),
    bankReceived: 0,
    bankPaid: 0,
    companyReceived: 0,
    companyPaid: 0,
    reconciledBook: 0,
    reconciledStatement: 0,
    diff: 0,
    diffReason: String(raw.diffReason || ''),
  })
}

function dateValue(value: string): number | null {
  if (!value) return null
  const time = new Date(`${value}T00:00:00`).getTime()
  return Number.isFinite(time) ? time : null
}

export function getOutstandingItemAgeDays(item: OutstandingItem): number | null {
  const start = dateValue(item.bankDate || item.statementDate)
  if (start === null) return null
  const end = dateValue(item.postingDate) ?? Date.now()
  return Math.max(0, Math.floor((end - start) / 86_400_000))
}

export function getOutstandingItemRiskTags(item: OutstandingItem): string[] {
  const tags: string[] = []
  const ageDays = getOutstandingItemAgeDays(item)
  if (ageDays !== null && ageDays > 90) tags.push(`长期未达 ${ageDays} 天`)
  if (Math.abs(item.amount) >= LARGE_AMOUNT_THRESHOLD) tags.push('大额未达')
  if (item.postedAfterPeriod && !item.postingDate) tags.push('报表日后未入账')
  return tags
}

export function useE1Reconciliation(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options
  const rows = ref<ReconciliationRow[]>([createEmptyRow()])
  const isLoading = ref(false)

  function loadFromResponses(): void {
    const raw = allResponses.value.get(STORAGE_KEY)?.remark
    if (!raw) {
      rows.value = [createEmptyRow()]
      return
    }
    try {
      const parsed = JSON.parse(raw)
      rows.value = Array.isArray(parsed) && parsed.length ? parsed.map(normalizeRow) : [createEmptyRow()]
    } catch {
      console.warn('[useE1Reconciliation] JSON parse failed, fallback to empty')
      rows.value = [createEmptyRow()]
    }
  }

  function serializeRows(): string {
    return JSON.stringify(rows.value.map(recalcRow))
  }

  loadFromResponses()
  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    (next, previous) => {
      if (next !== previous && next !== serializeRows()) loadFromResponses()
    },
  )

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function persistToResponses(): void {
    const remark = serializeRows()
    const item: ChecklistItem = { item_id: STORAGE_KEY, conclusion: null, remark }
    allResponses.value.set(STORAGE_KEY, item)
    saveImmediate([item]).catch(() => { /* parent handles save errors */ })
  }
  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistToResponses()
    }, 2000)
  }

  function hasDiff(row: ReconciliationRow): boolean {
    return Math.abs(row.diff) > TOLERANCE
  }
  function isMissingReason(row: ReconciliationRow): boolean {
    return hasDiff(row) && !row.diffReason.trim()
  }
  function categoryTotal(row: ReconciliationRow, category: OutstandingItemCategory): number {
    return sumItems(row[category])
  }
  function getRiskAlerts(row: ReconciliationRow): string[] {
    const counts = { longTerm: 0, large: 0, unposted: 0 }
    for (const category of OUTSTANDING_ITEM_CATEGORIES) {
      for (const item of row[category.key]) {
        const risks = getOutstandingItemRiskTags(item)
        if (risks.some(risk => risk.startsWith('长期未达'))) counts.longTerm += 1
        if (risks.includes('大额未达')) counts.large += 1
        if (risks.includes('报表日后未入账')) counts.unposted += 1
      }
    }
    const alerts: string[] = []
    if (counts.longTerm) alerts.push(`${counts.longTerm} 笔未达账项超过 90 天，请核查长期挂账原因及可收回性。`)
    if (counts.large) alerts.push(`${counts.large} 笔未达账项金额达到 10 万元，请结合重要性水平扩大核查。`)
    if (counts.unposted) alerts.push(`${counts.unposted} 笔标记为报表日后处理但尚无入账日期，请追查期后凭证。`)
    return alerts
  }

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow()]
    scheduleSave()
  }
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.filter(row => row.id !== rowId)
    scheduleSave()
  }
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const index = rows.value.findIndex(row => row.id === rowId)
    if (index < 0) return
    const row = { ...rows.value[index] }
    if (field === 'bookBalance' || field === 'statementBalance') (row as any)[field] = parseNum(value)
    else (row as any)[field] = String(value)
    rows.value = rows.value.map((current, idx) => idx === index ? recalcRow(row) : current)
    scheduleSave()
  }
  function addOutstandingItem(rowId: string, category: OutstandingItemCategory): void {
    if (isReadonly.value) return
    rows.value = rows.value.map(row => row.id === rowId
      ? recalcRow({ ...row, [category]: [...row[category], createEmptyItem()] })
      : row)
    scheduleSave()
  }
  function removeOutstandingItem(rowId: string, category: OutstandingItemCategory, itemId: string): void {
    if (isReadonly.value) return
    rows.value = rows.value.map(row => row.id === rowId
      ? recalcRow({ ...row, [category]: row[category].filter(item => item.id !== itemId) })
      : row)
    scheduleSave()
  }
  function updateOutstandingItem(
    rowId: string,
    category: OutstandingItemCategory,
    itemId: string,
    field: keyof OutstandingItem,
    value: unknown,
  ): void {
    if (isReadonly.value) return
    rows.value = rows.value.map(row => {
      if (row.id !== rowId) return row
      const items = row[category].map(item => {
        if (item.id !== itemId) return item
        if (field === 'amount') return { ...item, amount: parseNum(value) }
        if (field === 'postedAfterPeriod') return { ...item, postedAfterPeriod: value === true }
        if (field === 'accountingCorrect' || field === 'adjustmentRequired') {
          return { ...item, [field]: normalizeNullableBoolean(value) }
        }
        return { ...item, [field]: String(value ?? '') }
      })
      return recalcRow({ ...row, [category]: items })
    })
    scheduleSave()
  }

  function hydrate(): void {
    isLoading.value = true
    try { loadFromResponses() } finally { isLoading.value = false }
  }

  // ─── P1-6: E1-6 余额调节 ↔ E1-3 银行明细交叉校验 ─────────────────────────

  /**
   * 检查调节表中每个银行账户的对账单余额(statementBalance)是否与 E1-3 同账号行一致。
   * 返回不一致的账户列表(含账号、调节表值、明细表值)。
   */
  const reconciliationCrossCheck = computed<Array<{ accountNo: string; reconBalance: number; bankDetailBalance: number; diff: number }>>(() => {
    const bankDetailRaw = allResponses.value.get('E1-bank-detail-rows')?.remark
    if (!bankDetailRaw) return []
    try {
      const bankRows = JSON.parse(bankDetailRaw)
      if (!Array.isArray(bankRows)) return []
      // Build map: accountNo → E1-3 statementBalance
      const bankMap = new Map<string, number>()
      for (const r of bankRows) {
        const no = String(r.accountNo || '').trim()
        if (no) bankMap.set(no, parseNum(r.statementBalance))
      }
      // Compare with reconciliation rows
      const mismatches: Array<{ accountNo: string; reconBalance: number; bankDetailBalance: number; diff: number }> = []
      for (const row of rows.value) {
        const no = row.accountNo?.trim()
        if (!no || !bankMap.has(no)) continue
        const bankBalance = bankMap.get(no) || 0
        const reconBalance = row.statementBalance
        const diff = Math.abs(reconBalance - bankBalance)
        if (diff > 0.01) {
          mismatches.push({ accountNo: no, reconBalance, bankDetailBalance: bankBalance, diff })
        }
      }
      return mismatches
    } catch { return [] }
  })

  onBeforeUnmount(() => {
    if (!saveTimer) return
    clearTimeout(saveTimer)
    saveTimer = null
    persistToResponses()
  })

  return {
    rows,
    isLoading,
    hasDiff,
    isMissingReason,
    categoryTotal,
    getRiskAlerts,
    getOutstandingItemRiskTags,
    reconciliationCrossCheck,
    addRow,
    removeRow,
    updateCell,
    addOutstandingItem,
    removeOutstandingItem,
    updateOutstandingItem,
    hydrate,
  }
}

