/**
 * useE1Reconciliation — E1-6 银行存款余额调节表 composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 7.1
 *
 * 职责：
 * - 按银行账户分组的动态调节行
 * - 企业侧调节：调节后企业余额 = 账面余额 + 企收银未收 - 企付银未付
 * - 银行侧调节：调节后银行余额 = 对账单余额 + 银收企未收 - 银付企未付
 * - 差异 = 调节后企业余额 - 调节后银行余额
 * - 差异≠0 时红色高亮 + 强制填写差异原因
 * - 序列化/反序列化 → checklist_responses (item_id: 'E1-reconciliation-rows')
 * - Debounce 2s 自动保存
 *
 * Requirements: 6.1-6.5
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum, calcReconciled, sumField } from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ReconciliationRow {
  id: string
  bankName: string           // 开户银行
  accountNo: string          // 银行账号
  bookBalance: number        // 企业账面余额
  bankReceived: number       // 企业已收银行未收(企收银未收)
  bankPaid: number           // 企业已付银行未付(企付银未付)
  reconciledBook: number     // 调节后企业余额 (readonly: bookBalance + bankReceived - bankPaid)
  statementBalance: number   // 银行对账单余额
  companyReceived: number    // 银行已收企业未收(银收企未收)
  companyPaid: number        // 银行已付企业未付(银付企未付)
  reconciledStatement: number // 调节后银行余额 (readonly: statementBalance + companyReceived - companyPaid)
  diff: number               // 差异 (readonly: reconciledBook - reconciledStatement)
  diffReason: string         // 差异原因 (强制 when diff≠0)
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'E1-reconciliation-rows'

/** 用户输入字段（序列化保留，计算字段重算） */
const USER_FIELDS: Array<keyof ReconciliationRow> = [
  'id', 'bankName', 'accountNo', 'bookBalance', 'bankReceived', 'bankPaid',
  'statementBalance', 'companyReceived', 'companyPaid', 'diffReason',
]

/** 浮点容差 */
const TOLERANCE = 0.005

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `recon-${crypto.randomUUID()}`
  }
  return `recon-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

/** 重算行内公式字段 */
function recalcRow(row: ReconciliationRow): ReconciliationRow {
  const reconciledBook = calcReconciled(row.bookBalance, row.bankReceived, row.bankPaid)
  const reconciledStatement = calcReconciled(row.statementBalance, row.companyReceived, row.companyPaid)
  const diff = reconciledBook - reconciledStatement
  return { ...row, reconciledBook, reconciledStatement, diff }
}

/** 创建空白行 */
function createEmptyRow(): ReconciliationRow {
  return recalcRow({
    id: generateRowId(),
    bankName: '',
    accountNo: '',
    bookBalance: 0,
    bankReceived: 0,
    bankPaid: 0,
    reconciledBook: 0,
    statementBalance: 0,
    companyReceived: 0,
    companyPaid: 0,
    reconciledStatement: 0,
    diff: 0,
    diffReason: '',
  })
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1Reconciliation(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<ReconciliationRow[]>([createEmptyRow()])
  const isLoading = ref(false)

  // ─── Deserialization ───────────────────────────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(STORAGE_KEY)
    const raw = response?.remark
    if (!raw) {
      rows.value = [createEmptyRow()]
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = [createEmptyRow()]
        return
      }
      rows.value = parsed.map((r: Record<string, unknown>) => recalcRow({
        id: String(r.id || generateRowId()),
        bankName: String(r.bankName || ''),
        accountNo: String(r.accountNo || ''),
        bookBalance: parseNum(r.bookBalance),
        bankReceived: parseNum(r.bankReceived),
        bankPaid: parseNum(r.bankPaid),
        reconciledBook: 0,
        statementBalance: parseNum(r.statementBalance),
        companyReceived: parseNum(r.companyReceived),
        companyPaid: parseNum(r.companyPaid),
        reconciledStatement: 0,
        diff: 0,
        diffReason: String(r.diffReason || ''),
      }))
    } catch {
      console.warn('[useE1Reconciliation] JSON parse failed, fallback to empty')
      rows.value = [createEmptyRow()]
    }
  }

  loadFromResponses()

  watch(
    () => allResponses.value.get(STORAGE_KEY)?.remark,
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
      { item_id: STORAGE_KEY, conclusion: null, remark: serialized },
    ]
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: serialized })
    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Highlight / Validation Helpers ────────────────────────────────────

  /** 是否有差异（需强制填写原因） */
  function hasDiff(row: ReconciliationRow): boolean {
    return Math.abs(row.diff) > TOLERANCE
  }

  /** 差异原因是否缺失 */
  function isMissingReason(row: ReconciliationRow): boolean {
    return hasDiff(row) && !row.diffReason.trim()
  }

  // ─── Row CRUD ──────────────────────────────────────────────────────────

  function addRow(): void {
    if (isReadonly.value) return
    rows.value = [...rows.value, createEmptyRow()]
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
    const numericFields: Array<keyof ReconciliationRow> = [
      'bookBalance', 'bankReceived', 'bankPaid',
      'statementBalance', 'companyReceived', 'companyPaid',
    ]
    if (numericFields.includes(field as keyof ReconciliationRow)) {
      ;(row as any)[field] = parseNum(value)
    } else {
      ;(row as any)[field] = String(value)
    }

    const recalculated = recalcRow(row)
    const newRows = [...rows.value]
    newRows[idx] = recalculated
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
    isLoading,
    hasDiff,
    isMissingReason,
    addRow,
    removeRow,
    updateCell,
    hydrate,
  }
}
