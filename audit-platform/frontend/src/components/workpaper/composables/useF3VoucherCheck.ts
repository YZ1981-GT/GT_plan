/**
 * useF3VoucherCheck — F3-7 应付票据检查表
 *
 * 对齐源表三个检查区：
 *  1. 本期借方金额检查（票据减少·兑付）：记账凭证 + 付款审批单 + 银行回单
 *  2. 本期贷方金额检查（票据增加·开票）：记账凭证 + 入库单/验收单 + 采购发票
 *  3. 资产负债表日后借方检查：结构同借方区，关注应计未计
 * 每笔通过弹窗逐单据上传OCR核对（参照F2-56模式），并计算检查比例。
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { calcSubtotal, parseNum } from './useF3FormulaEngine'
import type { UseF3BaseOptions } from './useF3Adjudication'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'
import { rowClosingAdjusted, rowPeriodCredit, rowPeriodDebit } from './useF3CrossSheet'

export type F3VoucherSection = 'debit' | 'credit' | 'subsequent'

/** 检查区证据模式：payment=付款审批单+银行回单；purchase=入库单+采购发票 */
export type F3EvidenceKind = 'payment' | 'purchase'

export function sectionEvidenceKind(section: F3VoucherSection): F3EvidenceKind {
  return section === 'credit' ? 'purchase' : 'payment'
}

export const F3_VOUCHER_NOTE_TYPES = ['银行承兑汇票', '商业承兑汇票', '供应链票据', '其他'] as const

export interface F3VoucherCheckRow {
  rowId: string
  seq: number
  attSlot: number
  // 记账凭证
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  detailAccount: string
  amount: number
  noteType: string
  // 付款审批单（借方/日后区）
  approvalDateNo: string
  approvalProper: string
  // 银行回单（借方/日后区）
  bankReceiptDate: string
  bankPayee: string
  bankAmount: number
  // 入库单/验收单（贷方区）
  receiptDateNo: string
  receiptProduct: string
  receiptUnit: string
  receiptQty: number
  // 采购发票（贷方区）
  invoiceDateNo: string
  invoiceCounterparty: string
  invoiceAmount: number
  otherEvidence: string
  indexNo: string
  isAbnormal: string
  issueDesc: string
  sampleSource: string
}

export interface F3VoucherEvidenceCheck {
  key: string
  label: string
  status: 'ok' | 'missing' | 'mismatch'
  detail: string
}

const ITEM_KEYS: Record<F3VoucherSection, string> = {
  debit: 'F3-7-debit-rows',
  credit: 'F3-7-credit-rows',
  subsequent: 'F3-7-subsequent-rows',
}

export const F3_VOUCHER_SECTION_LABELS: Record<F3VoucherSection, string> = {
  debit: '1. 本期借方金额检查（票据减少·到期兑付/背书转让）',
  credit: '2. 本期贷方金额检查（票据增加·开票承兑）',
  subsequent: '3. 资产负债表日后借方检查（日后偿付·应计未计）',
}

function generateRowId(): string {
  return `f3v-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function emptyVoucherRow(seq: number, attSlot = seq): F3VoucherCheckRow {
  return {
    rowId: generateRowId(), seq, attSlot,
    voucherDate: '', voucherNo: '', businessContent: '', counterAccount: '',
    detailAccount: '', amount: 0, noteType: '',
    approvalDateNo: '', approvalProper: '',
    bankReceiptDate: '', bankPayee: '', bankAmount: 0,
    receiptDateNo: '', receiptProduct: '', receiptUnit: '', receiptQty: 0,
    invoiceDateNo: '', invoiceCounterparty: '', invoiceAmount: 0,
    otherEvidence: '', indexNo: '', isAbnormal: '', issueDesc: '', sampleSource: '',
  }
}

export function isBlankVoucherRow(row: F3VoucherCheckRow): boolean {
  return !row.voucherDate && !row.voucherNo && !row.businessContent && !row.counterAccount
    && !row.detailAccount && !row.amount && !row.noteType && !row.approvalDateNo
    && !row.bankReceiptDate && !row.bankPayee && !row.bankAmount && !row.receiptDateNo
    && !row.receiptProduct && !row.receiptQty && !row.invoiceDateNo && !row.invoiceCounterparty
    && !row.invoiceAmount && !row.otherEvidence && !row.indexNo && !row.isAbnormal && !row.issueDesc
}

/** 逐笔证据勾稽（参照F2-56 evaluateContractCostEvidence） */
export function evaluateF3VoucherEvidence(
  row: F3VoucherCheckRow,
  kind: F3EvidenceKind,
): F3VoucherEvidenceCheck[] {
  const checks: F3VoucherEvidenceCheck[] = []

  if (row.voucherNo && row.amount > 0) {
    checks.push({ key: 'voucher', label: '记账凭证', status: 'ok', detail: `${row.voucherNo} / ${row.amount.toLocaleString('zh-CN')}` })
  } else {
    checks.push({ key: 'voucher', label: '记账凭证', status: 'missing', detail: '凭证编号或金额未登记' })
  }

  if (kind === 'payment') {
    if (!row.approvalDateNo) {
      checks.push({ key: 'approval', label: '付款审批单', status: 'missing', detail: '未登记审批单日期/编号' })
    } else if (row.approvalProper === '否') {
      checks.push({ key: 'approval', label: '付款审批单', status: 'mismatch', detail: '审批不恰当，需说明' })
    } else {
      checks.push({ key: 'approval', label: '付款审批单', status: 'ok', detail: `${row.approvalDateNo}${row.approvalProper ? ` / 审批${row.approvalProper === '是' ? '恰当' : row.approvalProper}` : ''}` })
    }

    if (!row.bankReceiptDate && !row.bankAmount) {
      checks.push({ key: 'bank', label: '银行回单', status: 'missing', detail: '未登记银行回单' })
    } else if (row.amount > 0 && row.bankAmount > 0 && Math.abs(row.bankAmount - row.amount) > 0.01) {
      checks.push({ key: 'bank', label: '银行回单', status: 'mismatch', detail: `回单金额 ${row.bankAmount.toLocaleString('zh-CN')} 与凭证金额不符` })
    } else {
      checks.push({ key: 'bank', label: '银行回单', status: 'ok', detail: `${row.bankReceiptDate}${row.bankPayee ? ` / ${row.bankPayee}` : ''}` })
    }
  } else {
    if (!row.receiptDateNo && !row.receiptProduct) {
      checks.push({ key: 'receipt', label: '入库单/验收单', status: 'missing', detail: '未登记入库/验收信息' })
    } else {
      checks.push({ key: 'receipt', label: '入库单/验收单', status: 'ok', detail: `${row.receiptDateNo}${row.receiptProduct ? ` / ${row.receiptProduct}` : ''}${row.receiptQty ? ` × ${row.receiptQty}` : ''}` })
    }

    if (!row.invoiceDateNo && !row.invoiceAmount) {
      checks.push({ key: 'invoice', label: '采购发票', status: 'missing', detail: '未登记采购发票' })
    } else if (row.amount > 0 && row.invoiceAmount > 0 && Math.abs(row.invoiceAmount - row.amount) > 0.01) {
      checks.push({ key: 'invoice', label: '采购发票', status: 'mismatch', detail: `发票金额 ${row.invoiceAmount.toLocaleString('zh-CN')} 与凭证金额不符` })
    } else {
      checks.push({ key: 'invoice', label: '采购发票', status: 'ok', detail: `${row.invoiceDateNo}${row.invoiceCounterparty ? ` / ${row.invoiceCounterparty}` : ''}` })
    }
  }

  return checks
}

function migrateRow(raw: any, i: number, section: F3VoucherSection): F3VoucherCheckRow {
  const base = emptyVoucherRow(i + 1, Number(raw.attSlot) || i + 1)
  const legacyIssue = [
    raw.purchaseContractCheck ? `采购合同核对：${raw.purchaseContractCheck}` : '',
    raw.goodsReceiptCheck ? `商品验收核对：${raw.goodsReceiptCheck}` : '',
    raw.bankReconciliation ? `银行对账：${raw.bankReconciliation}` : '',
    raw.isOverduePayment ? `是否逾期付款：${raw.isOverduePayment}` : '',
    raw.auditConclusion && raw.auditConclusion !== '无异常' ? raw.auditConclusion : '',
    raw.remark,
  ].filter(Boolean).join('；')
  const legacyAbnormal = raw.auditConclusion && raw.auditConclusion !== '无异常' ? '是'
    : raw.auditConclusion === '无异常' ? '否' : ''
  return {
    ...base,
    rowId: raw.rowId || raw.id || generateRowId(),
    seq: raw.seq ?? i + 1,
    voucherDate: String(raw.voucherDate || ''),
    voucherNo: String(raw.voucherNo || ''),
    businessContent: String(raw.businessContent ?? raw.summary ?? ''),
    counterAccount: String(raw.counterAccount || ''),
    detailAccount: String(raw.detailAccount || ''),
    amount: parseNum(raw.amount),
    noteType: String(raw.noteType || ''),
    approvalDateNo: String(raw.approvalDateNo || ''),
    approvalProper: String(raw.approvalProper || ''),
    bankReceiptDate: String(raw.bankReceiptDate || ''),
    bankPayee: String(raw.bankPayee || (section !== 'credit' ? raw.acceptor || '' : '')),
    bankAmount: parseNum(raw.bankAmount),
    receiptDateNo: String(raw.receiptDateNo || ''),
    receiptProduct: String(raw.receiptProduct || ''),
    receiptUnit: String(raw.receiptUnit || ''),
    receiptQty: parseNum(raw.receiptQty),
    invoiceDateNo: String(raw.invoiceDateNo || ''),
    invoiceCounterparty: String(raw.invoiceCounterparty || (section === 'credit' ? raw.acceptor || '' : '')),
    invoiceAmount: parseNum(raw.invoiceAmount),
    otherEvidence: String(raw.otherEvidence || ''),
    indexNo: String(raw.indexNo || ''),
    isAbnormal: String(raw.isAbnormal || legacyAbnormal),
    issueDesc: String(raw.issueDesc || legacyIssue),
    sampleSource: String(raw.sampleSource || ''),
  }
}

export function safeParseVoucherRows(
  jsonStr: string | null | undefined,
  section: F3VoucherSection,
): F3VoucherCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    const rows = parsed.map((raw, i) => migrateRow(raw, i, section))
    const pruned = rows.filter((row) => !isBlankVoucherRow(row))
    const kept = pruned.length ? pruned : rows.slice(0, 1)
    return kept.map((row, i) => ({ ...row, seq: i + 1 }))
  } catch {
    return []
  }
}

/** 检查比例：从 F3-2 明细行汇总账面数（借方=本期承兑、贷方=本期开票、期末=审定数） */
export function calcF3BookAmounts(f3DetailJson: string | null | undefined): {
  bookDebit: number
  bookCredit: number
  bookClosing: number
} {
  const empty = { bookDebit: 0, bookCredit: 0, bookClosing: 0 }
  if (!f3DetailJson) return empty
  try {
    const rows = JSON.parse(f3DetailJson)
    if (!Array.isArray(rows)) return empty
    return {
      bookDebit: calcSubtotal(rows.map((r: any) => rowPeriodDebit(r))),
      bookCredit: calcSubtotal(rows.map((r: any) => rowPeriodCredit(r))),
      bookClosing: calcSubtotal(rows.map((r: any) => rowClosingAdjusted(r))),
    }
  } catch {
    return empty
  }
}

export function useF3VoucherCheck(options: UseF3BaseOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null

  const stored: Record<F3VoucherSection, ReturnType<typeof ref<F3VoucherCheckRow[]>>> = {
    debit: ref<F3VoucherCheckRow[]>([]),
    credit: ref<F3VoucherCheckRow[]>([]),
    subsequent: ref<F3VoucherCheckRow[]>([]),
  }
  const auditConclusion = ref('')

  function loadSection(section: F3VoucherSection): void {
    const target = stored[section]
    target.value = safeParseVoucherRows(allResponses.value.get(ITEM_KEYS[section])?.remark, section)
    if (!target.value || target.value.length === 0) target.value = [emptyVoucherRow(1)]
  }

  for (const section of ['debit', 'credit', 'subsequent'] as F3VoucherSection[]) {
    watch(() => allResponses.value.get(ITEM_KEYS[section])?.remark, (raw) => {
      if (raw && raw === JSON.stringify(stored[section].value)) return
      if (!stored[section].value || stored[section].value.length === 0) loadSection(section)
    }, { immediate: true })
  }

  watch(() => allResponses.value.get('F3-7-conclusion')?.remark, (v) => {
    auditConclusion.value = v || ''
  }, { immediate: true })

  const debitRows = computed(() => stored.debit.value ?? []) as ComputedRef<F3VoucherCheckRow[]>
  const creditRows = computed(() => stored.credit.value ?? []) as ComputedRef<F3VoucherCheckRow[]>
  const subsequentRows = computed(() => stored.subsequent.value ?? []) as ComputedRef<F3VoucherCheckRow[]>

  function sectionRows(section: F3VoucherSection): ComputedRef<F3VoucherCheckRow[]> {
    return section === 'debit' ? debitRows : section === 'credit' ? creditRows : subsequentRows
  }

  const debitTotal = computed(() => calcSubtotal(debitRows.value.map((r) => r.amount)))
  const creditTotal = computed(() => calcSubtotal(creditRows.value.map((r) => r.amount)))
  const subsequentTotal = computed(() => calcSubtotal(subsequentRows.value.map((r) => r.amount)))

  const debitAbnormal = computed(() => debitRows.value.filter((r) => r.isAbnormal === '是').length)
  const creditAbnormal = computed(() => creditRows.value.filter((r) => r.isAbnormal === '是').length)
  const subsequentAbnormal = computed(() => subsequentRows.value.filter((r) => r.isAbnormal === '是').length)

  /** 检查比例（账面金额取自 F3-2 明细表） */
  const checkRatios = computed(() => {
    const book = calcF3BookAmounts(allResponses.value.get('F3-2-rows')?.remark)
    const build = (label: string, bookAmount: number, checkedAmount: number) => ({
      label,
      bookAmount,
      checkedAmount,
      ratio: bookAmount > 0 ? Math.round((checkedAmount / bookAmount) * 10000) / 100 : 0,
    })
    return [
      build('本期借方', book.bookDebit, debitTotal.value),
      build('本期贷方', book.bookCredit, creditTotal.value),
      build('期末余额', book.bookClosing, subsequentTotal.value),
    ]
  })

  function nextAttSlot(section: F3VoucherSection): number {
    const rows = stored[section].value ?? []
    return Math.max(0, ...rows.map((r) => Number(r.attSlot) || 0)) + 1
  }

  function addRow(section: F3VoucherSection): void {
    if (readonly.value) return
    const target = stored[section]
    target.value = [...(target.value ?? []), emptyVoucherRow((target.value?.length ?? 0) + 1, nextAttSlot(section))]
    persistRows()
  }

  function removeRow(section: F3VoucherSection, rowId: string): void {
    if (readonly.value) return
    const target = stored[section]
    const rows = target.value ?? []
    if (rows.length <= 1) return
    const idx = rows.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    rows.splice(idx, 1)
    rows.forEach((r, i) => { r.seq = i + 1 })
    persistRows()
  }

  function updateCell(section: F3VoucherSection, rowId: string, field: string, value: unknown): void {
    if (readonly.value) return
    const row = (stored[section].value ?? []).find((r) => r.rowId === rowId)
    if (!row) return
    const numericFields = ['amount', 'bankAmount', 'receiptQty', 'invoiceAmount']
    ;(row as any)[field] = numericFields.includes(field)
      ? parseNum(value as string | number | null | undefined)
      : String(value ?? '')
    persistRows()
  }

  /** 弹窗“保存本笔”整行回写 */
  function saveRow(section: F3VoucherSection, patch: F3VoucherCheckRow): void {
    if (readonly.value) return
    const rows = stored[section].value ?? []
    const idx = rows.findIndex((r) => r.rowId === patch.rowId)
    if (idx === -1) return
    rows[idx] = { ...patch }
    persistRows()
  }

  function mapVoucherToEntries(v: SampledVoucher): Array<{ direction: 'debit' | 'credit'; data: Partial<F3VoucherCheckRow> }> {
    const debit = v.debitAmount ? parseFloat(v.debitAmount) : 0
    const credit = v.creditAmount ? parseFloat(v.creditAmount) : 0
    const base: Partial<F3VoucherCheckRow> = {
      businessContent: v.summary || '',
      counterAccount: v.counterpartAccount || '',
      voucherDate: v.voucherDate || '',
      voucherNo: v.voucherNo || '',
      sampleSource: '抽凭引擎',
    }
    const entries: Array<{ direction: 'debit' | 'credit'; data: Partial<F3VoucherCheckRow> }> = []
    if (credit > 0) entries.push({ direction: 'credit', data: { ...base, amount: credit } })
    if (debit > 0) entries.push({ direction: 'debit', data: { ...base, amount: debit } })
    if (entries.length === 0) {
      const amount = Math.max(debit, credit)
      entries.push({ direction: credit >= debit ? 'credit' : 'debit', data: { ...base, amount } })
    }
    return entries
  }

  function mergeSamples(samples: Array<{ direction: 'debit' | 'credit'; data: Partial<F3VoucherCheckRow> }>): void {
    if (readonly.value) return
    for (const s of samples) {
      const target = stored[s.direction]
      target.value = [
        ...(target.value ?? []),
        { ...emptyVoucherRow((target.value?.length ?? 0) + 1, nextAttSlot(s.direction)), ...s.data },
      ]
    }
    for (const section of ['debit', 'credit'] as F3VoucherSection[]) {
      (stored[section].value ?? []).forEach((r, i) => { r.seq = i + 1 })
    }
    persistRows()
  }

  /** GtVoucherSamplingEngine @filled 处理（append/replace/merge） */
  function applySamplingResults(vouchers: SampledVoucher[], fillMode: FillMode): void {
    if (readonly.value) return
    const mapped = vouchers.flatMap(mapVoucherToEntries)

    if (fillMode === 'replace') {
      for (const section of ['debit', 'credit'] as F3VoucherSection[]) {
        const rows = mapped
          .filter((m) => m.direction === section)
          .map((m, i) => ({ ...emptyVoucherRow(i + 1, i + 1), ...m.data }))
        stored[section].value = rows.length ? rows : [emptyVoucherRow(1)]
      }
      persistRows()
    } else if (fillMode === 'merge') {
      const existingNos: Record<'debit' | 'credit', Set<string>> = {
        debit: new Set((stored.debit.value ?? []).map((r) => r.voucherNo).filter(Boolean)),
        credit: new Set((stored.credit.value ?? []).map((r) => r.voucherNo).filter(Boolean)),
      }
      mergeSamples(mapped.filter((m) => {
        const no = m.data.voucherNo || ''
        return !no || !existingNos[m.direction].has(no)
      }))
    } else {
      mergeSamples(mapped)
    }
  }

  function persistRows(): void {
    for (const section of ['debit', 'credit', 'subsequent'] as F3VoucherSection[]) {
      const key = ITEM_KEYS[section]
      allResponses.value.set(key, {
        item_id: key, conclusion: null, remark: JSON.stringify(stored[section].value ?? []),
      })
    }
    debounceSave()
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => { debounceTimer = null; flushSave() }, 2000)
  }

  function flushSave(): void {
    const items = [
      allResponses.value.get(ITEM_KEYS.debit),
      allResponses.value.get(ITEM_KEYS.credit),
      allResponses.value.get(ITEM_KEYS.subsequent),
      allResponses.value.get('F3-7-conclusion'),
    ].filter(Boolean)
    if (items.length) window.dispatchEvent(new CustomEvent('f3:save-items', { detail: { items } }))
  }

  watch(auditConclusion, (val) => {
    allResponses.value.set('F3-7-conclusion', { item_id: 'F3-7-conclusion', conclusion: null, remark: val })
    debounceSave()
  })

  onBeforeUnmount(() => {
    if (debounceTimer) { clearTimeout(debounceTimer); debounceTimer = null; flushSave() }
  })

  return {
    debitRows, creditRows, subsequentRows, sectionRows,
    debitTotal, creditTotal, subsequentTotal,
    debitAbnormal, creditAbnormal, subsequentAbnormal,
    checkRatios, auditConclusion,
    addRow, removeRow, updateCell, saveRow,
    mergeSamples, applySamplingResults, mapVoucherToEntries,
  }
}

export default useF3VoucherCheck
