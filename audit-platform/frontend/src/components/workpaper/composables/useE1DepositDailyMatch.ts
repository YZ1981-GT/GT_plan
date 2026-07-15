/**
 * useE1DepositDailyMatch — E1-30 存款规模与利息收入匹配性分析
 *
 * - 按活期 / 七天通知 / 大额存单配置银行账号
 * - 按日填写余额；利息 = 余额 × 年利率 / 360（对齐源模板）
 * - 测算合计 vs 账面利息 → 差异
 */
import { computed, onBeforeUnmount, ref, watch, type Ref } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'

export const E1_DEPOSIT_DAILY_PACK_KEY = 'E1-deposit-daily-pack'
export const E1_DEPOSIT_DAILY_NOTE_KEY = 'E1-deposit-daily-audit-note'
export const E1_DEPOSIT_DAILY_CONCLUSION_KEY = 'E1-deposit-daily-audit-conclusion'
export const E1_IPO_APPLICABLE_KEY = 'E1-ipo-applicable'

/** E1-15 月度利息测算账户行 */
const E1_15_MONTHLY_KEY = 'E1-interest-monthly-rows'
const E1_15_SUMMARY_KEY = 'E1-interest-monthly-rows-summary'

export type E15SyncMode = 'replace' | 'merge'

export function mapDepositTypeFromE15(raw: string): DailyDepositType {
  const s = String(raw || '')
  if (s.includes('七天') || s.includes('通知')) return 'notice'
  if (s.includes('大额') || s.includes('存单') || s.includes('CD')) return 'cd'
  return 'demand'
}

/** 解析 E1-15 月度账户 JSON（支持数组 / {accounts} / {rows}） */
export function parseE15AccountList(raw: string | null | undefined): any[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed
    if (parsed && Array.isArray(parsed.accounts)) return parsed.accounts
    if (parsed && Array.isArray(parsed.rows)) return parsed.rows
  } catch {
    return []
  }
  return []
}

export function readE15BookInterest(summaryRaw: string | null | undefined, accounts: any[]): number {
  if (summaryRaw) {
    try {
      const sum = JSON.parse(summaryRaw)
      const v = parseNum(sum.bookInterest ?? sum.totalBook)
      if (v) return v
    } catch { /* ignore */ }
  }
  let bookInterest = 0
  for (const a of accounts) {
    if (Array.isArray(a.bookInterests)) {
      bookInterest += a.bookInterests.reduce((s: number, v: any) => s + parseNum(v), 0)
    }
  }
  return bookInterest
}

export interface E15SyncPreview {
  accountCount: number
  banks: string[]
  bookInterest: number
  existingGroups: number
}

export function previewE15Accounts(
  accounts: any[],
  bookInterest: number,
  existingGroups: number,
): E15SyncPreview {
  const banks = Array.from(new Set(
    accounts.map(a => String(a.bank || '').trim()).filter(Boolean),
  )).slice(0, 8)
  return {
    accountCount: accounts.length,
    banks,
    bookInterest,
    existingGroups,
  }
}

function groupKey(bank: string, depositType: DailyDepositType): string {
  return `${depositType}||${bank}`
}

function acctKey(bank: string, accountNo: string, depositType: DailyDepositType): string {
  return `${depositType}||${bank}||${accountNo}`
}

/** 由 E1-15 账户生成 E1-30 组（纯函数，便于单测） */
export function buildGroupsFromE15Accounts(accounts: any[]): Array<DailyBankGroup & { _balances: number[]; _acctId: string }> {
  return accounts.map((a: any) => {
    const depositType = mapDepositTypeFromE15(a.depositType || a.type || '')
    const acctId = uid('da')
    return {
      id: uid('dg'),
      depositType,
      bank: String(a.bank || ''),
      annualRate: parseNum(a.annualRate ?? a.rate),
      accounts: [{
        id: acctId,
        accountNo: String(a.accountNo || a.account || '账号'),
      }],
      _balances: Array.isArray(a.balances) ? a.balances.map((x: any) => parseNum(x)) : [],
      _acctId: acctId,
    }
  })
}

/** 月余额摊成日余额；skipExisting 时不覆盖已有格子 */
export function expandMonthlyToDailyBalances(
  year: number,
  groups: Array<{ _acctId: string; _balances: number[] }>,
  existing: Record<string, Record<string, number>>,
  skipExisting: boolean,
): { balances: Record<string, Record<string, number>>; daysFilled: number } {
  const balances: Record<string, Record<string, number>> = skipExisting
    ? JSON.parse(JSON.stringify(existing || {}))
    : {}
  let daysFilled = 0
  for (const g of groups) {
    const acctId = g._acctId
    const monthly = g._balances || []
    for (let m = 1; m <= 12; m++) {
      const bal = parseNum(monthly[m - 1])
      if (!bal) continue
      const dim = daysInMonth(year, m)
      for (let d = 1; d <= dim; d++) {
        const date = `${year}-${String(m).padStart(2, '0')}-${String(d).padStart(2, '0')}`
        if (!balances[date]) balances[date] = {}
        if (skipExisting && balances[date][acctId] != null && balances[date][acctId] !== 0) continue
        balances[date][acctId] = bal
        daysFilled += 1
      }
    }
  }
  return { balances, daysFilled }
}

/** merge：按 类型+银行+账号 合并，保留已有日余额/利率 */
export function mergeE15GroupsIntoExisting(
  existing: DailyBankGroup[],
  incoming: Array<DailyBankGroup & { _balances: number[]; _acctId: string }>,
): {
  groups: DailyBankGroup[]
  stashed: Array<{ _acctId: string; _balances: number[] }>
  addedAccounts: number
} {
  const groups: DailyBankGroup[] = existing.map(g => ({
    ...g,
    accounts: g.accounts.map(a => ({ ...a })),
  }))
  const byAcct = new Map<string, { groupIdx: number; acctId: string }>()
  const byGroup = new Map<string, number>()
  groups.forEach((g, gi) => {
    byGroup.set(groupKey(g.bank, g.depositType), gi)
    g.accounts.forEach(a => {
      byAcct.set(acctKey(g.bank, a.accountNo, g.depositType), { groupIdx: gi, acctId: a.id })
    })
  })

  const stashed: Array<{ _acctId: string; _balances: number[] }> = []
  let addedAccounts = 0

  for (const inc of incoming) {
    const ak = acctKey(inc.bank, inc.accounts[0]?.accountNo || '', inc.depositType)
    const hit = byAcct.get(ak)
    if (hit) {
      const g = groups[hit.groupIdx]
      if (!g.annualRate && inc.annualRate) g.annualRate = inc.annualRate
      stashed.push({ _acctId: hit.acctId, _balances: inc._balances })
      continue
    }
    const gk = groupKey(inc.bank, inc.depositType)
    let gi = byGroup.get(gk)
    if (gi == null) {
      gi = groups.length
      groups.push({
        id: inc.id,
        depositType: inc.depositType,
        bank: inc.bank,
        annualRate: inc.annualRate,
        accounts: [],
      })
      byGroup.set(gk, gi)
    }
    const acct = { id: inc._acctId, accountNo: inc.accounts[0]?.accountNo || '账号' }
    groups[gi].accounts.push(acct)
    if (!groups[gi].annualRate && inc.annualRate) groups[gi].annualRate = inc.annualRate
    byAcct.set(ak, { groupIdx: gi, acctId: acct.id })
    stashed.push({ _acctId: acct.id, _balances: inc._balances })
    addedAccounts += 1
  }
  return { groups, stashed, addedAccounts }
}

function daysInMonth(year: number, month1to12: number): number {
  return new Date(year, month1to12, 0).getDate()
}

export type DailyDepositType = 'demand' | 'notice' | 'cd'

export const DAILY_DEPOSIT_TYPE_OPTIONS: Array<{ value: DailyDepositType; label: string }> = [
  { value: 'demand', label: '活期存款' },
  { value: 'notice', label: '七天通知存款' },
  { value: 'cd', label: '大额存单' },
]

export function dailyDepositTypeLabel(t: DailyDepositType): string {
  return DAILY_DEPOSIT_TYPE_OPTIONS.find(o => o.value === t)?.label || t
}

/** 银行组：同源模板「XX银行」下挂若干账号；活期利率在组级，七天/大额可按日覆写 */
export interface DailyBankGroup {
  id: string
  depositType: DailyDepositType
  bank: string
  /** 年利率（小数，如 0.0035 = 0.35%） */
  annualRate: number
  accounts: Array<{ id: string; accountNo: string }>
}

export interface DepositDailyPack {
  year: number
  groups: DailyBankGroup[]
  /** dateISO -> accountId -> balance */
  balances: Record<string, Record<string, number>>
  /** dateISO -> accountId -> 年利率覆写（七天/大额按日利率）；缺省用组 annualRate */
  rateOverrides: Record<string, Record<string, number>>
  bookInterest: number
}

function uid(prefix: string): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

export function createEmptyGroup(
  depositType: DailyDepositType = 'demand',
  partial?: Partial<DailyBankGroup>,
): DailyBankGroup {
  const acctId = uid('da')
  return {
    id: uid('dg'),
    depositType,
    bank: '',
    annualRate: 0,
    accounts: [{ id: acctId, accountNo: '账号1' }],
    ...(partial || {}),
    accounts: partial?.accounts?.length
      ? partial.accounts.map(a => ({
          id: a.id || uid('da'),
          accountNo: a.accountNo || '账号',
        }))
      : [{ id: acctId, accountNo: '账号1' }],
    depositType: partial?.depositType || depositType,
  }
}

export function defaultGroups(): DailyBankGroup[] {
  return [
    createEmptyGroup('demand', { bank: 'XX银行' }),
    createEmptyGroup('notice', { bank: 'XX银行' }),
    createEmptyGroup('cd', { bank: 'XX银行' }),
  ]
}

/** 从报表截止日或年份得到自然年日期列表（含闰年） */
export function buildYearDates(year: number): string[] {
  const y = year > 1900 && year < 2200 ? year : new Date().getFullYear() - 1
  const dates: string[] = []
  const d = new Date(Date.UTC(y, 0, 1))
  const end = Date.UTC(y, 11, 31)
  while (d.getTime() <= end) {
    const mm = String(d.getUTCMonth() + 1).padStart(2, '0')
    const dd = String(d.getUTCDate()).padStart(2, '0')
    dates.push(`${y}-${mm}-${dd}`)
    d.setUTCDate(d.getUTCDate() + 1)
  }
  return dates
}

export function yearFromBsDate(bsDate?: string): number {
  if (bsDate && bsDate.length >= 4) {
    const y = parseInt(bsDate.slice(0, 4), 10)
    if (Number.isFinite(y) && y > 1900) return y
  }
  return new Date().getFullYear() - 1
}

/** 单日：组利息 */
export function calcGroupDayInterest(
  group: DailyBankGroup,
  date: string,
  balances: Record<string, number>,
  rateOverrides: Record<string, number>,
): number {
  const rateDefault = parseNum(group.annualRate)
  if (group.depositType === 'demand') {
    const sumBal = group.accounts.reduce((s, a) => s + parseNum(balances[a.id]), 0)
    return sumBal * rateDefault / 360
  }
  // 七天 / 大额：各账号 余额×利率/360 后加总
  return group.accounts.reduce((s, a) => {
    const bal = parseNum(balances[a.id])
    const rate = rateOverrides[a.id] != null && rateOverrides[a.id] !== undefined
      ? parseNum(rateOverrides[a.id])
      : rateDefault
    return s + bal * rate / 360
  }, 0)
}

function normalizeGroup(raw: any): DailyBankGroup {
  const type = String(raw.depositType || 'demand') as DailyDepositType
  const accountsRaw = Array.isArray(raw.accounts) ? raw.accounts : []
  const accounts = accountsRaw.length
    ? accountsRaw.map((a: any) => ({
        id: String(a.id || uid('da')),
        accountNo: String(a.accountNo || '账号'),
      }))
    : [{ id: uid('da'), accountNo: '账号1' }]
  return {
    id: String(raw.id || uid('dg')),
    depositType: (['demand', 'notice', 'cd'] as DailyDepositType[]).includes(type) ? type : 'demand',
    bank: String(raw.bank || ''),
    annualRate: parseNum(raw.annualRate),
    accounts,
  }
}

function emptyPack(year: number): DepositDailyPack {
  return {
    year,
    groups: defaultGroups(),
    balances: {},
    rateOverrides: {},
    bookInterest: 0,
  }
}

export function useE1DepositDailyMatch(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly, bsDate } = options

  const pack = ref<DepositDailyPack>(emptyPack(yearFromBsDate(bsDate?.value)))
  const auditNote = ref('')
  const auditConclusion = ref('')
  const isLoading = ref(false)
  /** 当前查看月份 1–12，避免一次渲染整年 */
  const viewMonth = ref(1)

  const isApplicable = computed(() => {
    const v = allResponses.value.get(E1_IPO_APPLICABLE_KEY)?.conclusion
    return v !== 'N'
  })

  const yearDates = computed(() => buildYearDates(pack.value.year))

  const monthDates = computed(() => {
    const prefix = `${pack.value.year}-${String(viewMonth.value).padStart(2, '0')}-`
    return yearDates.value.filter(d => d.startsWith(prefix))
  })

  const allAccountIds = computed(() =>
    pack.value.groups.flatMap(g => g.accounts.map(a => a.id)),
  )

  function dayBalances(date: string): Record<string, number> {
    return pack.value.balances[date] || {}
  }
  function dayRates(date: string): Record<string, number> {
    return pack.value.rateOverrides[date] || {}
  }

  function dayInterest(date: string): number {
    const bal = dayBalances(date)
    const rates = dayRates(date)
    return pack.value.groups.reduce(
      (s, g) => s + calcGroupDayInterest(g, date, bal, rates),
      0,
    )
  }

  function groupDayInterest(groupId: string, date: string): number {
    const g = pack.value.groups.find(x => x.id === groupId)
    if (!g) return 0
    return calcGroupDayInterest(g, date, dayBalances(date), dayRates(date))
  }

  const calculatedInterest = computed(() =>
    yearDates.value.reduce((s, d) => s + dayInterest(d), 0),
  )

  const interestDiff = computed(() =>
    calculatedInterest.value - parseNum(pack.value.bookInterest),
  )

  const groupYearInterest = computed(() => {
    const map: Record<string, number> = {}
    for (const g of pack.value.groups) {
      map[g.id] = yearDates.value.reduce(
        (s, d) => s + calcGroupDayInterest(g, d, dayBalances(d), dayRates(d)),
        0,
      )
    }
    return map
  })

  /** 按类型小计 */
  const typeYearInterest = computed(() => {
    const map: Record<DailyDepositType, number> = { demand: 0, notice: 0, cd: 0 }
    for (const g of pack.value.groups) {
      map[g.depositType] += groupYearInterest.value[g.id] || 0
    }
    return map
  })

  function load(): void {
    isLoading.value = true
    try {
      const y = yearFromBsDate(bsDate?.value)
      const raw = allResponses.value.get(E1_DEPOSIT_DAILY_PACK_KEY)?.remark
      if (raw) {
        try {
          const parsed = JSON.parse(raw)
          if (parsed && typeof parsed === 'object') {
            // 兼容旧 IPO 扁平行
            if (Array.isArray(parsed)) {
              pack.value = emptyPack(y)
              const g = pack.value.groups[0]
              const acct = g.accounts[0]
              for (const row of parsed) {
                const date = String(row.date || '')
                if (!date) continue
                if (!pack.value.balances[date]) pack.value.balances[date] = {}
                pack.value.balances[date][acct.id] = parseNum(
                  row.demandDeposit ?? row.balance ?? row.amount,
                )
              }
            } else {
              pack.value = {
                year: parseNum(parsed.year) || y,
                groups: Array.isArray(parsed.groups) && parsed.groups.length
                  ? parsed.groups.map(normalizeGroup)
                  : defaultGroups(),
                balances: typeof parsed.balances === 'object' && parsed.balances
                  ? parsed.balances
                  : {},
                rateOverrides: typeof parsed.rateOverrides === 'object' && parsed.rateOverrides
                  ? parsed.rateOverrides
                  : {},
                bookInterest: parseNum(parsed.bookInterest),
              }
            }
          }
        } catch {
          pack.value = emptyPack(y)
        }
      } else {
        // 旧 IPO 扁平行 E1-ipo-E1-30-rows
        const legacy = allResponses.value.get('E1-ipo-E1-30-rows')?.remark
        if (legacy) {
          try {
            const list = JSON.parse(legacy)
            if (Array.isArray(list) && list.length) {
              pack.value = emptyPack(y)
              const g = pack.value.groups[0]
              const acct = g.accounts[0]
              for (const row of list) {
                const date = String(row.date || '')
                if (!date) continue
                if (!pack.value.balances[date]) pack.value.balances[date] = {}
                pack.value.balances[date][acct.id] = parseNum(
                  row.demandDeposit ?? row.balance ?? row.amount ?? row.sevenDayNotice ?? row.largeCd,
                )
              }
            } else {
              pack.value = emptyPack(y)
            }
          } catch {
            pack.value = emptyPack(y)
          }
        } else {
          pack.value = emptyPack(y)
        }
      }
      auditNote.value = allResponses.value.get(E1_DEPOSIT_DAILY_NOTE_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-note-E1-30')?.remark
        || ''
      auditConclusion.value = allResponses.value.get(E1_DEPOSIT_DAILY_CONCLUSION_KEY)?.remark
        || allResponses.value.get('E1-ipo-audit-conclusion-E1-30')?.remark
        || ''
    } finally {
      isLoading.value = false
    }
  }

  load()

  watch(
    () => allResponses.value.get(E1_DEPOSIT_DAILY_PACK_KEY)?.remark,
    (n, o) => {
      if (n !== o) load()
    },
  )
  watch(
    () => bsDate?.value,
    (v) => {
      const y = yearFromBsDate(v)
      if (y !== pack.value.year && !Object.keys(pack.value.balances).length) {
        pack.value = { ...pack.value, year: y }
      }
    },
  )

  let saveTimer: ReturnType<typeof setTimeout> | null = null
  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persist()
    }, 2000)
  }

  function persist(): void {
    const remark = JSON.stringify({
      year: pack.value.year,
      groups: pack.value.groups,
      balances: pack.value.balances,
      rateOverrides: pack.value.rateOverrides,
      bookInterest: pack.value.bookInterest,
    })
    const item: ChecklistItem = {
      item_id: E1_DEPOSIT_DAILY_PACK_KEY,
      conclusion: null,
      remark,
    }
    allResponses.value.set(E1_DEPOSIT_DAILY_PACK_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function setApplicable(val: boolean): void {
    if (isReadonly.value) return
    const item = {
      item_id: E1_IPO_APPLICABLE_KEY,
      conclusion: val ? 'Y' : 'N',
      remark: null,
    }
    allResponses.value.set(E1_IPO_APPLICABLE_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function setYear(y: number): void {
    if (isReadonly.value) return
    pack.value = { ...pack.value, year: y }
    scheduleSave()
  }

  function setBookInterest(v: number): void {
    if (isReadonly.value) return
    pack.value = { ...pack.value, bookInterest: parseNum(v) }
    scheduleSave()
  }

  function addGroup(depositType: DailyDepositType): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      groups: [...pack.value.groups, createEmptyGroup(depositType)],
    }
    scheduleSave()
  }

  function removeGroup(groupId: string): void {
    if (isReadonly.value) return
    const g = pack.value.groups.find(x => x.id === groupId)
    const ids = new Set(g?.accounts.map(a => a.id) || [])
    const balances = { ...pack.value.balances }
    const rateOverrides = { ...pack.value.rateOverrides }
    for (const date of Object.keys(balances)) {
      const row = { ...balances[date] }
      for (const id of ids) delete row[id]
      balances[date] = row
    }
    for (const date of Object.keys(rateOverrides)) {
      const row = { ...rateOverrides[date] }
      for (const id of ids) delete row[id]
      rateOverrides[date] = row
    }
    let groups = pack.value.groups.filter(x => x.id !== groupId)
    if (!groups.length) groups = defaultGroups()
    pack.value = { ...pack.value, groups, balances, rateOverrides }
    scheduleSave()
  }

  function updateGroup(
    groupId: string,
    field: 'bank' | 'annualRate' | 'depositType',
    value: string | number,
  ): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      groups: pack.value.groups.map(g => {
        if (g.id !== groupId) return g
        if (field === 'annualRate') return { ...g, annualRate: parseNum(value) }
        if (field === 'depositType') {
          const t = String(value) as DailyDepositType
          return {
            ...g,
            depositType: (['demand', 'notice', 'cd'] as DailyDepositType[]).includes(t) ? t : g.depositType,
          }
        }
        return { ...g, bank: String(value ?? '') }
      }),
    }
    scheduleSave()
  }

  function addAccount(groupId: string): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      groups: pack.value.groups.map(g => {
        if (g.id !== groupId) return g
        return {
          ...g,
          accounts: [...g.accounts, { id: uid('da'), accountNo: `账号${g.accounts.length + 1}` }],
        }
      }),
    }
    scheduleSave()
  }

  function removeAccount(groupId: string, accountId: string): void {
    if (isReadonly.value) return
    const balances = { ...pack.value.balances }
    const rateOverrides = { ...pack.value.rateOverrides }
    for (const date of Object.keys(balances)) {
      const row = { ...balances[date] }
      delete row[accountId]
      balances[date] = row
    }
    for (const date of Object.keys(rateOverrides)) {
      const row = { ...rateOverrides[date] }
      delete row[accountId]
      rateOverrides[date] = row
    }
    pack.value = {
      ...pack.value,
      balances,
      rateOverrides,
      groups: pack.value.groups.map(g => {
        if (g.id !== groupId) return g
        const accounts = g.accounts.filter(a => a.id !== accountId)
        return {
          ...g,
          accounts: accounts.length ? accounts : [{ id: uid('da'), accountNo: '账号1' }],
        }
      }),
    }
    scheduleSave()
  }

  function updateAccountNo(groupId: string, accountId: string, accountNo: string): void {
    if (isReadonly.value) return
    pack.value = {
      ...pack.value,
      groups: pack.value.groups.map(g => {
        if (g.id !== groupId) return g
        return {
          ...g,
          accounts: g.accounts.map(a =>
            a.id === accountId ? { ...a, accountNo: String(accountNo ?? '') } : a,
          ),
        }
      }),
    }
    scheduleSave()
  }

  function setBalance(date: string, accountId: string, value: number): void {
    if (isReadonly.value) return
    const balances = { ...pack.value.balances }
    const row = { ...(balances[date] || {}) }
    const n = parseNum(value)
    if (!n) delete row[accountId]
    else row[accountId] = n
    balances[date] = row
    pack.value = { ...pack.value, balances }
    scheduleSave()
  }

  function setRateOverride(date: string, accountId: string, value: number): void {
    if (isReadonly.value) return
    const rateOverrides = { ...pack.value.rateOverrides }
    const row = { ...(rateOverrides[date] || {}) }
    const n = parseNum(value)
    if (!n) delete row[accountId]
    else row[accountId] = n
    rateOverrides[date] = row
    pack.value = { ...pack.value, rateOverrides }
    scheduleSave()
  }

  /**
   * 预览 E1-15 → E1-30 同步规模（不写盘）
   */
  function previewSyncFromE15(): E15SyncPreview | null {
    const accounts = parseE15AccountList(allResponses.value.get(E1_15_MONTHLY_KEY)?.remark)
    if (!accounts.length) return null
    const bookInterest = readE15BookInterest(
      allResponses.value.get(E1_15_SUMMARY_KEY)?.remark,
      accounts,
    )
    return previewE15Accounts(accounts, bookInterest, pack.value.groups.length)
  }

  /**
   * 从 E1-15 同步：账户组（类型/银行/账号/年利率）+ 账面利息合计；
   * mode=replace 覆盖账户组；mode=merge 按账号合并并保留已有日余额。
   * 可选把月均余额摊成日余额（同月每日同额），便于再人工精修。
   */
  function syncFromE15(opts?: {
    fillDailyFromMonthly?: boolean
    mode?: E15SyncMode
  }): {
    groups: number
    bookInterest: number
    daysFilled: number
    addedAccounts: number
    mode: E15SyncMode
  } {
    const mode: E15SyncMode = opts?.mode === 'merge' ? 'merge' : 'replace'
    if (isReadonly.value) {
      return { groups: 0, bookInterest: 0, daysFilled: 0, addedAccounts: 0, mode }
    }
    const accounts = parseE15AccountList(allResponses.value.get(E1_15_MONTHLY_KEY)?.remark)
    if (!accounts.length) {
      return { groups: 0, bookInterest: 0, daysFilled: 0, addedAccounts: 0, mode }
    }

    const y = pack.value.year || yearFromBsDate(bsDate?.value)
    const incoming = buildGroupsFromE15Accounts(accounts)
    const bookInterest = readE15BookInterest(
      allResponses.value.get(E1_15_SUMMARY_KEY)?.remark,
      accounts,
    ) || pack.value.bookInterest

    let cleanGroups: DailyBankGroup[]
    let stashed: Array<{ _acctId: string; _balances: number[] }>
    let addedAccounts = 0

    if (mode === 'merge') {
      const m = mergeE15GroupsIntoExisting(pack.value.groups, incoming)
      cleanGroups = m.groups
      stashed = m.stashed
      addedAccounts = m.addedAccounts
    } else {
      cleanGroups = incoming.map(g => ({
        id: g.id,
        depositType: g.depositType,
        bank: g.bank,
        annualRate: g.annualRate,
        accounts: g.accounts,
      }))
      stashed = incoming.map(g => ({ _acctId: g._acctId, _balances: g._balances }))
      addedAccounts = cleanGroups.reduce((s, g) => s + g.accounts.length, 0)
    }

    const fillDaily = opts?.fillDailyFromMonthly !== false
    let daysFilled = 0
    let balances = pack.value.balances
    if (fillDaily) {
      const exp = expandMonthlyToDailyBalances(
        y,
        stashed,
        pack.value.balances,
        mode === 'merge',
      )
      balances = exp.balances
      daysFilled = exp.daysFilled
    }

    pack.value = {
      ...pack.value,
      year: y,
      groups: cleanGroups.length ? cleanGroups : pack.value.groups,
      balances: fillDaily ? balances : pack.value.balances,
      bookInterest: bookInterest || pack.value.bookInterest,
    }
    scheduleSave()
    return {
      groups: cleanGroups.length,
      bookInterest: pack.value.bookInterest,
      daysFilled,
      addedAccounts,
      mode,
    }
  }

  function saveNote(val: string): void {
    if (isReadonly.value) return
    auditNote.value = val
    const item = { item_id: E1_DEPOSIT_DAILY_NOTE_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_DEPOSIT_DAILY_NOTE_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function saveConclusion(val: string): void {
    if (isReadonly.value) return
    auditConclusion.value = val
    const item = { item_id: E1_DEPOSIT_DAILY_CONCLUSION_KEY, conclusion: null, remark: val }
    allResponses.value.set(E1_DEPOSIT_DAILY_CONCLUSION_KEY, item)
    saveImmediate([item]).catch(() => {})
  }

  function hydrate(): void {
    load()
  }

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persist()
    }
  })

  return {
    pack,
    auditNote,
    auditConclusion,
    isLoading,
    isApplicable,
    viewMonth,
    yearDates,
    monthDates,
    allAccountIds,
    calculatedInterest,
    interestDiff,
    groupYearInterest,
    typeYearInterest,
    dayInterest,
    groupDayInterest,
    dayBalances,
    dayRates,
    setApplicable,
    setYear,
    setBookInterest,
    addGroup,
    removeGroup,
    updateGroup,
    addAccount,
    removeAccount,
    updateAccountNo,
    setBalance,
    setRateOverride,
    syncFromE15,
    previewSyncFromE15,
    saveNote,
    saveConclusion,
    hydrate,
    scheduleSave,
    persist,
  }
}
