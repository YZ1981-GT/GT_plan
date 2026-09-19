/**
 * useE1CutoffTest — E1-21/22 截止测试 composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 14.1
 *
 * 职责：
 * - variant: 'bank' (E1-21 银行存款截止) | 'other' (E1-22 其他货币资金截止)
 * - 动态行：voucherNo(凭证号), date(日期), amount(金额), counterparty(对方账户),
 *   bsDate(资产负债表日, from options.bsDate), isCrossover(readonly: date > bsDate)
 * - determineCutoff(date, bsDate): boolean — date > bsDate → 跨期高亮
 * - 序列化/反序列化 → checklist_responses
 *   - bank: 'E1-cutoff-bank-rows'
 *   - other: 'E1-cutoff-other-rows'
 * - Debounce 2s 自动保存
 *
 * Requirements: 10.4-10.5
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type CutoffVariant = 'bank' | 'other'

export interface CutoffTestRow {
  id: string
  voucherNo: string      // 凭证号
  date: string           // 日期
  amount: number         // 金额
  counterparty: string   // 对方账户
  isCrossover: boolean   // readonly: date > bsDate → 跨期
  note: string           // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

function getStorageKey(variant: CutoffVariant): string {
  return variant === 'bank' ? 'E1-cutoff-bank-rows' : 'E1-cutoff-other-rows'
}

const USER_FIELDS: Array<keyof CutoffTestRow> = [
  'id', 'voucherNo', 'date', 'amount', 'counterparty', 'note',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(variant: CutoffVariant): string {
  const prefix = variant === 'bank' ? 'cutoff-b' : 'cutoff-o'
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/**
 * 判断是否跨期：date > bsDate → true
 * 日期格式支持 YYYY-MM-DD
 */
export function determineCutoff(date: string, bsDate: string): boolean {
  if (!date || !bsDate) return false
  const d = new Date(date)
  const bs = new Date(bsDate)
  if (isNaN(d.getTime()) || isNaN(bs.getTime())) return false
  return d.getTime() > bs.getTime()
}

function createEmptyRow(variant: CutoffVariant): CutoffTestRow {
  return {
    id: generateRowId(variant),
    voucherNo: '',
    date: '',
    amount: 0,
    counterparty: '',
    isCrossover: false,
    note: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1CutoffTest(options: UseE1BaseOptions & { variant: CutoffVariant }) {
  const { allResponses, saveImmediate, isReadonly, bsDate, variant } = options
  const storageKey = getStorageKey(variant)

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<CutoffTestRow[]>([createEmptyRow(variant)])
  const isLoading = ref(false)

  /** 资产负债表日（从options或allResponses获取） */
  const balanceSheetDate = computed(() => {
    return bsDate?.value || ''
  })

  // ─── Recalculate crossover status ──────────────────────────────────────

  function recalcCrossovers(): void {
    const bs = balanceSheetDate.value
    rows.value = rows.value.map(row => ({
      ...row,
      isCrossover: determineCutoff(row.date, bs),
    }))
  }

  // Watch bsDate changes to recompute crossover
  watch(balanceSheetDate, () => { recalcCrossovers() })

  // ─── Deserialization ───────────────────────────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(storageKey)
    const raw = response?.remark
    if (!raw) {
      rows.value = [createEmptyRow(variant)]
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = [createEmptyRow(variant)]
        return
      }
      const bs = balanceSheetDate.value
      rows.value = parsed.map((r: Record<string, unknown>) => {
        const date = String(r.date || '')
        return {
          id: String(r.id || generateRowId(variant)),
          voucherNo: String(r.voucherNo || ''),
          date,
          amount: parseNum(r.amount),
          counterparty: String(r.counterparty || ''),
          isCrossover: determineCutoff(date, bs),
          note: String(r.note || ''),
        }
      })
    } catch {
      console.warn(`[useE1CutoffTest:${variant}] JSON parse failed, fallback to empty`)
      rows.value = [createEmptyRow(variant)]
    }
  }

  loadFromResponses()

  watch(
    () => allResponses.value.get(storageKey)?.remark,
    (newRemark, oldRemark) => {
      if (newRemark !== oldRemark && newRemark !== serializeRows()) {
        loadFromResponses()
      }
    },
  )

  // ─── Serialization ─────────────────────────────────────────────────────

  function serializeRows(): string {
    const data = rows.value.map(row => {
      const obj: Record<string, unknown> = {}
      for (const field of USER_FIELDS) {
        obj[field] = row[field]
      }
      return obj
    })
    return JSON.stringify(data)
  }

  // ─── Debounce Save ─────────────────────────────────────────────────────

  let saveTimer: ReturnType<typeof setTimeout> | null = null

  function scheduleSave(): void {
    if (saveTimer) clearTimeout(saveTimer)
    saveTimer = setTimeout(() => {
      saveTimer = null
      persistToResponses()
    }, 2000)
  }

  function persistToResponses(): void {
    const serialized = serializeRows()
    const items: ChecklistItem[] = [
      { item_id: storageKey, conclusion: null, remark: serialized },
    ]
    allResponses.value.set(storageKey, { item_id: storageKey, conclusion: null, remark: serialized })
    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Row CRUD ──────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow(variant)]
    scheduleSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    rows.value = rows.value.filter(r => r.id !== rowId)
    scheduleSave()
  }

  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    if (field === 'amount') {
      row.amount = parseNum(value)
    } else {
      ;(row as any)[field] = String(value)
    }

    // Recalculate crossover if date changed
    if (field === 'date') {
      row.isCrossover = determineCutoff(String(value), balanceSheetDate.value)
    }

    const newRows = [...rows.value]
    newRows[idx] = row
    rows.value = newRows
    scheduleSave()
  }

  // ─── Hydration ─────────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    try {
      loadFromResponses()
    } finally {
      isLoading.value = false
    }
  }

  // ─── Cleanup ───────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persistToResponses()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    rows,
    balanceSheetDate,
    isLoading,
    determineCutoff,
    addRow,
    removeRow,
    updateCell,
    hydrate,
  }
}
