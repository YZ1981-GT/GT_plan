/**
 * useD3DisclosureListed — 附注披露信息（上市公司）核心逻辑 composable
 *
 * Spec: .kiro/specs/d3-prepaid-accounts/
 * Task: 14.1
 *
 * 职责：
 * - 3子节（按性质/超1年/重大变动）
 * - 从crossSheet取数（natureAggregation + longTermRows）
 * - 动态行 + 合计
 * - 说明textarea + EventBus双向回写
 * - applicable_standards 适用性判断
 *
 * Requirements: 12.1-12.8, 14.1-14.6
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useD3FormulaEngine'
import type { ChecklistResponse } from './useD3FormData'
import type { useD3CrossSheet } from './useD3CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface DisclosureRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
  reason?: string
}

export interface DisclosureSection {
  sectionKey: string
  sectionLabel: string
  rows: DisclosureRow[]
  subtotalRow: DisclosureRow
  note: string
  isFromCrossSheet: boolean
}

export interface UseD3DisclosureListedOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useD3CrossSheet>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PREFIX = 'D3-note-listed-'
const ITEM_SECTION2_ROWS = `${PREFIX}section2-rows`
const ITEM_SECTION3_ROWS = `${PREFIX}section3-rows`

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function safeParseRows(jsonStr: string | null | undefined): DisclosureRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function createEmptyRow(): DisclosureRow {
  return { rowId: generateRowId(), label: '', endAmount: 0, priorAmount: 0, reason: '' }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD3DisclosureListed(options: UseD3DisclosureListedOptions) {
  const { allResponses, debouncedSave, crossSheet, isReadonly, applicableStandards } = options
  const eventListeners: Array<{ event: string; handler: (e: Event) => void }> = []

  // ─── Applicable check ────────────────────────────────────────────────

  const isApplicable: ComputedRef<boolean> = computed(() => {
    return applicableStandards.value.some(s =>
      s === 'listed_standalone' || s === 'listed_consolidated',
    )
  })

  // ─── Section 1: 按性质分类（from crossSheet）────────────────────────

  const section1Rows: ComputedRef<DisclosureRow[]> = computed(() => {
    const natureAgg = crossSheet.natureAggregation.value
    return Object.entries(natureAgg).map(([label, { current, prior }]) => ({
      rowId: `cs-nature-${label}`,
      label,
      endAmount: current,
      priorAmount: prior,
    }))
  })

  const section1Subtotal: ComputedRef<DisclosureRow> = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section1Rows.value.map(r => r.endAmount)),
    priorAmount: calcSubtotal(section1Rows.value.map(r => r.priorAmount)),
  }))

  // ─── Section 2: 超1年重要预收（from crossSheet + dynamic rows）────

  const section2DynamicRows = ref<DisclosureRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_SECTION2_ROWS)?.remark,
    (jsonStr) => { section2DynamicRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  const section2Rows: ComputedRef<DisclosureRow[]> = computed(() => {
    // From crossSheet longTermRows
    const ltRows = crossSheet.longTermRows.value.map(r => ({
      rowId: `cs-lt-${r.customerName}`,
      label: r.customerName,
      endAmount: r.endAudited,
      priorAmount: 0,
      reason: r.agingDescription,
    }))
    return [...ltRows, ...section2DynamicRows.value]
  })

  const section2Subtotal: ComputedRef<DisclosureRow> = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section2Rows.value.map(r => r.endAmount)),
    priorAmount: calcSubtotal(section2Rows.value.map(r => r.priorAmount)),
  }))

  // ─── Section 3: 重大变动（dynamic rows only）──────────────────────

  const section3Rows = ref<DisclosureRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_SECTION3_ROWS)?.remark,
    (jsonStr) => { section3Rows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  const section3Subtotal: ComputedRef<DisclosureRow> = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section3Rows.value.map(r => r.endAmount)),
    priorAmount: calcSubtotal(section3Rows.value.map(r => r.priorAmount)),
  }))

  // ─── Notes (per section) ─────────────────────────────────────────────

  const note1 = ref('')
  const note2 = ref('')
  const note3 = ref('')

  watch(() => allResponses.value.get(`${PREFIX}note-1`)?.remark, (v) => { note1.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(`${PREFIX}note-2`)?.remark, (v) => { note2.value = v || '' }, { immediate: true })
  watch(() => allResponses.value.get(`${PREFIX}note-3`)?.remark, (v) => { note3.value = v || '' }, { immediate: true })

  watch(() => note1.value, (val) => { debouncedSave(`${PREFIX}note-1`, { remark: val }) })
  watch(() => note2.value, (val) => { debouncedSave(`${PREFIX}note-2`, { remark: val }) })
  watch(() => note3.value, (val) => {
    debouncedSave(`${PREFIX}note-3`, { remark: val })
    // EventBus双向回写附注模块
    try {
      window.dispatchEvent(new CustomEvent('disclosure:note-text-updated', {
        detail: {
          wpCode: 'D3',
          accountCode: '2203',
          projectId: options.projectId.value,
          section: 'listed-3',
          sectionIds: ['五、38'],
          text: val,
        },
      }))
    } catch { /* silent */ }
  })

  // ─── EventBus: 监听附注模块更新 ─────────────────────────────────────

  const noteUpdateHandler = (e: Event) => {
    const detail = (e as CustomEvent).detail
    if (detail?.wpCode === 'D3' && detail?.section?.startsWith('listed-')) {
      const idx = detail.section.replace('listed-', '')
      if (idx === '1') note1.value = detail.text || ''
      else if (idx === '2') note2.value = detail.text || ''
      else if (idx === '3') note3.value = detail.text || ''
    }
  }
  window.addEventListener('note:section-updated', noteUpdateHandler)
  eventListeners.push({ event: 'note:section-updated', handler: noteUpdateHandler })

  // ─── Row operations (section 2 & 3) ──────────────────────────────────

  function addRow(section: 2 | 3): void {
    if (isReadonly.value) return
    const row = createEmptyRow()
    if (section === 2) {
      section2DynamicRows.value = [...section2DynamicRows.value, row]
      debouncedSave(ITEM_SECTION2_ROWS, { remark: JSON.stringify(section2DynamicRows.value) })
    } else {
      section3Rows.value = [...section3Rows.value, row]
      debouncedSave(ITEM_SECTION3_ROWS, { remark: JSON.stringify(section3Rows.value) })
    }
  }

  function removeRow(section: 2 | 3, rowId: string): void {
    if (isReadonly.value) return
    if (section === 2) {
      section2DynamicRows.value = section2DynamicRows.value.filter(r => r.rowId !== rowId)
      debouncedSave(ITEM_SECTION2_ROWS, { remark: JSON.stringify(section2DynamicRows.value) })
    } else {
      section3Rows.value = section3Rows.value.filter(r => r.rowId !== rowId)
      debouncedSave(ITEM_SECTION3_ROWS, { remark: JSON.stringify(section3Rows.value) })
    }
  }

  function updateCell(section: 2 | 3, rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const rows = section === 2 ? section2DynamicRows.value : section3Rows.value
    const idx = rows.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...rows[idx] }
    if (field === 'endAmount' || field === 'priorAmount') {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    const newRows = [...rows]
    newRows[idx] = row

    if (section === 2) {
      section2DynamicRows.value = newRows
      debouncedSave(ITEM_SECTION2_ROWS, { remark: JSON.stringify(newRows) })
    } else {
      section3Rows.value = newRows
      debouncedSave(ITEM_SECTION3_ROWS, { remark: JSON.stringify(newRows) })
    }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    for (const { event, handler } of eventListeners) {
      window.removeEventListener(event, handler)
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    isApplicable,
    // Section 1
    section1Rows,
    section1Subtotal,
    note1,
    // Section 2
    section2Rows,
    section2Subtotal,
    note2,
    // Section 3
    section3Rows,
    section3Subtotal,
    note3,
    // Operations
    addRow,
    removeRow,
    updateCell,
  }
}

export default useD3DisclosureListed
