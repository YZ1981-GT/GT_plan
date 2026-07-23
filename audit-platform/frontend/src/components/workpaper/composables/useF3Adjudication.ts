/**
 * useF3Adjudication — F3-1 审定表核心逻辑（贷方科目 2201）
 *
 * Spec: .kiro/specs/f3-notes-payable/ Task 4.1
 * 比照 useD4Adjudication
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  parseNum,
  calcAuditedAmount,
  calcCreditBalance,
  calcSubtotal,
} from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'
import { rowClosingAdjusted, F3_CATEGORY_META, type F3CategoryKey } from './useF3CrossSheet'

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

function categoryDefaultStored(rowKey: F3CategoryKey, label: string): StoredF3AdjRow {
  return {
    rowKey,
    label,
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
  }
}

/** 各票据类别默认存储行（单一真源，供审定表按需补行） */
const CATEGORY_DEFAULT: Record<F3CategoryKey, StoredF3AdjRow> = Object.fromEntries(
  F3_CATEGORY_META.map((m) => [m.rowKey, categoryDefaultStored(m.rowKey, m.label)]),
) as Record<F3CategoryKey, StoredF3AdjRow>

/** 银行/商业承兑默认始终展示；供应链/其他按明细存在时动态补入 */
const DEFAULT_STORED: StoredF3AdjRow[] = [
  { ...CATEGORY_DEFAULT.bank },
  { ...CATEGORY_DEFAULT.commercial },
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

  const CATEGORY_KEYS = new Set<string>(F3_CATEGORY_META.map((m) => m.rowKey))

  const storedRows = computed<StoredF3AdjRow[]>(() => {
    const resp = allResponses.value.get(ADJ_STORAGE_KEY)
    const base = ensureDefaultRows(safeParseRows<StoredF3AdjRow>(resp?.remark))
    // P0-1：明细存在供应链/其他票据时，动态补入对应审定行（避免金额被丢弃）
    if (crossSheet) {
      const keys = new Set(base.map((r) => r.rowKey))
      for (const key of ['supplychain', 'other'] as F3CategoryKey[]) {
        if (!keys.has(key) && crossSheet.hasCategory(key)) {
          base.push({ ...CATEGORY_DEFAULT[key] })
        }
      }
    }
    return base
  })

function mergeCrossSheet(stored: StoredF3AdjRow): StoredF3AdjRow {
  if (!crossSheet?.hasDetailData.value) return stored
  if (CATEGORY_KEYS.has(stored.rowKey)) {
    const key = stored.rowKey as F3CategoryKey
    return {
      ...stored,
      periodCredit: crossSheet.periodCreditByKey(key),
      periodDebit: crossSheet.periodDebitByKey(key),
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
    const total = crossSheet?.hasDetailData.value
      ? crossSheet.detailGrandTotal.value
      : (() => {
          const f3_2 = allResponses.value.get('F3-2-rows')
          if (!f3_2?.remark) return null
          const detailRows = safeParseRows<any>(f3_2.remark)
          if (detailRows.length === 0) return null
          return calcSubtotal(detailRows.map(rowClosingAdjusted))
        })()
    if (total == null) return null
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
    let idx = stored.findIndex((r) => r.rowKey === rowKey)
    // P0-1：首次编辑动态类别行（供应链/其他）时落库，保证可持久化
    if (idx === -1 && CATEGORY_KEYS.has(rowKey)) {
      stored.push({ ...CATEGORY_DEFAULT[rowKey as F3CategoryKey] })
      idx = stored.length - 1
    }
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
    // P1-8：统一走 eventBus（crossWpEventBridge 会镜像到 window，旧监听者不受影响）
    try {
      eventBus.emit('substantive:adjudicated', payload)
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
