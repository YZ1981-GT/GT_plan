/**
 * useF4Detail — F4-2 应付账款明细表（27列 / 3区段Tab）
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 5.1
 * 贷方科目公式：期末 = 期初 + 贷方 - 借方
 * 账龄合计 = 各段SUM；审定 = 期末 + AJE + RJE
 * 账龄交叉校验：合计≠期末 → 红色标记
 * Requirements: 5.1~5.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcCreditBalance,
  calcAuditedAmount,
  calcAgingTotal,
  calcAgingCrossCheck,
  calcSubtotal,
} from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface APDetailRow {
  rowId: string
  seq: number
  // 基础信息区段 (9列)
  creditor: string
  companyCode: string
  relatedPartyType: string
  paymentNature: string
  openingAdjusted: number
  currentDebit: number
  currentCredit: number
  closingBalance: number          // 公式=期初+贷方-借方
  // 账龄与核对区段 (10列)
  aging1Year: number
  aging1to2Year: number
  aging2to3Year: number
  aging3YearPlus: number
  agingTotal: number              // 公式=各账龄段SUM
  isConfirmed: string
  confirmationResult: string
  subsequentPayment: number
  subsequentPaymentDate: string
  remark: string
  // 调整与审定区段 (8列)
  ajeAdjustment: number
  rjeReclassification: number
  adjustedBalance: number         // 公式=期末+AJE+RJE
  adjustedAging1: number
  adjustedAging2: number
  adjustedAging3: number
  adjustedAging4: number
  indexRef: string
  // 交叉校验标记
  agingMismatch: boolean
}

export interface F4DetailColumn {
  prop: keyof APDetailRow | string
  label: string
  width?: number
  minWidth?: number
  formula?: string
  editable?: boolean
}

// ─── 3区段列配置 ──────────────────────────────────────────────────────────────

/** 基础信息区段 9列 */
export const F4_DETAIL_BASIC_COLUMNS: F4DetailColumn[] = [
  { prop: 'seq', label: '序号', width: 60 },
  { prop: 'creditor', label: '债权人', minWidth: 130, editable: true },
  { prop: 'companyCode', label: '公司代码', minWidth: 100, editable: true },
  { prop: 'relatedPartyType', label: '关联方类型', minWidth: 100, editable: true },
  { prop: 'paymentNature', label: '款项性质', minWidth: 100, editable: true },
  { prop: 'openingAdjusted', label: '期初审定', minWidth: 110, editable: true },
  { prop: 'currentDebit', label: '本期借方', minWidth: 110, editable: true },
  { prop: 'currentCredit', label: '本期贷方', minWidth: 110, editable: true },
  { prop: 'closingBalance', label: '期末余额', minWidth: 110, formula: '期初+贷方-借方', editable: false },
]

/** 账龄与核对区段 10列 */
export const F4_DETAIL_AGING_COLUMNS: F4DetailColumn[] = [
  { prop: 'aging1Year', label: '1年以内', minWidth: 100, editable: true },
  { prop: 'aging1to2Year', label: '1-2年', minWidth: 90, editable: true },
  { prop: 'aging2to3Year', label: '2-3年', minWidth: 90, editable: true },
  { prop: 'aging3YearPlus', label: '3年以上', minWidth: 90, editable: true },
  { prop: 'agingTotal', label: '账龄合计', minWidth: 100, formula: '各账龄段SUM', editable: false },
  { prop: 'isConfirmed', label: '是否函证', minWidth: 90, editable: true },
  { prop: 'confirmationResult', label: '函证结果', minWidth: 100, editable: true },
  { prop: 'subsequentPayment', label: '期后付款金额', minWidth: 110, editable: true },
  { prop: 'subsequentPaymentDate', label: '期后付款日期', minWidth: 110, editable: true },
  { prop: 'remark', label: '备注', minWidth: 120, editable: true },
]

/** 调整与审定区段 8列 */
export const F4_DETAIL_AUDIT_COLUMNS: F4DetailColumn[] = [
  { prop: 'ajeAdjustment', label: '账项调整', minWidth: 100, editable: true },
  { prop: 'rjeReclassification', label: '重分类', minWidth: 100, editable: true },
  { prop: 'adjustedBalance', label: '审定余额', minWidth: 110, formula: '期末+AJE+RJE', editable: false },
  { prop: 'adjustedAging1', label: '审定1年内', minWidth: 100, editable: true },
  { prop: 'adjustedAging2', label: '审定1-2年', minWidth: 100, editable: true },
  { prop: 'adjustedAging3', label: '审定2-3年', minWidth: 100, editable: true },
  { prop: 'adjustedAging4', label: '审定3年以上', minWidth: 100, editable: true },
  { prop: 'indexRef', label: '索引', minWidth: 90, editable: true },
]

// ─── 内部类型（存储用，不含公式列） ──────────────────────────────────────────

interface StoredAPDetailRow {
  rowId: string
  seq: number
  creditor: string
  companyCode: string
  relatedPartyType: string
  paymentNature: string
  openingAdjusted: number
  currentDebit: number
  currentCredit: number
  aging1Year: number
  aging1to2Year: number
  aging2to3Year: number
  aging3YearPlus: number
  isConfirmed: string
  confirmationResult: string
  subsequentPayment: number
  subsequentPaymentDate: string
  remark: string
  ajeAdjustment: number
  rjeReclassification: number
  adjustedAging1: number
  adjustedAging2: number
  adjustedAging3: number
  adjustedAging4: number
  indexRef: string
}

export interface UseF4DetailOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

const STORAGE_KEY = 'F4-2-rows'

function generateRowId(): string {
  return `f4d-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyStored(seq: number): StoredAPDetailRow {
  return {
    rowId: generateRowId(),
    seq,
    creditor: '',
    companyCode: '',
    relatedPartyType: '',
    paymentNature: '',
    openingAdjusted: 0,
    currentDebit: 0,
    currentCredit: 0,
    aging1Year: 0,
    aging1to2Year: 0,
    aging2to3Year: 0,
    aging3YearPlus: 0,
    isConfirmed: '',
    confirmationResult: '',
    subsequentPayment: 0,
    subsequentPaymentDate: '',
    remark: '',
    ajeAdjustment: 0,
    rjeReclassification: 0,
    adjustedAging1: 0,
    adjustedAging2: 0,
    adjustedAging3: 0,
    adjustedAging4: 0,
    indexRef: '',
  }
}

function computeRow(stored: StoredAPDetailRow): APDetailRow {
  const closingBalance = calcCreditBalance(stored.openingAdjusted, stored.currentCredit, stored.currentDebit)
  const agingTotal = calcAgingTotal(stored.aging1Year, stored.aging1to2Year, stored.aging2to3Year, stored.aging3YearPlus)
  const adjustedBalance = calcAuditedAmount(closingBalance, stored.ajeAdjustment, stored.rjeReclassification)
  const agingMismatch = !calcAgingCrossCheck(agingTotal, closingBalance)
  return {
    ...stored,
    closingBalance,
    agingTotal,
    adjustedBalance,
    agingMismatch,
  }
}

function safeParseRows(jsonStr: string | null | undefined): StoredAPDetailRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyStored(i + 1),
      rowId: raw.rowId || raw.id || generateRowId(),
      seq: raw.seq ?? i + 1,
      creditor: raw.creditor || '',
      companyCode: raw.companyCode || '',
      relatedPartyType: raw.relatedPartyType || '',
      paymentNature: raw.paymentNature || '',
      openingAdjusted: parseNum(raw.openingAdjusted),
      currentDebit: parseNum(raw.currentDebit),
      currentCredit: parseNum(raw.currentCredit),
      aging1Year: parseNum(raw.aging1Year),
      aging1to2Year: parseNum(raw.aging1to2Year),
      aging2to3Year: parseNum(raw.aging2to3Year),
      aging3YearPlus: parseNum(raw.aging3YearPlus),
      isConfirmed: raw.isConfirmed || '',
      confirmationResult: raw.confirmationResult || '',
      subsequentPayment: parseNum(raw.subsequentPayment),
      subsequentPaymentDate: raw.subsequentPaymentDate || '',
      remark: raw.remark || '',
      ajeAdjustment: parseNum(raw.ajeAdjustment),
      rjeReclassification: parseNum(raw.rjeReclassification),
      adjustedAging1: parseNum(raw.adjustedAging1),
      adjustedAging2: parseNum(raw.adjustedAging2),
      adjustedAging3: parseNum(raw.adjustedAging3),
      adjustedAging4: parseNum(raw.adjustedAging4),
      indexRef: raw.indexRef || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4Detail(options: UseF4DetailOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const activeSegment = ref<'basic' | 'aging' | 'audit'>('basic')
  const storedData = ref<StoredAPDetailRow[]>([])
  const searchQuery = ref('')

  // ─── 加载 ─────────────────────────────────────────────────────────────────

  function loadRows(): void {
    storedData.value = safeParseRows(allResponses.value.get(STORAGE_KEY)?.remark)
    if (storedData.value.length === 0) storedData.value = [emptyStored(1)]
  }

  watch(() => allResponses.value.get(STORAGE_KEY)?.remark, () => {
    if (storedData.value.length === 0) loadRows()
  }, { immediate: true })

  // ─── 计算行 ───────────────────────────────────────────────────────────────

  const rows: ComputedRef<APDetailRow[]> = computed(() => storedData.value.map(computeRow))

  const filteredRows: ComputedRef<APDetailRow[]> = computed(() => {
    const q = searchQuery.value.trim().toLowerCase()
    if (!q) return rows.value
    return rows.value.filter(
      (r) =>
        r.creditor.toLowerCase().includes(q) ||
        r.companyCode.toLowerCase().includes(q) ||
        r.paymentNature.toLowerCase().includes(q),
    )
  })

  // ─── 合计行 ───────────────────────────────────────────────────────────────

  const subtotalRow: ComputedRef<APDetailRow> = computed(() =>
    computeRow({
      ...emptyStored(0),
      rowId: 'subtotal',
      creditor: '合计',
      openingAdjusted: calcSubtotal(rows.value.map((r) => r.openingAdjusted)),
      currentDebit: calcSubtotal(rows.value.map((r) => r.currentDebit)),
      currentCredit: calcSubtotal(rows.value.map((r) => r.currentCredit)),
      aging1Year: calcSubtotal(rows.value.map((r) => r.aging1Year)),
      aging1to2Year: calcSubtotal(rows.value.map((r) => r.aging1to2Year)),
      aging2to3Year: calcSubtotal(rows.value.map((r) => r.aging2to3Year)),
      aging3YearPlus: calcSubtotal(rows.value.map((r) => r.aging3YearPlus)),
      ajeAdjustment: calcSubtotal(rows.value.map((r) => r.ajeAdjustment)),
      rjeReclassification: calcSubtotal(rows.value.map((r) => r.rjeReclassification)),
      adjustedAging1: calcSubtotal(rows.value.map((r) => r.adjustedAging1)),
      adjustedAging2: calcSubtotal(rows.value.map((r) => r.adjustedAging2)),
      adjustedAging3: calcSubtotal(rows.value.map((r) => r.adjustedAging3)),
      adjustedAging4: calcSubtotal(rows.value.map((r) => r.adjustedAging4)),
    }),
  )

  // ─── 动态行操作 ───────────────────────────────────────────────────────────

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
      'creditor', 'companyCode', 'relatedPartyType', 'paymentNature',
      'isConfirmed', 'confirmationResult', 'subsequentPaymentDate', 'remark', 'indexRef',
    ]
    if (strFields.includes(field)) (row as any)[field] = String(value ?? '')
    else (row as any)[field] = parseNum(value)
    persistRows()
  }

  // ─── 持久化 ───────────────────────────────────────────────────────────────

  function persistRows(): void {
    allResponses.value.set(STORAGE_KEY, {
      item_id: STORAGE_KEY,
      conclusion: null,
      remark: JSON.stringify(storedData.value),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const item = allResponses.value.get(STORAGE_KEY)
    if (item) window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items: [item] } }))
  }

  // ─── 样式 ─────────────────────────────────────────────────────────────────

  function rowClassName({ row }: { row: APDetailRow }): string {
    return row.agingMismatch ? 'aging-mismatch-row' : ''
  }

  // ─── 清理 ─────────────────────────────────────────────────────────────────

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
    basicColumns: F4_DETAIL_BASIC_COLUMNS,
    agingColumns: F4_DETAIL_AGING_COLUMNS,
    auditColumns: F4_DETAIL_AUDIT_COLUMNS,
  }
}

export default useF4Detail
