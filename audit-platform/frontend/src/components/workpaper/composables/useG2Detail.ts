/**
 * useG2Detail — G2-2 明细表（应收利息逐笔明细 16列）
 *
 * 公式链：
 *   计息天数 = 计息截止日 - 计息起始日
 *   应计利息 = 面值 × 票面利率/100 × 计息天数/365
 *   期末应收 = 应计利息 - 已收利息
 *   差异 = 期末应收 - 企业账面值
 *
 * 特性：差异>100橙色标记 + 动态行增删 + 合计 + 序列化
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 5.1
 * Requirements: 5.1~5.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAccruedDays,
  calcInterest365,
  calcNetReceivable,
} from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ────────────────────────────────────────────────────────────────────

export interface InterestDetailRow {
  id: string
  seq: number
  investTarget: string          // 投资标的
  investType: string            // 投资类型
  faceValue: number             // 面值/本金
  couponRate: number            // 票面利率(%)
  accrualStart: string          // 计息起始日
  accrualEnd: string            // 计息截止日
  accruedDays: number           // 计息天数(公式)
  accruedInterest: number       // 应计利息(公式)
  receivedInterest: number      // 已收利息
  netReceivable: number         // 期末应收(公式)
  bookValue: number             // 企业账面值
  variance: number              // 差异(公式)
  eclStage: 'Stage1' | 'Stage2' | 'Stage3'
  remark: string
  indexRef: string
}

/** 存储行（不含公式计算字段） */
interface StoredDetailRow {
  id: string
  seq: number
  investTarget: string
  investType: string
  faceValue: number
  couponRate: number
  accrualStart: string
  accrualEnd: string
  receivedInterest: number
  bookValue: number
  eclStage: 'Stage1' | 'Stage2' | 'Stage3'
  remark: string
  indexRef: string
}

export interface InterestDetailTotals {
  faceValue: number
  accruedInterest: number
  netReceivable: number
  variance: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'G2-2-detail-rows'
const VARIANCE_THRESHOLD = 100

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateId(): string {
  return `detail-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function safeParseRows(jsonStr: string | null | undefined): StoredDetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 从存储行计算展示行（含公式字段） */
function computeRow(stored: StoredDetailRow): InterestDetailRow {
  const accruedDays = calcAccruedDays(stored.accrualStart, stored.accrualEnd)
  const accruedInterest = calcInterest365(stored.faceValue, stored.couponRate, accruedDays)
  const netReceivable = calcNetReceivable(accruedInterest, stored.receivedInterest)
  const variance = netReceivable - stored.bookValue

  return {
    ...stored,
    accruedDays,
    accruedInterest,
    netReceivable,
    variance,
  }
}

function createEmptyStoredRow(seq: number): StoredDetailRow {
  return {
    id: generateId(),
    seq,
    investTarget: '',
    investType: '',
    faceValue: 0,
    couponRate: 0,
    accrualStart: '',
    accrualEnd: '',
    receivedInterest: 0,
    bookValue: 0,
    eclStage: 'Stage1',
    remark: '',
    indexRef: '',
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export interface UseG2DetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2Detail(options: UseG2DetailOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── 从 allResponses 解析行数据 ──────────────────────────────────────

  const storedRows = computed<StoredDetailRow[]>(() => {
    const resp = allResponses.value.get(STORAGE_KEY)
    return safeParseRows(resp?.remark)
  })

  /** 数据行（公式自动计算） */
  const dataRows: ComputedRef<InterestDetailRow[]> = computed(() =>
    storedRows.value.map((s) => computeRow(s)),
  )

  /** 合计行 */
  const totals: ComputedRef<InterestDetailTotals> = computed(() => {
    const rows = dataRows.value
    return {
      faceValue: rows.reduce((sum, r) => sum + r.faceValue, 0),
      accruedInterest: rows.reduce((sum, r) => sum + r.accruedInterest, 0),
      netReceivable: rows.reduce((sum, r) => sum + r.netReceivable, 0),
      variance: rows.reduce((sum, r) => sum + r.variance, 0),
    }
  })

  // ─── 差异高亮判断 ──────────────────────────────────────────────────────

  /** |差异|>100 → 橙色标记 */
  function isVarianceWarning(row: InterestDetailRow): boolean {
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
    // 重新编序
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistRows(filtered)
  }

  // ─── 单元格编辑 ─────────────────────────────────────────────────────────

  function updateCell(rowId: string, field: keyof StoredDetailRow, value: string | number): void {
    if (readonly.value) return
    const current = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const numericFields = ['faceValue', 'couponRate', 'receivedInterest', 'bookValue'] as const
    if ((numericFields as readonly string[]).includes(field)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }

    persistRows(current)
  }

  // ─── 持久化 ─────────────────────────────────────────────────────────────

  function persistRows(rows: StoredDetailRow[]): void {
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

export default useG2Detail
