/**
 * useE1AccountList — E1-10 已开立银行账户清单核对表 composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 10.1
 *
 * 职责：
 * - 动态行管理（开户银行/账号/账户性质/开户日期/是否征信/是否审定表/核对结果/原因）
 * - 核对结果为"不一致"时红色高亮 + 强制填写原因
 * - 序列化/反序列化 → checklist_responses (item_id: 'E1-account-list-rows')
 * - Debounce 2s 自动保存
 *
 * Requirements: 8.1-8.2
 */
import { ref, computed, watch, onBeforeUnmount } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type CheckResultType = '一致' | '不一致' | ''
export type YesNoType = 'Y' | 'N' | ''

export interface AccountListRow {
  id: string
  bank: string               // 开户银行
  accountNo: string          // 银行账号
  accountType: string        // 账户性质
  openDate: string           // 开户日期
  inCreditReport: YesNoType  // 是否在征信报告中
  inAdjudication: YesNoType  // 是否在审定表中
  checkResult: CheckResultType  // 核对结果
  reason: string             // 不一致原因 (强制 when checkResult='不一致')
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'E1-account-list-rows'

const USER_FIELDS: Array<keyof AccountListRow> = [
  'id', 'bank', 'accountNo', 'accountType', 'openDate',
  'inCreditReport', 'inAdjudication', 'checkResult', 'reason',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `acct-${crypto.randomUUID()}`
  }
  return `acct-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createEmptyRow(): AccountListRow {
  return {
    id: generateRowId(),
    bank: '',
    accountNo: '',
    accountType: '',
    openDate: '',
    inCreditReport: '',
    inAdjudication: '',
    checkResult: '',
    reason: '',
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1AccountList(options: UseE1BaseOptions) {
  const { allResponses, saveImmediate, isReadonly } = options

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<AccountListRow[]>([createEmptyRow()])
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
      rows.value = parsed.map((r: Record<string, unknown>) => ({
        id: String(r.id || generateRowId()),
        bank: String(r.bank || ''),
        accountNo: String(r.accountNo || ''),
        accountType: String(r.accountType || ''),
        openDate: String(r.openDate || ''),
        inCreditReport: (['Y', 'N'].includes(String(r.inCreditReport)) ? String(r.inCreditReport) : '') as YesNoType,
        inAdjudication: (['Y', 'N'].includes(String(r.inAdjudication)) ? String(r.inAdjudication) : '') as YesNoType,
        checkResult: (['一致', '不一致'].includes(String(r.checkResult)) ? String(r.checkResult) : '') as CheckResultType,
        reason: String(r.reason || ''),
      }))
    } catch {
      console.warn('[useE1AccountList] JSON parse failed, fallback to empty')
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

  // ─── Validation Helpers ────────────────────────────────────────────────

  /** 核对结果不一致高亮 */
  function isInconsistent(row: AccountListRow): boolean {
    return row.checkResult === '不一致'
  }

  /** 不一致但未填原因 */
  function isMissingReason(row: AccountListRow): boolean {
    return isInconsistent(row) && !row.reason.trim()
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

  function updateCell(rowId: string, field: string, value: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    ;(row as any)[field] = value

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
    isLoading,
    isInconsistent,
    isMissingReason,
    addRow,
    removeRow,
    updateCell,
    hydrate,
  }
}
