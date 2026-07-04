/**
 * useF1DisclosureSoe — 附注披露信息（国企）核心逻辑 composable
 *
 * Spec: .kiro/specs/f1-prepayment/
 * Task: 14.1
 *
 * 职责：
 * - 2子节（按账龄/超1年）
 * - 从crossSheet取数（agingAggregation + longTermRows）
 * - 动态行 + 合计
 * - applicable_standards 适用性判断（soe显示控制）
 *
 * Requirements: 13.1-13.7, 14.1-14.6
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { useF1CrossSheet } from './useF1CrossSheet'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SoeDisclosureRow {
  rowId: string
  label: string
  endAmount: number
  priorAmount: number
  reason?: string
}

export interface UseD3DisclosureSoeOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  crossSheet: ReturnType<typeof useF1CrossSheet>
  isReadonly: Ref<boolean>
  applicableStandards: Ref<string[]>
}

// ─── Constants ───────────────────────────────────────────────────────────────

const PREFIX = 'F1-note-soe-'
const ITEM_SECTION2_ROWS = `${PREFIX}section2-rows`

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

function safeParseRows(jsonStr: string | null | undefined): SoeDisclosureRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function createEmptyRow(): SoeDisclosureRow {
  return { rowId: generateRowId(), label: '', endAmount: 0, priorAmount: 0, reason: '' }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1DisclosureSoe(options: UseD3DisclosureSoeOptions) {
  const { allResponses, debouncedSave, crossSheet, isReadonly, applicableStandards } = options

  // ─── Applicable check ────────────────────────────────────────────────

  const isApplicable: ComputedRef<boolean> = computed(() => {
    return applicableStandards.value.some(s =>
      s === 'soe_standalone' || s === 'soe_consolidated',
    )
  })

  // ─── Section 1: 按账龄（from crossSheet）────────────────────────────

  const section1Rows: ComputedRef<SoeDisclosureRow[]> = computed(() => {
    const aging = crossSheet.agingAggregation.value
    const within1End = aging.within1
    const over1End = aging.y1to2 + aging.y2to3 + aging.over3
    const within1Prior = aging.prior_within1
    const over1Prior = aging.prior_y1to2 + aging.prior_y2to3 + aging.prior_over3

    return [
      { rowId: 'cs-aging-within1', label: '1年以内', endAmount: within1End, priorAmount: within1Prior },
      { rowId: 'cs-aging-over1', label: '1年以上', endAmount: over1End, priorAmount: over1Prior },
    ]
  })

  const section1Subtotal: ComputedRef<SoeDisclosureRow> = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section1Rows.value.map(r => r.endAmount)),
    priorAmount: calcSubtotal(section1Rows.value.map(r => r.priorAmount)),
  }))

  // ─── Section 2: 超1年重要预收（from crossSheet + dynamic rows）────

  const section2DynamicRows = ref<SoeDisclosureRow[]>([])

  watch(
    () => allResponses.value.get(ITEM_SECTION2_ROWS)?.remark,
    (jsonStr) => { section2DynamicRows.value = safeParseRows(jsonStr) },
    { immediate: true },
  )

  const section2Rows: ComputedRef<SoeDisclosureRow[]> = computed(() => {
    const ltRows = crossSheet.longTermRows.value.map(r => ({
      rowId: `cs-lt-${r.customerName}`,
      label: r.customerName,
      endAmount: r.endAudited,
      priorAmount: 0,
      reason: r.agingDescription,
    }))
    return [...ltRows, ...section2DynamicRows.value]
  })

  const section2Subtotal: ComputedRef<SoeDisclosureRow> = computed(() => ({
    rowId: '__subtotal__',
    label: '合计',
    endAmount: calcSubtotal(section2Rows.value.map(r => r.endAmount)),
    priorAmount: calcSubtotal(section2Rows.value.map(r => r.priorAmount)),
  }))

  // ─── Row operations (section 2 only) ─────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    section2DynamicRows.value = [...section2DynamicRows.value, createEmptyRow()]
    debouncedSave(ITEM_SECTION2_ROWS, { remark: JSON.stringify(section2DynamicRows.value) })
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    section2DynamicRows.value = section2DynamicRows.value.filter(r => r.rowId !== rowId)
    debouncedSave(ITEM_SECTION2_ROWS, { remark: JSON.stringify(section2DynamicRows.value) })
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const idx = section2DynamicRows.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return

    const row = { ...section2DynamicRows.value[idx] }
    if (field === 'endAmount' || field === 'priorAmount') {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = value
    }

    const newRows = [...section2DynamicRows.value]
    newRows[idx] = row
    section2DynamicRows.value = newRows
    debouncedSave(ITEM_SECTION2_ROWS, { remark: JSON.stringify(newRows) })
  }

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    isApplicable,
    // Section 1
    section1Rows,
    section1Subtotal,
    // Section 2
    section2Rows,
    section2Subtotal,
    // Operations
    addRow,
    removeRow,
    updateCell,
  }
}

export default useF1DisclosureSoe
