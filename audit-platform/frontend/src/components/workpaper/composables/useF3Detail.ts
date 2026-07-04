/**
 * useF3Detail — F3-2 应付票据明细（25列 / 3区段Tab）
 * Spec: .kiro/specs/f3-notes-payable/ Task 5.1
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcCreditBalance,
  calcAuditedAmount,
  calcOverdueDays,
  calcTermDays,
  calcSubtotal,
} from './useF3FormulaEngine'
import type { ChecklistResponse } from './useF3FormData'
import type { UseF3BaseOptions } from './useF3Adjudication'

export interface F3NoteDetailRow {
  rowId: string
  seq: number
  issueDate: string
  dueDate: string
  noteType: string
  drawer: string
  payee: string
  faceValue: number
  currency: string
  purpose: string
  interestRate: number
  termDays: number
  isInterestBearing: string
  isOverdue: string
  overdueDays: number
  acceptBank: string
  noteStatus: string
  remark: string
  openingBalance: number
  increase: number
  decrease: number
  closingBalance: number
  aje: number
  rje: number
  adjustedBalance: number
  indexRef: string
}

export interface F3DetailColumn {
  prop: keyof F3NoteDetailRow | string
  label: string
  width?: number
  minWidth?: number
  formula?: string
  editable?: boolean
}

/** 基础信息区段 9 列 */
export const F3_DETAIL_BASIC_COLUMNS: F3DetailColumn[] = [
  { prop: 'seq', label: '序号', width: 60 },
  { prop: 'issueDate', label: '出票日期', minWidth: 110, editable: true },
  { prop: 'dueDate', label: '到期日', minWidth: 110, editable: true },
  { prop: 'noteType', label: '票据类型', minWidth: 100, editable: true },
  { prop: 'drawer', label: '出票人', minWidth: 120, editable: true },
  { prop: 'payee', label: '收票人', minWidth: 120, editable: true },
  { prop: 'faceValue', label: '面值', minWidth: 110, editable: true },
  { prop: 'currency', label: '币种', width: 80, editable: true },
  { prop: 'purpose', label: '用途', minWidth: 100, editable: true },
]

/** 票据详情区段 8 列 */
export const F3_DETAIL_INFO_COLUMNS: F3DetailColumn[] = [
  { prop: 'interestRate', label: '票面利率(%)', minWidth: 100, editable: true },
  { prop: 'termDays', label: '期限(天)', minWidth: 90, formula: '到期日-出票日', editable: false },
  { prop: 'isInterestBearing', label: '是否带息', minWidth: 90, editable: true },
  { prop: 'isOverdue', label: '是否逾期', minWidth: 90, editable: false },
  { prop: 'overdueDays', label: '逾期天数', minWidth: 90, formula: 'MAX(0,今天-到期日)', editable: false },
  { prop: 'acceptBank', label: '承兑银行', minWidth: 120, editable: true },
  { prop: 'noteStatus', label: '票据状态', minWidth: 100, editable: true },
  { prop: 'remark', label: '备注', minWidth: 120, editable: true },
]

/** 审定调整区段 8 列 */
export const F3_DETAIL_AUDIT_COLUMNS: F3DetailColumn[] = [
  { prop: 'openingBalance', label: '期初余额', minWidth: 110, editable: true },
  { prop: 'increase', label: '本期增加', minWidth: 110, editable: true },
  { prop: 'decrease', label: '本期减少', minWidth: 110, editable: true },
  { prop: 'closingBalance', label: '期末余额', minWidth: 110, formula: '期初+增加-减少', editable: false },
  { prop: 'aje', label: '账项调整', minWidth: 100, editable: true },
  { prop: 'rje', label: '重分类', minWidth: 100, editable: true },
  { prop: 'adjustedBalance', label: '审定余额', minWidth: 110, formula: '期末+AJE+RJE', editable: false },
  { prop: 'indexRef', label: '索引', minWidth: 90, editable: true },
]

interface StoredF3DetailRow {
  rowId: string
  seq: number
  issueDate: string
  dueDate: string
  noteType: string
  drawer: string
  payee: string
  faceValue: number
  currency: string
  purpose: string
  interestRate: number
  termDays: number
  isInterestBearing: string
  isOverdue: string
  acceptBank: string
  noteStatus: string
  remark: string
  openingBalance: number
  increase: number
  decrease: number
  aje: number
  rje: number
  indexRef: string
}

const STORAGE_KEY = 'F3-2-rows'

function generateRowId(): string {
  return `f3d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number): StoredF3DetailRow {
  return {
    rowId: generateRowId(),
    seq,
    issueDate: '',
    dueDate: '',
    noteType: '银行承兑',
    drawer: '',
    payee: '',
    faceValue: 0,
    currency: 'CNY',
    purpose: '',
    interestRate: 0,
    termDays: 0,
    isInterestBearing: '否',
    isOverdue: '否',
    acceptBank: '',
    noteStatus: '流通',
    remark: '',
    openingBalance: 0,
    increase: 0,
    decrease: 0,
    aje: 0,
    rje: 0,
    indexRef: '',
  }
}

function safeParseRows(jsonStr: string | null | undefined): StoredF3DetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyStored(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      issueDate: raw.issueDate || '',
      dueDate: raw.dueDate || '',
      noteType: raw.noteType || '银行承兑',
      drawer: raw.drawer || '',
      payee: raw.payee || '',
      faceValue: parseNum(raw.faceValue),
      currency: raw.currency || 'CNY',
      purpose: raw.purpose || '',
      interestRate: parseNum(raw.interestRate ?? raw.rate),
      termDays: parseNum(raw.termDays),
      isInterestBearing: raw.isInterestBearing || '否',
      isOverdue: raw.isOverdue || '否',
      acceptBank: raw.acceptBank || raw.acceptorBank || '',
      noteStatus: raw.noteStatus || raw.status || '流通',
      remark: raw.remark || '',
      openingBalance: parseNum(raw.openingBalance),
      increase: parseNum(raw.increase ?? raw.currentIncrease),
      decrease: parseNum(raw.decrease ?? raw.currentDecrease),
      aje: parseNum(raw.aje ?? raw.ajeAdjustment),
      rje: parseNum(raw.rje ?? raw.rjeReclassification),
      indexRef: raw.indexRef || '',
    }))
  } catch {
    return []
  }
}

function computeRow(stored: StoredF3DetailRow): F3NoteDetailRow {
  const termDays = stored.termDays > 0 ? stored.termDays : calcTermDays(stored.issueDate, stored.dueDate)
  const overdueDays = calcOverdueDays(stored.dueDate)
  const closingBalance = calcCreditBalance(stored.openingBalance, stored.increase, stored.decrease)
  const adjustedBalance = calcAuditedAmount(closingBalance, stored.aje, stored.rje)
  const isOverdue = overdueDays > 0 ? '是' : stored.isOverdue
  return { ...stored, termDays, overdueDays, closingBalance, adjustedBalance, isOverdue }
}

export function useF3Detail(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const activeSegment = ref<'basic' | 'detail' | 'audit'>('basic')
  const storedData = ref<StoredF3DetailRow[]>([])
  const searchQuery = ref('')

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [emptyStored(1)]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  const rows: ComputedRef<F3NoteDetailRow[]> = computed(() => storedData.value.map(computeRow))

  const filteredRows: ComputedRef<F3NoteDetailRow[]> = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter(
      (r) =>
        r.drawer.toLowerCase().includes(q) ||
        r.payee.toLowerCase().includes(q) ||
        r.noteType.toLowerCase().includes(q),
    )
  })

  const subtotalRow: ComputedRef<F3NoteDetailRow> = computed(() =>
    computeRow({
      ...emptyStored(0),
      rowId: 'subtotal',
      drawer: '合计',
      faceValue: calcSubtotal(rows.value.map((r) => r.faceValue)),
      openingBalance: calcSubtotal(rows.value.map((r) => r.openingBalance)),
      increase: calcSubtotal(rows.value.map((r) => r.increase)),
      decrease: calcSubtotal(rows.value.map((r) => r.decrease)),
      aje: calcSubtotal(rows.value.map((r) => r.aje)),
      rje: calcSubtotal(rows.value.map((r) => r.rje)),
    }),
  )

  function addRow(): void {
    if (readonly.value) return
    storedData.value.push(emptyStored(storedData.value.length + 1))
    persistRows()
  }

  function removeRow(rowId: string): void {
    if (readonly.value || storedData.value.length <= 1) return
    const idx = storedData.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    storedData.value.splice(idx, 1)
    storedData.value.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = storedData.value.find((r) => r.rowId === rowId)
    if (!row) return
    const strFields = ['issueDate', 'dueDate', 'noteType', 'drawer', 'payee', 'currency', 'purpose',
      'isInterestBearing', 'isOverdue', 'acceptBank', 'noteStatus', 'remark', 'indexRef']
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    persistRows()
  }

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, { item_id: STORAGE_KEY, conclusion: null, remark: JSON.stringify(storedData.value) })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items: [item] } }))
  }

  function rowClassName({ row }: { row: F3NoteDetailRow }): string {
    return row.overdueDays > 0 ? 'overdue-row' : ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    activeSegment,
    rows,
    filteredRows,
    subtotalRow,
    searchQuery,
    addRow,
    removeRow,
    updateCell,
    rowClassName,
    basicColumns: F3_DETAIL_BASIC_COLUMNS,
    infoColumns: F3_DETAIL_INFO_COLUMNS,
    auditColumns: F3_DETAIL_AUDIT_COLUMNS,
  }
}

export default useF3Detail
