/**
 * useF3DisclosureSoe — F3 附注披露（国企）
 * Spec: .kiro/specs/f3-notes-payable/ Task 9.2
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { calcSubtotal } from './useF3FormulaEngine'
import { buildF3DisclosureClassRows } from './useF3CrossSheet'
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
const DETAIL_KEY = 'F3-2-rows'

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

export function useF3DisclosureSoe(options: {
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}) {
  const { allResponses, isReadonly, applicableStandards } = options
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const adjudicatedRefreshKey = ref(0)

  // 与 F2 附注同口径：项目未配置适用准则时默认适用，已配置时按 soe/国企 关键字判断。
  const isApplicable: ComputedRef<boolean> = computed(() => {
    const list = applicableStandards.value || []
    if (list.length === 0) return true
    return list.some((s) => {
      const x = String(s).toLowerCase()
      return x.includes('soe') || x.includes('state_owned') || x.includes('国企') || x.includes('国有')
    })
  })

  const section1Rows: ComputedRef<F3SoeDisclosureRow[]> = computed(() => {
    void adjudicatedRefreshKey.value
    // P0-1：按类别（银行/商业/供应链/其他）从审定表+明细表组装分类行
    return buildF3DisclosureClassRows(
      allResponses.value.get(ADJ_KEY)?.remark,
      allResponses.value.get(DETAIL_KEY)?.remark,
    ).map((r) => ({
      rowId: `cs-${r.rowKey}`,
      label: r.label,
      endAmount: r.endAmount,
      priorAmount: r.priorAmount,
    }))
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
