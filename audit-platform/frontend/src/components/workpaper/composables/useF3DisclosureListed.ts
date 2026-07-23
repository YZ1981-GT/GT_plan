/**
 * useF3DisclosureListed — F3 附注披露（上市）
 * Spec: .kiro/specs/f3-notes-payable/ Task 9.2
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useF3FormulaEngine'
import { buildF3DisclosureClassRows } from './useF3CrossSheet'
import type { ChecklistResponse } from './useF3FormData'

export interface F3DisclosureRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
  remark?: string
}

const PREFIX = 'F3-note-listed-'
const ITEM_SECTION2 = `${PREFIX}section2-rows`
const ADJ_KEY = 'F3-1-adj-rows'
const DETAIL_KEY = 'F3-2-rows'

function generateRowId(): string {
  return `f3nl-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows(jsonStr: string | null | undefined): F3DisclosureRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * P0-1：由审定表 + 明细表按类别（银行/商业/供应链/其他）组装分类行，
 * 供应链票据不再丢失，且期末数含本期发生（本期开票−兑付）+ 期末调整。
 */
function rowsFromAdjudication(allResponses: Ref<Map<string, ChecklistResponse>>): F3DisclosureRow[] {
  const rows = buildF3DisclosureClassRows(
    allResponses.value.get(ADJ_KEY)?.remark,
    allResponses.value.get(DETAIL_KEY)?.remark,
  )
  return rows.map((r) => ({
    rowId: `cs-${r.rowKey}`,
    label: r.label,
    endAmount: r.endAmount,
    priorAmount: r.priorAmount,
  }))
}

export function useF3DisclosureListed(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}) {
  const { allResponses, isReadonly, applicableStandards } = options
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  const adjudicatedRefreshKey = ref(0)

  // 与 F2 附注同口径：项目未配置适用准则时默认适用（避免整页被"不适用"空态卡死），
  // 已配置时按 listed 关键字判断。
  const isApplicable: ComputedRef<boolean> = computed(() => {
    const list = applicableStandards.value || []
    if (list.length === 0) return true
    return list.some((s) => {
      const x = String(s).toLowerCase()
      return x.includes('listed') || x.includes('上市')
    })
  })

  const section1Rows: ComputedRef<F3DisclosureRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    return rowsFromAdjudication(allResponses)
  })

  const section1Subtotal: ComputedRef<F3DisclosureRow> = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section1Rows.value.map((r) => r.endAmount)),
    priorAmount: calcSubtotal(section1Rows.value.map((r) => r.priorAmount)),
  }))

  const section2DynamicRows = ref<F3DisclosureRow[]>([])
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
        detail: { wpCode: 'F3', section: 'listed', text: val },
      }))
    } catch { /* silent */ }
  })

  const adjudicatedHandler = (e: Event) => {
    const d = (e as CustomEvent).detail
    const code = String(d?.accountCode ?? '')
    if (code === '2201' || code.includes('2201')) {
      adjudicatedRefreshKey.value += 1
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
    for (const { event, handler } of eventListeners) window.removeEventListener(event, handler)
  })

  return {
    isApplicable,
    section1Rows,
    section1Subtotal,
    section2Rows,
    section2Subtotal,
    noteText,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useF3DisclosureListed
