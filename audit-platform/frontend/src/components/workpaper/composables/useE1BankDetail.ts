/**
 * useE1BankDetail — E1-3 银行存款及其他货币资金明细表 composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 5.1
 *
 * 职责：
 * - 双variant切换：'rmb'（仅人民币）/ 'multi'（人民币及外币）
 * - 三分组（存款本金principal / 存放财务公司finance / 其他货币资金other）
 * - 动态行管理（每组内可增删）
 * - 公式字段自动计算：
 *   - 期末余额 = 期初 + 增加 - 减少 (calcCashBalance)
 *   - 审定数 = 期末余额 + 账项调整 (calcAudited)
 *   - 账面与对账单差异 = 审定数 - 对账单余额
 *   - 函证差异 = 审定数 - 回函确认金额
 *   - 外币版折算人民币 = 原币 × 汇率 (calcFxConvert)
 * - 函证列：回函确认金额/询证函索引号(从E0 allResponses取数)
 * - 分组合计写入 allResponses 供 E1-1 审定表取数：
 *   - 'E1-bank-detail-{group}-total-unaudited' (期末未审)
 *   - 'E1-bank-detail-{group}-opening-unaudited' (期初未审)
 * - 序列化/反序列化 → checklist_responses (item_id: 'E1-bank-detail-rows')
 * - Debounce 2s 自动保存
 *
 * Requirements: 2.1-2.6, 4.1-4.7
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import {
  parseNum,
  calcCashBalance,
  calcFxConvert,
  sumField,
} from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type BankDetailVariant = 'rmb' | 'multi'
export type BankDetailGroup = 'principal' | 'finance' | 'other'

export interface BankDetailRow {
  id: string
  group: BankDetailGroup
  bankName: string             // 开户银行
  totalLedgerBank: string      // 总账银行名称
  accountNo: string            // 银行账号
  accountType: string          // 账户性质/主要用途
  opening: number              // 期初余额
  increase: number             // 本期增加
  decrease: number             // 本期减少
  ending: number               // 期末余额 (readonly: opening+increase-decrease)
  adjustment: number           // 账项调整
  audited: number              // 期末审定数 (readonly: ending+adjustment)
  statementBalance: number     // 期末对账单余额
  accountStatementDiff: number // 账面与对账单差异 (readonly: audited-statementBalance)
  confirmAmount: number        // 回函确认金额 (from E0)
  confirmIndexNo: string       // 银行询证函索引号
  confirmDiff: number          // 函证差异 (readonly: audited-confirmAmount)
  restrictedAmount: number     // 受限金额
  restrictedReason: string     // 受限原因
  note: string                 // 备注
  // Multi variant (外币版)
  fxCurrency: string           // 原币币种
  fxRate: number               // 期末汇率
  openingFc: number            // 期初-原币
  increaseFc: number           // 增加-原币
  decreaseFc: number           // 减少-原币
  endingFc: number             // 期末-原币 (readonly)
  adjustmentFc: number         // 调整-原币
  auditedFc: number            // 审定-原币 (readonly)
}

export interface BankDetailGroupTotal {
  group: BankDetailGroup
  groupName: string
  opening: number
  increase: number
  decrease: number
  ending: number
  adjustment: number
  audited: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

const STORAGE_KEY = 'E1-bank-detail-rows'
const VARIANT_KEY = 'E1-bank-variant'

const GROUP_NAMES: Record<BankDetailGroup, string> = {
  principal: '（一）存款本金',
  finance: '其他金融机构（存放财务公司款项）',
  other: '其他货币资金',
}

/** Cross-sheet key map for E1-1 consumption */
const CROSS_SHEET_KEYS: Record<BankDetailGroup, { opening: string; ending: string }> = {
  principal: {
    opening: 'E1-bank-detail-principal-opening-unaudited',
    ending: 'E1-bank-detail-principal-total-unaudited',
  },
  finance: {
    opening: 'E1-bank-detail-finance-opening-unaudited',
    ending: 'E1-bank-detail-finance-total-unaudited',
  },
  other: {
    opening: 'E1-bank-detail-other-opening-unaudited',
    ending: 'E1-bank-detail-other-total-unaudited',
  },
}

/** User-input fields to serialize (computed fields excluded) */
const USER_FIELDS: Array<keyof BankDetailRow> = [
  'id', 'group', 'bankName', 'totalLedgerBank', 'accountNo', 'accountType',
  'opening', 'increase', 'decrease', 'adjustment',
  'statementBalance', 'confirmAmount', 'confirmIndexNo',
  'restrictedAmount', 'restrictedReason', 'note',
  'fxCurrency', 'fxRate', 'openingFc', 'increaseFc', 'decreaseFc', 'adjustmentFc',
]

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(group: BankDetailGroup): string {
  const ts = Date.now()
  const rand = Math.random().toString(36).slice(2, 8)
  return `bank-${group}-${ts}-${rand}`
}

/** Recalculate all computed fields for a row */
function recalcRow(row: BankDetailRow, variant: BankDetailVariant): BankDetailRow {
  if (variant === 'multi' && row.fxRate > 0) {
    // Multi variant: compute FC fields first, then convert to RMB
    const endingFc = calcCashBalance(row.openingFc, row.increaseFc, row.decreaseFc)
    const auditedFc = endingFc + row.adjustmentFc
    const opening = calcFxConvert(row.openingFc, row.fxRate)
    const increase = calcFxConvert(row.increaseFc, row.fxRate)
    const decrease = calcFxConvert(row.decreaseFc, row.fxRate)
    const ending = calcCashBalance(opening, increase, decrease)
    const adjustment = calcFxConvert(row.adjustmentFc, row.fxRate)
    const audited = ending + adjustment
    const accountStatementDiff = audited - row.statementBalance
    const confirmDiff = row.confirmAmount !== 0 ? audited - row.confirmAmount : 0
    return {
      ...row,
      opening, increase, decrease,
      ending, adjustment, audited,
      endingFc, auditedFc,
      accountStatementDiff, confirmDiff,
    }
  }
  // RMB variant or fxRate=0: direct calculation
  const ending = calcCashBalance(row.opening, row.increase, row.decrease)
  const audited = ending + row.adjustment
  const accountStatementDiff = audited - row.statementBalance
  const confirmDiff = row.confirmAmount !== 0 ? audited - row.confirmAmount : 0
  const endingFc = calcCashBalance(row.openingFc, row.increaseFc, row.decreaseFc)
  const auditedFc = endingFc + row.adjustmentFc
  return { ...row, ending, audited, accountStatementDiff, confirmDiff, endingFc, auditedFc }
}

function createEmptyRow(group: BankDetailGroup): BankDetailRow {
  return {
    id: generateRowId(group),
    group,
    bankName: '', totalLedgerBank: '', accountNo: '', accountType: '',
    opening: 0, increase: 0, decrease: 0, ending: 0,
    adjustment: 0, audited: 0,
    statementBalance: 0, accountStatementDiff: 0,
    confirmAmount: 0, confirmIndexNo: '', confirmDiff: 0,
    restrictedAmount: 0, restrictedReason: '', note: '',
    fxCurrency: '', fxRate: 1,
    openingFc: 0, increaseFc: 0, decreaseFc: 0, endingFc: 0,
    adjustmentFc: 0, auditedFc: 0,
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1BankDetail(options: UseE1BaseOptions & { variant: Ref<BankDetailVariant> }) {
  const { allResponses, saveImmediate, isReadonly, variant } = options

  // ─── State ───────────────────────────────────────────────────────────

  const rows = ref<BankDetailRow[]>([])
  const isLoading = ref(false)

  // ─── Deserialization ─────────────────────────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(STORAGE_KEY)
    const raw = response?.remark
    if (!raw) {
      rows.value = [
        createEmptyRow('principal'),
        createEmptyRow('finance'),
        createEmptyRow('other'),
      ]
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = [createEmptyRow('principal'), createEmptyRow('finance'), createEmptyRow('other')]
        return
      }
      rows.value = parsed.map((r: Record<string, unknown>) => {
        const group = (['principal', 'finance', 'other'].includes(String(r.group))
          ? String(r.group) : 'principal') as BankDetailGroup
        const base: BankDetailRow = {
          id: String(r.id || generateRowId(group)),
          group,
          bankName: String(r.bankName || ''),
          totalLedgerBank: String(r.totalLedgerBank || ''),
          accountNo: String(r.accountNo || ''),
          accountType: String(r.accountType || ''),
          opening: parseNum(r.opening),
          increase: parseNum(r.increase),
          decrease: parseNum(r.decrease),
          ending: 0,
          adjustment: parseNum(r.adjustment),
          audited: 0,
          statementBalance: parseNum(r.statementBalance),
          accountStatementDiff: 0,
          confirmAmount: parseNum(r.confirmAmount),
          confirmIndexNo: String(r.confirmIndexNo || ''),
          confirmDiff: 0,
          restrictedAmount: parseNum(r.restrictedAmount),
          restrictedReason: String(r.restrictedReason || ''),
          note: String(r.note || ''),
          fxCurrency: String(r.fxCurrency || ''),
          fxRate: parseNum(r.fxRate) || 1,
          openingFc: parseNum(r.openingFc),
          increaseFc: parseNum(r.increaseFc),
          decreaseFc: parseNum(r.decreaseFc),
          endingFc: 0,
          adjustmentFc: parseNum(r.adjustmentFc),
          auditedFc: 0,
        }
        return recalcRow(base, variant.value)
      })
    } catch {
      rows.value = [createEmptyRow('principal'), createEmptyRow('finance'), createEmptyRow('other')]
    }
  }

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

  // ─── Serialization ───────────────────────────────────────────────────

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

  // ─── Grouped Rows (computed) ─────────────────────────────────────────

  const groupedRows = computed(() => {
    const groups: Record<BankDetailGroup, BankDetailRow[]> = {
      principal: [], finance: [], other: [],
    }
    for (const row of rows.value) {
      if (groups[row.group]) groups[row.group].push(row)
    }
    return groups
  })

  // ─── Group Totals (computed) ─────────────────────────────────────────

  function calcGroupTotal(group: BankDetailGroup): BankDetailGroupTotal {
    const groupRows = groupedRows.value[group]
    const asRecords = groupRows as unknown as Array<Record<string, unknown>>
    return {
      group,
      groupName: GROUP_NAMES[group],
      opening: sumField(asRecords, 'opening'),
      increase: sumField(asRecords, 'increase'),
      decrease: sumField(asRecords, 'decrease'),
      ending: sumField(asRecords, 'ending'),
      adjustment: sumField(asRecords, 'adjustment'),
      audited: sumField(asRecords, 'audited'),
    }
  }

  const groupTotals: ComputedRef<Record<BankDetailGroup, BankDetailGroupTotal>> = computed(() => ({
    principal: calcGroupTotal('principal'),
    finance: calcGroupTotal('finance'),
    other: calcGroupTotal('other'),
  }))

  // ─── Cross-Sheet Sync (write totals to allResponses) ─────────────────

  function syncCrossSheetTotals(): void {
    const totals = groupTotals.value
    const items: ChecklistItem[] = []

    for (const group of ['principal', 'finance', 'other'] as BankDetailGroup[]) {
      const keys = CROSS_SHEET_KEYS[group]
      const total = totals[group]

      const openingStr = String(total.opening)
      const endingStr = String(total.ending)

      allResponses.value.set(keys.opening, { item_id: keys.opening, conclusion: null, remark: openingStr })
      allResponses.value.set(keys.ending, { item_id: keys.ending, conclusion: null, remark: endingStr })
      items.push({ item_id: keys.opening, conclusion: null, remark: openingStr })
      items.push({ item_id: keys.ending, conclusion: null, remark: endingStr })
    }
  }

  watch(
    () => [groupTotals.value.principal.audited, groupTotals.value.finance.audited, groupTotals.value.other.audited],
    () => { syncCrossSheetTotals() },
    { immediate: true },
  )

  // ─── Debounce Save ───────────────────────────────────────────────────

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

    // Save rows
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: serialized })
    items.push({ item_id: STORAGE_KEY, conclusion: null, remark: serialized })

    // Save variant
    allResponses.value.set(VARIANT_KEY, { item_id: VARIANT_KEY, conclusion: null, remark: variant.value })
    items.push({ item_id: VARIANT_KEY, conclusion: null, remark: variant.value })

    // Cross-sheet totals
    const totals = groupTotals.value
    for (const group of ['principal', 'finance', 'other'] as BankDetailGroup[]) {
      const keys = CROSS_SHEET_KEYS[group]
      const total = totals[group]
      items.push({ item_id: keys.opening, conclusion: null, remark: String(total.opening) })
      items.push({ item_id: keys.ending, conclusion: null, remark: String(total.ending) })
    }

    saveImmediate(items).catch(() => { /* silent */ })
  }

  // ─── Row CRUD ────────────────────────────────────────────────────────

  function addRow(group: BankDetailGroup): void {
    if (isReadonly.value) return
    const newRow = recalcRow(createEmptyRow(group), variant.value)
    rows.value = [...rows.value, newRow]
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
    const stringFields: Array<keyof BankDetailRow> = [
      'bankName', 'totalLedgerBank', 'accountNo', 'accountType',
      'confirmIndexNo', 'restrictedReason', 'note', 'fxCurrency',
    ]
    if (stringFields.includes(field as keyof BankDetailRow)) {
      ;(row as any)[field] = String(value)
    } else {
      ;(row as any)[field] = parseNum(value)
    }

    const recalculated = recalcRow(row, variant.value)
    const newRows = [...rows.value]
    newRows[idx] = recalculated
    rows.value = newRows
    scheduleSave()
  }

  // ─── Confirmation Data from E0 ──────────────────────────────────────

  function getE0ConfirmAmount(accountNo: string): number {
    const key = `E0-bank-confirm-amount-${accountNo}`
    return parseNum(allResponses.value.get(key)?.remark)
  }

  function getE0ConfirmIndexNo(accountNo: string): string {
    const key = `E0-bank-confirm-index-${accountNo}`
    return allResponses.value.get(key)?.remark || ''
  }

  /** Check if a row has confirmation difference (for highlight) */
  function hasConfirmDiff(row: BankDetailRow): boolean {
    return row.confirmAmount !== 0 && Math.abs(row.confirmDiff) > 0.005
  }

  // ─── Hydration ───────────────────────────────────────────────────────

  function hydrate(): void {
    isLoading.value = true
    try {
      loadFromResponses()
    } finally {
      isLoading.value = false
    }
  }

  // ─── Cleanup ─────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (saveTimer) {
      clearTimeout(saveTimer)
      saveTimer = null
      persistToResponses()
    }
  })

  // ─── Return ──────────────────────────────────────────────────────────

  return {
    rows,
    groupedRows,
    groupTotals,
    isLoading,
    addRow,
    removeRow,
    updateCell,
    hasConfirmDiff,
    getE0ConfirmAmount,
    getE0ConfirmIndexNo,
    hydrate,
    GROUP_NAMES,
  }
}
