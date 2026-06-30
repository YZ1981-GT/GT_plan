/**
 * useD4OtherRevenue — D4-3 其他业务收入明细 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 6.3
 *
 * 职责：
 * - OtherRevenueRow 完整定义（含审定/占比/变动自动计算）
 * - rows reactive + 自动计算字段
 * - subtotalRow computed（SUM all rows）
 * - verificationRow computed（合计 - TB数 6051）
 * - addRow / removeRow / updateCell
 *
 * Requirements: 4.1-4.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAuditedWithAdj,
  calcSubtotal,
  calcChangeRate,
  calcChangeAmount,
  calcProportion,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface OtherRevenueRow {
  rowId: string
  item: string
  currentUnadjusted: number
  currentAdjustment: number
  currentAudited: number    // = 未审 + 调整 (auto)
  currentProportion: number // = 本行/合计×100% (auto)
  priorUnadjusted: number
  priorAdjustment: number
  priorAudited: number      // auto
  priorProportion: number   // auto
  changeAmount: number      // = 本期审定 - 上期审定 (auto)
  changeRate: number | '' | 'N/A'  // auto
  remark: string
}

/** Stored format (without auto-computed fields) */
interface StoredOtherRow {
  rowId: string
  item: string
  currentUnadjusted: number
  currentAdjustment: number
  priorUnadjusted: number
  priorAdjustment: number
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D4-3-rows'

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `d4o-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows(jsonStr: string | null | undefined): StoredOtherRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      item: raw.item || '',
      currentUnadjusted: parseNum(raw.currentUnadjusted),
      currentAdjustment: parseNum(raw.currentAdjustment),
      priorUnadjusted: parseNum(raw.priorUnadjusted),
      priorAdjustment: parseNum(raw.priorAdjustment),
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4OtherRevenue(options: UseD4BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Reactive State ──────────────────────────────────────────────────

  const storedData = ref<StoredOtherRow[]>([])

  // ─── Load from allResponses ──────────────────────────────────────────

  function loadRows(): void {
    const resp = allResponses.value.get(STORAGE_KEY)
    storedData.value = safeParseRows(resp?.remark)
  }

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    () => {
      if (storedData.value.length === 0) {
        loadRows()
      }
    },
    { immediate: true },
  )

  // ─── Compute full rows with formulas ─────────────────────────────────

  /**
   * Total current audited (for proportion calculation)
   */
  const totalCurrentAudited = computed(() => {
    return calcSubtotal(
      storedData.value.map(r => calcAuditedWithAdj(r.currentUnadjusted, r.currentAdjustment)),
    )
  })

  const totalPriorAudited = computed(() => {
    return calcSubtotal(
      storedData.value.map(r => calcAuditedWithAdj(r.priorUnadjusted, r.priorAdjustment)),
    )
  })

  /**
   * Full computed rows with auto-calculated fields
   */
  const rows: ComputedRef<OtherRevenueRow[]> = computed(() => {
    const totalCurrent = totalCurrentAudited.value
    const totalPrior = totalPriorAudited.value

    return storedData.value.map(stored => {
      const currentAudited = calcAuditedWithAdj(stored.currentUnadjusted, stored.currentAdjustment)
      const priorAudited = calcAuditedWithAdj(stored.priorUnadjusted, stored.priorAdjustment)
      const currentProportion = calcProportion(currentAudited, totalCurrent)
      const priorProportion = calcProportion(priorAudited, totalPrior)
      const changeAmt = calcChangeAmount(currentAudited, priorAudited)
      const changeRt = calcChangeRate(currentAudited, priorAudited)

      return {
        rowId: stored.rowId,
        item: stored.item,
        currentUnadjusted: stored.currentUnadjusted,
        currentAdjustment: stored.currentAdjustment,
        currentAudited,
        currentProportion,
        priorUnadjusted: stored.priorUnadjusted,
        priorAdjustment: stored.priorAdjustment,
        priorAudited,
        priorProportion,
        changeAmount: changeAmt,
        changeRate: changeRt,
        remark: stored.remark,
      }
    })
  })

  // ─── Subtotal Row ────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<OtherRevenueRow> = computed(() => {
    const allRows = rows.value
    const currentUnadjusted = calcSubtotal(allRows.map(r => r.currentUnadjusted))
    const currentAdjustment = calcSubtotal(allRows.map(r => r.currentAdjustment))
    const currentAudited = calcAuditedWithAdj(currentUnadjusted, currentAdjustment)
    const priorUnadjusted = calcSubtotal(allRows.map(r => r.priorUnadjusted))
    const priorAdjustment = calcSubtotal(allRows.map(r => r.priorAdjustment))
    const priorAudited = calcAuditedWithAdj(priorUnadjusted, priorAdjustment)
    const changeAmt = calcChangeAmount(currentAudited, priorAudited)
    const changeRt = calcChangeRate(currentAudited, priorAudited)

    return {
      rowId: 'subtotal',
      item: '合计',
      currentUnadjusted,
      currentAdjustment,
      currentAudited,
      currentProportion: 100,
      priorUnadjusted,
      priorAdjustment,
      priorAudited,
      priorProportion: 100,
      changeAmount: changeAmt,
      changeRate: changeRt,
      remark: '',
    }
  })

  // ─── Verification Row ────────────────────────────────────────────────

  const verificationRow: ComputedRef<{ diff: number }> = computed(() => {
    const tb6051 = parseNum(allResponses.value.get('D4-1-adj-tb-6051')?.remark)
    return { diff: subtotalRow.value.currentAudited - tb6051 }
  })

  // ─── Row Operations ──────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push({
      rowId: generateRowId(),
      item: '',
      currentUnadjusted: 0,
      currentAdjustment: 0,
      priorUnadjusted: 0,
      priorAdjustment: 0,
      remark: '',
    })
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value) return
    const idx = storedData.value.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find(r => r.rowId === rowId)
    if (!row) return

    if (field === 'item' || field === 'remark') {
      ;(row as any)[field] = String(value ?? '')
    } else if (
      field === 'currentUnadjusted' ||
      field === 'currentAdjustment' ||
      field === 'priorUnadjusted' ||
      field === 'priorAdjustment'
    ) {
      ;(row as any)[field] = parseNum(value)
    }

    debounceSave()
  }

  // ─── Persist / Save ──────────────────────────────────────────────────

  function persistRows(): void {
    const json = JSON.stringify(storedData.value)
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
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
    const item = allResponses.value.get(STORAGE_KEY)
    if (!item) return
    try {
      window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items: [item] } }))
    } catch { /* silent */ }
  }

  // ─── Lifecycle ───────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    subtotalRow,
    verificationRow,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useD4OtherRevenue
