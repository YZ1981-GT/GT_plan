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
  /** 账面金额：本期借方 / 本期贷方 / 期后贷方（检查比例基准；对齐 F1-2 借/贷/Z列） */
  bookDebit: number
  bookCredit: number
  bookPostPeriod: number
  /** @deprecated 旧口径「期末余额」，读取时迁入 bookPostPeriod（若后者为 0） */
  bookEndBalance?: number
}

export interface CoverageRatioRow {
  direction: string
  bookAmount: number
  checkedAmount: number
  ratio: number | null
}

export interface UseF1VoucherCheckOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveImmediate: (itemId: string, data: Partial<ChecklistResponse>) => Promise<void>
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void
  isReadonly: Ref<boolean>
}

export type F1EvidenceKind = 'payment' | 'purchase'
export type F1VoucherSection = 'debit' | 'credit' | 'postPeriod'

export function f1SectionEvidenceKind(section: F1VoucherSection): F1EvidenceKind {
  return section === 'debit' ? 'payment' : 'purchase'
}

export const F1_VOUCHER_SECTION_LABELS: Record<F1VoucherSection, string> = {
  debit: '本期借方',
  credit: '本期贷方',
  postPeriod: '期后贷方',
}

export interface F1EvidenceCheck {
  key: string
  label: string
  status: 'ok' | 'missing' | 'mismatch'
  detail: string
}

/** 借方证据勾稽：凭证 / 审批 / 银行回单 / 合同 */
export function evaluateF1DebitEvidence(row: F1DebitCheckRow): F1EvidenceCheck[] {
  const checks: F1EvidenceCheck[] = []
  if (row.voucherNo && parseNum(row.debitAmount) > 0) {
    checks.push({
      key: 'voucher',
      label: '记账凭证',
      status: 'ok',
      detail: `${row.supplierName || '未填供应商'} / ${row.voucherNo} / ${parseNum(row.debitAmount).toLocaleString('zh-CN')}`,
    })
  } else {
    checks.push({ key: 'voucher', label: '记账凭证', status: 'missing', detail: '供应商、凭证编号或借方金额未完整登记' })
  }

  if (!row.approvalDateNo) {
    checks.push({ key: 'approval', label: '付款审批单', status: 'missing', detail: '未登记审批单日期/编号' })
  } else if (row.approvalOk === 'N' || row.approvalOk === '否') {
    checks.push({ key: 'approval', label: '付款审批单', status: 'mismatch', detail: '审批不恰当，需说明' })
  } else {
    checks.push({
      key: 'approval',
      label: '付款审批单',
      status: 'ok',
      detail: `${row.approvalDateNo}${row.approvalOk === 'Y' || row.approvalOk === '是' ? ' / 审批恰当' : ''}`,
    })
  }

  const bankAmt = parseNum(row.bankAmount)
  if (!row.bankPayee && !bankAmt) {
    checks.push({ key: 'bank', label: '银行回单', status: 'missing', detail: '未登记银行回单收款方/金额' })
  } else if (bankAmt > 0 && Math.abs(bankAmt - parseNum(row.debitAmount)) > 0.01) {
    checks.push({
      key: 'bank',
      label: '银行回单',
      status: 'mismatch',
      detail: `回单金额 ${bankAmt.toLocaleString('zh-CN')} ≠ 借方 ${parseNum(row.debitAmount).toLocaleString('zh-CN')}`,
    })
  } else {
    checks.push({
      key: 'bank',
      label: '银行回单',
      status: 'ok',
      detail: `${row.bankPayee || '已登记'}${bankAmt ? ` / ${bankAmt.toLocaleString('zh-CN')}` : ''}`,
    })
  }

  if (!row.contractName && !parseNum(row.contractAmount)) {
    checks.push({ key: 'contract', label: '合同/订单', status: 'missing', detail: '未登记合同或订单' })
  } else {
    checks.push({
      key: 'contract',
      label: '合同/订单',
      status: 'ok',
      detail: `${row.contractName || '已登记'}${parseNum(row.contractAmount) ? ` / ${parseNum(row.contractAmount).toLocaleString('zh-CN')}` : ''}`,
    })
  }
  return checks
}

/** 贷方/期后证据勾稽：凭证 / 入库验收 / 发票 */
export function evaluateF1CreditEvidence(row: F1CreditCheckRow): F1EvidenceCheck[] {
  const checks: F1EvidenceCheck[] = []
  if (row.voucherNo && parseNum(row.creditAmount) > 0) {
    checks.push({
      key: 'voucher',
      label: '记账凭证',
      status: 'ok',
      detail: `${row.supplierName || '未填供应商'} / ${row.voucherNo} / ${parseNum(row.creditAmount).toLocaleString('zh-CN')}`,
    })
  } else {
    checks.push({ key: 'voucher', label: '记账凭证', status: 'missing', detail: '供应商、凭证编号或贷方金额未完整登记' })
  }

  if (!row.recvDateNo && !row.recvItemName) {
    checks.push({ key: 'recv', label: '入库/验收单', status: 'missing', detail: '未登记入库或验收单据' })
  } else {
    checks.push({
      key: 'recv',
      label: '入库/验收单',
      status: 'ok',
      detail: `${row.recvDateNo || ''}${row.recvItemName ? ` / ${row.recvItemName}` : ''}`.trim() || '已登记',
    })
  }

  const invAmt = parseNum(row.invoiceAmount)
  if (!row.invoiceDateNo && !invAmt) {
    checks.push({ key: 'invoice', label: '发票', status: 'missing', detail: '未登记发票' })
  } else if (invAmt > 0 && Math.abs(invAmt - parseNum(row.creditAmount)) > 0.01) {
    checks.push({
      key: 'invoice',
      label: '发票',
      status: 'mismatch',
      detail: `发票金额 ${invAmt.toLocaleString('zh-CN')} ≠ 贷方 ${parseNum(row.creditAmount).toLocaleString('zh-CN')}`,
    })
  } else {
    checks.push({
      key: 'invoice',
      label: '发票',
      status: 'ok',
      detail: `${row.invoiceCounterparty || row.invoiceDateNo || '已登记'}${invAmt ? ` / ${invAmt.toLocaleString('zh-CN')}` : ''}`,
    })
  }
  return checks
}

export function evaluateF1Evidence(
  section: F1VoucherSection,
  row: F1DebitCheckRow | F1CreditCheckRow,
): F1EvidenceCheck[] {
  return section === 'debit'
    ? evaluateF1DebitEvidence(row as F1DebitCheckRow)
    : evaluateF1CreditEvidence(row as F1CreditCheckRow)
}

export function f1EvidenceStatusLabel(checks: F1EvidenceCheck[]): {
  type: 'success' | 'warning' | 'danger'
  label: string
} {
  if (checks.some(c => c.status === 'mismatch')) return { type: 'danger', label: '勾稽不符' }
  if (checks.some(c => c.status === 'missing')) return { type: 'warning', label: '单据待补' }
  return { type: 'success', label: '勾稽完成' }
}

export const F1_SAMPLING_METHOD_OPTIONS = [
  '随机选样',
  '系统选样',
  '货币单元抽样',
  '随意选样',
] as const

export const F1_YES_NO_OPTIONS = [
  { value: 'Y', label: '是' },
  { value: 'N', label: '否' },
] as const

export const F1_ABNORMAL_OPTIONS = [
  { value: '', label: '—' },
  { value: 'N', label: '无异常' },
  { value: '金额不符', label: '金额不符' },
  { value: '单据缺失', label: '单据缺失' },
  { value: '审批瑕疵', label: '审批瑕疵' },
  { value: '跨期疑点', label: '跨期疑点' },
  { value: '其他异常', label: '其他异常' },
] as const

/** 是否计为异常：排除空 / N / 否 / 无 / 正常 */
export function isAbnormalFlag(flag: string | null | undefined): boolean {
  const v = String(flag || '').trim()
  if (!v) return false
  const upper = v.toUpperCase()
  if (upper === 'N' || upper === 'NO' || upper === 'FALSE' || upper === '0') return false
  if (v === '否' || v === '无' || v === '无异常' || v === '正常') return false
  return true
}

export interface F1DetailSampleSource {
  customerName: string
  endAudited?: number
  debit?: number
  credit?: number
  relationType?: string
  agingAudited?: Record<string, number>
  postPeriodSettlement?: number
}

/** 从 F1-2 筛选重点样本：关联方 / 超1年账龄 / 大额（默认 topN 或阈值） */
export function selectPrioritySamplesFromDetail(
  rows: F1DetailSampleSource[],
  opts?: { largeThreshold?: number; topN?: number },
): Array<{ supplierName: string; debitAmount: number; creditAmount: number; reason: string }> {
  const threshold = opts?.largeThreshold ?? 0
  const topN = opts?.topN ?? 10
  const data = rows.filter(r => String(r.customerName || '').trim() && !String(r.customerName).startsWith('__'))
  const byBalance = [...data].sort((a, b) => parseNum(b.endAudited) - parseNum(a.endAudited))
  const largeNames = new Set(
    byBalance
      .filter((r, i) => {
        const bal = parseNum(r.endAudited)
        if (bal <= 0) return false
        if (i < topN) return true
        return threshold > 0 && bal >= threshold
      })
      .map(r => r.customerName),
  )

  const out: Array<{ supplierName: string; debitAmount: number; creditAmount: number; reason: string }> = []
  const seen = new Set<string>()
  for (const r of data) {
    const name = String(r.customerName).trim()
    if (seen.has(name)) continue
    const reasons: string[] = []
    const rel = String(r.relationType || '').trim()
    if (rel && rel !== '非关联方') reasons.push(`关联方:${rel}`)
    const aging = r.agingAudited || {}
    const over1 = Object.entries(aging).reduce((sum, [k, v]) => {
      const key = k.toLowerCase()
      const isWithin1 = key.includes('within') || key === 'y0to1' || key === 'within1' || key === 'lte1'
      return isWithin1 ? sum : sum + parseNum(v)
    }, 0)
    if (over1 > 0.01) reasons.push('超1年账龄')
    if (largeNames.has(name) && parseNum(r.endAudited) > 0) reasons.push('大额')
    if (!reasons.length) continue
    seen.add(name)
    out.push({
      supplierName: name,
      debitAmount: parseNum(r.debit) || parseNum(r.endAudited),
      creditAmount: parseNum(r.credit),
      reason: reasons.join('；'),
    })
  }
  return out.sort((a, b) => b.debitAmount - a.debitAmount)
}

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
  const anomalyCount = rows.filter(r => isAbnormalFlag(r.isAbnormal)).length
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
    bookPostPeriod: 0,
  }
  if (!jsonStr) return defaults
  try {
    const parsed = JSON.parse(jsonStr)
    const merged: SamplingParams = { ...defaults, ...parsed }
    // 旧口径 bookEndBalance → bookPostPeriod（仅当新字段为空）
    if (!merged.bookPostPeriod && parseNum(parsed.bookEndBalance) > 0) {
      merged.bookPostPeriod = parseNum(parsed.bookEndBalance)
    }
    return merged
  } catch {
    return defaults
  }
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useF1VoucherCheck(options: UseF1VoucherCheckOptions) {
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

  /** 从 F1-2 合计回填账面金额基准（借/贷发生额 + 期后结转 Z 列） */
  function fillBookFromDetail(totals: {
    debit: number
    credit: number
    postPeriodSettlement: number
    /** @deprecated 兼容旧调用方 */
    endAudited?: number
  }): void {
    if (isReadonly.value) return
    samplingParams.value = {
      ...samplingParams.value,
      bookDebit: totals.debit,
      bookCredit: totals.credit,
      bookPostPeriod: totals.postPeriodSettlement || parseNum(totals.endAudited),
    }
    debouncedSave(ITEM_ID_PARAMS, { remark: JSON.stringify(samplingParams.value) })
  }

  /** 从 F1-2 重点户（关联方/超1年/大额）插入借方样本行，已存在同名跳过 */
  function importPrioritySamples(sources: F1DetailSampleSource[]): number {
    if (isReadonly.value) return 0
    const picked = selectPrioritySamplesFromDetail(sources)
    if (!picked.length) return 0
    const existing = new Set(debitRows.value.map(r => r.supplierName.trim().toLowerCase()))
    const toAdd: F1DebitCheckRow[] = []
    for (const p of picked) {
      const key = p.supplierName.trim().toLowerCase()
      if (!key || existing.has(key)) continue
      existing.add(key)
      toAdd.push(normalizeDebitRow({
        supplierName: p.supplierName,
        debitAmount: p.debitAmount,
        businessContent: `重点样本：${p.reason}`,
        indexRef: 'wp:F1-2',
      }))
    }
    if (!toAdd.length) return 0
    debitRows.value = [...debitRows.value, ...toAdd]
    persistDebit()
    const reasons = picked.map(p => p.supplierName).slice(0, 8).join('、')
    updateSamplingParams(
      'specificSamples',
      [samplingParams.value.specificSamples, `重点样本：${reasons}${picked.length > 8 ? '…' : ''}`]
        .filter(Boolean)
        .join('；'),
    )
    updateSamplingParams(
      'currentSampleSize',
      debitRows.value.length + creditRows.value.length + postPeriodRows.value.length,
    )
    return toAdd.length
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
      direction: '期后贷方',
      bookAmount: samplingParams.value.bookPostPeriod,
      checkedAmount: postChecked.value,
      ratio: calcCoverageRatio(postChecked.value, samplingParams.value.bookPostPeriod),
    },
  ])

  const totalChecked = computed(() =>
    debitRows.value.length + creditRows.value.length + postPeriodRows.value.length,
  )
  const anomalyCount = computed(() => {
    const all = [...debitRows.value, ...creditRows.value, ...postPeriodRows.value]
    return all.filter(r => isAbnormalFlag(r.isAbnormal)).length
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

  function saveRow(
    section: F1VoucherSection,
    patch: F1DebitCheckRow | F1CreditCheckRow,
  ): void {
    if (isReadonly.value) return
    if (section === 'debit') {
      const idx = debitRows.value.findIndex(r => r.rowId === patch.rowId)
      if (idx === -1) return
      const next = [...debitRows.value]
      next[idx] = normalizeDebitRow(patch)
      debitRows.value = next
      persistDebit()
      return
    }
    const rows = section === 'credit' ? creditRows.value : postPeriodRows.value
    const idx = rows.findIndex(r => r.rowId === patch.rowId)
    if (idx === -1) return
    const next = [...rows]
    next[idx] = normalizeCreditRow(patch)
    if (section === 'credit') {
      creditRows.value = next
      persistCredit()
    } else {
      postPeriodRows.value = next
      persistPost()
    }
  }

  /** 期后区：凭证日期早于资产负债表日/截止基准日 → 标「跨期疑点」 */
  function autoMarkCrossPeriod(cutoffDate: string): number {
    if (isReadonly.value || !cutoffDate) return 0
    const cutoff = new Date(cutoffDate)
    if (isNaN(cutoff.getTime())) return 0
    let changed = 0
    const newRows = postPeriodRows.value.map(row => {
      if (!row.date) return row
      const voucherDate = new Date(row.date)
      if (isNaN(voucherDate.getTime())) return row
      if (shouldMarkCrossPeriod(voucherDate, cutoff) && row.isAbnormal !== '跨期疑点') {
        changed += 1
        return { ...row, isAbnormal: '跨期疑点' }
      }
      return row
    })
    if (changed) {
      postPeriodRows.value = newRows
      persistPost()
    }
    return changed
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
    saveRow,
    updateSamplingParams,
    fillBookFromDetail,
    importPrioritySamples,
    autoMarkCrossPeriod,
    distributeSamples,
  }
}

export default useF1VoucherCheck
