/**
 * useF3Adjudication — F3-1 审定表核心逻辑（贷方科目 2201）
 *
 * Spec: .kiro/specs/f3-notes-payable/ Task 4.1
 * 比照 useD4Adjudication
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedAmount,
  calcCreditBalance,
  calcSubtotal,
} from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'

export interface UseF3BaseOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export interface F3AdjudicationRow {
  rowKey: string
  label: string
  isFixed: boolean
  openingUnadjusted: number
  openingAje: number
  openingRje: number
  openingAdjusted: number
  periodCredit: number
  periodDebit: number
  closingUnadjusted: number
  closingAje: number
  closingRje: number
  closingAdjusted: number
  indexRef: string
  isFromCrossSheet: boolean
  isEditable: boolean
}

interface StoredF3AdjRow {
  rowKey: string
  label: string
  isFixed: boolean
  openingUnadjusted: number
  openingAje: number
  openingRje: number
  periodCredit: number
  periodDebit: number
  closingAje: number
  closingRje: number
  indexRef: string
  isFromCrossSheet: boolean
}

const ADJ_STORAGE_KEY = 'F3-1-adj-rows'
const BALANCE_TOLERANCE = 0.005

const DEFAULT_STORED: StoredF3AdjRow[] = [
  {
    rowKey: 'bank',
    label: '银行承兑汇票',
    isFixed: true,
    openingUnadjusted: 0,
    openingAje: 0,
    openingRje: 0,
    periodCredit: 0,
    periodDebit: 0,
    closingAje: 0,
    closingRje: 0,
    indexRef: '',
    isFromCrossSheet: false,
  },
  {
    rowKey: 'commercial',
    label: '商业承兑汇票',
    isFixed: true,
    openingUnadjusted: 0,
    openingAje: 0,
    openingRje: 0,
    periodCredit: 0,
    periodDebit: 0,
    closingAje: 0,
    closingRje: 0,
    indexRef: '',
    isFromCrossSheet: false,
  },
]

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function computeRow(stored: StoredF3AdjRow): F3AdjudicationRow {
  const openingAdjusted = calcAuditedAmount(stored.openingUnadjusted, stored.openingAje, stored.openingRje)
  const closingUnadjusted = calcCreditBalance(openingAdjusted, stored.periodCredit, stored.periodDebit)
  const closingAdjusted = calcAuditedAmount(closingUnadjusted, stored.closingAje, stored.closingRje)
  return {
    rowKey: stored.rowKey,
    label: stored.label,
    isFixed: stored.isFixed,
    openingUnadjusted: stored.openingUnadjusted,
    openingAje: stored.openingAje,
    openingRje: stored.openingRje,
    openingAdjusted,
    periodCredit: stored.periodCredit,
    periodDebit: stored.periodDebit,
    closingUnadjusted,
    closingAje: stored.closingAje,
    closingRje: stored.closingRje,
    closingAdjusted,
    indexRef: stored.indexRef,
    isFromCrossSheet: stored.isFromCrossSheet,
    isEditable: !stored.isFromCrossSheet,
  }
}

function ensureDefaultRows(stored: StoredF3AdjRow[]): StoredF3AdjRow[] {
  if (stored.length === 0) return DEFAULT_STORED.map((r) => ({ ...r }))
  const keys = new Set(stored.map((r) => r.rowKey))
  const merged = [...stored]
  for (const def of DEFAULT_STORED) {
    if (!keys.has(def.rowKey)) merged.push({ ...def })
  }
  return merged
}

export function useF3Adjudication(options: UseF3BaseOptions & { crossSheet?: ReturnType<typeof import('./useF3CrossSheet').useF3CrossSheet> }) {
  const { wpId, projectId, allResponses, isReadonly, crossSheet } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const auditNote = ref('')
  const auditConclusion = ref('')

  const storedRows = computed<StoredF3AdjRow[]>(() => {
    const resp = allResponses.value.get(ADJ_STORAGE_KEY)
    return ensureDefaultRows(safeParseRows<StoredF3AdjRow>(resp?.remark))
  })

function mergeCrossSheet(stored: StoredF3AdjRow): StoredF3AdjRow {
  if (!crossSheet?.hasDetailData.value) return stored
  if (stored.rowKey === 'bank') {
    return {
      ...stored,
      periodCredit: crossSheet.bankPeriodCredit.value,
      periodDebit: crossSheet.bankPeriodDebit.value,
      isFromCrossSheet: true,
    }
  }
  if (stored.rowKey === 'commercial') {
    return {
      ...stored,
      periodCredit: crossSheet.commercialPeriodCredit.value,
      periodDebit: crossSheet.commercialPeriodDebit.value,
      isFromCrossSheet: true,
    }
  }
  return stored
}

  const dataRows: ComputedRef<F3AdjudicationRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(mergeCrossSheet(s))),
  )

  const subtotalRow: ComputedRef<F3AdjudicationRow> = computed(() => {
    const rows = dataRows.value
    const stored: StoredF3AdjRow = {
      rowKey: 'subtotal',
      label: '合计',
      isFixed: true,
      openingUnadjusted: calcSubtotal(rows.map((r) => r.openingUnadjusted)),
      openingAje: calcSubtotal(rows.map((r) => r.openingAje)),
      openingRje: calcSubtotal(rows.map((r) => r.openingRje)),
      periodCredit: calcSubtotal(rows.map((r) => r.periodCredit)),
      periodDebit: calcSubtotal(rows.map((r) => r.periodDebit)),
      closingAje: calcSubtotal(rows.map((r) => r.closingAje)),
      closingRje: calcSubtotal(rows.map((r) => r.closingRje)),
      indexRef: '',
      isFromCrossSheet: false,
    }
    return computeRow(stored)
  })

  const trialBalanceRow: ComputedRef<number> = computed(() =>
    parseNum(allResponses.value.get('F3-1-adj-tb-2201')?.remark),
  )

  const differenceRow: ComputedRef<number> = computed(() =>
    subtotalRow.value.closingAdjusted - trialBalanceRow.value,
  )

  const detailCrossValidation: ComputedRef<string | null> = computed(() => {
    const f3_2 = allResponses.value.get('F3-2-rows')
    if (!f3_2?.remark) return null
    const detailRows = safeParseRows<any>(f3_2.remark)
    if (detailRows.length === 0) return null
    let total = 0
    for (const row of detailRows) {
      total += parseNum(row.adjustedBalance ?? row.closingBalance)
    }
    const diff = subtotalRow.value.closingAdjusted - total
    if (Math.abs(diff) > BALANCE_TOLERANCE) {
      return `F3-1合计(${subtotalRow.value.closingAdjusted.toFixed(2)}) 与 F3-2合计(${total.toFixed(2)}) 差异${diff.toFixed(2)}`
    }
    return null
  })

  watch(
    () => allResponses.value.get('F3-1-adj-note')?.remark,
    (v) => { auditNote.value = v || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get('F3-1-adj-conclusion')?.remark,
    (v) => { auditConclusion.value = v || '' },
    { immediate: true },
  )

  function updateCell(rowKey: string, field: string, value: number | string): void {
    if (readonly.value) return
    const stored = ensureDefaultRows(safeParseRows<StoredF3AdjRow>(allResponses.value.get(ADJ_STORAGE_KEY)?.remark))
    const idx = stored.findIndex((r) => r.rowKey === rowKey)
    if (idx === -1) return
    if (field === 'indexRef') {
      stored[idx].indexRef = String(value ?? '')
    } else {
      ;(stored[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    }
    persistRows(stored)
  }

  function persistRows(rows: StoredF3AdjRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(ADJ_STORAGE_KEY, {
      item_id: ADJ_STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
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
    try {
      const items = [
        allResponses.value.get(ADJ_STORAGE_KEY),
        allResponses.value.get('F3-1-adj-note'),
        allResponses.value.get('F3-1-adj-conclusion'),
        allResponses.value.get('F3-1-adj-tb-2201'),
      ].filter(Boolean)
      window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  function publishAdjudicated(): void {
    const amount = subtotalRow.value.closingAdjusted
    const payload = {
      wpCode: 'F3',
      accountCode: '2201',
      auditedAmount: amount,
    }
    try {
      window.dispatchEvent(new CustomEvent('substantive:adjudicated', { detail: payload }))
    } catch { /* silent */ }

    if (projectId.value) {
      try {
        window.dispatchEvent(new CustomEvent('f3:writeback-trial-balance', {
          detail: { projectId: projectId.value, accountCode: '2201', auditedAmount: amount },
        }))
      } catch { /* silent */ }
    }
  }

  watch(auditNote, (val) => {
    allResponses.value.set('F3-1-adj-note', { item_id: 'F3-1-adj-note', conclusion: null, remark: val })
    debounceSave()
  })

  watch(auditConclusion, (val) => {
    allResponses.value.set('F3-1-adj-conclusion', {
      item_id: 'F3-1-adj-conclusion',
      conclusion: null,
      remark: val,
    })
    debounceSave()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    dataRows,
    subtotalRow,
    trialBalanceRow,
    differenceRow,
    detailCrossValidation,
    auditNote,
    auditConclusion,
    updateCell,
    publishAdjudicated,
  }
}

export default useF3Adjudication
