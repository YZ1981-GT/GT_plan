/**
 * useD4Inspection — D4-12~20 检查程序组通用 composable
 *
 * Spec: .kiro/specs/d4-operating-revenue/
 * Task: 11.1
 *
 * 职责：
 * - D4-12 合同检查（动态行+覆盖率+下拉）
 * - D4-13 ERP核对（差异=账面-ERP）
 * - D4-14/15 发生/完整性（抽样参数+凭证明细+汇总）
 * - D4-16 出口核对（月度对比+汇率+差异）
 * - D4-17/18 截止双向（跨期自动判断+天数+红色高亮）
 * - D4-19 折扣（政策+明细+符合性）
 * - D4-20 退货（本期+期后+退货模式AI）
 *
 * Requirements: 9.1-9.7, 10.1-10.8, 11.1-11.8, 12.1-12.8
 */
import { ref, computed, watch, onBeforeUnmount, type Ref, type ComputedRef } from 'vue'
import {
  parseNum,
  calcAnomalyRate,
  calcCoverageRate,
  isCrossPeriod,
  calcCrossPeriodDays,
  calcSubtotal,
} from './useD4FormulaEngine'
import type { ChecklistResponse } from './useD4FormData'
import type { UseD4BaseOptions } from './useD4Adjudication'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface SamplingParams {
  testPopulation: string
  specificSamples: string
  samplingPopulation: string
  samplingMethod: string
  targetSampleSize: number
  currentSampleSize: number
}

export interface ContractRow {
  rowId: string
  customerName: string
  contractNo: string
  contractDate: string
  amount: number
  revenueType: string
  performanceObligation: string
  recognitionBasis: string
  conclusion: 'Y' | 'N' | 'NA' | ''
  remark: string
}

export interface ErpCheckRow {
  rowId: string
  month: string
  bookAmount: number
  erpAmount: number
  difference: number  // auto = bookAmount - erpAmount
  explanation: string
}

export interface VoucherCheckRow {
  rowId: string
  voucherNo: string
  voucherDate: string
  customerName: string
  amount: number
  hasContract: 'Y' | 'N' | ''
  hasDelivery: 'Y' | 'N' | ''
  hasInvoice: 'Y' | 'N' | ''
  isAnomalous: boolean
  remark: string
}

export interface ExportCheckRow {
  rowId: string
  month: string
  bookAmount: number
  customsAmount: number
  exchangeRate: number
  convertedAmount: number  // auto = customsAmount * exchangeRate
  difference: number       // auto = bookAmount - convertedAmount
  remark: string
}

export interface CutoffRow {
  rowId: string
  voucherNo: string
  voucherDate: string
  customerName: string
  amount: number
  shipDate: string
  signDate: string
  acceptDate: string
  isCrossPeriod: boolean     // auto
  crossPeriodDays: number    // auto
  adjustSuggestion: string
  remark: string
}

export interface DiscountRow {
  rowId: string
  customerName: string
  contractNo: string
  discountPolicy: string
  discountRate: number
  originalAmount: number
  discountAmount: number
  netAmount: number         // auto = originalAmount - discountAmount
  isCompliant: 'Y' | 'N' | ''
  remark: string
}

export interface ReturnRow {
  rowId: string
  customerName: string
  returnDate: string
  invoiceNo: string
  productName: string
  quantity: number
  amount: number
  reason: string
  isPostPeriod: boolean
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

function safeParseObj<T>(jsonStr: string | null | undefined, defaults: T): T {
  if (!jsonStr) return defaults
  try {
    return { ...defaults, ...JSON.parse(jsonStr) }
  } catch {
    return defaults
  }
}

const DEFAULT_SAMPLING: SamplingParams = {
  testPopulation: '',
  specificSamples: '',
  samplingPopulation: '',
  samplingMethod: '',
  targetSampleSize: 0,
  currentSampleSize: 0,
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useD4Inspection(options: UseD4BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)

  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  // Balance sheet date for cutoff determination (default: Dec 31)
  const balanceSheetDate = computed(() => {
    const resp = allResponses.value.get('D4-balance-sheet-date')
    return resp?.remark || '2025-12-31'
  })

  // ─── D4-12 合同检查 ─────────────────────────────────────────────────

  const contractRows = ref<ContractRow[]>([])

  function loadContractRows(): void {
    const resp = allResponses.value.get('D4-12-rows')
    contractRows.value = safeParseRows<ContractRow>(resp?.remark)
  }

  watch(
    () => allResponses.value.get('D4-12-rows')?.remark,
    () => loadContractRows(),
    { immediate: true },
  )

  const coverageRate = computed<number>(() => {
    const checkedAmount = calcSubtotal(contractRows.value.map(r => parseNum(r.amount)))
    const totalRevenueResp = allResponses.value.get('D4-12-total-revenue')
    const totalRevenue = parseNum(totalRevenueResp?.remark)
    return calcCoverageRate(checkedAmount, totalRevenue)
  })

  // ─── D4-13 ERP核对 ──────────────────────────────────────────────────

  const erpRows = ref<ErpCheckRow[]>([])

  function loadErpRows(): void {
    const resp = allResponses.value.get('D4-13-rows')
    erpRows.value = safeParseRows<ErpCheckRow>(resp?.remark).map(r => ({
      ...r,
      difference: parseNum(r.bookAmount) - parseNum(r.erpAmount),
    }))
  }

  watch(
    () => allResponses.value.get('D4-13-rows')?.remark,
    () => loadErpRows(),
    { immediate: true },
  )

  // ─── D4-14 发生检查 ─────────────────────────────────────────────────

  const occurrenceSampling = ref<SamplingParams>({ ...DEFAULT_SAMPLING })
  const occurrenceRows = ref<VoucherCheckRow[]>([])

  function loadOccurrence(): void {
    const paramsResp = allResponses.value.get('D4-14-params')
    occurrenceSampling.value = safeParseObj(paramsResp?.remark, DEFAULT_SAMPLING)
    const rowsResp = allResponses.value.get('D4-14-rows')
    occurrenceRows.value = safeParseRows<VoucherCheckRow>(rowsResp?.remark)
  }

  watch(
    () => allResponses.value.get('D4-14-rows')?.remark,
    () => loadOccurrence(),
    { immediate: true },
  )

  // ─── D4-15 完整性检查 ───────────────────────────────────────────────

  const completenessSampling = ref<SamplingParams>({ ...DEFAULT_SAMPLING })
  const completenessRows = ref<VoucherCheckRow[]>([])

  function loadCompleteness(): void {
    const paramsResp = allResponses.value.get('D4-15-params')
    completenessSampling.value = safeParseObj(paramsResp?.remark, DEFAULT_SAMPLING)
    const rowsResp = allResponses.value.get('D4-15-rows')
    completenessRows.value = safeParseRows<VoucherCheckRow>(rowsResp?.remark)
  }

  watch(
    () => allResponses.value.get('D4-15-rows')?.remark,
    () => loadCompleteness(),
    { immediate: true },
  )

  // ─── D4-16 出口核对 ─────────────────────────────────────────────────

  const exportRows = ref<ExportCheckRow[]>([])

  function loadExportRows(): void {
    const resp = allResponses.value.get('D4-16-rows')
    exportRows.value = safeParseRows<ExportCheckRow>(resp?.remark).map(r => {
      const converted = parseNum(r.customsAmount) * parseNum(r.exchangeRate)
      return {
        ...r,
        convertedAmount: converted,
        difference: parseNum(r.bookAmount) - converted,
      }
    })
  }

  watch(
    () => allResponses.value.get('D4-16-rows')?.remark,
    () => loadExportRows(),
    { immediate: true },
  )

  // ─── D4-17 截止正向 ─────────────────────────────────────────────────

  const cutoffForwardRows = ref<CutoffRow[]>([])

  function loadCutoffForward(): void {
    const resp = allResponses.value.get('D4-17-rows')
    const bsDate = balanceSheetDate.value
    cutoffForwardRows.value = safeParseRows<CutoffRow>(resp?.remark).map(r => {
      const referenceDate = r.shipDate || r.signDate || r.acceptDate || r.voucherDate
      return {
        ...r,
        isCrossPeriod: isCrossPeriod(r.voucherDate, referenceDate, bsDate),
        crossPeriodDays: calcCrossPeriodDays(r.voucherDate, referenceDate),
      }
    })
  }

  watch(
    () => allResponses.value.get('D4-17-rows')?.remark,
    () => loadCutoffForward(),
    { immediate: true },
  )

  // ─── D4-18 截止反向 ─────────────────────────────────────────────────

  const cutoffBackwardRows = ref<CutoffRow[]>([])

  function loadCutoffBackward(): void {
    const resp = allResponses.value.get('D4-18-rows')
    const bsDate = balanceSheetDate.value
    cutoffBackwardRows.value = safeParseRows<CutoffRow>(resp?.remark).map(r => {
      const referenceDate = r.shipDate || r.signDate || r.acceptDate || r.voucherDate
      return {
        ...r,
        isCrossPeriod: isCrossPeriod(r.voucherDate, referenceDate, bsDate),
        crossPeriodDays: calcCrossPeriodDays(r.voucherDate, referenceDate),
      }
    })
  }

  watch(
    () => allResponses.value.get('D4-18-rows')?.remark,
    () => loadCutoffBackward(),
    { immediate: true },
  )

  // ─── Cutoff Summary ─────────────────────────────────────────────────

  const cutoffSummary = computed(() => {
    const allCutoff = [...cutoffForwardRows.value, ...cutoffBackwardRows.value]
    const crossRows = allCutoff.filter(r => r.isCrossPeriod)
    return {
      total: allCutoff.length,
      crossCount: crossRows.length,
      crossAmount: calcSubtotal(crossRows.map(r => parseNum(r.amount))),
      adjustAmount: calcSubtotal(crossRows.filter(r => r.adjustSuggestion).map(r => parseNum(r.amount))),
    }
  })

  // ─── D4-19 折扣折让 ─────────────────────────────────────────────────

  const discountRows = ref<DiscountRow[]>([])

  function loadDiscountRows(): void {
    const resp = allResponses.value.get('D4-19-rows')
    discountRows.value = safeParseRows<DiscountRow>(resp?.remark).map(r => ({
      ...r,
      netAmount: parseNum(r.originalAmount) - parseNum(r.discountAmount),
    }))
  }

  watch(
    () => allResponses.value.get('D4-19-rows')?.remark,
    () => loadDiscountRows(),
    { immediate: true },
  )

  // ─── D4-20 退货检查 ─────────────────────────────────────────────────

  const returnRows = ref<ReturnRow[]>([])
  const postReturnRows = ref<ReturnRow[]>([])

  function loadReturnRows(): void {
    const resp = allResponses.value.get('D4-20-rows')
    returnRows.value = safeParseRows<ReturnRow>(resp?.remark)
    const postResp = allResponses.value.get('D4-20-post-rows')
    postReturnRows.value = safeParseRows<ReturnRow>(postResp?.remark)
  }

  watch(
    () => allResponses.value.get('D4-20-rows')?.remark,
    () => loadReturnRows(),
    { immediate: true },
  )

  // ─── Generic Row Operations ─────────────────────────────────────────

  function addSample(section: string): void {
    if (readonly.value) return
    switch (section) {
      case 'D4-12':
        contractRows.value.push({
          rowId: generateRowId(), customerName: '', contractNo: '', contractDate: '',
          amount: 0, revenueType: '', performanceObligation: '', recognitionBasis: '',
          conclusion: '', remark: '',
        })
        persistSection('D4-12-rows', contractRows.value)
        break
      case 'D4-13':
        erpRows.value.push({
          rowId: generateRowId(), month: '', bookAmount: 0, erpAmount: 0, difference: 0, explanation: '',
        })
        persistSection('D4-13-rows', erpRows.value)
        break
      case 'D4-14':
        occurrenceRows.value.push({
          rowId: generateRowId(), voucherNo: '', voucherDate: '', customerName: '',
          amount: 0, hasContract: '', hasDelivery: '', hasInvoice: '', isAnomalous: false, remark: '',
        })
        persistSection('D4-14-rows', occurrenceRows.value)
        break
      case 'D4-15':
        completenessRows.value.push({
          rowId: generateRowId(), voucherNo: '', voucherDate: '', customerName: '',
          amount: 0, hasContract: '', hasDelivery: '', hasInvoice: '', isAnomalous: false, remark: '',
        })
        persistSection('D4-15-rows', completenessRows.value)
        break
      case 'D4-16':
        exportRows.value.push({
          rowId: generateRowId(), month: '', bookAmount: 0, customsAmount: 0,
          exchangeRate: 1, convertedAmount: 0, difference: 0, remark: '',
        })
        persistSection('D4-16-rows', exportRows.value)
        break
      case 'D4-17':
        cutoffForwardRows.value.push({
          rowId: generateRowId(), voucherNo: '', voucherDate: '', customerName: '',
          amount: 0, shipDate: '', signDate: '', acceptDate: '',
          isCrossPeriod: false, crossPeriodDays: 0, adjustSuggestion: '', remark: '',
        })
        persistSection('D4-17-rows', cutoffForwardRows.value)
        break
      case 'D4-18':
        cutoffBackwardRows.value.push({
          rowId: generateRowId(), voucherNo: '', voucherDate: '', customerName: '',
          amount: 0, shipDate: '', signDate: '', acceptDate: '',
          isCrossPeriod: false, crossPeriodDays: 0, adjustSuggestion: '', remark: '',
        })
        persistSection('D4-18-rows', cutoffBackwardRows.value)
        break
      case 'D4-19':
        discountRows.value.push({
          rowId: generateRowId(), customerName: '', contractNo: '', discountPolicy: '',
          discountRate: 0, originalAmount: 0, discountAmount: 0, netAmount: 0, isCompliant: '', remark: '',
        })
        persistSection('D4-19-rows', discountRows.value)
        break
      case 'D4-20':
        returnRows.value.push({
          rowId: generateRowId(), customerName: '', returnDate: '', invoiceNo: '',
          productName: '', quantity: 0, amount: 0, reason: '', isPostPeriod: false, remark: '',
        })
        persistSection('D4-20-rows', returnRows.value)
        break
    }
  }

  function removeSample(section: string, rowId: string): void {
    if (readonly.value) return
    switch (section) {
      case 'D4-12':
        contractRows.value = contractRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-12-rows', contractRows.value)
        break
      case 'D4-13':
        erpRows.value = erpRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-13-rows', erpRows.value)
        break
      case 'D4-14':
        occurrenceRows.value = occurrenceRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-14-rows', occurrenceRows.value)
        break
      case 'D4-15':
        completenessRows.value = completenessRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-15-rows', completenessRows.value)
        break
      case 'D4-16':
        exportRows.value = exportRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-16-rows', exportRows.value)
        break
      case 'D4-17':
        cutoffForwardRows.value = cutoffForwardRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-17-rows', cutoffForwardRows.value)
        break
      case 'D4-18':
        cutoffBackwardRows.value = cutoffBackwardRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-18-rows', cutoffBackwardRows.value)
        break
      case 'D4-19':
        discountRows.value = discountRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-19-rows', discountRows.value)
        break
      case 'D4-20':
        returnRows.value = returnRows.value.filter(r => r.rowId !== rowId)
        persistSection('D4-20-rows', returnRows.value)
        break
    }
  }

  // ─── Anomaly Rate helper ────────────────────────────────────────────

  function computeAnomalyRate(rows: VoucherCheckRow[]): number {
    if (rows.length === 0) return 0
    const anomalyCount = rows.filter(r => r.isAnomalous).length
    return calcAnomalyRate(anomalyCount, rows.length)
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
        'D4-12-rows', 'D4-13-rows', 'D4-14-params', 'D4-14-rows',
        'D4-15-params', 'D4-15-rows', 'D4-16-rows',
        'D4-17-rows', 'D4-18-rows', 'D4-19-rows', 'D4-20-rows', 'D4-20-post-rows',
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
    // D4-12
    contractRows,
    coverageRate,
    // D4-13
    erpRows,
    // D4-14
    occurrenceSampling,
    occurrenceRows,
    // D4-15
    completenessSampling,
    completenessRows,
    // D4-16
    exportRows,
    // D4-17/18
    cutoffForwardRows,
    cutoffBackwardRows,
    cutoffSummary,
    // D4-19
    discountRows,
    // D4-20
    returnRows,
    postReturnRows,
    // Helpers
    computeAnomalyRate,
    addSample,
    removeSample,
  }
}

export default useD4Inspection
