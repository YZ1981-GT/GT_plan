/**
 * useG2VoucherCheck — G2-8 凭证检查表（借方/贷方独立区块）
 *
 * 借方检查区（增加/利息确认 14列）：
 *   序号|摘要|对方科目|金额|凭证日期|凭证编号|投资标的|面值|利率|计息天数|测算利息(公式)|差异|审计结论|备注
 *   测算利息 = 面值 × 利率/100 × 计息天数/365
 *   差异 = 测算利息 - 金额
 *
 * 贷方检查区（减少/利息收回 12列）：
 *   序号|摘要|对方科目|金额|凭证日期|凭证编号|收款银行|收款日期|是否到期收回|逾期天数|审计结论|备注
 *
 * 特性：两个独立数组(debitRows + creditRows) + 各自独立增删 + 底部小计
 *
 * Spec: .kiro/specs/g2-interest-receivable/ Task 5.4
 * Requirements: 11.1~11.11
 */
import { ref, computed, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcInterest365,
  calcOverdueDays,
} from './useG2IntRecFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ────────────────────────────────────────────────────────────────────

// --- 借方检查区 ---

/** 借方存储行 */
interface StoredDebitCheckRow {
  id: string
  seq: number
  summary: string               // 摘要
  counterAccount: string        // 对方科目
  amount: number                // 金额
  voucherDate: string           // 凭证日期
  voucherNo: string             // 凭证编号
  investTarget: string          // 投资标的
  faceValue: number             // 面值
  rate: number                  // 利率(%)
  accruedDays: number           // 计息天数
  auditConclusion: string       // 审计结论
  remark: string                // 备注
  source?: string               // 来源（抽凭引擎标记）
}

/** 借方展示行（含公式字段） */
export interface DebitCheckRow {
  id: string
  seq: number
  summary: string
  counterAccount: string
  amount: number
  voucherDate: string
  voucherNo: string
  investTarget: string
  faceValue: number
  rate: number
  accruedDays: number
  calculatedInterest: number    // 测算利息(公式)
  variance: number              // 差异(公式)
  auditConclusion: string
  remark: string
  source?: string
}

// --- 贷方检查区 ---

/** 贷方存储行 */
interface StoredCreditCheckRow {
  id: string
  seq: number
  summary: string               // 摘要
  counterAccount: string        // 对方科目
  amount: number                // 金额
  voucherDate: string           // 凭证日期
  voucherNo: string             // 凭证编号
  receivingBank: string         // 收款银行
  receiptDate: string           // 收款日期
  isOnTimeRecovery: string      // 是否到期收回
  auditConclusion: string       // 审计结论
  remark: string                // 备注
  source?: string               // 来源（抽凭引擎标记）
}

/** 贷方展示行（含逾期天数） */
export interface CreditCheckRow {
  id: string
  seq: number
  summary: string
  counterAccount: string
  amount: number
  voucherDate: string
  voucherNo: string
  receivingBank: string
  receiptDate: string
  isOnTimeRecovery: string
  overdueDays: number           // 逾期天数(公式)
  auditConclusion: string
  remark: string
  source?: string
}

export interface DebitCheckTotals {
  amount: number
  calculatedInterest: number
  variance: number
}

export interface CreditCheckTotals {
  amount: number
  overdueCount: number
}

// ─── Constants ────────────────────────────────────────────────────────────────

const DEBIT_STORAGE_KEY = 'G2-8-debit-check-rows'
const CREDIT_STORAGE_KEY = 'G2-8-credit-check-rows'

// ─── Helpers ──────────────────────────────────────────────────────────────────

function generateDebitId(): string {
  return `dchk-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function generateCreditId(): string {
  return `cchk-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function safeParseDebitRows(jsonStr: string | null | undefined): StoredDebitCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

function safeParseCreditRows(jsonStr: string | null | undefined): StoredCreditCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** 借方行公式计算 */
function computeDebitRow(stored: StoredDebitCheckRow): DebitCheckRow {
  const calculatedInterest = calcInterest365(stored.faceValue, stored.rate, stored.accruedDays)
  const variance = calculatedInterest - stored.amount

  return {
    ...stored,
    calculatedInterest,
    variance,
  }
}

/** 贷方行公式计算（逾期天数） */
function computeCreditRow(stored: StoredCreditCheckRow): CreditCheckRow {
  // 逾期天数：约定收款日期到现在（receiptDate作为约定日）
  const overdueDays = stored.isOnTimeRecovery === '否'
    ? calcOverdueDays(stored.voucherDate)
    : 0

  return {
    ...stored,
    overdueDays,
  }
}

function createEmptyDebitRow(seq: number): StoredDebitCheckRow {
  return {
    id: generateDebitId(),
    seq,
    summary: '',
    counterAccount: '',
    amount: 0,
    voucherDate: '',
    voucherNo: '',
    investTarget: '',
    faceValue: 0,
    rate: 0,
    accruedDays: 0,
    auditConclusion: '',
    remark: '',
  }
}

function createEmptyCreditRow(seq: number): StoredCreditCheckRow {
  return {
    id: generateCreditId(),
    seq,
    summary: '',
    counterAccount: '',
    amount: 0,
    voucherDate: '',
    voucherNo: '',
    receivingBank: '',
    receiptDate: '',
    isOnTimeRecovery: '',
    auditConclusion: '',
    remark: '',
  }
}

// ─── Composable ───────────────────────────────────────────────────────────────

export interface UseG2VoucherCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

export function useG2VoucherCheck(options: UseG2VoucherCheckOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ═══════════════════════════════════════════════════════════════════════════
  // 借方检查区
  // ═══════════════════════════════════════════════════════════════════════════

  const storedDebitRows = computed<StoredDebitCheckRow[]>(() => {
    const resp = allResponses.value.get(DEBIT_STORAGE_KEY)
    return safeParseDebitRows(resp?.remark)
  })

  /** 借方数据行（公式自动计算） */
  const debitRows: ComputedRef<DebitCheckRow[]> = computed(() =>
    storedDebitRows.value.map((s) => computeDebitRow(s)),
  )

  /** 借方小计 */
  const debitTotals: ComputedRef<DebitCheckTotals> = computed(() => {
    const rows = debitRows.value
    return {
      amount: rows.reduce((sum, r) => sum + r.amount, 0),
      calculatedInterest: rows.reduce((sum, r) => sum + r.calculatedInterest, 0),
      variance: rows.reduce((sum, r) => sum + r.variance, 0),
    }
  })

  function addDebitRow(): void {
    if (readonly.value) return
    const current = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    const nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyDebitRow(nextSeq))
    persistDebitRows(current)
  }

  function removeDebitRow(id: string): void {
    if (readonly.value) return
    const current = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistDebitRows(filtered)
  }

  function updateDebitCell(rowId: string, field: keyof StoredDebitCheckRow, value: string | number): void {
    if (readonly.value) return
    const current = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const numericFields = ['amount', 'faceValue', 'rate', 'accruedDays'] as const
    if ((numericFields as readonly string[]).includes(field)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }

    persistDebitRows(current)
  }

  /** 批量填入借方行（抽凭引擎样本） */
  function insertDebitSamples(samples: Partial<StoredDebitCheckRow>[]): void {
    if (readonly.value) return
    const current = safeParseDebitRows(allResponses.value.get(DEBIT_STORAGE_KEY)?.remark)
    let nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    for (const sample of samples) {
      const row: StoredDebitCheckRow = {
        ...createEmptyDebitRow(nextSeq),
        ...sample,
        id: generateDebitId(),
        seq: nextSeq,
      }
      current.push(row)
      nextSeq++
    }
    persistDebitRows(current)
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 贷方检查区
  // ═══════════════════════════════════════════════════════════════════════════

  const storedCreditRows = computed<StoredCreditCheckRow[]>(() => {
    const resp = allResponses.value.get(CREDIT_STORAGE_KEY)
    return safeParseCreditRows(resp?.remark)
  })

  /** 贷方数据行（公式自动计算） */
  const creditRows: ComputedRef<CreditCheckRow[]> = computed(() =>
    storedCreditRows.value.map((s) => computeCreditRow(s)),
  )

  /** 贷方小计 */
  const creditTotals: ComputedRef<CreditCheckTotals> = computed(() => {
    const rows = creditRows.value
    return {
      amount: rows.reduce((sum, r) => sum + r.amount, 0),
      overdueCount: rows.filter((r) => r.overdueDays > 0).length,
    }
  })

  function addCreditRow(): void {
    if (readonly.value) return
    const current = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    const nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    current.push(createEmptyCreditRow(nextSeq))
    persistCreditRows(current)
  }

  function removeCreditRow(id: string): void {
    if (readonly.value) return
    const current = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    const filtered = current.filter((r) => r.id !== id)
    filtered.forEach((r, i) => { r.seq = i + 1 })
    persistCreditRows(filtered)
  }

  function updateCreditCell(rowId: string, field: keyof StoredCreditCheckRow, value: string | number): void {
    if (readonly.value) return
    const current = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    const idx = current.findIndex((r) => r.id === rowId)
    if (idx === -1) return

    const numericFields = ['amount'] as const
    if ((numericFields as readonly string[]).includes(field)) {
      ;(current[idx] as any)[field] = typeof value === 'number' ? value : parseNum(value)
    } else {
      ;(current[idx] as any)[field] = value
    }

    persistCreditRows(current)
  }

  /** 批量填入贷方行（抽凭引擎样本） */
  function insertCreditSamples(samples: Partial<StoredCreditCheckRow>[]): void {
    if (readonly.value) return
    const current = safeParseCreditRows(allResponses.value.get(CREDIT_STORAGE_KEY)?.remark)
    let nextSeq = current.length > 0 ? Math.max(...current.map((r) => r.seq)) + 1 : 1
    for (const sample of samples) {
      const row: StoredCreditCheckRow = {
        ...createEmptyCreditRow(nextSeq),
        ...sample,
        id: generateCreditId(),
        seq: nextSeq,
      }
      current.push(row)
      nextSeq++
    }
    persistCreditRows(current)
  }

  // ═══════════════════════════════════════════════════════════════════════════
  // 持久化（共用 debounce）
  // ═══════════════════════════════════════════════════════════════════════════

  function persistDebitRows(rows: StoredDebitCheckRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(DEBIT_STORAGE_KEY, {
      item_id: DEBIT_STORAGE_KEY,
      conclusion: null,
      remark: json,
    })
    debounceSave()
  }

  function persistCreditRows(rows: StoredCreditCheckRow[]): void {
    const json = JSON.stringify(rows)
    allResponses.value.set(CREDIT_STORAGE_KEY, {
      item_id: CREDIT_STORAGE_KEY,
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
      const items = [
        allResponses.value.get(DEBIT_STORAGE_KEY),
        allResponses.value.get(CREDIT_STORAGE_KEY),
      ].filter(Boolean)
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
    // 借方检查区
    debitRows,
    debitTotals,
    addDebitRow,
    removeDebitRow,
    updateDebitCell,
    insertDebitSamples,
    // 贷方检查区
    creditRows,
    creditTotals,
    addCreditRow,
    removeCreditRow,
    updateCreditCell,
    insertCreditSamples,
  }
}

export default useG2VoucherCheck
