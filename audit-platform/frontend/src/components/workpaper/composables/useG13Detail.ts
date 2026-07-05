/**
 * useG13Detail — G13-2 明细表（动态行 + FV变动勾稽）
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { ElMessageBox } from 'element-plus'
import { G13_BELONG_ACCOUNTS, G13_BELONG_ACCOUNT_LABELS, mapBelongToAdjRow, G13_SOURCE_INDEX_BY_BELONG } from './g13Constants'
import {
  parseNum,
  calcAdjustedAmount,
  calcFVChange,
  calcSubtotal,
  isFvReconciled,
} from './useG13FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export type G13CrossVerification = 'consistent' | 'inconsistent' | 'pending'

export interface G13DetailRow {
  rowId: string
  seq: number
  instrumentName: string
  belongAccount: string
  instrumentType: string
  openingFairValue: number
  closingFairValue: number
  fvChange: number
  currentUnadjusted: number
  adjustment: number
  currentAudited: number
  sourceIndex: string
  crossVerification: G13CrossVerification
  remark: string
  fvReconciled: boolean
}

const ITEM_ID_ROWS = 'G13-detail-rows'

function generateRowId(): string {
  return `g13d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 6)}`
}

function enrichRow(raw: Partial<G13DetailRow> & { rowId: string }): G13DetailRow {
  const openingFairValue = parseNum(raw.openingFairValue)
  const closingFairValue = parseNum(raw.closingFairValue)
  const currentUnadjusted = parseNum(raw.currentUnadjusted)
  const adjustment = parseNum(raw.adjustment)
  const fvChange = calcFVChange(openingFairValue, closingFairValue)
  const currentAudited = calcAdjustedAmount(currentUnadjusted, adjustment)
  return {
    rowId: raw.rowId,
    seq: parseNum(raw.seq) || 0,
    instrumentName: raw.instrumentName ?? '',
    belongAccount: raw.belongAccount ?? '',
    instrumentType: raw.instrumentType ?? '',
    openingFairValue,
    closingFairValue,
    fvChange,
    currentUnadjusted,
    adjustment,
    currentAudited,
    sourceIndex: raw.sourceIndex ?? '',
    crossVerification: (raw.crossVerification as G13CrossVerification) ?? 'pending',
    remark: raw.remark ?? '',
    fvReconciled: isFvReconciled(fvChange, currentAudited),
  }
}

export function createEmptyG13DetailRow(seq: number): G13DetailRow {
  return enrichRow({ rowId: generateRowId(), seq, instrumentName: '' })
}

function parseStoredRows(json: string | null | undefined): G13DetailRow[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: any, i: number) => enrichRow({ ...r, rowId: r.rowId || generateRowId(), seq: r.seq ?? i + 1 }))
  } catch {
    return []
  }
}

export interface UseG13DetailOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean> | ComputedRef<boolean>
}

export function useG13Detail(options: UseG13DetailOptions) {
  const rows = ref<G13DetailRow[]>([])
  const searchQuery = ref('')

  watch(
    () => options.allResponses.value.get(ITEM_ID_ROWS)?.remark,
    (json) => { rows.value = parseStoredRows(json) },
    { immediate: true },
  )

  function persist(): void {
    const payload = rows.value.map((r) => ({
      rowId: r.rowId,
      seq: r.seq,
      instrumentName: r.instrumentName,
      belongAccount: r.belongAccount,
      instrumentType: r.instrumentType,
      openingFairValue: r.openingFairValue,
      closingFairValue: r.closingFairValue,
      currentUnadjusted: r.currentUnadjusted,
      adjustment: r.adjustment,
      sourceIndex: r.sourceIndex,
      crossVerification: r.crossVerification,
      remark: r.remark,
    }))
    options.debouncedSave(ITEM_ID_ROWS, { remark: JSON.stringify(payload) })
    window.dispatchEvent(new CustomEvent('g13:detail-updated'))
  }

  function updateCell(rowId: string, field: keyof G13DetailRow, value: unknown): void {
    if (options.isReadonly.value) return
    const idx = rows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const raw = { ...rows.value[idx], [field]: value }
    if (field === 'belongAccount' && typeof value === 'string') {
      if (!raw.sourceIndex && G13_SOURCE_INDEX_BY_BELONG[value]) {
        raw.sourceIndex = G13_SOURCE_INDEX_BY_BELONG[value]
      }
    }
    const next = [...rows.value]
    next[idx] = enrichRow(raw)
    rows.value = next
    persist()
  }

  async function addRow(): Promise<void> {
    if (options.isReadonly.value) return
    try {
      const { value } = await ElMessageBox.prompt('请输入金融工具名称', '新增明细行', {
        confirmButtonText: '确定',
        cancelButtonText: '取消',
        inputPattern: /\S+/,
        inputErrorMessage: '名称不能为空',
      })
      const seq = rows.value.length + 1
      rows.value = [...rows.value, enrichRow({ rowId: generateRowId(), seq, instrumentName: value ?? '' })]
      persist()
    } catch { /* cancelled */ }
  }

  function removeRow(rowId: string): void {
    if (options.isReadonly.value) return
    rows.value = rows.value.filter((r) => r.rowId !== rowId).map((r, i) => enrichRow({ ...r, seq: i + 1 }))
    persist()
  }

  const dataRows = computed(() => rows.value)

  const filteredRows = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter((r) => {
      const belongLabel = G13_BELONG_ACCOUNT_LABELS[r.belongAccount] ?? r.belongAccount
      return (
        r.instrumentName.toLowerCase().includes(q)
        || r.instrumentType.toLowerCase().includes(q)
        || belongLabel.toLowerCase().includes(q)
        || r.sourceIndex.toLowerCase().includes(q)
      )
    })
  })

  const groupSubtotals = computed(() => {
    const groups: Record<string, { label: string; currentAudited: number; fvChange: number }> = {}
    for (const acct of G13_BELONG_ACCOUNTS) {
      groups[acct] = { label: `${acct} 小计`, currentAudited: 0, fvChange: 0 }
    }
    groups.other = { label: '其他小计', currentAudited: 0, fvChange: 0 }
    for (const r of rows.value) {
      const key = G13_BELONG_ACCOUNTS.includes(r.belongAccount as any) ? r.belongAccount : 'other'
      groups[key].currentAudited += r.currentAudited
      groups[key].fvChange += r.fvChange
    }
    return groups
  })

  const totalRow = computed((): G13DetailRow => {
    const r = rows.value
    const currentUnadjusted = calcSubtotal(r.map((x) => x.currentUnadjusted))
    const adjustment = calcSubtotal(r.map((x) => x.adjustment))
    const currentAudited = calcSubtotal(r.map((x) => x.currentAudited))
    const fvChange = calcSubtotal(r.map((x) => x.fvChange))
    return enrichRow({
      rowId: 'total',
      seq: 0,
      instrumentName: '合计',
      currentUnadjusted,
      adjustment,
      currentAudited,
      fvChange,
    })
  })

  const grandTotalAudited = computed(() => totalRow.value.currentAudited)
  const hasFvMismatch = computed(() => rows.value.some((r) => !r.fvReconciled))

  function aggregateByAdjRowKey(): Record<string, { unadjusted: number; adjustment: number; audited: number }> {
    const acc: Record<string, { unadjusted: number; adjustment: number; audited: number }> = {}
    for (const r of rows.value) {
      const key = mapBelongToAdjRow(r.belongAccount)
      if (!acc[key]) acc[key] = { unadjusted: 0, adjustment: 0, audited: 0 }
      acc[key].unadjusted += r.currentUnadjusted
      acc[key].adjustment += r.adjustment
      acc[key].audited += r.currentAudited
    }
    return acc
  }

  return {
    rows: dataRows,
    filteredRows,
    searchQuery,
    totalRow,
    groupSubtotals,
    grandTotalAudited,
    hasFvMismatch,
    updateCell,
    addRow,
    removeRow,
    persist,
    aggregateByAdjRowKey,
    ITEM_ID_ROWS,
    G13_BELONG_ACCOUNTS,
  }
}
