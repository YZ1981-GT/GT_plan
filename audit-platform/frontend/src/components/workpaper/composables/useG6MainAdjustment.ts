/**
 * useG6MainAdjustment — G6-4 调整分录汇总
 *
 * 对齐 Excel《调整分录汇总G6-4》列结构：
 *   调整事项说明 | 类别（报表调整/账项调整/其他）| 报表项目 | 科目名称 |
 *   附注项目 | 借方调整金额 | 贷方调整金额 | 索引 | 备注
 *
 * 持久化：G6-4-rows（conclusion JSON）
 * 回写：按科目分流写入 G6-1（成本/利息/减值），排除「报表调整」
 */
import {
  ref,
  computed,
  watch,
  onBeforeUnmount,
  getCurrentInstance,
  type Ref,
  type ComputedRef,
} from 'vue'
import { ElMessage } from 'element-plus'
import { parseNum } from '@/composables/useG6MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  applyG6MultiAdjustmentWriteback,
  parseG6AdjStore,
} from './g6AdjudicationItems'

export const G6_ACCOUNT_CODE = '1503'
export const G6_4_STORAGE_KEY = 'G6-4-rows'
const BALANCE_TOLERANCE = 0.005

export interface G6AdjustmentEntry {
  id: string
  rowId: string
  seq: number
  description: string
  category: string
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  /** 兼容旧字段 / 导入导出 */
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  preparedBy: string
}

export interface G6AdjustmentSummary {
  accountCode: string
  ajeNet: number
  rjeNet: number
  net: number
}

export const G6_CATEGORY_OPTIONS = ['账项调整', '报表调整', '其他'] as const

export const G6_OTHER_BOND_ACCOUNTS = [
  { code: '1503', name: '其他债权投资' },
  { code: '150301', name: '其他债权投资——成本' },
  { code: '150302', name: '其他债权投资——利息调整' },
  { code: '150303', name: '其他债权投资——应计利息' },
  { code: '150304', name: '其他债权投资——公允价值变动' },
  { code: '150305', name: '其他债权投资减值准备' },
  { code: '6011', name: '利息收入' },
  { code: '6111', name: '投资收益' },
  { code: '6702', name: '信用减值损失' },
  { code: '1012', name: '银行存款' },
  { code: '1132', name: '应收利息' },
] as const

function generateId(): string {
  return `g6adj-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function createEmptyG6Entry(seq = 1, description = ''): G6AdjustmentEntry {
  return {
    id: generateId(),
    rowId: generateId(),
    seq,
    description,
    category: '账项调整',
    reportItem: '其他债权投资',
    accountCode: G6_ACCOUNT_CODE,
    accountName: '其他债权投资',
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: 'G6-4',
    remark: '',
    entryType: 'AJE',
    date: '',
    summary: description,
    preparedBy: '',
  }
}

function categoryFromLegacy(raw: any): string {
  if (raw.category) return String(raw.category)
  if (raw.entryType === 'RJE') return '报表调整'
  if (raw.entryType === 'AJE') return '账项调整'
  return '账项调整'
}

export function normalizeG6AdjustmentEntry(raw: any, idx: number): G6AdjustmentEntry {
  const description = String(raw.description || raw.summary || '')
  const category = categoryFromLegacy(raw)
  const entryType: 'AJE' | 'RJE' = category === '报表调整' ? 'RJE' : 'AJE'
  const id = String(raw.id || raw.rowId || generateId())
  const accountCode = String(raw.accountCode || G6_ACCOUNT_CODE)
  const known = G6_OTHER_BOND_ACCOUNTS.find((a) => a.code === accountCode)
  return {
    id,
    rowId: String(raw.rowId || id),
    seq: Number(raw.seq) || idx + 1,
    description,
    category,
    reportItem: String(raw.reportItem || '其他债权投资'),
    accountCode,
    accountName: String(raw.accountName || known?.name || '其他债权投资'),
    noteItem: String(raw.noteItem || ''),
    debitAmount: parseNum(raw.debitAmount ?? raw.debit),
    creditAmount: parseNum(raw.creditAmount ?? raw.credit),
    indexRef: String(raw.indexRef || raw.preparedBy || 'G6-4'),
    remark: String(raw.remark || ''),
    entryType,
    date: String(raw.date || ''),
    summary: description,
    preparedBy: String(raw.preparedBy || ''),
  }
}

export function parseG6AdjustmentEntries(
  resp: { conclusion?: string | null; remark?: string | null } | undefined | null,
): G6AdjustmentEntry[] {
  const raw = resp?.conclusion || resp?.remark
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    const arr = Array.isArray(parsed)
      ? parsed
      : Array.isArray(parsed?.entries)
        ? parsed.entries
        : Array.isArray(parsed?.rows)
          ? parsed.rows
          : []
    return arr.map(normalizeG6AdjustmentEntry)
  } catch {
    return []
  }
}

export function isG6InterestAccount(code: string): boolean {
  const c = String(code || '')
  return c === '150302' || c.startsWith('150302')
}

export function isG6FvAccount(code: string): boolean {
  const c = String(code || '')
  return c === '150304' || c.startsWith('150304')
}

export function isG6ImpairmentAccount(code: string, name = ''): boolean {
  const c = String(code || '')
  const n = String(name || '')
  return (
    c === '150305'
    || c.startsWith('150305')
    || /减值准备/.test(n)
    || (c.startsWith('1503') && /减值/.test(n))
  )
}

export function isG6CostAccount(code: string, name = ''): boolean {
  const c = String(code || '')
  if (!c.startsWith('1503')) return false
  if (isG6InterestAccount(c) || isG6FvAccount(c) || isG6ImpairmentAccount(c, name)) return false
  return true
}

function isReportReclass(entry: G6AdjustmentEntry): boolean {
  return entry.category === '报表调整' || entry.entryType === 'RJE'
}

export function aggregateG6WritebackNets(entries: G6AdjustmentEntry[]): {
  costNet: number
  interestNet: number
  impairmentNet: number
  fvNet: number
} {
  let costNet = 0
  let interestNet = 0
  let impairmentNet = 0
  let fvNet = 0
  for (const entry of entries) {
    if (isReportReclass(entry)) continue
    if (!entry.debitAmount && !entry.creditAmount) continue
    const debitMinusCredit = parseNum(entry.debitAmount) - parseNum(entry.creditAmount)
    if (isG6ImpairmentAccount(entry.accountCode, entry.accountName)) {
      // 减值准备增加通常贷记准备：贷−借
      impairmentNet += parseNum(entry.creditAmount) - parseNum(entry.debitAmount)
    } else if (isG6InterestAccount(entry.accountCode)) {
      interestNet += debitMinusCredit
    } else if (isG6FvAccount(entry.accountCode)) {
      fvNet += debitMinusCredit
    } else if (isG6CostAccount(entry.accountCode, entry.accountName)) {
      costNet += debitMinusCredit
    }
  }
  return {
    costNet: Math.round(costNet * 100) / 100,
    interestNet: Math.round(interestNet * 100) / 100,
    impairmentNet: Math.round(impairmentNet * 100) / 100,
    fvNet: Math.round(fvNet * 100) / 100,
  }
}

export interface UseG6MainAdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean> | ComputedRef<boolean>
}

export function useG6MainAdjustment(options: UseG6MainAdjustmentOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const entries = ref<G6AdjustmentEntry[]>([])

  const accountOptions = computed(() => [...G6_OTHER_BOND_ACCOUNTS])

  function loadEntries(): void {
    const stored = parseG6AdjustmentEntries(allResponses.value.get(G6_4_STORAGE_KEY))
    entries.value = stored.length > 0 ? stored : [createEmptyG6Entry(1)]
  }

  watch(
    () => {
      const item = allResponses.value.get(G6_4_STORAGE_KEY)
      return item?.conclusion ?? item?.remark
    },
    () => {
      const stored = parseG6AdjustmentEntries(allResponses.value.get(G6_4_STORAGE_KEY))
      if (stored.length > 0) {
        entries.value = stored
      } else if (entries.value.length === 0) {
        entries.value = [createEmptyG6Entry(1)]
      }
    },
    { immediate: true },
  )

  const totalDebits = computed(() =>
    entries.value.reduce((sum, e) => sum + parseNum(e.debitAmount), 0),
  )
  const totalCredits = computed(() =>
    entries.value.reduce((sum, e) => sum + parseNum(e.creditAmount), 0),
  )
  const balanceDiff = computed(() => totalDebits.value - totalCredits.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const writebackNets = computed(() => aggregateG6WritebackNets(entries.value))

  function persist(): void {
    if (readonly.value) return
    const json = JSON.stringify(entries.value)
    const payload: ChecklistResponse = {
      item_id: G6_4_STORAGE_KEY,
      conclusion: json,
      remark: json,
    }
    allResponses.value.set(G6_4_STORAGE_KEY, payload)
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 2000)
  }

  function flushSave(): void {
    const item = allResponses.value.get(G6_4_STORAGE_KEY)
    if (item) {
      window.dispatchEvent(new CustomEvent('g6:save-items', { detail: { items: [item] } }))
    }
  }

  function addEntry(description = ''): void {
    if (readonly.value) return
    entries.value = [
      ...entries.value,
      createEmptyG6Entry(entries.value.length + 1, description),
    ]
    persist()
  }

  function removeEntry(id: string): void {
    if (readonly.value) return
    if (entries.value.length <= 1) return
    const next = entries.value.filter((e) => e.id !== id && e.rowId !== id)
    next.forEach((e, i) => {
      e.seq = i + 1
    })
    entries.value = next
    persist()
  }

  function updateCell(id: string, field: keyof G6AdjustmentEntry, value: unknown): void {
    if (readonly.value) return
    const idx = entries.value.findIndex((e) => e.id === id || e.rowId === id)
    if (idx === -1) return
    const row = { ...entries.value[idx] }

    if (field === 'debitAmount' || field === 'creditAmount') {
      row[field] = parseNum(value)
    } else if (field === 'category') {
      row.category = String(value ?? '账项调整')
      row.entryType = row.category === '报表调整' ? 'RJE' : 'AJE'
    } else if (field === 'entryType') {
      row.entryType = value === 'RJE' ? 'RJE' : 'AJE'
      row.category = row.entryType === 'RJE' ? '报表调整' : '账项调整'
    } else if (field === 'accountCode') {
      row.accountCode = String(value ?? '')
      const acc = accountOptions.value.find((a) => a.code === row.accountCode)
      if (acc) row.accountName = acc.name
    } else if (field === 'accountName') {
      row.accountName = String(value ?? '')
      const acc = accountOptions.value.find((a) => a.name === row.accountName)
      if (acc) row.accountCode = acc.code
    } else if (field === 'description' || field === 'summary') {
      row.description = String(value ?? '')
      row.summary = row.description
    } else if (field === 'seq' || field === 'id' || field === 'rowId') {
      return
    } else {
      ;(row as any)[field] = String(value ?? '')
    }

    const next = [...entries.value]
    next[idx] = row
    entries.value = next
    persist()
  }

  function aggregateForWriteback(): G6AdjustmentSummary[] {
    const map = new Map<string, { ajeNet: number; rjeNet: number }>()
    for (const entry of entries.value) {
      if (entry.debitAmount === 0 && entry.creditAmount === 0) continue
      const key = entry.accountCode || G6_ACCOUNT_CODE
      if (!map.has(key)) map.set(key, { ajeNet: 0, rjeNet: 0 })
      const bucket = map.get(key)!
      const net = parseNum(entry.debitAmount) - parseNum(entry.creditAmount)
      if (isReportReclass(entry)) bucket.rjeNet += net
      else bucket.ajeNet += net
    }
    return Array.from(map.entries()).map(([accountCode, amounts]) => ({
      accountCode,
      ajeNet: amounts.ajeNet,
      rjeNet: amounts.rjeNet,
      net: amounts.ajeNet + amounts.rjeNet,
    }))
  }

  function writebackToG6_1Store(): void {
    try {
      const item = allResponses.value.get('G6-1-rows')
      const raw = item?.conclusion || item?.remark
      const store = parseG6AdjStore(raw)
      const nets = writebackNets.value
      const next = applyG6MultiAdjustmentWriteback(store, {
        cost: nets.costNet,
        interest: nets.interestNet,
        impairment: nets.impairmentNet,
        fv: nets.fvNet,
      })
      const json = JSON.stringify(next)
      const payload: ChecklistResponse = {
        item_id: 'G6-1-rows',
        conclusion: json,
        remark: json,
      }
      allResponses.value.set('G6-1-rows', payload)
      window.dispatchEvent(new CustomEvent('g6:save-items', { detail: { items: [payload] } }))
    } catch {
      /* silent */
    }
  }

  function saveAndWriteback(): boolean {
    if (!isBalanced.value) {
      ElMessage.error('借贷不平衡，无法保存回写')
      return false
    }
    persist()
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    flushSave()

    const summaries = aggregateForWriteback()
    const nets = writebackNets.value
    writebackToG6_1Store()

    window.dispatchEvent(
      new CustomEvent('g6:adjustment-writeback', {
        detail: {
          accountCode: G6_ACCOUNT_CODE,
          summaries,
          costNet: nets.costNet,
          interestNet: nets.interestNet,
          impairmentNet: nets.impairmentNet,
          fvNet: nets.fvNet,
          // 兼容旧监听
          ajeTotal: nets.costNet + nets.interestNet,
          rjeTotal: 0,
          totalAdjustment: nets.costNet + nets.interestNet + nets.impairmentNet + nets.fvNet,
        },
      }),
    )
    window.dispatchEvent(
      new CustomEvent('g6:adjustment-confirmed', {
        detail: {
          accountCode: G6_ACCOUNT_CODE,
          summaries,
          costNet: nets.costNet,
          interestNet: nets.interestNet,
          impairmentNet: nets.impairmentNet,
          fvNet: nets.fvNet,
        },
      }),
    )

    ElMessage.success(
      `已保存回写：成本 ${nets.costNet.toFixed(2)} / 利息 ${nets.interestNet.toFixed(2)} / 减值 ${nets.impairmentNet.toFixed(2)}`,
    )
    return true
  }

  if (getCurrentInstance()) {
    onBeforeUnmount(() => {
      if (debounceTimer) {
        clearTimeout(debounceTimer)
        debounceTimer = null
        flushSave()
      }
    })
  }

  return {
    entries,
    totalDebits,
    totalCredits,
    balanceDiff,
    isBalanced,
    writebackNets,
    addEntry,
    removeEntry,
    updateCell,
    saveAndWriteback,
    aggregateForWriteback,
    loadEntries,
    accountOptions,
    categoryOptions: G6_CATEGORY_OPTIONS,
    STORAGE_KEY: G6_4_STORAGE_KEY,
  }
}

export default useG6MainAdjustment
