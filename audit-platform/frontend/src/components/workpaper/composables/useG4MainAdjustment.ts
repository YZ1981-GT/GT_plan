/**
 * useG4MainAdjustment — G4-3 调整分录汇总（对齐 Excel 模板列结构 + 参照 G1-3）
 *
 * Excel 列：调整事项说明 | 类别（报表调整/账项调整/其他）| 报表项目 | 科目名称 |
 *          附注项目 | …… | 借方调整金额 | 贷方调整金额 | 索引 | 备注
 *
 * 存储：conclusion 规范字段，兼容旧 remark。
 * 回写：1501* → G4-1 原值；1502* → G4-1 减值准备（贷−借）。
 */
import { ref, computed, watch, onBeforeUnmount, getCurrentInstance, type Ref, type ComputedRef } from 'vue'
import { parseNum } from '@/composables/useG4MainFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import {
  applyG4SplitAdjustmentWriteback,
  parseG4AdjStore,
} from './g4AdjudicationItems'
import {
  G4_ITEM_IDS,
  buildCanonicalPayload,
  parseCanonicalArray,
  resolveCreditLossAccount,
} from './g4StorageContract'

export const G4_ACCOUNT_CODE = '1501'
const STORAGE_KEY = G4_ITEM_IDS.G4_3_ROWS
const BALANCE_TOLERANCE = 0.005

/** 与 Excel G4-3 对齐的列 + 异常路由溯源字段 */
export interface AdjustmentEntry {
  id: string
  rowId: string
  description: string
  category: string
  reportItem: string
  accountName: string
  accountCode: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
  seq: number
  entryType: 'AJE' | 'RJE'
  date: string
  summary: string
  preparedBy: string
  /** 异常路由溯源 */
  sourceKey?: string
  sourceSheet?: 'G4-4' | 'G4-8' | 'G4-10' | 'G4-12' | 'G4-13' | string
  sourceRowId?: string
  sourceKind?: string
  sourceFingerprint?: string
  sourceLine?: 'debit' | 'credit' | 'memo'
  draftStatus?: 'draft' | 'accepted' | 'dismissed'
}

export interface AdjustmentSummary {
  accountCode: string
  ajeNet: number
  rjeNet: number
  net: number
}

export const G4_BOND_ACCOUNTS = [
  { code: '1501', name: '债权投资' },
  { code: '150101', name: '债权投资——成本' },
  { code: '150102', name: '债权投资——利息调整' },
  { code: '150103', name: '债权投资——应计利息' },
  { code: '1502', name: '债权投资减值准备' },
  { code: '6011', name: '利息收入' },
  { code: '6702', name: '信用减值损失' },
  { code: '6701', name: '资产减值损失' },
  { code: '1012', name: '银行存款' },
  { code: '1101', name: '应收利息' },
] as const

const CATEGORY_OPTIONS = ['账项调整', '报表调整', '其他'] as const

function generateId(): string {
  return `g4adj-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function createEmptyEntry(seq = 1, description = ''): AdjustmentEntry {
  return {
    id: generateId(),
    rowId: generateId(),
    description,
    category: '账项调整',
    reportItem: '债权投资',
    accountName: '债权投资',
    accountCode: G4_ACCOUNT_CODE,
    noteItem: '',
    debitAmount: 0,
    creditAmount: 0,
    indexRef: 'G4-3',
    remark: '',
    seq,
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

function normalizeEntry(raw: any, idx: number): AdjustmentEntry {
  const description = raw.description || raw.summary || ''
  const category = categoryFromLegacy(raw)
  const entryType: 'AJE' | 'RJE' = category === '报表调整' ? 'RJE' : 'AJE'
  const id = raw.id || raw.rowId || generateId()
  return {
    id,
    rowId: raw.rowId || id,
    description,
    category,
    reportItem: raw.reportItem || '债权投资',
    accountName: raw.accountName || '债权投资',
    accountCode: raw.accountCode || G4_ACCOUNT_CODE,
    noteItem: raw.noteItem || '',
    debitAmount: parseNum(raw.debitAmount ?? raw.debit),
    creditAmount: parseNum(raw.creditAmount ?? raw.credit),
    indexRef: raw.indexRef || 'G4-3',
    remark: raw.remark || '',
    seq: raw.seq ?? idx + 1,
    entryType,
    date: raw.date || '',
    summary: description,
    preparedBy: raw.preparedBy || raw.preparer || '',
    sourceKey: raw.sourceKey,
    sourceSheet: raw.sourceSheet,
    sourceRowId: raw.sourceRowId,
    sourceKind: raw.sourceKind,
    sourceFingerprint: raw.sourceFingerprint,
    sourceLine: raw.sourceLine,
    draftStatus: raw.draftStatus,
  }
}

function parseEntriesFromResponse(
  resp: { conclusion?: string | null; remark?: string | null } | undefined,
): AdjustmentEntry[] {
  const arr = parseCanonicalArray(resp)
  return arr.map(normalizeEntry)
}

function isOriginalAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1501' || c.startsWith('1501')
}

function isImpairmentAccount(code: string): boolean {
  const c = String(code || '')
  return c === '1502' || c.startsWith('1502')
}

/**
 * 幂等合并来源草稿：按 sourceKey 更新未人工接受的草稿；保留手工行与已接受行。
 */
export function mergeProvenanceDrafts(
  existing: AdjustmentEntry[],
  incoming: AdjustmentEntry[],
): { entries: AdjustmentEntry[]; added: number; updated: number; skipped: number } {
  const byKey = new Map(
    existing.filter((e) => e.sourceKey).map((e) => [String(e.sourceKey), e]),
  )
  const retained = existing.filter((e) => !e.sourceKey || !incoming.some((i) => i.sourceKey === e.sourceKey))
  let added = 0
  let updated = 0
  let skipped = 0
  const merged: AdjustmentEntry[] = [...retained]

  for (const draft of incoming) {
    if (!draft.sourceKey) {
      merged.push(draft)
      added++
      continue
    }
    const prev = byKey.get(draft.sourceKey)
    if (!prev) {
      merged.push({ ...draft, draftStatus: draft.draftStatus || 'draft' })
      added++
      continue
    }
    if (prev.draftStatus === 'accepted' || prev.draftStatus === 'dismissed') {
      merged.push(prev)
      skipped++
      continue
    }
    if (prev.sourceFingerprint === draft.sourceFingerprint) {
      merged.push(prev)
      skipped++
      continue
    }
    merged.push({
      ...draft,
      id: prev.id,
      rowId: prev.rowId,
      draftStatus: 'draft',
    })
    updated++
  }

  merged.forEach((e, i) => { e.seq = i + 1 })
  return { entries: merged, added, updated, skipped }
}

export interface UseG4MainAdjustmentOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean> | ComputedRef<boolean>
  onWritebackG4_1?: (summaries: AdjustmentSummary[]) => void
}

export function useG4MainAdjustment(options: UseG4MainAdjustmentOptions) {
  const { allResponses, isReadonly, onWritebackG4_1 } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const entries = ref<AdjustmentEntry[]>([])

  const creditLossAccount = computed(() => resolveCreditLossAccount(allResponses.value))

  const accountOptions = computed(() => {
    const loss = creditLossAccount.value
    const base = [...G4_BOND_ACCOUNTS]
    if (!base.some((a) => a.code === loss.code)) {
      base.splice(6, 0, { code: loss.code, name: loss.name } as any)
    }
    return base
  })

  function loadEntries(): void {
    const stored = parseEntriesFromResponse(allResponses.value.get(STORAGE_KEY))
    entries.value = stored.length > 0 ? stored : [createEmptyEntry(1)]
  }

  watch(
    () => {
      const item = allResponses.value.get(STORAGE_KEY)
      return item?.conclusion ?? item?.remark
    },
    () => {
      const stored = parseEntriesFromResponse(allResponses.value.get(STORAGE_KEY))
      if (stored.length > 0) {
        entries.value = stored
      } else if (entries.value.length === 0) {
        entries.value = [createEmptyEntry(1)]
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

  /** 原值净调整（1501* 借−贷，排除 RJE） */
  const originalNetAje = computed(() => {
    let net = 0
    for (const r of entries.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isOriginalAccount(r.accountCode)) continue
      net += parseNum(r.debitAmount) - parseNum(r.creditAmount)
    }
    return Math.round(net * 100) / 100
  })

  /** 减值准备净调整（1502* 贷−借，排除 RJE；正数=准备增加） */
  const impairmentNetAje = computed(() => {
    let net = 0
    for (const r of entries.value) {
      if (r.category === '报表调整' || r.entryType === 'RJE') continue
      if (!isImpairmentAccount(r.accountCode)) continue
      net += parseNum(r.creditAmount) - parseNum(r.debitAmount)
    }
    return Math.round(net * 100) / 100
  })

  /** @deprecated 兼容旧调用：原值+减值错误合并口径，请改用 originalNetAje */
  const netAjeToG4 = computed(() => originalNetAje.value)

  function persist(): void {
    const payload = buildCanonicalPayload(STORAGE_KEY, entries.value)
    allResponses.value.set(STORAGE_KEY, payload)
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
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) {
      window.dispatchEvent(new CustomEvent('g4:save-items', { detail: { items: [item] } }))
    }
  }

  async function addEntry(): Promise<void> {
    if (readonly.value) return
    entries.value = [...entries.value, createEmptyEntry(entries.value.length + 1)]
    persist()
  }

  function removeEntry(id: string): void {
    if (readonly.value) return
    if (entries.value.length <= 1) return
    const next = entries.value.filter((e) => e.id !== id && e.rowId !== id)
    next.forEach((e, i) => { e.seq = i + 1 })
    entries.value = next
    persist()
  }

  function updateCell(id: string, field: keyof AdjustmentEntry, value: unknown): void {
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

    // 人工编辑来源草稿 → 标记 accepted，避免被路由覆盖
    if (row.sourceKey && row.draftStatus === 'draft') {
      row.draftStatus = 'accepted'
    }

    const next = [...entries.value]
    next[idx] = row
    entries.value = next
    persist()
  }

  function aggregateForWriteback(): AdjustmentSummary[] {
    const map = new Map<string, { ajeNet: number; rjeNet: number }>()
    for (const entry of entries.value) {
      if (entry.debitAmount === 0 && entry.creditAmount === 0) continue
      const key = entry.accountCode || '1501'
      if (!map.has(key)) map.set(key, { ajeNet: 0, rjeNet: 0 })
      const bucket = map.get(key)!
      const net = parseNum(entry.debitAmount) - parseNum(entry.creditAmount)
      if (entry.category === '报表调整' || entry.entryType === 'RJE') {
        bucket.rjeNet += net
      } else {
        bucket.ajeNet += net
      }
    }
    return Array.from(map.entries()).map(([accountCode, amounts]) => ({
      accountCode,
      ajeNet: amounts.ajeNet,
      rjeNet: amounts.rjeNet,
      net: amounts.ajeNet + amounts.rjeNet,
    }))
  }

  /** 唯一权威回写路径：分离原值 / 减值准备 */
  function writebackToG4_1Store(): void {
    try {
      const item = allResponses.value.get(G4_ITEM_IDS.G4_1_ROWS)
      const raw = item?.conclusion || item?.remark
      const store = parseG4AdjStore(raw)
      const next = applyG4SplitAdjustmentWriteback(
        store,
        originalNetAje.value,
        impairmentNetAje.value,
      )
      const payload = buildCanonicalPayload(G4_ITEM_IDS.G4_1_ROWS, next)
      allResponses.value.set(G4_ITEM_IDS.G4_1_ROWS, payload)
      window.dispatchEvent(
        new CustomEvent('g4:save-items', {
          detail: { items: [payload] },
        }),
      )
    } catch { /* silent */ }
  }

  function upsertDraftsFromSource(drafts: AdjustmentEntry[]): {
    added: number
    updated: number
    skipped: number
  } {
    if (readonly.value) return { added: 0, updated: 0, skipped: 0 }
    const result = mergeProvenanceDrafts(entries.value, drafts)
    entries.value = result.entries.length ? result.entries : [createEmptyEntry(1)]
    persist()
    return { added: result.added, updated: result.updated, skipped: result.skipped }
  }

  function saveAndWriteback(): void {
    persist()
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
    }
    flushSave()

    const summaries = aggregateForWriteback()
    if (onWritebackG4_1) onWritebackG4_1(summaries)

    // 单一权威回写（不再依赖外部再写一遍）
    writebackToG4_1Store()

    window.dispatchEvent(
      new CustomEvent('g4:adjustment-writeback', {
        detail: {
          summaries,
          originalNet: originalNetAje.value,
          impairmentNet: impairmentNetAje.value,
          // 兼容旧监听
          netAdjustment: originalNetAje.value,
        },
      }),
    )
    window.dispatchEvent(
      new CustomEvent('g4:adjustment-confirmed', {
        detail: {
          originalNet: originalNetAje.value,
          impairmentNet: impairmentNetAje.value,
          netAdjustment: originalNetAje.value,
          summaries,
        },
      }),
    )
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
    netAjeToG4,
    originalNetAje,
    impairmentNetAje,
    creditLossAccount,
    addEntry,
    removeEntry,
    updateCell,
    saveAndWriteback,
    aggregateForWriteback,
    upsertDraftsFromSource,
    loadEntries,
    accountOptions,
    categoryOptions: CATEGORY_OPTIONS,
    STORAGE_KEY,
  }
}

export default useG4MainAdjustment
