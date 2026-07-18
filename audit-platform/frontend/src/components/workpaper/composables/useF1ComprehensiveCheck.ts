/**
 * useF1VoucherCheck — F1-7 预付账款检查表
 *
 * Excel 结构：
 *  一、审计目标
 *  二、样本选取标准与规模
 *  三、(1)本期借方核查 (2)本期贷方核查 (3)期后贷方核查
 *  四、检查比例（账面/核实/比例）+ 审计说明
 *  五、审计结论
 *
 * 借方证据：付款审批单 + 银行回单 + 合同/订单
 * 贷方/期后证据：入库单/验收单 + 发票
 */
import { ref, computed, watch, type Ref, type ComputedRef } from 'vue'
import { parseNum, calcSubtotal, calcAnomalyRate } from './useF1FormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** (1) 本期借方发生额核查行 */
export interface F1DebitCheckRow {
  rowId: string
  supplierName: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetailAccount: string
  debitAmount: number
  // 付款审批单
  approvalDateNo: string
  approvalOk: string
  // 银行回单
  bankPayment: string
  bankPayee: string
  bankAmount: number
  // 合同/发票/定单
  contractName: string
  contractAmount: number
  receiptDoc: string
  indexRef: string
  isAbnormal: string
  remark: string
}

/** (2)(3) 本期贷方 / 期后发生额核查行 */
export interface F1CreditCheckRow {
  rowId: string
  supplierName: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetailAccount: string
  creditAmount: number
  // 入库单/签收单
  recvDateNo: string
  recvItemName: string
  recvUnit: string
  recvQty: string
  // 发票
  invoiceDateNo: string
  invoiceCounterparty: string
  invoiceAmount: number
  indexRef: string
  isAbnormal: string
  remark: string
}

/** @deprecated 旧混合行，仅用于迁移 */
export interface VoucherCheckRow {
  rowId: string
  customerName: string
  date: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  counterDetailAccount: string
  debitAmount?: number
  creditAmount: number
  supportingDoc: string
  checkItems: [boolean, boolean, boolean, boolean, boolean]
  indexRef: string
  isAbnormal: string
  remark: string
}

export interface SamplingParams {
  testName: string
  testPopulation: string
  specificSamples: string
  samplingPopulation: string
  samplingPopulationAmount: number
  samplingPopulationCount: number
  samplingMethod: string
  samplingProcess: string
  targetSampleSize: number
  currentSampleSize: number
  /** 账面金额：本期借方 / 本期贷方 / 期末余额（检查比例基准） */
  bookDebit: number
  bookCredit: number
  bookEndBalance: number
}

export interface CoverageRatioRow {
  direction: string
  bookAmount: number
  checkedAmount: number
  ratio: number | null
}

export interface UseD3VoucherCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

export const F1_SAMPLING_METHOD_OPTIONS = [
  '随机选样',
  '系统选样',
  '货币单元抽样',
  '随意选样',
] as const

// ─── Constants ───────────────────────────────────────────────────────────────

const ITEM_ID_PARAMS = 'F1-vc-params'
const ITEM_ID_DEBIT_ROWS = 'F1-vc-current-rows' // 兼容原 F1-7 导入 item_id
const ITEM_ID_CREDIT_ROWS = 'F1-vc-credit-rows'
const ITEM_ID_POST_ROWS = 'F1-vc-post-rows'
const ITEM_ID_NOTE = 'F1-vc-audit-note'
const ITEM_ID_CONCLUSION = 'F1-vc-audit-conclusion'

// ─── Pure helpers ────────────────────────────────────────────────────────────

export function calcCoverageRatio(checked: number, book: number): number | null {
  if (!book || book === 0) return null
  return Math.round((checked / book) * 10000) / 100
}

export function computeAnomalyRate(rows: { isAbnormal: string }[]): number {
  if (rows.length === 0) return 0
  const anomalyCount = rows.filter(r => r.isAbnormal !== '' && r.isAbnormal != null).length
  return calcAnomalyRate(anomalyCount, rows.length)
}

export function shouldMarkCrossPeriod(voucherDate: Date, revenueDate: Date): boolean {
  return voucherDate < revenueDate
}

function generateRowId(): string {
  return `row-${crypto.randomUUID ? crypto.randomUUID() : Date.now().toString(36) + Math.random().toString(36).slice(2)}`
}

export function createEmptyDebitRow(): F1DebitCheckRow {
  return {
    rowId: generateRowId(),
    supplierName: '',
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterDetailAccount: '',
    debitAmount: 0,
    approvalDateNo: '',
    approvalOk: '',
    bankPayment: '',
    bankPayee: '',
    bankAmount: 0,
    contractName: '',
    contractAmount: 0,
    receiptDoc: '',
    indexRef: '',
    isAbnormal: '',
    remark: '',
  }
}

export function createEmptyCreditRow(): F1CreditCheckRow {
  return {
    rowId: generateRowId(),
    supplierName: '',
    date: '',
    voucherNo: '',
    businessContent: '',
    counterAccount: '',
    counterDetailAccount: '',
    creditAmount: 0,
    recvDateNo: '',
    recvItemName: '',
    recvUnit: '',
    recvQty: '',
    invoiceDateNo: '',
    invoiceCounterparty: '',
    invoiceAmount: 0,
    indexRef: '',
    isAbnormal: '',
    remark: '',
  }
}

export function normalizeDebitRow(raw: any): F1DebitCheckRow {
  return {
    ...createEmptyDebitRow(),
    rowId: raw.rowId || generateRowId(),
    supplierName: raw.supplierName || raw.customerName || '',
    date: raw.date || '',
    voucherNo: raw.voucherNo || '',
    businessContent: raw.businessContent || '',
    counterAccount: raw.counterAccount || '',
    counterDetailAccount: raw.counterDetailAccount || '',
    debitAmount: parseNum(raw.debitAmount),
    approvalDateNo: raw.approvalDateNo || '',
    approvalOk: raw.approvalOk || '',
    bankPayment: raw.bankPayment || '',
    bankPayee: raw.bankPayee || '',
    bankAmount: parseNum(raw.bankAmount),
    contractName: raw.contractName || '',
    contractAmount: parseNum(raw.contractAmount),
    receiptDoc: raw.receiptDoc || raw.supportingDoc || '',
    indexRef: raw.indexRef || '',
    isAbnormal: raw.isAbnormal || '',
    remark: raw.remark || '',
  }
}

export function normalizeCreditRow(raw: any): F1CreditCheckRow {
  return {
    ...createEmptyCreditRow(),
    rowId: raw.rowId || generateRowId(),
    supplierName: raw.supplierName || raw.customerName || '',
    date: raw.date || '',
    voucherNo: raw.voucherNo || '',
    businessContent: raw.businessContent || '',
    counterAccount: raw.counterAccount || '',
    counterDetailAccount: raw.counterDetailAccount || '',
    creditAmount: parseNum(raw.creditAmount),
    recvDateNo: raw.recvDateNo || '',
    recvItemName: raw.recvItemName || '',
    recvUnit: raw.recvUnit || '',
    recvQty: raw.recvQty != null ? String(raw.recvQty) : '',
    invoiceDateNo: raw.invoiceDateNo || '',
    invoiceCounterparty: raw.invoiceCounterparty || '',
    invoiceAmount: parseNum(raw.invoiceAmount),
    indexRef: raw.indexRef || '',
    isAbnormal: raw.isAbnormal || '',
    remark: raw.remark || raw.supportingDoc || '',
  }
}

/**
 * 将旧版「本期增减」混合行（含 debit+credit+checkItems）拆成借方/贷方两表。
 * 有借方金额→借方；仅贷方→贷方；皆无→借方空行保留。
 */
export function migrateLegacyCurrentRows(jsonStr: string | null | undefined): {
  debit: F1DebitCheckRow[]
  credit: F1CreditCheckRow[]
} {
  if (!jsonStr) return { debit: [], credit: [] }
  let parsed: any[]
  try {
    parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return { debit: [], credit: [] }
  } catch {
    return { debit: [], credit: [] }
  }

  const debit: F1DebitCheckRow[] = []
  const credit: F1CreditCheckRow[] = []

  for (const raw of parsed) {
    const debitAmt = parseNum(raw.debitAmount)
    const creditAmt = parseNum(raw.creditAmount)
    const isNewDebit = raw.approvalDateNo != null || raw.bankPayee != null || raw.contractName != null
    const isNewCredit = raw.recvDateNo != null || raw.invoiceDateNo != null

    if (isNewDebit && !isNewCredit) {
      debit.push(normalizeDebitRow(raw))
      continue
    }
    if (isNewCredit && !isNewDebit && debitAmt === 0) {
      credit.push(normalizeCreditRow(raw))
      continue
    }

    // 旧混合行
    if (creditAmt !== 0 && debitAmt === 0) {
      credit.push(normalizeCreditRow({
        ...raw,
        remark: raw.remark || raw.supportingDoc || '',
      }))
    } else {
      debit.push(normalizeDebitRow({
        ...raw,
        receiptDoc: raw.receiptDoc || raw.supportingDoc || '',
      }))
    }
  }

  return { debit, credit }
}

function safeParseDebitRows(jsonStr: string | null | undefined): F1DebitCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    const first = parsed[0]
    if (first && Array.isArray(first.checkItems) && first.approvalDateNo == null) {
      return migrateLegacyCurrentRows(jsonStr).debit
    }
    return parsed.map(normalizeDebitRow)
  } catch {
    return []
  }
}

function safeParseCreditRows(jsonStr: string | null | undefined): F1CreditCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed.map(normalizeCreditRow) : []
  } catch {
    return []
  }
}

function safeParseParams(jsonStr: string | null | undefined): SamplingParams {
  const defaults: SamplingParams = {
    testName: '',
    testPopulation: '',
    specificSamples: '',
    samplingPopulation: '',
    samplingPopulationAmount: 0,
    samplingPopulationCount: 0,
    samplingMethod: '货币单元抽样',
    samplingProcess: '',
    targetSampleSize: 0,
    currentSampleSize: 0,
    bookDebit: 0,
    bookCredit: 0,
    bookEndBalance: 0,
  }
  if (!jsonStr) return defaults
  try {
    const parsed = JSON.parse(jsonStr)
    return { ...defaults, ...parsed }
  } catch {
    return defaults
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1VoucherCheck(options: UseD3VoucherCheckOptions) {
  const { allResponses, debouncedSave, isReadonly } = options

  const samplingParams = ref<SamplingParams>(safeParseParams(null))
  const debitRows = ref<F1DebitCheckRow[]>([])
  const creditRows = ref<F1CreditCheckRow[]>([])
  const postPeriodRows = ref<F1CreditCheckRow[]>([])
  const auditNote = ref('')
  const conclusion = ref('')
  let migratedLegacy = false

  watch(
    () => allResponses.value.get(ITEM_ID_PARAMS)?.remark,
    (jsonStr) => { samplingParams.value = safeParseParams(jsonStr) },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_ID_DEBIT_ROWS)?.remark,
    (jsonStr) => {
      if (!jsonStr) {
        debitRows.value = []
        return
      }
      try {
        const parsed = JSON.parse(jsonStr)
        const first = Array.isArray(parsed) ? parsed[0] : null
        const looksLegacy = first && Array.isArray(first.checkItems) && first.approvalDateNo == null
          && !allResponses.value.get(ITEM_ID_CREDIT_ROWS)?.remark
        if (looksLegacy && !migratedLegacy) {
          const { debit, credit } = migrateLegacyCurrentRows(jsonStr)
          debitRows.value = debit
          creditRows.value = credit
          migratedLegacy = true
          if (!isReadonly.value) {
            debouncedSave(ITEM_ID_DEBIT_ROWS, { remark: JSON.stringify(debit) })
            if (credit.length) {
              debouncedSave(ITEM_ID_CREDIT_ROWS, { remark: JSON.stringify(credit) })
            }
          }
          return
        }
      } catch { /* fall through */ }
      debitRows.value = safeParseDebitRows(jsonStr)
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_ID_CREDIT_ROWS)?.remark,
    (jsonStr) => {
      if (migratedLegacy && !jsonStr) return
      creditRows.value = safeParseCreditRows(jsonStr)
    },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_ID_POST_ROWS)?.remark,
    (jsonStr) => { postPeriodRows.value = safeParseCreditRows(jsonStr) },
    { immediate: true },
  )

  watch(
    () => allResponses.value.get(ITEM_ID_NOTE)?.remark,
    (val) => { auditNote.value = val || '' },
    { immediate: true },
  )
  watch(
    () => allResponses.value.get(ITEM_ID_CONCLUSION)?.remark,
    (val) => { conclusion.value = val || '' },
    { immediate: true },
  )
  watch(() => auditNote.value, (val) => {
    if (!isReadonly.value) debouncedSave(ITEM_ID_NOTE, { remark: val })
  })
  watch(() => conclusion.value, (val) => {
    if (!isReadonly.value) debouncedSave(ITEM_ID_CONCLUSION, { remark: val })
  })

  function persistDebit(): void {
    debouncedSave(ITEM_ID_DEBIT_ROWS, { remark: JSON.stringify(debitRows.value) })
  }
  function persistCredit(): void {
    debouncedSave(ITEM_ID_CREDIT_ROWS, { remark: JSON.stringify(creditRows.value) })
  }
  function persistPost(): void {
    debouncedSave(ITEM_ID_POST_ROWS, { remark: JSON.stringify(postPeriodRows.value) })
  }

  function updateSamplingParams(field: string, value: any): void {
    if (isReadonly.value) return
    ;(samplingParams.value as any)[field] = value
    debouncedSave(ITEM_ID_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  /** 从 F1-2 合计回填账面金额基准 */
  function fillBookFromDetail(totals: { debit: number; credit: number; endAudited: number }): void {
    if (isReadonly.value) return
    samplingParams.value = {
      ...samplingParams.value,
      bookDebit: totals.debit,
      bookCredit: totals.credit,
      bookEndBalance: totals.endAudited,
    }
    debouncedSave(ITEM_ID_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  const debitChecked = computed(() => calcSubtotal(debitRows.value.map(r => r.debitAmount)))
  const creditChecked = computed(() => calcSubtotal(creditRows.value.map(r => r.creditAmount)))
  const postChecked = computed(() => calcSubtotal(postPeriodRows.value.map(r => r.creditAmount)))

  const coverageRows: ComputedRef<CoverageRatioRow[]> = computed(() => [
    {
      direction: '本期借方',
      bookAmount: samplingParams.value.bookDebit,
      checkedAmount: debitChecked.value,
      ratio: calcCoverageRatio(debitChecked.value, samplingParams.value.bookDebit),
    },
    {
      direction: '本期贷方',
      bookAmount: samplingParams.value.bookCredit,
      checkedAmount: creditChecked.value,
      ratio: calcCoverageRatio(creditChecked.value, samplingParams.value.bookCredit),
    },
    {
      direction: '期末余额',
      bookAmount: samplingParams.value.bookEndBalance,
      checkedAmount: postChecked.value,
      ratio: calcCoverageRatio(postChecked.value, samplingParams.value.bookEndBalance),
    },
  ])

  const totalChecked = computed(() =>
    debitRows.value.length + creditRows.value.length + postPeriodRows.value.length,
  )
  const anomalyCount = computed(() => {
    const all = [...debitRows.value, ...creditRows.value, ...postPeriodRows.value]
    return all.filter(r => r.isAbnormal !== '').length
  })
  const anomalyRate = computed(() =>
    computeAnomalyRate([...debitRows.value, ...creditRows.value, ...postPeriodRows.value]),
  )

  const currentChangeRows = debitRows

  type Section = 'debit' | 'credit' | 'postPeriod' | 'current'

  function resolveSection(section: Section): 'debit' | 'credit' | 'postPeriod' {
    if (section === 'current') return 'debit'
    return section
  }

  function addSample(section: Section): void {
    if (isReadonly.value) return
    const s = resolveSection(section)
    if (s === 'debit') {
      debitRows.value = [...debitRows.value, createEmptyDebitRow()]
      persistDebit()
    } else if (s === 'credit') {
      creditRows.value = [...creditRows.value, createEmptyCreditRow()]
      persistCredit()
    } else {
      postPeriodRows.value = [...postPeriodRows.value, createEmptyCreditRow()]
      persistPost()
    }
  }

  function removeSample(section: Section, rowId: string): void {
    if (isReadonly.value) return
    const s = resolveSection(section)
    if (s === 'debit') {
      debitRows.value = debitRows.value.filter(r => r.rowId !== rowId)
      persistDebit()
    } else if (s === 'credit') {
      creditRows.value = creditRows.value.filter(r => r.rowId !== rowId)
      persistCredit()
    } else {
      postPeriodRows.value = postPeriodRows.value.filter(r => r.rowId !== rowId)
      persistPost()
    }
  }

  const DEBIT_NUM = new Set(['debitAmount', 'bankAmount', 'contractAmount'])
  const CREDIT_NUM = new Set(['creditAmount', 'invoiceAmount'])

  function updateCell(section: Section, rowId: string, field: string, value: any): void {
    if (isReadonly.value) return
    const s = resolveSection(section)

    if (s === 'debit') {
      const idx = debitRows.value.findIndex(r => r.rowId === rowId)
      if (idx === -1) return
      const row = { ...debitRows.value[idx] }
      ;(row as any)[field] = DEBIT_NUM.has(field) ? parseNum(value) : value
      const next = [...debitRows.value]
      next[idx] = row
      debitRows.value = next
      persistDebit()
      return
    }

    const rows = s === 'credit' ? creditRows.value : postPeriodRows.value
    const idx = rows.findIndex(r => r.rowId === rowId)
    if (idx === -1) return
    const row = { ...rows[idx] }
    ;(row as any)[field] = CREDIT_NUM.has(field) ? parseNum(value) : value
    const next = [...rows]
    next[idx] = row
    if (s === 'credit') {
      creditRows.value = next
      persistCredit()
    } else {
      postPeriodRows.value = next
      persistPost()
    }
  }

  function autoMarkCrossPeriod(revenueRecognitionDate: string): void {
    if (isReadonly.value || !revenueRecognitionDate) return
    const revenueDate = new Date(revenueRecognitionDate)
    if (isNaN(revenueDate.getTime())) return
    let changed = false
    const newRows = postPeriodRows.value.map(row => {
      if (!row.date) return row
      const voucherDate = new Date(row.date)
      if (isNaN(voucherDate.getTime())) return row
      if (shouldMarkCrossPeriod(voucherDate, revenueDate) && row.isAbnormal !== '跨期疑点') {
        changed = true
        return { ...row, isAbnormal: '跨期疑点' }
      }
      return row
    })
    if (changed) {
      postPeriodRows.value = newRows
      persistPost()
    }
  }

  /** 抽凭回填：按借贷分配到借方/贷方表 */
  function distributeSamples(samples: Array<Record<string, any>>): void {
    if (isReadonly.value || !samples.length) return
    const debitAdd: F1DebitCheckRow[] = []
    const creditAdd: F1CreditCheckRow[] = []
    for (const s of samples) {
      const debitAmt = parseNum(s.debitAmount ?? s.amount)
      const creditAmt = parseNum(s.creditAmount)
      const base = {
        supplierName: s.counterpartName || s.customerName || s.supplierName || '',
        date: s.voucherDate || s.date || '',
        voucherNo: s.voucherNo || '',
        businessContent: s.summary || s.businessContent || '',
        counterAccount: s.counterpartAccount || s.counterAccount || '',
        counterDetailAccount: s.counterDetailAccount || '',
      }
      if (creditAmt > 0 && debitAmt === 0) {
        creditAdd.push(normalizeCreditRow({ ...base, creditAmount: creditAmt }))
      } else {
        debitAdd.push(normalizeDebitRow({ ...base, debitAmount: debitAmt || creditAmt }))
      }
    }
    if (debitAdd.length) {
      debitRows.value = [...debitRows.value, ...debitAdd]
      persistDebit()
    }
    if (creditAdd.length) {
      creditRows.value = [...creditRows.value, ...creditAdd]
      persistCredit()
    }
    updateSamplingParams(
      'currentSampleSize',
      debitRows.value.length + creditRows.value.length + postPeriodRows.value.length,
    )
  }

  return {
    samplingParams,
    debitRows,
    creditRows,
    postPeriodRows,
    currentChangeRows,
    auditNote,
    conclusion,
    coverageRows,
    debitChecked,
    creditChecked,
    postChecked,
    totalChecked,
    anomalyCount,
    anomalyRate,
    addSample,
    removeSample,
    updateCell,
    updateSamplingParams,
    fillBookFromDetail,
    autoMarkCrossPeriod,
    distributeSamples,
  }
}

export default useF1VoucherCheck
