/**
 * useF2DisclosureListed — F2 附注披露（上市）
 * Spec: .kiro/specs/f2-inventory-main/ Task 15.5
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
  remark?: string
}

const PREFIX = 'F2-note-listed-'
const ITEM_SECTION2 = `${PREFIX}section2-rows`

function generateRowId(): string {
  return `f2nl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows(jsonStr: string | null | undefined): F2DisclosureRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

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

    return {
      rowId: `cs-${cat.rowKey}`,
      label: cat.label,
      endAmount,
      priorAmount,
    }
  })
}

function isF2InventoryAccount(code: string): boolean {
  const n = parseInt(code, 10)
  return n >= 1401 && n <= 1412
}

export function useF2DisclosureListed(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}) {
  const { allResponses, isReadonly, applicableStandards } = options
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []
  const adjudicatedRefreshKey = ref(0)
  const dataUpdatedVisible = ref(false)
  let dataUpdatedTimer: ReturnType<typeof setTimeout> | null = null

  const isApplicable: ComputedRef<boolean> = computed(() =>
    applicableStandards.value.some((s) => s === 'listed_standalone' || s === 'listed_consolidated'),
  )

  const section1Rows: ComputedRef<F2DisclosureRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    return rowsFromAdjudication(allResponses)
  })

  const section1Subtotal: ComputedRef<F2DisclosureRow> = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section1Rows.value.map((r) => r.endAmount)),
    priorAmount: calcSubtotal(section1Rows.value.map((r) => r.priorAmount)),
  }))

  const section2DynamicRows = ref<F2DisclosureRow[]>([])
  watch(
    () => allResponses.value.get(ITEM_SECTION2)?.remark,
    (jsonStr) => { section2DynamicRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  const section2Rows = computed(() => section2DynamicRows.value)
  const section2Subtotal = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section2Rows.value.map((r) => r.endAmount)),
    priorAmount: calcSubtotal(section2Rows.value.map((r) => r.priorAmount)),
  }))

  const noteText = ref('')
  watch(() => allResponses.value.get(`${PREFIX}note`)?.remark, (v) => { noteText.value = v || '' }, { immediate: true })

  function flushSave(): void {
    const items = [
      allResponses.value.get(ITEM_SECTION2),
      allResponses.value.get(`${PREFIX}note`),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f2:save-items', { detail: { items } }))
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
        detail: { wpCode: 'F2', section: 'listed', text: val },
      }))
    } catch { /* silent */ }
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

  function addRow(): void {
    if (isReadonly.value) return
    section2DynamicRows.value = [...section2DynamicRows.value, {
      rowId: generateRowId(), label: '', endAmount: 0, priorAmount: 0, remark: '',
    }]
    allResponses.value.set(ITEM_SECTION2, {
      item_id: ITEM_SECTION2, conclusion: null, remark: JSON.stringify(section2DynamicRows.value),
    })
    debounceSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    section2DynamicRows.value = section2DynamicRows.value.filter((r) => r.rowId !== rowId)
    allResponses.value.set(ITEM_SECTION2, {
      item_id: ITEM_SECTION2, conclusion: null, remark: JSON.stringify(section2DynamicRows.value),
    })
    debounceSave()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = section2DynamicRows.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...section2DynamicRows.value[idx] }
    if (field === 'endAmount' || field === 'priorAmount') (row as any)[field] = parseNum(value)
    else (row as any)[field] = value
    section2DynamicRows.value.splice(idx, 1, row)
    allResponses.value.set(ITEM_SECTION2, {
      item_id: ITEM_SECTION2, conclusion: null, remark: JSON.stringify(section2DynamicRows.value),
    })
    debounceSave()
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); flushSave() }
    if (dataUpdatedTimer) clearTimeout(dataUpdatedTimer)
    for (const { event, handler } of eventListeners) window.removeEventListener(event, handler)
  })

  return {
    isApplicable,
    section1Rows,
    section1Subtotal,
    section2Rows,
    section2Subtotal,
    noteText,
    dataUpdatedVisible,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useF2DisclosureListed
