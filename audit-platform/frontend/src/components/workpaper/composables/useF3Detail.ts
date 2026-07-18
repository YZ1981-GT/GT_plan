/**
 * useF3Detail — F3-2 期末应付票据明细（源表 22 列 + 到期账龄 / 3区段）
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
  ticketNo: string
  relatedPartyType: string
  issueDate: string
  dueDate: string
  noteType: string
  drawer: string
  acceptor: string
  payee: string
  interestRate: number
  termDays: number
  maturityBucket: string
  isAccepted: string
  isOverdue: string
  overdueDays: number
  openingBalance: number
  currentIssued: number
  currentAccepted: number
  closingUnadjusted: number
  aje: number
  rje: number
  closingAdjusted: number
  accruedInterest: number
  isConfirmed: string
  depositRate: number
  depositAmount: number
  remark: string
}

export interface F3DetailColumn {
  prop: keyof F3NoteDetailRow | string
  label: string
  group: 'basic' | 'detail' | 'audit'
  width?: number
  minWidth?: number
  formula?: string
  editable?: boolean
  inputType?: 'text' | 'number' | 'date' | 'select'
  options?: readonly string[]
  sticky?: 'seq' | 'ticketNo' | 'noteType'
}

export const F3_NOTE_TYPE_OPTIONS = ['银行承兑汇票', '商业承兑汇票', '供应链票据', '其他'] as const
export const F3_RELATED_PARTY_OPTIONS = [
  '非关联方', '母公司', '子公司', '同一控制下企业', '联营企业', '合营企业', '其他关联方',
] as const
export const F3_YES_NO_OPTIONS = ['是', '否', '不适用'] as const

/** 基础信息：票据身份及关系人（源表 A–F） */
export const F3_DETAIL_BASIC_COLUMNS: F3DetailColumn[] = [
  { prop: 'seq', label: '序号', group: 'basic', width: 58, sticky: 'seq' },
  { prop: 'ticketNo', label: '票据号', group: 'basic', minWidth: 150, editable: true, inputType: 'text', sticky: 'ticketNo' },
  { prop: 'noteType', label: '票据类别', group: 'basic', minWidth: 130, editable: true, inputType: 'select', options: F3_NOTE_TYPE_OPTIONS, sticky: 'noteType' },
  { prop: 'relatedPartyType', label: '关联方类型', group: 'basic', minWidth: 140, editable: true, inputType: 'select', options: F3_RELATED_PARTY_OPTIONS },
  { prop: 'drawer', label: '出票人', group: 'basic', minWidth: 150, editable: true, inputType: 'text' },
  { prop: 'acceptor', label: '承兑人', group: 'basic', minWidth: 150, editable: true, inputType: 'text' },
  { prop: 'payee', label: '收款人', group: 'basic', minWidth: 150, editable: true, inputType: 'text' },
]

/** 票据条款：日期、期限、利率、承兑及到期账龄（源表 G–K + 风险增强） */
export const F3_DETAIL_INFO_COLUMNS: F3DetailColumn[] = [
  { prop: 'issueDate', label: '出票日', group: 'detail', minWidth: 125, editable: true, inputType: 'date' },
  { prop: 'dueDate', label: '到期日', group: 'detail', minWidth: 125, editable: true, inputType: 'date' },
  { prop: 'termDays', label: '期限(天)', group: 'detail', minWidth: 90, formula: '到期日－出票日', editable: false },
  { prop: 'maturityBucket', label: '到期账龄', group: 'detail', minWidth: 125, formula: '按到期日自动枚举：未到期/逾期1-30天/31-90天/91-180天/181天以上', editable: false },
  { prop: 'interestRate', label: '票面利率(%)', group: 'detail', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'isAccepted', label: '是否承兑', group: 'detail', minWidth: 100, editable: true, inputType: 'select', options: F3_YES_NO_OPTIONS },
  { prop: 'isOverdue', label: '是否逾期', group: 'detail', minWidth: 90, formula: '到期账龄自动判断', editable: false },
  { prop: 'overdueDays', label: '逾期天数', group: 'detail', minWidth: 90, formula: 'MAX(0,今天－到期日)', editable: false },
]

/** 余额及审计核对（源表 L–V） */
export const F3_DETAIL_AUDIT_COLUMNS: F3DetailColumn[] = [
  { prop: 'openingBalance', label: '期初余额', group: 'audit', minWidth: 115, editable: true, inputType: 'number' },
  { prop: 'currentIssued', label: '本期开票', group: 'audit', minWidth: 115, editable: true, inputType: 'number' },
  { prop: 'currentAccepted', label: '本期承兑', group: 'audit', minWidth: 115, editable: true, inputType: 'number' },
  { prop: 'closingUnadjusted', label: '期末未审数', group: 'audit', minWidth: 120, formula: '期初余额＋本期开票－本期承兑', editable: false },
  { prop: 'aje', label: '账项调整', group: 'audit', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'rje', label: '重分类调整', group: 'audit', minWidth: 115, editable: true, inputType: 'number' },
  { prop: 'closingAdjusted', label: '期末审定数', group: 'audit', minWidth: 120, formula: '期末未审数＋账项调整＋重分类调整', editable: false },
  { prop: 'accruedInterest', label: '已计利息', group: 'audit', minWidth: 110, editable: true, inputType: 'number' },
  { prop: 'isConfirmed', label: '是否函证', group: 'audit', minWidth: 100, editable: true, inputType: 'select', options: F3_YES_NO_OPTIONS },
  { prop: 'depositRate', label: '票据保证金比例(%)', group: 'audit', minWidth: 145, editable: true, inputType: 'number' },
  { prop: 'depositAmount', label: '保证金金额', group: 'audit', minWidth: 120, editable: true, inputType: 'number' },
  { prop: 'remark', label: '备注', group: 'audit', minWidth: 180, editable: true, inputType: 'text' },
]

interface StoredF3DetailRow {
  rowId: string
  seq: number
  ticketNo: string
  relatedPartyType: string
  issueDate: string
  dueDate: string
  noteType: string
  drawer: string
  acceptor: string
  payee: string
  interestRate: number
  termDays: number
  isAccepted: string
  isOverdue: string
  openingBalance: number
  currentIssued: number
  currentAccepted: number
  aje: number
  rje: number
  accruedInterest: number
  isConfirmed: string
  depositRate: number
  depositAmount: number
  remark: string
}

const STORAGE_KEY = 'F3-2-rows'

function generateRowId(): string {
  return `f3d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number): StoredF3DetailRow {
  return {
    rowId: generateRowId(),
    seq,
    ticketNo: '',
    relatedPartyType: '非关联方',
    issueDate: '',
    dueDate: '',
    noteType: '银行承兑汇票',
    drawer: '',
    acceptor: '',
    payee: '',
    interestRate: 0,
    termDays: 0,
    isAccepted: '是',
    isOverdue: '否',
    openingBalance: 0,
    currentIssued: 0,
    currentAccepted: 0,
    aje: 0,
    rje: 0,
    accruedInterest: 0,
    isConfirmed: '否',
    depositRate: 0,
    depositAmount: 0,
    remark: '',
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
      ticketNo: raw.ticketNo || raw.noteNo || raw.billNo || '',
      relatedPartyType: raw.relatedPartyType || raw.relationship || '非关联方',
      issueDate: raw.issueDate || '',
      dueDate: raw.dueDate || '',
      noteType: raw.noteType === '银行承兑' ? '银行承兑汇票'
        : raw.noteType === '商业承兑' ? '商业承兑汇票'
          : raw.noteType || '银行承兑汇票',
      drawer: raw.drawer || '',
      acceptor: raw.acceptor || raw.acceptBank || raw.acceptorBank || '',
      payee: raw.payee || '',
      interestRate: parseNum(raw.interestRate ?? raw.rate),
      termDays: parseNum(raw.termDays),
      isAccepted: raw.isAccepted || '是',
      isOverdue: raw.isOverdue || '否',
      openingBalance: parseNum(raw.openingBalance),
      currentIssued: parseNum(raw.currentIssued ?? raw.increase ?? raw.currentIncrease),
      currentAccepted: parseNum(raw.currentAccepted ?? raw.decrease ?? raw.currentDecrease),
      aje: parseNum(raw.aje ?? raw.ajeAdjustment),
      rje: parseNum(raw.rje ?? raw.rjeReclassification),
      accruedInterest: parseNum(raw.accruedInterest ?? raw.bookInterest),
      isConfirmed: raw.isConfirmed || raw.confirmationStatus || '否',
      depositRate: parseNum(raw.depositRate ?? raw.guaranteeRate),
      depositAmount: parseNum(raw.depositAmount ?? raw.guaranteeAmount),
      remark: raw.remark || (raw.indexRef ? `索引：${raw.indexRef}` : ''),
    }))
  } catch {
    return []
  }
}

function computeRow(stored: StoredF3DetailRow): F3NoteDetailRow {
  const termDays = stored.termDays > 0 ? stored.termDays : calcTermDays(stored.issueDate, stored.dueDate)
  const overdueDays = calcOverdueDays(stored.dueDate)
  const closingUnadjusted = calcCreditBalance(
    stored.openingBalance,
    stored.currentIssued,
    stored.currentAccepted,
  )
  const closingAdjusted = calcAuditedAmount(closingUnadjusted, stored.aje, stored.rje)
  const isOverdue = overdueDays > 0 ? '是' : stored.isOverdue
  const maturityBucket = overdueDays <= 0
    ? '未到期'
    : overdueDays <= 30
      ? '逾期1-30天'
      : overdueDays <= 90
        ? '逾期31-90天'
        : overdueDays <= 180
          ? '逾期91-180天'
          : '逾期181天以上'
  return {
    ...stored,
    termDays,
    overdueDays,
    maturityBucket,
    closingUnadjusted,
    closingAdjusted,
    isOverdue,
  }
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
  const abnormalCount = computed(() =>
    rows.value.filter((row) => row.overdueDays > 0 || Math.abs(row.aje) > 0.005 || Math.abs(row.rje) > 0.005).length,
  )
  const filledCount = computed(() =>
    rows.value.filter((row) => row.ticketNo || row.drawer || row.payee || row.openingBalance
      || row.currentIssued || row.currentAccepted).length,
  )

  const filteredRows: ComputedRef<F3NoteDetailRow[]> = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter(
      (r) =>
        r.ticketNo.toLowerCase().includes(q) ||
        r.drawer.toLowerCase().includes(q) ||
        r.acceptor.toLowerCase().includes(q) ||
        r.payee.toLowerCase().includes(q) ||
        r.noteType.toLowerCase().includes(q),
    )
  })

  const subtotalRow: ComputedRef<F3NoteDetailRow> = computed(() =>
    computeRow({
      ...emptyStored(0),
      rowId: 'subtotal',
      drawer: '合计',
      openingBalance: calcSubtotal(rows.value.map((r) => r.openingBalance)),
      currentIssued: calcSubtotal(rows.value.map((r) => r.currentIssued)),
      currentAccepted: calcSubtotal(rows.value.map((r) => r.currentAccepted)),
      aje: calcSubtotal(rows.value.map((r) => r.aje)),
      rje: calcSubtotal(rows.value.map((r) => r.rje)),
      accruedInterest: calcSubtotal(rows.value.map((r) => r.accruedInterest)),
      depositAmount: calcSubtotal(rows.value.map((r) => r.depositAmount)),
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
    const strFields = [
      'ticketNo', 'relatedPartyType', 'issueDate', 'dueDate', 'noteType', 'drawer',
      'acceptor', 'payee', 'isAccepted', 'isOverdue', 'isConfirmed', 'remark',
    ]
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
    filledCount,
    abnormalCount,
    searchQuery,
    addRow,
    removeRow,
    updateCell,
    rowClassName,
    basicColumns: F3_DETAIL_BASIC_COLUMNS,
    infoColumns: F3_DETAIL_INFO_COLUMNS,
    auditColumns: F3_DETAIL_AUDIT_COLUMNS,
    allColumns: [...F3_DETAIL_BASIC_COLUMNS, ...F3_DETAIL_INFO_COLUMNS, ...F3_DETAIL_AUDIT_COLUMNS],
  }
}

export default useF3Detail
