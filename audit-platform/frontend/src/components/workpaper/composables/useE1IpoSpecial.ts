/**
 * useE1IpoSpecial — E1-23/E1-26~32 IPO组通用CRUD composable
 *
 * Spec: .kiro/specs/e1-monetary-fund-refactor/
 * Task: 16.1
 *
 * 职责：
 * - sheetCode prop 驱动列定义 (COLUMN_CONFIG[sheetCode])
 * - 通用动态行 CRUD：根据配置的 columns 渲染、序列化、反序列化
 * - Column types: text, number, date, boolean, computed
 * - sheetCodes: 'E1-23'|'E1-26'|'E1-27'|'E1-28'|'E1-29'|'E1-30'|'E1-31'|'E1-32'
 * - 适用性开关：reads 'E1-ipo-applicable' (Y/N) from allResponses
 * - 序列化/反序列化 → checklist_responses (item_id: 'E1-ipo-{sheetCode}-rows')
 * - Debounce 2s 自动保存
 *
 * Requirements: 11.1-11.9
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import type { UseE1BaseOptions, ChecklistItem } from './useE1Adjudication'
import { parseNum } from './useE1FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export type IpoSheetCode = 'E1-23' | 'E1-26' | 'E1-27' | 'E1-28' | 'E1-29' | 'E1-30' | 'E1-31' | 'E1-32'

export type ColumnType = 'text' | 'number' | 'date' | 'boolean' | 'computed'

export interface ColumnDef {
  key: string
  label: string
  type: ColumnType
  width?: number
  computeFn?: (row: Record<string, unknown>) => unknown
}

export type IpoRow = Record<string, unknown> & { id: string }

// ─── Column Configurations ───────────────────────────────────────────────────

export const COLUMN_CONFIG: Record<IpoSheetCode, ColumnDef[]> = {
  // E1-23 货币资金收支检查情况表（源模板：凭证级收支明细，借方/贷方检查合并为方向列）
  'E1-23': [
    { key: 'direction', label: '方向(收/支)', type: 'text', width: 100 },
    { key: 'accountName', label: '所属科目', type: 'text', width: 110 },
    { key: 'date', label: '日期', type: 'date', width: 140 },
    { key: 'voucherNo', label: '凭证编号', type: 'text', width: 120 },
    { key: 'content', label: '业务内容', type: 'text', width: 180 },
    { key: 'counterAccount', label: '对方科目', type: 'text', width: 130 },
    { key: 'counterSubAccount', label: '对方明细科目', type: 'text', width: 140 },
    { key: 'amount', label: '金额', type: 'number', width: 130 },
    { key: 'bankReceiptDate', label: '银行回单日期', type: 'date', width: 140 },
    { key: 'bankReceiptParty', label: '银行回单对方(收/付款方)', type: 'text', width: 170 },
    { key: 'bankReceiptAmount', label: '银行回单金额', type: 'number', width: 130 },
    { key: 'otherDoc', label: '其他支持性文件', type: 'text', width: 150 },
    { key: 'indexNo', label: '索引号', type: 'text', width: 100 },
    { key: 'isAbnormal', label: '是否异常', type: 'boolean', width: 90 },
    { key: 'issue', label: '异常说明/备注', type: 'text', width: 180 },
  ],
  'E1-26': [
    { key: 'month', label: '月份', type: 'number' },
    { key: 'cashSalesCurrent', label: '现金销售收款-本期', type: 'number' },
    { key: 'cashSalesPrior', label: '现金销售收款-上期', type: 'number' },
    { key: 'cashPurchaseCurrent', label: '现金采购付款-本期', type: 'number' },
    { key: 'cashPurchasePrior', label: '现金采购付款-上期', type: 'number' },
    { key: 'changeRate', label: '变动率', type: 'computed', computeFn: (r) => {
      const current = parseNum(r.cashSalesCurrent) + parseNum(r.cashPurchaseCurrent)
      const prior = parseNum(r.cashSalesPrior) + parseNum(r.cashPurchasePrior)
      if (prior === 0) return current === 0 ? 0 : 1
      return (current - prior) / prior
    }},
  ],
  'E1-27': [
    { key: 'date', label: '日期', type: 'date' },
    { key: 'voucherNo', label: '凭证编号', type: 'text' },
    { key: 'content', label: '业务内容', type: 'text' },
    { key: 'debitAmount', label: '借方金额', type: 'number' },
    { key: 'creditAmount', label: '贷方金额', type: 'number' },
    { key: 'receiptDate', label: '收付款凭单日期', type: 'date' },
    { key: 'originalDocDate', label: '其他原始凭单日期', type: 'date' },
    { key: 'isCrossover', label: '是否跨期', type: 'boolean' },
  ],
  'E1-28': [
    { key: 'accountCode', label: '所属科目', type: 'text' },
    { key: 'date', label: '日期', type: 'date' },
    { key: 'voucherNo', label: '凭证编号', type: 'text' },
    { key: 'content', label: '业务内容', type: 'text' },
    { key: 'counterAccount', label: '对方科目', type: 'text' },
    { key: 'amount', label: '金额', type: 'number' },
    { key: 'receipt', label: '收据/收款单', type: 'text' },
    { key: 'contract', label: '合同', type: 'text' },
    { key: 'acceptance', label: '签收/验收单', type: 'text' },
    { key: 'indexNo', label: '索引号', type: 'text' },
    { key: 'isAbnormal', label: '是否异常', type: 'boolean' },
  ],
  'E1-29': [
    { key: 'bank', label: '开户银行', type: 'text' },
    { key: 'accountNo', label: '账号', type: 'text' },
    { key: 'accountType', label: '账户性质', type: 'text' },
    { key: 'location', label: '账户开户地', type: 'text' },
    { key: 'hasBusiness', label: '是否有经济业务', type: 'boolean' },
    { key: 'remoteReason', label: '异地开户原因', type: 'text' },
  ],
  'E1-30': [
    { key: 'date', label: '日期', type: 'date' },
    { key: 'demandDeposit', label: '活期存款', type: 'number' },
    { key: 'sevenDayNotice', label: '七天通知存款', type: 'number' },
    { key: 'largeCd', label: '大额存单', type: 'number' },
    { key: 'dailyRate', label: '日利率(/360)', type: 'number' },
    { key: 'calculatedInterest', label: '测算利息', type: 'computed', computeFn: (r) => {
      const total = parseNum(r.demandDeposit) + parseNum(r.sevenDayNotice) + parseNum(r.largeCd)
      return total * parseNum(r.dailyRate)
    }},
  ],
  'E1-31': [
    { key: 'month', label: '月份', type: 'number' },
    { key: 'stmtIncome', label: '对账单收入', type: 'number' },
    { key: 'stmtExpense', label: '对账单支出', type: 'number' },
    { key: 'stmtBalance', label: '对账单余额', type: 'number' },
    { key: 'journalDebit', label: '日记账借方', type: 'number' },
    { key: 'journalCredit', label: '日记账贷方', type: 'number' },
    { key: 'journalBalance', label: '日记账余额', type: 'number' },
    { key: 'diffAmount', label: '差额', type: 'computed', computeFn: (r) => {
      return parseNum(r.stmtBalance) - parseNum(r.journalBalance)
    }},
    { key: 'diffRate', label: '差异率', type: 'computed', computeFn: (r) => {
      const journal = parseNum(r.journalBalance)
      const stmt = parseNum(r.stmtBalance)
      if (journal === 0) return stmt === 0 ? 0 : 1
      return (stmt - journal) / journal
    }},
  ],
  'E1-32': [
    { key: 'name', label: '姓名', type: 'text' },
    { key: 'position', label: '职位', type: 'text' },
    { key: 'accountNo', label: '账号', type: 'text' },
    { key: 'bank', label: '开户行', type: 'text' },
    { key: 'transDate', label: '交易日期', type: 'date' },
    { key: 'amount', label: '收支金额', type: 'number' },
    { key: 'counterpartyName', label: '对方户名', type: 'text' },
    { key: 'transBackground', label: '交易背景', type: 'text' },
    { key: 'isRelatedParty', label: '是否关联方', type: 'boolean' },
    { key: 'abnormalFlag', label: '异常标记', type: 'text' },
  ],
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(sheetCode: string): string {
  const prefix = sheetCode.replace('-', '').toLowerCase()
  if (typeof crypto !== 'undefined' && crypto.randomUUID) {
    return `${prefix}-${crypto.randomUUID()}`
  }
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 8)}`
}

function getStorageKey(sheetCode: string): string {
  return `E1-ipo-${sheetCode}-rows`
}

function createEmptyRow(sheetCode: IpoSheetCode): IpoRow {
  const columns = COLUMN_CONFIG[sheetCode]
  const row: IpoRow = { id: generateRowId(sheetCode) }
  for (const col of columns) {
    if (col.type === 'computed') continue
    switch (col.type) {
      case 'number': row[col.key] = 0; break
      case 'boolean': row[col.key] = false; break
      default: row[col.key] = ''; break
    }
  }
  return row
}

function recalcRow(row: IpoRow, columns: ColumnDef[]): IpoRow {
  const result = { ...row }
  for (const col of columns) {
    if (col.type === 'computed' && col.computeFn) {
      result[col.key] = col.computeFn(result)
    }
  }
  return result
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useE1IpoSpecial(options: UseE1BaseOptions & { sheetCode: IpoSheetCode }) {
  const { allResponses, saveImmediate, isReadonly, sheetCode } = options
  const storageKey = getStorageKey(sheetCode)
  const columns = COLUMN_CONFIG[sheetCode]

  // ─── State ─────────────────────────────────────────────────────────────

  const rows = ref<IpoRow[]>([createEmptyRow(sheetCode)])
  const isLoading = ref(false)

  // ─── Applicability Switch ──────────────────────────────────────────────

  /** IPO组适用性开关 */
  const isApplicable: ComputedRef<boolean> = computed(() => {
    const resp = allResponses.value.get('E1-ipo-applicable')
    return resp?.conclusion === 'Y'
  })

  // ─── Deserialization ───────────────────────────────────────────────────

  function loadFromResponses(): void {
    const response = allResponses.value.get(storageKey)
    const raw = response?.remark
    if (!raw) {
      rows.value = [createEmptyRow(sheetCode)]
      return
    }
    try {
      const parsed = JSON.parse(raw)
      if (!Array.isArray(parsed) || parsed.length === 0) {
        rows.value = [createEmptyRow(sheetCode)]
        return
      }
      rows.value = parsed.map((r: Record<string, unknown>) => {
        const row: IpoRow = { id: String(r.id || generateRowId(sheetCode)) }
        for (const col of columns) {
          if (col.type === 'computed') continue
          switch (col.type) {
            case 'number': row[col.key] = parseNum(r[col.key]); break
            case 'boolean': row[col.key] = r[col.key] === true || r[col.key] === 'true'; break
            default: row[col.key] = String(r[col.key] ?? ''); break
          }
        }
        return recalcRow(row, columns)
      })
    } catch {
      console.warn(`[useE1IpoSpecial:${sheetCode}] JSON parse failed, fallback to empty`)
      rows.value = [createEmptyRow(sheetCode)]
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
    const userFields = columns.filter(c => c.type !== 'computed').map(c => c.key)
    const data = rows.value.map(row => {
      const obj: Record<string, unknown> = { id: row.id }
      for (const field of userFields) {
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
    rows.value = [...rows.value, createEmptyRow(sheetCode)]
    scheduleSave()
  }

  function removeRow(rowId: string): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return
    rows.value = rows.value.filter(r => r.id !== rowId)
    scheduleSave()
  }

  function updateCell(rowId: string, field: string, value: unknown): void {
    if (isReadonly.value) return
    const idx = rows.value.findIndex(r => r.id === rowId)
    if (idx === -1) return

    const row = { ...rows.value[idx] }
    const colDef = columns.find(c => c.key === field)
    if (!colDef || colDef.type === 'computed') return

    switch (colDef.type) {
      case 'number': row[field] = parseNum(value); break
      case 'boolean': row[field] = value === true || value === 'true'; break
      default: row[field] = String(value ?? ''); break
    }

    const recalculated = recalcRow(row, columns)
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
    columns,
    isApplicable,
    isLoading,
    addRow,
    removeRow,
    updateCell,
    hydrate,
  }
}
