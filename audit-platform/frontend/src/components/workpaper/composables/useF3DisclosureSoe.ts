/**
 * useF3DisclosureSoe — F3 附注披露（国企）
 * Spec: .kiro/specs/f3-notes-payable/ Task 9.2
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcCreditBalance, calcAdjustedAmount } from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'

export interface F3SoeDisclosureRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
}

const PREFIX = 'F3-note-soe-'
const ITEM_ROWS = `${PREFIX}rows`
const ADJ_KEY = 'F3-1-adj-rows'

function generateRowId(): string {
  return `f3ns-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows(jsonStr: string | null | undefined): F3SoeDisclosureRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function parseAdjClosing(row: any): number {
  const openingAdj = calcAdjustedAmount(
    parseNum(row.openingUnadjusted),
    parseNum(row.openingAje),
    parseNum(row.openingRje),
  )
  const closingUnadj = calcCreditBalance(openingAdj, parseNum(row.periodCredit), parseNum(row.periodDebit))
  return calcAdjustedAmount(closingUnadj, parseNum(row.closingAje), parseNum(row.closingRje))
}

export function useF3DisclosureSoe(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}) {
  const { allResponses, isReadonly, applicableStandards } = options
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const adjudicatedRefreshKey = ref(0)

  const isApplicable: ComputedRef<boolean> = computed(() =>
    applicableStandards.value.some((s) => s === 'soe_standalone' || s === 'soe_consolidated'),
  )

  const section1Rows: ComputedRef<F3SoeDisclosureRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    const raw = allResponses.value.get(ADJ_KEY)?.remark
    if (!raw) return []
    try {
      const stored = JSON.parse(raw) as any[]
      return stored
        .filter((r) => r.rowKey === 'bank' || r.rowKey === 'commercial')
        .map((r) => ({
          rowId: `cs-${r.rowKey}`,
          label: r.label || (r.rowKey === 'bank' ? '银行承兑汇票' : '商业承兑汇票'),
          endAmount: parseAdjClosing(r),
          priorAmount: calcAdjustedAmount(
            parseNum(r.openingUnadjusted),
            parseNum(r.openingAje),
            parseNum(r.openingRje),
          ),
        }))
    } catch {
      return []
    }
  })

  const section1Subtotal = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section1Rows.value.map((r) => r.endAmount)),
    priorAmount: calcSubtotal(section1Rows.value.map((r) => r.priorAmount)),
  }))

  const dynamicRows = ref<F3SoeDisclosureRow[]>([])
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (jsonStr) => { dynamicRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  const noteText = ref('')
  watch(() => allResponses.value.get(`${PREFIX}note`)?.remark, (v) => { noteText.value = v || '' }, { immediate: true })

  function flushSave(): void {
    const items = [allResponses.value.get(ITEM_ROWS), allResponses.value.get(`${PREFIX}note`)].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  watch(noteText, (val) => {
    allResponses.value.set(`${PREFIX}note`, { item_id: `${PREFIX}note`, conclusion: null, remark: val })
    debounceSave()
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: { wpCode: 'F3', section: 'soe', text: val },
      }))
    } catch { /* silent */ }
  })

  const adjudicatedHandler = () => { adjudicatedRefreshKey.value += 1 }
  window.addEventListener('substantive:adjudicated', adjudicatedHandler)

  function addRow(): void {
    if (isReadonly.value) return
    dynamicRows.value = [...dynamicRows.value, { rowId: generateRowId(), label: '', endAmount: 0, priorAmount: 0 }]
    allResponses.value.set(ITEM_ROWS, { item_id: ITEM_ROWS, conclusion: null, remark: JSON.stringify(dynamicRows.value) })
    debounceSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    dynamicRows.value = dynamicRows.value.filter((r) => r.rowId !== rowId)
    allResponses.value.set(ITEM_ROWS, { item_id: ITEM_ROWS, conclusion: null, remark: JSON.stringify(dynamicRows.value) })
    debounceSave()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = dynamicRows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...dynamicRows.value[idx] }
    if (field === 'endAmount' || field === 'priorAmount') (row as any)[field] = parseNum(value)
    else (row as any)[field] = value
    dynamicRows.value.splice(idx, 1, row)
    allResponses.value.set(ITEM_ROWS, { item_id: ITEM_ROWS, conclusion: null, remark: JSON.stringify(dynamicRows.value) })
    debounceSave()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
    window.removeEventListener('substantive:adjudicated', adjudicatedHandler)
  })

  return {
    isApplicable,
    section1Rows,
    section1Subtotal,
    dynamicRows,
    noteText,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useF3DisclosureSoe
