/**
 * useD4RevenueDetail — D4-2 主营业务收入明细22列宽表 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 6.2
 *
 * 职责：
 * - RevenueDetailRow 22列完整定义
 * - rows reactive + 行内公式（N=SUM months; P=N+O; S=Q+R; T/U变动率）
 * - subtotalRow computed（SUM all rows）
 * - verificationRow computed（合计 - TB数 6001）
 * - searchQuery + filteredRows（大小写不敏感product过滤）
 * - addRow / removeRow / updateCell
 * - importFromLedger stub
 *
 * Requirements: 3.1-3.10
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcMonthlyTotal,
  calcAuditedWithAdj,
  calcChangeRate,
  calcSubtotal,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface RevenueDetailRow {
  rowId: string
  product: string           // A: 项目
  months: number[]          // B~M: 1月~12月 (12 values)
  periodTotal: number       // N: =SUM(months) (auto)
  auditAdjustment: number   // O: 本期审计调整
  audited: number           // P: =N+O (auto)
  priorUnadjusted: number   // Q: 上期未审数
  priorAdjustment: number   // R: 上期审计调整
  priorAudited: number      // S: =Q+R (auto)
  unadjustedChangeRate: number | '' | 'N/A'  // T: =(N-Q)/Q (auto)
  auditedChangeRate: number | '' | 'N/A'     // U: =(P-S)/S (auto)
  remark: string            // V: 备注
}

/** Stored row (without computed fields) */
interface StoredRevenueRow {
  rowId: string
  product: string
  months: number[]
  auditAdjustment: number
  priorUnadjusted: number
  priorAdjustment: number
  remark: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'D4-2-rows'
const EMPTY_MONTHS = [0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `d4r-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows(jsonStr: string | null | undefined): StoredRevenueRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any) => ({
      rowId: raw.rowId || generateRowId(),
      product: raw.product || '',
      months: Array.isArray(raw.months) ? raw.months.map(parseNum) : [...EMPTY_MONTHS],
      auditAdjustment: parseNum(raw.auditAdjustment),
      priorUnadjusted: parseNum(raw.priorUnadjusted),
      priorAdjustment: parseNum(raw.priorAdjustment),
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

/**
 * Compute full RevenueDetailRow from stored data (apply formulas)
 */
function computeRow(stored: StoredRevenueRow): RevenueDetailRow {
  const months = stored.months.length === 12 ? stored.months : [...EMPTY_MONTHS]
  const periodTotal = calcMonthlyTotal(months)
  const audited = calcAuditedWithAdj(periodTotal, stored.auditAdjustment)
  const priorAudited = calcAuditedWithAdj(stored.priorUnadjusted, stored.priorAdjustment)
  const unadjustedChangeRate = calcChangeRate(periodTotal, stored.priorUnadjusted)
  const auditedChangeRate = calcChangeRate(audited, priorAudited)

  return {
    rowId: stored.rowId,
    product: stored.product,
    months,
    periodTotal,
    auditAdjustment: stored.auditAdjustment,
    audited,
    priorUnadjusted: stored.priorUnadjusted,
    priorAdjustment: stored.priorAdjustment,
    priorAudited,
    unadjustedChangeRate,
    auditedChangeRate,
    remark: stored.remark,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4RevenueDetail(options: UseD4BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── Reactive State ──────────────────────────────────────────────────

  const storedData = ref<StoredRevenueRow[]>([])
  const searchQuery = ref('')

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

  // ─── Computed: Full Rows (with formulas) ─────────────────────────────

  const rows: ComputedRef<RevenueDetailRow[]> = computed(() => {
    return storedData.value.map(computeRow)
  })

  // ─── Search / Filter ─────────────────────────────────────────────────

  const filteredRows: ComputedRef<RevenueDetailRow[]> = computed(() => {
    const query = searchQuery.value.trim().toLowerCase()
    if (!query) return rows.value
    return rows.value.filter(r => r.product.toLowerCase().includes(query))
  })

  // ─── Subtotal Row ────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<RevenueDetailRow> = computed(() => {
    const allRows = rows.value
    if (allRows.length === 0) {
      return computeRow({
        rowId: 'subtotal', product: '合计', months: [...EMPTY_MONTHS],
        auditAdjustment: 0, priorUnadjusted: 0, priorAdjustment: 0, remark: '',
      })
    }

    const months: number[] = []
    for (let m = 0; m < 12; m++) {
      months.push(calcSubtotal(allRows.map(r => r.months[m] ?? 0)))
    }
    const auditAdjustment = calcSubtotal(allRows.map(r => r.auditAdjustment))
    const priorUnadjusted = calcSubtotal(allRows.map(r => r.priorUnadjusted))
    const priorAdjustment = calcSubtotal(allRows.map(r => r.priorAdjustment))

    const stored: StoredRevenueRow = {
      rowId: 'subtotal',
      product: '合计',
      months,
      auditAdjustment,
      priorUnadjusted,
      priorAdjustment,
      remark: '',
    }
    return computeRow(stored)
  })

  // ─── Verification Row ────────────────────────────────────────────────

  const verificationRow: ComputedRef<{ diff: number }> = computed(() => {
    const tb6001 = parseNum(allResponses.value.get('D4-1-adj-tb-6001')?.remark)
    return { diff: subtotalRow.value.audited - tb6001 }
  })

  // ─── Row Operations ──────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push({
      rowId: generateRowId(),
      product: '',
      months: [...EMPTY_MONTHS],
      auditAdjustment: 0,
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

    if (field === 'product' || field === 'remark') {
      ;(row as any)[field] = String(value ?? '')
    } else if (field === 'auditAdjustment' || field === 'priorUnadjusted' || field === 'priorAdjustment') {
      ;(row as any)[field] = parseNum(value)
    } else if (field.startsWith('month-')) {
      const monthIdx = parseInt(field.replace('month-', ''), 10)
      if (monthIdx >= 0 && monthIdx < 12) {
        row.months[monthIdx] = parseNum(value)
      }
    }

    debounceSave()
  }

  // ─── Import From Ledger (stub) ───────────────────────────────────────

  async function importFromLedger(): Promise<void> {
    // Stub: actual implementation imports from tb_ledger 6001 monthly data
    // via API endpoint POST /api/workpapers/{wpId}/d4/import-from-ledger
    // which parses ledger entries into monthly sums per product/service line
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
    filteredRows,
    subtotalRow,
    verificationRow,
    searchQuery,
    addRow,
    removeRow,
    updateCell,
    importFromLedger,
  }
}

export default useD4RevenueDetail
