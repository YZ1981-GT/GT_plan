/**
 * useF4VoucherCheck — F4-8 应付账款检查表（借方/贷方区块）
 *
 * Spec: .kiro/specs/f4-accounts-payable/ Task 6.4
 * 借方区(付款减少) + 贷方区(采购增加) 独立el-table
 * GtVoucherSamplingEngine集成(dialog, 科目2202, 样本按借贷分配)
 * 贷方区特色：三单匹配(采购订单/入库单/发票)
 * Requirements: 11.1~11.9, 14.2
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal } from './useF4AccPayFormulaEngine'
import type { ChecklistResponse } from './useF4FormData'

// ─── 类型定义 ─────────────────────────────────────────────────────────────────

export interface VoucherCheckRow {
  rowId: string
  seq: number
  voucherNo: string
  voucherDate: string
  counterparty: string
  amount: number
  summary: string
  auditProcedure: string
  checkResult: string
  remark: string
}

/** 贷方区扩展：三单匹配 */
export interface CreditVoucherCheckRow extends VoucherCheckRow {
  purchaseOrderNo: string
  receiptNo: string
  invoiceNo: string
  threeWayMatch: '一致' | '不一致' | ''
}

export type VoucherSection = 'debit' | 'credit'

export interface F4VoucherCheckColumn {
  prop: string
  label: string
  width?: number
  minWidth?: number
  editable?: boolean
}

export const F4_DEBIT_COLUMNS: F4VoucherCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60 },
  { prop: 'voucherNo', label: '凭证号', minWidth: 100, editable: true },
  { prop: 'voucherDate', label: '凭证日期', minWidth: 110, editable: true },
  { prop: 'counterparty', label: '供应商', minWidth: 130, editable: true },
  { prop: 'amount', label: '付款金额', minWidth: 120, editable: true },
  { prop: 'summary', label: '摘要', minWidth: 140, editable: true },
  { prop: 'auditProcedure', label: '审计程序', minWidth: 140, editable: true },
  { prop: 'checkResult', label: '检查结果', minWidth: 120, editable: true },
  { prop: 'remark', label: '备注', minWidth: 120, editable: true },
]

export const F4_CREDIT_COLUMNS: F4VoucherCheckColumn[] = [
  { prop: 'seq', label: '序号', width: 60 },
  { prop: 'voucherNo', label: '凭证号', minWidth: 100, editable: true },
  { prop: 'voucherDate', label: '凭证日期', minWidth: 110, editable: true },
  { prop: 'counterparty', label: '供应商', minWidth: 130, editable: true },
  { prop: 'amount', label: '采购金额', minWidth: 120, editable: true },
  { prop: 'summary', label: '摘要', minWidth: 140, editable: true },
  { prop: 'purchaseOrderNo', label: '采购订单号', minWidth: 110, editable: true },
  { prop: 'receiptNo', label: '入库单号', minWidth: 100, editable: true },
  { prop: 'invoiceNo', label: '发票号', minWidth: 100, editable: true },
  { prop: 'threeWayMatch', label: '三单匹配', minWidth: 90, editable: true },
  { prop: 'auditProcedure', label: '审计程序', minWidth: 140, editable: true },
  { prop: 'checkResult', label: '检查结果', minWidth: 120, editable: true },
  { prop: 'remark', label: '备注', minWidth: 120, editable: true },
]

// ─── 内部存储类型 ─────────────────────────────────────────────────────────────

interface StoredDebitRow {
  rowId: string
  seq: number
  voucherNo: string
  voucherDate: string
  counterparty: string
  amount: number
  summary: string
  auditProcedure: string
  checkResult: string
  remark: string
}

interface StoredCreditRow extends StoredDebitRow {
  purchaseOrderNo: string
  receiptNo: string
  invoiceNo: string
  threeWayMatch: '一致' | '不一致' | ''
}

export interface UseF4VoucherCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

// ─── 常量 ─────────────────────────────────────────────────────────────────────

const DEBIT_KEY = 'F4-8-debit'
const CREDIT_KEY = 'F4-8-credit'
const DEBIT_NOTE_KEY = 'F4-8-debit-note'
const CREDIT_NOTE_KEY = 'F4-8-credit-note'

// ─── 工具函数 ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `f4vc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyDebit(seq: number): StoredDebitRow {
  return {
    rowId: generateRowId(),
    seq,
    voucherNo: '',
    voucherDate: '',
    counterparty: '',
    amount: 0,
    summary: '',
    auditProcedure: '',
    checkResult: '',
    remark: '',
  }
}

function emptyCredit(seq: number): StoredCreditRow {
  return {
    ...emptyDebit(seq),
    purchaseOrderNo: '',
    receiptNo: '',
    invoiceNo: '',
    threeWayMatch: '',
  }
}

function safeParseDebit(jsonStr: string | null | undefined): StoredDebitRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyDebit(i + 1),
      rowId: raw.rowId || generateRowId(),
      seq: raw.seq ?? i + 1,
      voucherNo: raw.voucherNo || '',
      voucherDate: raw.voucherDate || '',
      counterparty: raw.counterparty || '',
      amount: parseNum(raw.amount),
      summary: raw.summary || '',
      auditProcedure: raw.auditProcedure || '',
      checkResult: raw.checkResult || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

function safeParseCredit(jsonStr: string | null | undefined): StoredCreditRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    return parsed.map((raw: any, i: number) => ({
      ...emptyCredit(i + 1),
      rowId: raw.rowId || generateRowId(),
      seq: raw.seq ?? i + 1,
      voucherNo: raw.voucherNo || '',
      voucherDate: raw.voucherDate || '',
      counterparty: raw.counterparty || '',
      amount: parseNum(raw.amount),
      summary: raw.summary || '',
      purchaseOrderNo: raw.purchaseOrderNo || '',
      receiptNo: raw.receiptNo || '',
      invoiceNo: raw.invoiceNo || '',
      threeWayMatch: raw.threeWayMatch || '',
      auditProcedure: raw.auditProcedure || '',
      checkResult: raw.checkResult || '',
      remark: raw.remark || '',
    }))
  } catch {
    return []
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF4VoucherCheck(options: UseF4VoucherCheckOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const debitStored = ref<StoredDebitRow[]>([])
  const creditStored = ref<StoredCreditRow[]>([])
  const debitConclusion = ref('')
  const creditConclusion = ref('')

  // ─── 加载 ─────────────────────────────────────────────────────────────────

  function loadDebit(): void {
    debitStored.value = safeParseDebit(allResponses.value.get(DEBIT_KEY)?.remark)
    if (debitStored.value.length === 0) debitStored.value = [emptyDebit(1)]
  }

  function loadCredit(): void {
    creditStored.value = safeParseCredit(allResponses.value.get(CREDIT_KEY)?.remark)
    if (creditStored.value.length === 0) creditStored.value = [emptyCredit(1)]
  }

  watch(() => allResponses.value.get(DEBIT_KEY)?.remark, () => {
    if (debitStored.value.length === 0) loadDebit()
  }, { immediate: true })

  watch(() => allResponses.value.get(CREDIT_KEY)?.remark, () => {
    if (creditStored.value.length === 0) loadCredit()
  }, { immediate: true })

  watch(() => allResponses.value.get(DEBIT_NOTE_KEY)?.remark, (v) => {
    debitConclusion.value = v || ''
  }, { immediate: true })

  watch(() => allResponses.value.get(CREDIT_NOTE_KEY)?.remark, (v) => {
    creditConclusion.value = v || ''
  }, { immediate: true })

  // ─── 计算行 ───────────────────────────────────────────────────────────────

  const debitRows: ComputedRef<VoucherCheckRow[]> = computed(() =>
    debitStored.value.map((r) => ({ ...r })),
  )

  const creditRows: ComputedRef<CreditVoucherCheckRow[]> = computed(() =>
    creditStored.value.map((r) => ({ ...r })),
  )

  // ─── 小计 ─────────────────────────────────────────────────────────────────

  const debitSubtotal = computed(() => calcSubtotal(debitRows.value.map((r) => r.amount)))
  const creditSubtotal = computed(() => calcSubtotal(creditRows.value.map((r) => r.amount)))

  // ─── 动态行操作 ───────────────────────────────────────────────────────────

  function addDebitRow(): void {
    if (readonly.value) return
    debitStored.value.push(emptyDebit(debitStored.value.length + 1))
    persistSection('debit')
  }

  function addCreditRow(): void {
    if (readonly.value) return
    creditStored.value.push(emptyCredit(creditStored.value.length + 1))
    persistSection('credit')
  }

  function removeDebitRow(rowId: string): void {
    if (readonly.value || debitStored.value.length <= 1) return
    const idx = debitStored.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    debitStored.value.splice(idx, 1)
    debitStored.value.forEach((r, i) => { r.seq = i + 1 })
    persistSection('debit')
  }

  function removeCreditRow(rowId: string): void {
    if (readonly.value || creditStored.value.length <= 1) return
    const idx = creditStored.value.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    creditStored.value.splice(idx, 1)
    creditStored.value.forEach((r, i) => { r.seq = i + 1 })
    persistSection('credit')
  }

  function updateDebitCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = debitStored.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (field === 'amount') (row as any)[field] = parseNum(value)
    else (row as any)[field] = String(value ?? '')
    persistSection('debit')
  }

  function updateCreditCell(rowId: string, field: string, value: any): void {
    if (readonly.value) return
    const row = creditStored.value.find((r) => r.rowId === rowId)
    if (!row) return
    if (field === 'amount') (row as any)[field] = parseNum(value)
    else (row as any)[field] = String(value ?? '')
    persistSection('credit')
  }

  // ─── 抽凭引擎样本接收 ────────────────────────────────────────────────────

  function distributeSamples(
    samples: Array<{
      voucherNo: string
      voucherDate: string
      summary: string | null
      debitAmount: string | null
      creditAmount: string | null
      counterparty?: string
    }>,
  ): void {
    if (readonly.value || !samples.length) return

    const debitNew: StoredDebitRow[] = []
    const creditNew: StoredCreditRow[] = []

    for (const s of samples) {
      const debitAmt = parseNum(s.debitAmount)
      const creditAmt = parseNum(s.creditAmount)

      if (debitAmt > 0) {
        debitNew.push({
          ...emptyDebit(0),
          rowId: generateRowId(),
          voucherNo: s.voucherNo || '',
          voucherDate: s.voucherDate || '',
          counterparty: s.counterparty || '',
          amount: debitAmt,
          summary: s.summary || '',
        })
      }
      if (creditAmt > 0) {
        creditNew.push({
          ...emptyCredit(0),
          rowId: generateRowId(),
          voucherNo: s.voucherNo || '',
          voucherDate: s.voucherDate || '',
          counterparty: s.counterparty || '',
          amount: creditAmt,
          summary: s.summary || '',
        })
      }
    }

    if (debitNew.length) {
      if (debitStored.value.length === 1 && !debitStored.value[0].voucherNo && debitStored.value[0].amount === 0) {
        debitStored.value = []
      }
      debitStored.value.push(...debitNew)
      debitStored.value.forEach((r, i) => { r.seq = i + 1 })
      persistSection('debit')
    }

    if (creditNew.length) {
      if (creditStored.value.length === 1 && !creditStored.value[0].voucherNo && creditStored.value[0].amount === 0) {
        creditStored.value = []
      }
      creditStored.value.push(...creditNew)
      creditStored.value.forEach((r, i) => { r.seq = i + 1 })
      persistSection('credit')
    }
  }

  // ─── 持久化 ───────────────────────────────────────────────────────────────

  function persistSection(section: VoucherSection): void {
    const key = section === 'debit' ? DEBIT_KEY : CREDIT_KEY
    const data = section === 'debit' ? debitStored.value : creditStored.value
    allResponses.value.set(key, {
      item_id: key,
      conclusion: null,
      remark: JSON.stringify(data),
    })
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const items: ChecklistResponse[] = []
    for (const k of [DEBIT_KEY, CREDIT_KEY, DEBIT_NOTE_KEY, CREDIT_NOTE_KEY]) {
      const item = allResponses.value.get(k)
      if (item) items.push(item)
    }
    if (items.length) window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
  }

  watch(debitConclusion, (val) => {
    allResponses.value.set(DEBIT_NOTE_KEY, { item_id: DEBIT_NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  watch(creditConclusion, (val) => {
    allResponses.value.set(CREDIT_NOTE_KEY, { item_id: CREDIT_NOTE_KEY, conclusion: null, remark: val })
    debounceSave()
  })

  // ─── 清理 ─────────────────────────────────────────────────────────────────

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    debitRows,
    creditRows,
    debitSubtotal,
    creditSubtotal,
    debitConclusion,
    creditConclusion,
    addDebitRow,
    addCreditRow,
    removeDebitRow,
    removeCreditRow,
    updateDebitCell,
    updateCreditCell,
    distributeSamples,
    debitColumns: F4_DEBIT_COLUMNS,
    creditColumns: F4_CREDIT_COLUMNS,
  }
}

export default useF4VoucherCheck
