/**
 * useD1Adjustment — D1-5 调整分录（对齐 D4-4 双列借贷模型）
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { ChecklistItem, ChecklistResponse } from './useD1FormData'
import { parseNum } from './useD1FormulaEngine'

export type AdjustmentType = 'AJE' | 'RJE'

export interface D1AdjustmentRow {
  rowId: string
  description: string
  category: string
  reportItem: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  isPushedToAdjTable: boolean
}

/** @deprecated 兼容旧引用 */
export type AdjustmentEntry = D1AdjustmentRow & { index: number; type: AdjustmentType; debitAccount: string; creditAccount: string; amount: number }

export type SaveFn = (items: ChecklistItem[]) => Promise<void>

export interface UseD1AdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  saveImmediate: SaveFn
  isReadonly: Ref<boolean>
}

const STORAGE_KEY = 'D1-entry-rows'
const BALANCE_TOLERANCE = 0.005

function generateRowId(): string {
  return `d1a-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function mapCategory(raw: string): string {
  if (raw === 'AJE' || raw === '账项调整') return '账项调整'
  if (raw === 'RJE' || raw === '报表调整') return '报表调整'
  return raw || '账项调整'
}

function createEmptyRow(): D1AdjustmentRow {
  return {
    rowId: generateRowId(),
    description: '',
    category: '账项调整',
    reportItem: '',
    accountName: '',
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: '',
    isPushedToAdjTable: false,
  }
}

function migrateLegacyRow(raw: any): D1AdjustmentRow[] {
  if (raw.debitAmount != null || raw.creditAmount != null || raw.accountName) {
    return [{
      rowId: raw.rowId || generateRowId(),
      description: raw.description || raw.desc || '',
      category: mapCategory(raw.category || raw.type || '账项调整'),
      reportItem: raw.reportItem || '',
      accountName: raw.accountName || '',
      noteItem: raw.noteItem || '',
      debitAmount: parseNum(raw.debitAmount),
      creditAmount: parseNum(raw.creditAmount),
      indexRef: raw.indexRef || '',
      isPushedToAdjTable: Boolean(raw.isPushedToAdjTable ?? raw.pushed === 'Y'),
    }]
  }
  const amount = parseNum(raw.amount)
  const desc = raw.description || raw.desc || ''
  const category = mapCategory(raw.type || raw.entryType || 'AJE')
  const rows: D1AdjustmentRow[] = []
  const debit = raw.debitAccount || raw.debit || ''
  const credit = raw.creditAccount || raw.credit || ''
  if (debit && amount) {
    rows.push({
      ...createEmptyRow(),
      rowId: raw.rowId || generateRowId(),
      description: desc,
      category,
      accountName: debit,
      debitAmount: amount,
      isPushedToAdjTable: Boolean(raw.isPushedToAdjTable),
    })
  }
  if (credit && amount) {
    rows.push({
      ...createEmptyRow(),
      rowId: generateRowId(),
      description: desc,
      category,
      accountName: credit,
      creditAmount: amount,
      isPushedToAdjTable: Boolean(raw.isPushedToAdjTable),
    })
  }
  if (!rows.length) {
    rows.push({
      ...createEmptyRow(),
      rowId: raw.rowId || generateRowId(),
      description: desc,
      category,
      accountName: debit || credit,
      debitAmount: debit ? amount : 0,
      creditAmount: credit && !debit ? amount : 0,
      isPushedToAdjTable: Boolean(raw.isPushedToAdjTable),
    })
  }
  return rows
}

function safeParseRows(jsonStr: string | null | undefined): D1AdjustmentRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.flatMap((raw: any) => migrateLegacyRow(raw))
  } catch {
    return []
  }
}

function loadLegacyEntries(allResponses: Ref<Map<string, ChecklistResponse>>): D1AdjustmentRow[] {
  const getVal = (id: string) => allResponses.value.get(id)
  const count = parseNum(getVal('D1-entry-count')?.remark) || 0
  const list: D1AdjustmentRow[] = []
  for (let i = 1; i <= count; i++) {
    list.push(...migrateLegacyRow({
      rowId: generateRowId(),
      type: getVal(`D1-entry-${i}-type`)?.conclusion || 'AJE',
      debitAccount: getVal(`D1-entry-${i}-debit`)?.remark || '',
      creditAccount: getVal(`D1-entry-${i}-credit`)?.remark || '',
      amount: getVal(`D1-entry-${i}-amount`)?.remark,
      description: getVal(`D1-entry-${i}-desc`)?.remark || '',
      isPushedToAdjTable: getVal(`D1-entry-${i}-pushed`)?.conclusion === 'Y',
    }))
  }
  return list
}

export function useD1Adjustment(options: UseD1AdjustmentOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const rows = ref<D1AdjustmentRow[]>([])

  function loadRows(): void {
    const json = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    rows.value = json.length ? json : loadLegacyEntries(allResponses)
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => loadRows(),
    { immediate: true },
  )

  const debitTotal: ComputedRef<number> = computed(() =>
    rows.value.reduce((s, r) => s + parseNum(r.debitAmount), 0),
  )

  const creditTotal: ComputedRef<number> = computed(() =>
    rows.value.reduce((s, r) => s + parseNum(r.creditAmount), 0),
  )

  const balanceDiff = computed(() => debitTotal.value - creditTotal.value)
  const isBalanced = computed(() => Math.abs(balanceDiff.value) < BALANCE_TOLERANCE)

  const ajeTotal = computed(() =>
    rows.value
      .filter(r => mapCategory(r.category) === '账项调整')
      .reduce((s, r) => s + Math.max(r.debitAmount, r.creditAmount), 0),
  )

  const rjeTotal = computed(() =>
    rows.value
      .filter(r => mapCategory(r.category) === '报表调整')
      .reduce((s, r) => s + Math.max(r.debitAmount, r.creditAmount), 0),
  )

  /** 兼容旧 UI：带 index 的视图 */
  const entries = computed(() =>
    rows.value.map((r, i) => ({
      ...r,
      index: i + 1,
      type: (mapCategory(r.category) === '报表调整' ? 'RJE' : 'AJE') as AdjustmentType,
      debitAccount: r.debitAmount ? r.accountName : '',
      creditAccount: r.creditAmount ? r.accountName : '',
      amount: Math.max(r.debitAmount, r.creditAmount),
    })),
  )

  function persistRows(): void {
    const serialized = JSON.stringify(rows.value)
    const items: ChecklistItem[] = [
      { item_id: STORAGE_KEY, conclusion: null, remark: serialized },
      { item_id: 'D1-entry-count', conclusion: null, remark: String(rows.value.length) },
      // 🔴 已删除两条死写入 `D1-adj-bank-acceptance-aje-dr` / `-rje-dr`：
      // 全平台**无任何读取方**，且形状不匹配 `d_cycle_anchor_registry.json` 的 D1 锚点
      // 正则（后端 seed 会直接丢弃），只是在 checklist_responses 里堆无用行。
      // 调整分录 → 审定表 AJE/RJE 的真实通路是 EventBus `adjustment:created`
      // → `useD1Adjudication.onAdjustmentCreated` → `D1-adj-{section}-{slug}-current-{aje|rje}`。
    ]
    allResponses.value.set(STORAGE_KEY, items[0])
    saveImmediate(items)
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      persistRows()
    }, 2000)
  }

  function immediatelySave(): void {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    persistRows()
  }

  function addEntry(): void {
    if (isReadonly.value) return
    rows.value.push(createEmptyRow())
    immediatelySave()
  }

  function removeEntry(index: number): void {
    if (isReadonly.value) return
    const idx = index - 1
    if (idx < 0 || idx >= rows.value.length) return
    rows.value.splice(idx, 1)
    immediatelySave()
  }

  function updateEntry(index: number, data: Partial<D1AdjustmentRow & { type?: string; debitAccount?: string; creditAccount?: string; amount?: number }>): void {
    if (isReadonly.value) return
    const idx = index - 1
    if (idx < 0 || idx >= rows.value.length) return
    const row = rows.value[idx]

    if (data.type) row.category = mapCategory(data.type)
    if (data.category) row.category = mapCategory(data.category)
    if (data.description != null) row.description = data.description
    if (data.reportItem != null) row.reportItem = data.reportItem
    if (data.noteItem != null) row.noteItem = data.noteItem
    if (data.indexRef != null) row.indexRef = data.indexRef
    if (data.debitAmount != null) row.debitAmount = parseNum(data.debitAmount)
    if (data.creditAmount != null) row.creditAmount = parseNum(data.creditAmount)
    if (data.accountName != null) row.accountName = data.accountName
    if (data.debitAccount != null) {
      row.accountName = data.debitAccount
      row.debitAmount = parseNum(data.amount ?? row.debitAmount)
      row.creditAmount = 0
    }
    if (data.creditAccount != null) {
      row.accountName = data.creditAccount
      row.creditAmount = parseNum(data.amount ?? row.creditAmount)
      row.debitAmount = 0
    }
    if (data.amount != null && data.debitAccount == null && data.creditAccount == null) {
      if (row.debitAmount) row.debitAmount = parseNum(data.amount)
      else if (row.creditAmount) row.creditAmount = parseNum(data.amount)
    }

    if (data.category) immediatelySave()
    else debounceSave()
  }

  function updateCell(rowId: string, field: string, value: unknown): void {
    if (isReadonly.value) return
    const row = rows.value.find(r => r.rowId === rowId)
    if (!row) return
    const key = field as keyof D1AdjustmentRow
    if (key === 'rowId') return
    if (key === 'debitAmount' || key === 'creditAmount') {
      ;(row as any)[key] = parseNum(value)
    } else if (key === 'isPushedToAdjTable') {
      row.isPushedToAdjTable = Boolean(value)
    } else {
      ;(row as any)[key] = String(value ?? '')
    }
    if (key === 'category') immediatelySave()
    else debounceSave()
  }

  function publishAdjustment(): void {
    for (const row of rows.value) {
      if (row.debitAmount === 0 && row.creditAmount === 0) continue
      const payload = {
        wpCode: 'D1',
        entryType: mapCategory(row.category) === '报表调整' ? 'RJE' : 'AJE',
        amount: Math.max(row.debitAmount, row.creditAmount),
        accountCode: row.accountName,
        description: row.description,
      }
      try {
        window.dispatchEvent(new CustomEvent('adjustment:created', { detail: payload }))
      } catch { /* silent */ }
    }
  }

  function pushToA13(indices: number[]): void {
    const selected = entries.value.filter(e => indices.includes(e.index))
    if (!selected.length) return
    const misstatements = selected.map(entry => ({
      wpCode: 'D1',
      entryType: entry.type,
      description: entry.description,
      debitAccount: entry.debitAccount,
      creditAccount: entry.creditAccount,
      amount: entry.amount,
    }))
    try {
      window.dispatchEvent(new CustomEvent('a13:push-misstatement', { detail: { items: misstatements } }))
    } catch { /* silent */ }
    for (const entry of selected) {
      updateEntry(entry.index, { isPushedToAdjTable: true })
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      persistRows()
    }
  })

  return {
    rows,
    entries,
    ajeTotal,
    rjeTotal,
    debitTotal,
    creditTotal,
    isBalanced,
    balanceDiff,
    addEntry,
    removeEntry,
    updateEntry,
    updateCell,
    publishAdjustment,
    pushToA13,
  }
}

export default useD1Adjustment
