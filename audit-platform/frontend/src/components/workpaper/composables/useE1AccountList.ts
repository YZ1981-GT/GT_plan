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

// ─── Types ───────────────────────────────────────────────────────────────────

export type CheckResultType = '一致' | '不一致' | ''
export type YesNoType = 'Y' | 'N' | ''

export interface AccountListRow {
  id: string
  bank: string
  accountNo: string
  accountType: string
  openDate: string
  accountStatus: string
  closeDate: string
  openReason: string
  closeReason: string
  companyInfoConsistent: CheckResultType
  inconsistencyReason: string
  restrictionStatus: string
  // 旧 JSON 字段继续读写，确保历史数据及导入导出契约兼容。
  openPurpose: string
  isNewThisPeriod: YesNoType
  isClosedThisPeriod: YesNoType
  hasBookRecord: YesNoType
  checkResult: CheckResultType
  reason: string
}

export interface AccountCommitSnapshotRow {
  bank: string
  accountNo: string
  accountType: string
  openDate: string
  closeDate: string
  accountStatus: string
  restrictionStatus: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

export const E1_ACCOUNT_LIST_STORAGE_KEY = 'E1-account-list-rows'
export const E1_ACCOUNT_COMMIT_SNAPSHOT_KEY = 'E1-account-commit-snapshot'

const USER_FIELDS: Array<keyof AccountListRow> = [
  'id', 'bank', 'accountNo', 'accountType', 'openDate', 'accountStatus',
  'closeDate', 'openReason', 'closeReason', 'companyInfoConsistent',
  'inconsistencyReason', 'restrictionStatus', 'openPurpose',
  'isNewThisPeriod', 'isClosedThisPeriod', 'hasBookRecord', 'checkResult', 'reason',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `acct-${crypto.randomUUID()}`
  }
  return `acct-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function createEmptyRow(bank = ''): AccountListRow {
  return {
    id: generateRowId(),
    bank,
    accountNo: '',
    accountType: '',
    openDate: '',
    accountStatus: '正常',
    closeDate: '',
    openReason: '',
    closeReason: '',
    companyInfoConsistent: '',
    inconsistencyReason: '',
    restrictionStatus: '无',
    openPurpose: '',
    isNewThisPeriod: '',
    isClosedThisPeriod: '',
    hasBookRecord: '',
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
    const response = allResponses.value.get(E1_ACCOUNT_LIST_STORAGE_KEY)
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
        accountStatus: String(r.accountStatus || (r.isClosedThisPeriod === 'Y' ? '已注销' : '正常')),
        closeDate: String(r.closeDate || ''),
        openReason: String(r.openReason || r.openPurpose || ''),
        closeReason: String(r.closeReason || ''),
        companyInfoConsistent: (['一致', '不一致'].includes(String(r.companyInfoConsistent)) ? String(r.companyInfoConsistent) : '') as CheckResultType,
        inconsistencyReason: String(r.inconsistencyReason || ''),
        restrictionStatus: String(r.restrictionStatus || '无'),
        openPurpose: String(r.openPurpose || ''),
        isNewThisPeriod: (['Y', 'N'].includes(String(r.isNewThisPeriod)) ? String(r.isNewThisPeriod) : '') as YesNoType,
        isClosedThisPeriod: (['Y', 'N'].includes(String(r.isClosedThisPeriod)) ? String(r.isClosedThisPeriod) : '') as YesNoType,
        hasBookRecord: (['Y', 'N'].includes(String(r.hasBookRecord)) ? String(r.hasBookRecord) : '') as YesNoType,
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
    () => allResponses.value.get(E1_ACCOUNT_LIST_STORAGE_KEY)?.remark,
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
      { item_id: E1_ACCOUNT_LIST_STORAGE_KEY, conclusion: null, remark: serialized },
    ]
    allResponses.value.set(E1_ACCOUNT_LIST_STORAGE_KEY, { item_id: E1_ACCOUNT_LIST_STORAGE_KEY, conclusion: null, remark: serialized })
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

  /** 疑似账外账户：清单有该账户但账面无记录 → 完整性认定风险 */
  function isSuspectedOffBook(row: AccountListRow): boolean {
    return row.hasBookRecord === 'N'
  }

  /** 完整性统计（供审计说明/结论参考） */
  const summary = computed(() => {
    const list = rows.value.filter(r => r.bank.trim() || r.accountNo.trim())
    return {
      total: list.length,
      newCount: list.filter(r => r.isNewThisPeriod === 'Y').length,
      closedCount: list.filter(r => r.isClosedThisPeriod === 'Y').length,
      inconsistentCount: list.filter(isInconsistent).length,
      offBookCount: list.filter(isSuspectedOffBook).length,
      restrictedCount: list.filter(r => r.restrictionStatus.trim() && r.restrictionStatus !== '无').length,
      closedStatusCount: list.filter(r => r.accountStatus === '已注销').length,
      companyInconsistentCount: list.filter(r => r.companyInfoConsistent === '不一致').length,
    }
  })

  // ─── Row CRUD ──────────────────────────────────────────────────────────

  function addRow(bank = ''): AccountListRow | null {
    if (isReadonly.value) return null
    const row = createEmptyRow(bank)
    rows.value = [...rows.value, row]
    scheduleSave()
    return row
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    rows.value = rows.value.filter(r => r.id !== rowId)
    scheduleSave()
  }

  function updateRow(rowId: string, patch: Partial<AccountListRow>): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    const current = rows.value[idx]
    const next = { ...current, ...patch }
    // 新旧开户原因字段互补但不删除，保证历史 JSON 可继续被旧导入导出消费。
    if (!next.openReason && next.openPurpose) next.openReason = next.openPurpose
    if (!next.openPurpose && next.openReason) next.openPurpose = next.openReason
    const newRows = [...rows.value]
    newRows[idx] = next
    rows.value = newRows
    scheduleSave()
  }

  function updateCell(rowId: string, field: string, value: string): void {
    updateRow(rowId, { [field]: value } as Partial<AccountListRow>)
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
    summary,
    isInconsistent,
    isMissingReason,
    isSuspectedOffBook,
    addRow,
    removeRow,
    updateCell,
    updateRow,
    hydrate,
  }
}

