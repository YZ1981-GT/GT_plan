/**
 * useF2DisclosureSoe — F2 附注披露（国企）
 * Spec: .kiro/specs/f2-inventory-main/ Task 15.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcNetValue, calcAuditedEnd } from './useF2InvMaiFormulaEngine'
import type { ChecklistResponse } from './useF2FormData'
import { F2_CATEGORIES } from './useF2Adjudication'

export interface F2DisclosureRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
}

const PREFIX = 'F2-note-soe-'

function itemId(block: 'gross' | 'impairment', rowKey: string, field: string): string {
  return `F2-1-${block}-${rowKey}-${field}`
}

function loadField(map: Map<string, ChecklistResponse>, id: string): number {
  return parseNum(map.get(id)?.conclusion)
}

function rowsFromAdjudication(allResponses: Ref<Map<string, ChecklistResponse>>): F2DisclosureRow[] {
  const map = allResponses.value
  return F2_CATEGORIES.filter((c) => c.rowKey !== 'impairment-provision').map((cat) => {
    const openingG = loadField(map, itemId('gross', cat.rowKey, 'opening'))
    const openingI = loadField(map, itemId('impairment', cat.rowKey, 'opening'))
    const incG = loadField(map, itemId('gross', cat.rowKey, 'increase'))
    const incI = loadField(map, itemId('impairment', cat.rowKey, 'increase'))
    const decG = loadField(map, itemId('gross', cat.rowKey, 'decrease'))
    const decI = loadField(map, itemId('impairment', cat.rowKey, 'decrease'))
    const adjG = loadField(map, itemId('gross', cat.rowKey, 'adjustment'))
    const adjI = loadField(map, itemId('impairment', cat.rowKey, 'adjustment'))

    const priorAmount = calcNetValue(openingG, openingI)
    const endAuditedG = calcAuditedEnd(openingG, incG, decG, adjG)
    const endAuditedI = calcAuditedEnd(openingI, incI, decI, adjI)
    const endAmount = calcNetValue(endAuditedG, endAuditedI)

    return { rowId: `cs-${cat.rowKey}`, label: cat.label, endAmount, priorAmount }
  })
}

function isF2InventoryAccount(code: string): boolean {
  const n = parseInt(code, 10)
  return n >= 1401 && n <= 1412
}

export function useF2DisclosureSoe(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}) {
  const { allResponses, isReadonly, applicableStandards } = options
  const adjudicatedRefreshKey = ref(0)
  const dataUpdatedVisible = ref(false)
  let dataUpdatedTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  const isApplicable: ComputedRef<boolean> = computed(() =>
    applicableStandards.value.some((s) => s === 'soe' || s === 'state_owned'),
  )

  const rows: ComputedRef<F2DisclosureRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    return rowsFromAdjudication(allResponses)
  })

  const subtotal = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(rows.value.map((r) => r.endAmount)),
    priorAmount: calcSubtotal(rows.value.map((r) => r.priorAmount)),
  }))

  const noteText = ref('')
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  watch(() => allResponses.value.get(`${PREFIX}note`)?.remark, (v) => { noteText.value = v || '' }, { immediate: true })

  function flushSave(): void {
    const item = allResponses.value.get(`${PREFIX}note`)
    if (item) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items: [item] } }))
  }

  watch(noteText, (val) => {
    allResponses.value.set(`${PREFIX}note`, { item_id: `${PREFIX}note`, conclusion: null, remark: val })
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  })

  const adjudicatedHandler = (e: Event) => {
    const d = (e as CustomEvent).detail
    if (d?.wpCode !== 'F2') return
    const codes: string[] = d?.accountCodes ?? []
    if (codes.some(isF2InventoryAccount)) {
      adjudicatedRefreshKey.value += 1
      dataUpdatedVisible.value = true
      if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
      dataUpdatedTimer = setTimeout(() => { dataUpdatedVisible.value = false }, 3000)
    }
  }
  window.addEventListener('substantive:adjudicated', adjudicatedHandler)
  eventListeners.push({ event: 'substantive:adjudicated', handler: adjudicatedHandler })

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
    if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
    for (const { event, handler } of eventListeners) window.removeEventListener(event, handler)
  })

  return { isApplicable, rows, subtotal, noteText, dataUpdatedVisible }
}

export default useF2DisclosureSoe
