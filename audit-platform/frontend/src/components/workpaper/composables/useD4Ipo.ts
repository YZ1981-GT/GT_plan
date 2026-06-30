/**
 * useD4Ipo — D4-22A~32 IPO/舞弊组通用 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 14.1
 *
 * 职责：
 * - visibility guard (ipoGroupVisible externally checked)
 * - D4-23 invoiceRows: month/revenue/invoiceAmount/diff/diffRate
 * - D4-24 thirdPartyRows: payer/payee/amount/date/relation
 * - D4-25 dealerRows: name/registeredCapital/mainBusiness/purchaseAmount/isAbnormal
 * - D4-26 overseasRows: customer/country/tradeTerms/customsAmount/bookAmount/diff
 * - D4-27 undisclosedRpRows: customer/shareholders/controller/relation/conclusion
 * - D4-28 customerChecklistRows: fixed Y/N items
 * - D4-29 customerDetailRows: dynamic per-customer
 * - D4-30 interviewSummaryRows
 * - D4-31 interviewDetailRows
 * - D4-32 fundFlowRows: counterparty/inAmount/outAmount/netAmount/timeMatch/remark
 * - suspiciousFlows computed (isSuspiciousFundFlow)
 *
 * Requirements: 14.1-14.12
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcChangeRate,
  calcSubtotal,
  isSuspiciousFundFlow,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface InvoiceCompareRow {
  rowId: string
  month: string
  revenue: number
  invoiceAmount: number
  diff: number            // auto = revenue - invoiceAmount
  diffRate: number | '' | 'N/A'  // auto
}

export interface ThirdPartyRow {
  rowId: string
  payer: string
  payee: string
  amount: number
  date: string
  relation: string
  remark: string
}

export interface DealerRow {
  rowId: string
  name: string
  registeredCapital: number
  mainBusiness: string
  purchaseAmount: number
  isAbnormal: boolean
  remark: string
}

export interface OverseasRow {
  rowId: string
  customer: string
  country: string
  tradeTerms: string
  customsAmount: number
  bookAmount: number
  diff: number            // auto = bookAmount - customsAmount
  remark: string
}

export interface UndisclosedRpRow {
  rowId: string
  customer: string
  shareholders: string
  controller: string
  relation: string
  conclusion: 'related' | 'unrelated' | 'attention' | ''
  remark: string
}

export interface CustomerChecklistRow {
  rowId: string
  item: string
  answer: 'Y' | 'N' | 'NA' | ''
  explanation: string
}

export interface CustomerDetailRow {
  rowId: string
  customerName: string
  registrationDate: string
  registeredCapital: number
  mainBusiness: string
  transactionAmount: number
  cooperationYears: number
  remark: string
}

export interface InterviewSummaryRow {
  rowId: string
  customerName: string
  interviewDate: string
  interviewee: string
  keyFindings: string
  conclusion: 'normal' | 'abnormal' | 'attention' | ''
}

export interface InterviewDetailRow {
  rowId: string
  customerName: string
  question: string
  answer: string
  followUp: string
  remark: string
}

export interface FundFlowRow {
  rowId: string
  counterparty: string
  inAmount: number
  outAmount: number
  netAmount: number       // auto = inAmount - outAmount
  transactionDate: string
  daysDiff: number
  timeMatch: 'Y' | 'N' | ''
  isSuspicious: boolean   // auto
  remark: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function generateRowId(): string {
  return `row-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

// ─── Default Checklist Items (D4-28) ─────────────────────────────────────────

const DEFAULT_CHECKLIST_ITEMS = [
  '客户工商注册信息是否已核实',
  '客户实际控制人是否已确认',
  '客户与公司关键人员是否存在关联关系',
  '客户注册资本与交易规模是否匹配',
  '客户主营业务是否与采购产品相关',
  '客户是否在公司附近同一地址注册',
  '客户成立时间与首次交易时间是否接近',
  '客户是否存在异常回款模式',
  '客户是否为公司前员工控制',
  '客户是否同时为供应商',
]

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4Ipo(options: UseD4BaseOptions & { visible?: Ref<boolean> }) {
  const { allResponses, isReadonly, visible } = options
  const readonly = isReadonly ?? ref(false)
  const isVisible = visible ?? ref(true)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // ─── D4-23 发票对比 ─────────────────────────────────────────────────

  const invoiceRows = ref<InvoiceCompareRow[]>([])

  function loadInvoiceRows(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-23-rows')
    invoiceRows.value = safeParseRows<InvoiceCompareRow>(resp?.remark).map(r => ({
      ...r,
      diff: parseNum(r.revenue) - parseNum(r.invoiceAmount),
      diffRate: calcChangeRate(parseNum(r.revenue), parseNum(r.invoiceAmount)),
    }))
  }

  watch(() => allResponses.value.get('D4-23-rows')?.remark, () => loadInvoiceRows(), { immediate: true })

  // ─── D4-24 第三方回款 ───────────────────────────────────────────────

  const thirdPartyRows = ref<ThirdPartyRow[]>([])

  function loadThirdPartyRows(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-24-rows')
    thirdPartyRows.value = safeParseRows<ThirdPartyRow>(resp?.remark)
  }

  watch(() => allResponses.value.get('D4-24-rows')?.remark, () => loadThirdPartyRows(), { immediate: true })

  // ─── D4-25 经销商 ──────────────────────────────────────────────────

  const dealerRows = ref<DealerRow[]>([])

  function loadDealerRows(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-25-rows')
    dealerRows.value = safeParseRows<DealerRow>(resp?.remark)
  }

  watch(() => allResponses.value.get('D4-25-rows')?.remark, () => loadDealerRows(), { immediate: true })

  // ─── D4-26 境外 ────────────────────────────────────────────────────

  const overseasRows = ref<OverseasRow[]>([])

  function loadOverseasRows(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-26-rows')
    overseasRows.value = safeParseRows<OverseasRow>(resp?.remark).map(r => ({
      ...r,
      diff: parseNum(r.bookAmount) - parseNum(r.customsAmount),
    }))
  }

  watch(() => allResponses.value.get('D4-26-rows')?.remark, () => loadOverseasRows(), { immediate: true })

  // ─── D4-27 未披露关联方 ─────────────────────────────────────────────

  const undisclosedRpRows = ref<UndisclosedRpRow[]>([])

  function loadUndisclosedRpRows(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-27-rows')
    undisclosedRpRows.value = safeParseRows<UndisclosedRpRow>(resp?.remark)
  }

  watch(() => allResponses.value.get('D4-27-rows')?.remark, () => loadUndisclosedRpRows(), { immediate: true })

  // ─── D4-28 客户核查清单 (固定 Y/N items) ────────────────────────────

  const customerChecklistRows = ref<CustomerChecklistRow[]>([])

  function loadChecklist(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-28-rows')
    const parsed = safeParseRows<CustomerChecklistRow>(resp?.remark)
    if (parsed.length > 0) {
      customerChecklistRows.value = parsed
    } else {
      // Initialize with default items
      customerChecklistRows.value = DEFAULT_CHECKLIST_ITEMS.map((item, idx) => ({
        rowId: `checklist-${idx}`,
        item,
        answer: '' as const,
        explanation: '',
      }))
    }
  }

  watch(() => allResponses.value.get('D4-28-rows')?.remark, () => loadChecklist(), { immediate: true })

  // ─── D4-29 客户核查详细 ─────────────────────────────────────────────

  const customerDetailRows = ref<CustomerDetailRow[]>([])

  function loadCustomerDetails(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-29-rows')
    customerDetailRows.value = safeParseRows<CustomerDetailRow>(resp?.remark)
  }

  watch(() => allResponses.value.get('D4-29-rows')?.remark, () => loadCustomerDetails(), { immediate: true })

  // ─── D4-30 访谈汇总 ────────────────────────────────────────────────

  const interviewSummaryRows = ref<InterviewSummaryRow[]>([])

  function loadInterviewSummary(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-30-rows')
    interviewSummaryRows.value = safeParseRows<InterviewSummaryRow>(resp?.remark)
  }

  watch(() => allResponses.value.get('D4-30-rows')?.remark, () => loadInterviewSummary(), { immediate: true })

  // ─── D4-31 访谈详细 ────────────────────────────────────────────────

  const interviewDetailRows = ref<InterviewDetailRow[]>([])

  function loadInterviewDetails(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-31-rows')
    interviewDetailRows.value = safeParseRows<InterviewDetailRow>(resp?.remark)
  }

  watch(() => allResponses.value.get('D4-31-rows')?.remark, () => loadInterviewDetails(), { immediate: true })

  // ─── D4-32 资金流水 ────────────────────────────────────────────────

  const fundFlowRows = ref<FundFlowRow[]>([])

  function loadFundFlowRows(): void {
    if (!isVisible.value) return
    const resp = allResponses.value.get('D4-32-rows')
    fundFlowRows.value = safeParseRows<FundFlowRow>(resp?.remark).map(r => ({
      ...r,
      netAmount: parseNum(r.inAmount) - parseNum(r.outAmount),
      isSuspicious: isSuspiciousFundFlow(parseNum(r.inAmount), parseNum(r.outAmount), parseNum(r.daysDiff)),
    }))
  }

  watch(() => allResponses.value.get('D4-32-rows')?.remark, () => loadFundFlowRows(), { immediate: true })

  /** Computed: suspicious fund flow rows (auto-flagged) */
  const suspiciousFlows: ComputedRef<FundFlowRow[]> = computed(() => {
    return fundFlowRows.value.filter(r => r.isSuspicious)
  })

  // ─── Generic Row Operations ─────────────────────────────────────────

  function addRow(section: string): void {
    if (readonly.value) return
    switch (section) {
      case 'D4-23':
        invoiceRows.value.push({
          rowId: generateRowId(), month: '', revenue: 0, invoiceAmount: 0, diff: 0, diffRate: '',
        })
        persistSection('D4-23-rows', invoiceRows.value)
        break
      case 'D4-24':
        thirdPartyRows.value.push({
          rowId: generateRowId(), payer: '', payee: '', amount: 0, date: '', relation: '', remark: '',
        })
        persistSection('D4-24-rows', thirdPartyRows.value)
        break
      case 'D4-25':
        dealerRows.value.push({
          rowId: generateRowId(), name: '', registeredCapital: 0, mainBusiness: '',
          purchaseAmount: 0, isAbnormal: false, remark: '',
        })
        persistSection('D4-25-rows', dealerRows.value)
        break
      case 'D4-26':
        overseasRows.value.push({
          rowId: generateRowId(), customer: '', country: '', tradeTerms: '',
          customsAmount: 0, bookAmount: 0, diff: 0, remark: '',
        })
        persistSection('D4-26-rows', overseasRows.value)
        break
      case 'D4-27':
        undisclosedRpRows.value.push({
          rowId: generateRowId(), customer: '', shareholders: '', controller: '',
          relation: '', conclusion: '', remark: '',
        })
        persistSection('D4-27-rows', undisclosedRpRows.value)
        break
      case 'D4-29':
        customerDetailRows.value.push({
          rowId: generateRowId(), customerName: '', registrationDate: '',
          registeredCapital: 0, mainBusiness: '', transactionAmount: 0,
          cooperationYears: 0, remark: '',
        })
        persistSection('D4-29-rows', customerDetailRows.value)
        break
      case 'D4-30':
        interviewSummaryRows.value.push({
          rowId: generateRowId(), customerName: '', interviewDate: '',
          interviewee: '', keyFindings: '', conclusion: '',
        })
        persistSection('D4-30-rows', interviewSummaryRows.value)
        break
      case 'D4-31':
        interviewDetailRows.value.push({
          rowId: generateRowId(), customerName: '', question: '',
          answer: '', followUp: '', remark: '',
        })
        persistSection('D4-31-rows', interviewDetailRows.value)
        break
      case 'D4-32':
        fundFlowRows.value.push({
          rowId: generateRowId(), counterparty: '', inAmount: 0, outAmount: 0,
          netAmount: 0, transactionDate: '', daysDiff: 0, timeMatch: '', isSuspicious: false, remark: '',
        })
        persistSection('D4-32-rows', fundFlowRows.value)
        break
    }
  }

  function removeRow(section: string, rowId: string): void {
    if (readonly.value) return
    switch (section) {
      case 'D4-23':
        invoiceRows.value = invoiceRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-23-rows', invoiceRows.value)
        break
      case 'D4-24':
        thirdPartyRows.value = thirdPartyRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-24-rows', thirdPartyRows.value)
        break
      case 'D4-25':
        dealerRows.value = dealerRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-25-rows', dealerRows.value)
        break
      case 'D4-26':
        overseasRows.value = overseasRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-26-rows', overseasRows.value)
        break
      case 'D4-27':
        undisclosedRpRows.value = undisclosedRpRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-27-rows', undisclosedRpRows.value)
        break
      case 'D4-29':
        customerDetailRows.value = customerDetailRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-29-rows', customerDetailRows.value)
        break
      case 'D4-30':
        interviewSummaryRows.value = interviewSummaryRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-30-rows', interviewSummaryRows.value)
        break
      case 'D4-31':
        interviewDetailRows.value = interviewDetailRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-31-rows', interviewDetailRows.value)
        break
      case 'D4-32':
        fundFlowRows.value = fundFlowRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-32-rows', fundFlowRows.value)
        break
    }
  }

  // ─── Persistence ────────────────────────────────────────────────────

  function persistSection(itemId: string, data: any): void {
    const json = JSON.stringify(data)
    allResponses.value.set(itemId, { item_id: itemId, conclusion: null, remark: json })
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
      const keys = [
        'D4-23-rows', 'D4-24-rows', 'D4-25-rows', 'D4-26-rows', 'D4-27-rows',
        'D4-28-rows', 'D4-29-rows', 'D4-30-rows', 'D4-31-rows', 'D4-32-rows',
      ]
      const items = keys.map(k => allResponses.value.get(k)).filter(Boolean)
      window.dispatchEvent(new CustomEvent('d4:save-items', { detail: { items } }))
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
    // D4-23
    invoiceRows,
    // D4-24
    thirdPartyRows,
    // D4-25
    dealerRows,
    // D4-26
    overseasRows,
    // D4-27
    undisclosedRpRows,
    // D4-28
    customerChecklistRows,
    // D4-29
    customerDetailRows,
    // D4-30
    interviewSummaryRows,
    // D4-31
    interviewDetailRows,
    // D4-32
    fundFlowRows,
    suspiciousFlows,
    // Operations
    addRow,
    removeRow,
  }
}

export default useD4Ipo
