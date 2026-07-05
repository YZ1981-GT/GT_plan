/**
 * useG2InterestCalc — G2-5 利息测算表（11列）
 *
 * 公式链：
 *   计息天数 = 计息截止日 - 计息起始日
 *   应收利息 = 面值 × 票面利率/100 × 计息天数/365
 *   差异 = 应收利息 - 企业计提
 *
 * 特性：差异>100橙色标记 + 合计 + 动态行增删 + 序列化
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 5.2
 * Requirements: 8.1~8.8
 */
import { ref, computed, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAccruedDays,
  calcInterest365,
} from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ────────────────────────────────────────────────────────────────────

/** 存储行（不含公式计算字段） */
interface StoredInterestCalcRow {
  id: string
  seq: number
  investTarget: string          // 投资标的
  faceValue: number             // 面值/本金
  couponRate: number            // 票面利率(%)
  accrualStart: string          // 计息起始日
  accrualEnd: string            // 计息截止日
  companyAccrual: number        // 企业计提
  remark: string                // 备注
}

/** 展示行（含公式计算字段） */
export interface InterestCalcRow {
  id: string
  seq: number
  investTarget: string
  faceValue: number
  couponRate: number
  accrualStart: string
  accrualEnd: string
  accruedDays: number           // 计息天数(公式)
  calculatedInterest: number    // 应收利息(公式)
  companyAccrual: number        // 企业计提
  variance: number              // 差异(公式)
  remark: string
}

export interface InterestCalcTotals {
  faceValue: number
  calculatedInterest: number
  companyAccrual: number
  variance: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'G2-5-interest-calc-rows'
const VARIANCE_THRESHOLD = 100

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateId(): string {
  return `intcalc-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): StoredInterestCalcRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 从存储行计算展示行（含公式字段） */
function computeRow(stored: StoredInterestCalcRow): InterestCalcRow {
  const accruedDays = calcAccruedDays(stored.accrualStart, stored.accrualEnd)
  const calculatedInterest = calcInterest365(stored.faceValue, stored.couponRate, accruedDays)
  const variance = calculatedInterest - stored.companyAccrual

  return {
    ...stored,
    accruedDays,
    calculatedInterest,
    variance,
  }
}

function createEmptyStoredRow(seq: number): StoredInterestCalcRow {
  return {
    id: generateId(),
    seq,
    investTarget: '',
    faceValue: 0,
    couponRate: 0,
    accrualStart: '',
    accrualEnd: '',
    companyAccrual: 0,
    remark: '',
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export interface UseG2InterestCalcOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2InterestCalc(options: UseG2InterestCalcOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── 从 allResponses 解析行数据 ──────────────────────────────────────

  const storedRows = computed<StoredInterestCalcRow[]>(() => {
    const resp = allResponses.value.get(STORAGE_KEY)
    return safeParseRows(resp?.remark)
  })

  /** 数据行（公式自动计算） */
  const dataRows: ComputedRef<InterestCalcRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  /** 合计行 */
  const totals: ComputedRef<InterestCalcTotals> = computed(() => {
    const rows = dataRows.value
    return {
      faceValue: rows.reduce((sum, r) => sum + r.faceValue, 0),
      calculatedInterest: rows.reduce((sum, r) => sum + r.calculatedInterest, 0),
      companyAccrual: rows.reduce((sum, r) => sum + r.companyAccrual, 0),
      variance: rows.reduce((sum, r) => sum + r.variance, 0),
    }
  })

  // ─── 差异高亮判断 ──────────────────────────────────────────────────────

  /** |差异|>100 → 橙色标记 */
  function isVarianceWarning(row: InterestCalcRow): boolean {
    return Math.abs(row.variance) > VARIANCE_THRESHOLD
  }

  // ─── 动态行增删 ────────────────────────────────────────────────────────

  function addRow(): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    const newRow = createEmptyStoredRow(nextSeq)
    current.push(newRow)
    persistRows(current)
  }

  function removeRow(id: string): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistRows(filtered)
  }

  // ─── 单元格编辑 ─────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof StoredInterestCalcRow, value: string | number): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const numericFields = ['faceValue', 'couponRate', 'companyAccrual'] as const
    if ((numericFields as readonly string[]).includes(field)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }

    persistRows(current)
  }

  // ─── 持久化 ─────────────────────────────────────────────────────────────

  function persistRows(rows: StoredInterestCalcRow[]): void {
    const json = JSON.stringify(rows)
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
    try {
      const items = [allResponses.value.get(STORAGE_KEY)].filter(Boolean)
      window.dispatchEvent(new CustomEvent('g2:save-items', { detail: { items } }))
    } catch { /* silent */ }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    dataRows,
    totals,
    isVarianceWarning,
    addRow,
    removeRow,
    updateCell,
  }
}

export default useG2InterestCalc
