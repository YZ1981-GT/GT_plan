/**
 * useE1CashDetail — E1-2 现金明细表（按币种）composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 4.1
 *
 * 职责：
 * - 动态行管理（按币种：人民币/美元/日元/澳元/欧元…）
 * - 预设默认行：人民币（fxRate=1）
 * - 自动计算公式字段：
 *   - 期末原币 = 期初 + 增加 - 减少 (calcCashBalance)
 *   - 期末折算人民币 = 期末原币 × 汇率 (calcFxConvert)
 *   - 期末审定人民币 = 期末折算人民币 + 审计调整原币 × 汇率
 * - 固定合计行（SUM 各金额列）
 * - 期末合计写入 allResponses 供 E1-1 审定表取数：
 *   - 'E1-cash-detail-opening-unaudited' (SUM opening)
 *   - 'E1-cash-detail-total-unaudited' (SUM endingRmb — 未审期末)
 * - 序列化/反序列化 JSON → checklist_responses (item_id: 'E1-cash-detail-rows')
 * - Debounce 2s 自动保存
 *
 * Requirements: 3.1-3.6
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import {
  parseNum,
  calcCashBalance,
  calcFxConvert,
  sumField,
} from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CashDetailRow {
  id: string
  currency: string       // 币种(人民币/美元/日元/澳元/欧元...)
  opening: number        // 期初余额
  increase: number       // 本期增加
  decrease: number       // 本期减少
  endingFc: number       // 期末余额-原币 (readonly, computed: opening+increase-decrease)
  fxRate: number         // 期末折算汇率
  endingRmb: number      // 期末折算人民币金额 (readonly, computed: endingFc × fxRate)
  adjustment: number     // 审计调整-原币 (调减为负)
  auditedRmb: number     // 期末审定数-人民币 (readonly, computed: endingRmb + adjustment×fxRate)
  note: string           // 备注
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'E1-cash-detail-rows'

/** 用户输入字段（序列化时保留，计算字段重算） */
const USER_FIELDS: Array<keyof CashDetailRow> = [
  'id', 'currency', 'opening', 'increase', 'decrease', 'fxRate', 'adjustment', 'note',
]

/** 跨sheet写出key */
const CROSS_SHEET_KEY_OPENING = 'E1-cash-detail-opening-unaudited'
const CROSS_SHEET_KEY_ENDING = 'E1-cash-detail-total-unaudited'

// ─── Helpers ─────────────────────────────────────────────────────────────────

/** 生成行 ID */
function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `cash-${crypto.randomUUID()}`
  }
  return `cash-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 重算行内公式字段 */
function recalcRow(row: CashDetailRow): CashDetailRow {
  const endingFc = calcCashBalance(row.opening, row.increase, row.decrease)
  const endingRmb = calcFxConvert(endingFc, row.fxRate)
  const auditedRmb = endingRmb + calcFxConvert(row.adjustment, row.fxRate)
  return {
    ...row,
    endingFc,
    endingRmb,
    auditedRmb,
  }
}

/** 创建默认人民币行 */
function createDefaultRmbRow(): CashDetailRow {
  return recalcRow({
    id: 'fixed-rmb',
    currency: '人民币',
    opening: 0,
    increase: 0,
    decrease: 0,
    endingFc: 0,
    fxRate: 1,
    endingRmb: 0,
    adjustment: 0,
    auditedRmb: 0,
    note: '',
  })
}

/** 创建空白行 */
function createEmptyRow(): CashDetailRow {
  return recalcRow({
    id: generateRowId(),
    currency: '',
    opening: 0,
    increase: 0,
    decrease: 0,
    endingFc: 0,
    fxRate: 0,
    endingRmb: 0,
    adjustment: 0,
    auditedRmb: 0,
    note: '',
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1CashDetail(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ───────────────────────────────────────────────────────────────

  const rows = ref<CashDetailRow[]>([createDefaultRmbRow()])
  const isLoading = ref(false)

  // ─── Deserialization (Load from allResponses) ────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(STORAGE_KEY)
    const raw = response?.remark
    if (!raw) {
      rows.value = [createDefaultRmbRow()]
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = [createDefaultRmbRow()]
        return
      }
      const loadedRows: CashDetailRow[] = parsed.map((r: Record<string, unknown>) => recalcRow({
        id: String(r.id || generateRowId()),
        currency: String(r.currency || ''),
        opening: parseNum(r.opening),
        increase: parseNum(r.increase),
        decrease: parseNum(r.decrease),
        endingFc: 0, // recalculated
        fxRate: parseNum(r.fxRate),
        endingRmb: 0, // recalculated
        adjustment: parseNum(r.adjustment),
        auditedRmb: 0, // recalculated
        note: String(r.note || ''),
      }))

      // Ensure default RMB row exists
      const hasRmb = loadedRows.some(r => r.id === 'fixed-rmb')
      if (!hasRmb) {
        loadedRows.unshift(createDefaultRmbRow())
      }

      rows.value = loadedRows
    } catch {
      rows.value = [createDefaultRmbRow()]
    }
  }

  // Initial load
  loadFromResponses()

  // Watch allResponses for external changes
  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
    (newRemark, oldRemark) => {
      if (newRemark !== oldRemark && newRemark !== serializeRows()) {
        loadFromResponses()
      }
    },
  )

  // ─── Serialization ───────────────────────────────────────────────────────

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

  // ─── Debounce Save ───────────────────────────────────────────────────────

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
    const items: ChecklistItem[] = []

    // Save rows data
    const rowItem: ChecklistItem = { item_id: STORAGE_KEY, conclusion: null, remark: serialized }
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: serialized })
    items.push(rowItem)

    // Write cross-sheet totals for E1-1
    const openingTotal = String(totalRow.value.opening)
    const endingTotal = String(totalRow.value.endingRmb)

    allResponses.value.set(CROSS_SHEET_KEY_OPENING, {
      item_id: CROSS_SHEET_KEY_OPENING, conclusion: null, remark: openingTotal,
    })
    items.push({ item_id: CROSS_SHEET_KEY_OPENING, conclusion: null, remark: openingTotal })

    allResponses.value.set(CROSS_SHEET_KEY_ENDING, {
      item_id: CROSS_SHEET_KEY_ENDING, conclusion: null, remark: endingTotal,
    })
    items.push({ item_id: CROSS_SHEET_KEY_ENDING, conclusion: null, remark: endingTotal })

    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Total Row (computed) ────────────────────────────────────────────────

  const totalRow: ComputedRef<CashDetailRow> = computed(() => {
    const currentRows = rows.value
    return {
      id: 'total',
      currency: '合计',
      opening: sumField(currentRows as unknown as Array<Record<string, unknown>>, 'opening'),
      increase: sumField(currentRows as unknown as Array<Record<string, unknown>>, 'increase'),
      decrease: sumField(currentRows as unknown as Array<Record<string, unknown>>, 'decrease'),
      endingFc: sumField(currentRows as unknown as Array<Record<string, unknown>>, 'endingFc'),
      fxRate: 0, // 合计行汇率无意义
      endingRmb: sumField(currentRows as unknown as Array<Record<string, unknown>>, 'endingRmb'),
      adjustment: sumField(currentRows as unknown as Array<Record<string, unknown>>, 'adjustment'),
      auditedRmb: sumField(currentRows as unknown as Array<Record<string, unknown>>, 'auditedRmb'),
      note: '',
    }
  })

  // ─── Cross-Sheet Data Sync ───────────────────────────────────────────────

  // Watch total changes and update allResponses for E1-1 consumption
  watch(
    () => [totalRow.value.opening, totalRow.value.endingRmb],
    () => {
      // Update cross-sheet keys in allResponses (instant, no debounce needed for reads)
      const openingTotal = String(totalRow.value.opening)
      const endingTotal = String(totalRow.value.endingRmb)

      allResponses.value.set(CROSS_SHEET_KEY_OPENING, {
        item_id: CROSS_SHEET_KEY_OPENING, conclusion: null, remark: openingTotal,
      })
      allResponses.value.set(CROSS_SHEET_KEY_ENDING, {
        item_id: CROSS_SHEET_KEY_ENDING, conclusion: null, remark: endingTotal,
      })
    },
    { immediate: true },
  )

  // ─── Row CRUD ────────────────────────────────────────────────────────────

  /** 末尾新增空白行 */
  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow()]
    scheduleSave()
  }

  /** 删除行（不允许删除 fixed-rmb 默认行） */
  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    if (rowId === 'fixed-rmb') return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    rows.value = rows.value.filter(r => r.id !== rowId)
    scheduleSave()
  }

  /** 编辑单元格 → 公式重算 → debounce 保存 */
  function updateCell(rowId: string, field: string, value: number | string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }

    // Update the field
    if (field === 'currency' || field === 'note') {
      ;(row as any)[field] = String(value)
    } else {
      const numericFields: Array<keyof CashDetailRow> = [
        'opening', 'increase', 'decrease', 'fxRate', 'adjustment',
      ]
      if (numericFields.includes(field as keyof CashDetailRow)) {
        ;(row as any)[field] = parseNum(value)
      }
    }

    // Recalculate computed fields
    const recalculated = recalcRow(row)

    // Update immutably
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows

    scheduleSave()
  }

  // ─── Hydration ───────────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    try {
      loadFromResponses()
    } finally {
      isLoading.value = false
    }
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persistToResponses()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────────

  return {
    rows,
    totalRow,
    isLoading,
    addRow,
    removeRow,
    updateCell,
    hydrate,
  }
}
