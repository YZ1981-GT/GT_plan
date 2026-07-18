/**
 * useF4VoucherCheck — F4-8 应付账款检查表
 *
 * 源表两区：
 *  1. 本期借方金额检查：记账凭证 + 付款审批单 + 银行回单
 *  2. 本期贷方金额检查：记账凭证 + 入库单/验收单 + 采购发票（可结合 F2-33）
 * 每笔通过弹窗逐单据上传 OCR 核对，并与 F4-2 账面发生额计算检查比例。
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal, parseNum } from './useF4AccPayFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF4FormData'
import type { SampledVoucher, FillMode } from './useSamplingAlgorithms'

export type F4VoucherSection = 'debit' | 'credit'
export type F4EvidenceKind = 'payment' | 'purchase'

export function sectionEvidenceKind(section: F4VoucherSection): F4EvidenceKind {
  return section === 'credit' ? 'purchase' : 'payment'
}

export interface F4VoucherCheckRow {
  rowId: string
  seq: number
  attSlot: number
  // 记账凭证
  supplierName: string
  voucherDate: string
  voucherNo: string
  businessContent: string
  counterAccount: string
  detailAccount: string
  amount: number
  // 付款审批单（借方）
  approvalDateNo: string
  approvalProper: string
  // 银行回单（借方）
  bankReceiptDate: string
  bankPayee: string
  bankAmount: number
  // 入库单/验收单（贷方）
  receiptDateNo: string
  receiptProduct: string
  receiptUnit: string
  receiptQty: number
  // 采购发票（贷方）
  invoiceDateNo: string
  invoiceCounterparty: string
  invoiceAmount: number
  otherEvidence: string
  indexNo: string
  isAbnormal: string
  issueDesc: string
  sampleSource: string
}

export interface F4VoucherEvidenceCheck {
  key: string
  label: string
  status: 'ok' | 'missing' | 'mismatch'
  detail: string
}

export interface UseF4VoucherCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

const ITEM_KEYS: Record<F4VoucherSection, string> = {
  debit: 'F4-8-debit-rows',
  credit: 'F4-8-credit-rows',
}
const LEGACY_ITEM_KEYS: Record<F4VoucherSection, string[]> = {
  debit: ['F4-8-debit'],
  credit: ['F4-8-credit'],
}

export const F4_VOUCHER_SECTION_LABELS: Record<F4VoucherSection, string> = {
  debit: '1. 本期借方金额检查（付款/减少）',
  credit: '2. 本期贷方金额检查（采购/增加，可结合存货采购入库检查 F2-33）',
}

const NOTE_KEY = 'F4-8-audit-note'
const CONCLUSION_KEY = 'F4-8-audit-conclusion'
const DETAIL_KEY = 'F4-2-rows'
const TOLERANCE = 0.01

function generateRowId(): string {
  return `f4vc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

export function emptyF4VoucherRow(seq: number, attSlot = seq): F4VoucherCheckRow {
  return {
    rowId: generateRowId(), seq, attSlot,
    supplierName: '', voucherDate: '', voucherNo: '', businessContent: '',
    counterAccount: '', detailAccount: '', amount: 0,
    approvalDateNo: '', approvalProper: '',
    bankReceiptDate: '', bankPayee: '', bankAmount: 0,
    receiptDateNo: '', receiptProduct: '', receiptUnit: '', receiptQty: 0,
    invoiceDateNo: '', invoiceCounterparty: '', invoiceAmount: 0,
    otherEvidence: '', indexNo: '', isAbnormal: '', issueDesc: '', sampleSource: '',
  }
}

export function isBlankF4VoucherRow(row: F4VoucherCheckRow): boolean {
  return !row.supplierName && !row.voucherDate && !row.voucherNo && !row.businessContent
    && !row.counterAccount && !row.detailAccount && !row.amount
    && !row.approvalDateNo && !row.bankReceiptDate && !row.bankPayee && !row.bankAmount
    && !row.receiptDateNo && !row.receiptProduct && !row.receiptQty
    && !row.invoiceDateNo && !row.invoiceCounterparty && !row.invoiceAmount
    && !row.otherEvidence && !row.indexNo && !row.isAbnormal && !row.issueDesc
}

/** 逐笔证据勾稽 */
export function evaluateF4VoucherEvidence(
  row: F4VoucherCheckRow,
  kind: F4EvidenceKind,
): F4VoucherEvidenceCheck[] {
  const checks: F4VoucherEvidenceCheck[] = []

  if (row.voucherNo && row.amount > 0) {
    checks.push({
      key: 'voucher',
      label: '记账凭证',
      status: 'ok',
      detail: `${row.supplierName || '未填供应商'} / ${row.voucherNo} / ${row.amount.toLocaleString('zh-CN')}`,
    })
  } else {
    checks.push({
      key: 'voucher',
      label: '记账凭证',
      status: 'missing',
      detail: '供应商、凭证编号或金额未完整登记',
    })
  }

  if (kind === 'payment') {
    if (!row.approvalDateNo) {
      checks.push({ key: 'approval', label: '付款审批单', status: 'missing', detail: '未登记审批单日期/编号' })
    } else if (row.approvalProper === '否') {
      checks.push({ key: 'approval', label: '付款审批单', status: 'mismatch', detail: '审批不恰当，需说明' })
    } else {
      checks.push({
        key: 'approval',
        label: '付款审批单',
        status: 'ok',
        detail: `${row.approvalDateNo}${row.approvalProper ? ` / 审批${row.approvalProper === '是' ? '恰当' : row.approvalProper}` : ''}`,
      })
    }

    if (!row.bankReceiptDate && !row.bankAmount) {
      checks.push({ key: 'bank', label: '银行回单', status: 'missing', detail: '未登记银行回单' })
    } else if (row.amount > 0 && row.bankAmount > 0 && Math.abs(row.bankAmount - row.amount) > TOLERANCE) {
      checks.push({
        key: 'bank',
        label: '银行回单',
        status: 'mismatch',
        detail: `回单金额 ${row.bankAmount.toLocaleString('zh-CN')} 与凭证金额不符`,
      })
    } else if (row.bankPayee && row.supplierName && row.bankPayee !== row.supplierName) {
      checks.push({
        key: 'bank',
        label: '银行回单',
        status: 'mismatch',
        detail: `收款方「${row.bankPayee}」与供应商「${row.supplierName}」不一致`,
      })
    } else {
      checks.push({
        key: 'bank',
        label: '银行回单',
        status: 'ok',
        detail: `${row.bankReceiptDate}${row.bankPayee ? ` / ${row.bankPayee}` : ''}`,
      })
    }
  } else {
    if (!row.receiptDateNo && !row.receiptProduct) {
      checks.push({ key: 'receipt', label: '入库单/验收单', status: 'missing', detail: '未登记入库/验收信息' })
    } else {
      checks.push({
        key: 'receipt',
        label: '入库单/验收单',
        status: 'ok',
        detail: `${row.receiptDateNo}${row.receiptProduct ? ` / ${row.receiptProduct}` : ''}${row.receiptQty ? ` × ${row.receiptQty}` : ''}`,
      })
    }

    if (!row.invoiceDateNo && !row.invoiceAmount) {
      checks.push({ key: 'invoice', label: '采购发票', status: 'missing', detail: '未登记采购发票' })
    } else if (row.amount > 0 && row.invoiceAmount > 0 && Math.abs(row.invoiceAmount - row.amount) > TOLERANCE) {
      checks.push({
        key: 'invoice',
        label: '采购发票',
        status: 'mismatch',
        detail: `发票金额 ${row.invoiceAmount.toLocaleString('zh-CN')} 与凭证金额不符`,
      })
    } else if (row.invoiceCounterparty && row.supplierName && row.invoiceCounterparty !== row.supplierName) {
      checks.push({
        key: 'invoice',
        label: '采购发票',
        status: 'mismatch',
        detail: `发票对手方「${row.invoiceCounterparty}」与供应商「${row.supplierName}」不一致`,
      })
    } else {
      checks.push({
        key: 'invoice',
        label: '采购发票',
        status: 'ok',
        detail: `${row.invoiceDateNo}${row.invoiceCounterparty ? ` / ${row.invoiceCounterparty}` : ''}`,
      })
    }
  }

  return checks
}

function migrateRow(raw: any, i: number, section: F4VoucherSection): F4VoucherCheckRow {
  const base = emptyF4VoucherRow(i + 1, Number(raw?.attSlot) || i + 1)
  const legacyIssue = [
    raw?.auditProcedure ? `原审计程序：${raw.auditProcedure}` : '',
    raw?.checkResult && raw.checkResult !== '无异常' ? `原检查结果：${raw.checkResult}` : '',
    raw?.paymentMethod ? `原付款方式：${raw.paymentMethod}` : '',
    raw?.bankReconciliation ? `原银行流水：${raw.bankReconciliation}` : '',
    raw?.paymentApproval ? `原付款审批：${raw.paymentApproval}` : '',
    raw?.purchaseOrder || raw?.purchaseOrderNo ? `原采购订单：${raw.purchaseOrder || raw.purchaseOrderNo}` : '',
    raw?.goodsReceipt || raw?.receiptNo ? `原入库单：${raw.goodsReceipt || raw.receiptNo}` : '',
    raw?.invoiceCheck || raw?.invoiceNo ? `原发票：${raw.invoiceCheck || raw.invoiceNo}` : '',
    raw?.threeWayMatch ? `原三单匹配：${raw.threeWayMatch}` : '',
    raw?.auditConclusion && raw.auditConclusion !== '无异常' ? raw.auditConclusion : '',
    raw?.remark,
  ].filter(Boolean).join('；')

  const legacyAbnormal = raw?.isAbnormal
    || (raw?.threeWayMatch === '不一致' ? '是' : '')
    || (raw?.checkResult && raw.checkResult !== '无异常' && raw.checkResult !== '正常' ? '是' : '')
    || (raw?.auditConclusion && raw.auditConclusion !== '无异常' ? '是' : '')

  return {
    ...base,
    rowId: String(raw?.rowId || raw?.id || generateRowId()),
    seq: Number(raw?.seq) || i + 1,
    supplierName: String(raw?.supplierName || raw?.counterparty || ''),
    voucherDate: String(raw?.voucherDate || ''),
    voucherNo: String(raw?.voucherNo || ''),
    businessContent: String(raw?.businessContent || raw?.summary || ''),
    counterAccount: String(raw?.counterAccount || ''),
    detailAccount: String(raw?.detailAccount || ''),
    amount: parseNum(raw?.amount),
    approvalDateNo: String(raw?.approvalDateNo || raw?.paymentApproval || ''),
    approvalProper: String(raw?.approvalProper || ''),
    bankReceiptDate: String(raw?.bankReceiptDate || ''),
    bankPayee: String(raw?.bankPayee || (section === 'debit' ? raw?.counterparty || '' : '')),
    bankAmount: parseNum(raw?.bankAmount || (section === 'debit' && raw?.bankReconciliation ? raw.amount : 0)),
    receiptDateNo: String(raw?.receiptDateNo || raw?.goodsReceipt || raw?.receiptNo || ''),
    receiptProduct: String(raw?.receiptProduct || ''),
    receiptUnit: String(raw?.receiptUnit || ''),
    receiptQty: parseNum(raw?.receiptQty),
    invoiceDateNo: String(raw?.invoiceDateNo || raw?.invoiceCheck || raw?.invoiceNo || ''),
    invoiceCounterparty: String(raw?.invoiceCounterparty || (section === 'credit' ? raw?.counterparty || '' : '')),
    invoiceAmount: parseNum(raw?.invoiceAmount || (section === 'credit' && (raw?.invoiceNo || raw?.invoiceCheck) ? raw.amount : 0)),
    otherEvidence: String(raw?.otherEvidence || ''),
    indexNo: String(raw?.indexNo || ''),
    isAbnormal: String(legacyAbnormal || ''),
    issueDesc: String(raw?.issueDesc || legacyIssue),
    sampleSource: String(raw?.sampleSource || ''),
  }
}

export function migrateF4VoucherRows(
  value: string | null | undefined,
  section: F4VoucherSection,
): F4VoucherCheckRow[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    if (!Array.isArray(parsed)) return []
    const rows = parsed.map((raw, i) => migrateRow(raw, i, section))
    const pruned = rows.filter((row) => !isBlankF4VoucherRow(row))
    const kept = pruned.length ? pruned : rows.slice(0, 1)
    return kept.map((row, i) => ({ ...row, seq: i + 1 }))
  } catch {
    return []
  }
}

/** 检查比例：账面金额取自 F4-2 明细表借贷发生合计 */
export function calcF4BookAmounts(f4DetailJson: string | null | undefined): {
  bookDebit: number
  bookCredit: number
} {
  const empty = { bookDebit: 0, bookCredit: 0 }
  if (!f4DetailJson) return empty
  try {
    const rows = JSON.parse(f4DetailJson)
    if (!Array.isArray(rows)) return empty
    return {
      bookDebit: calcSubtotal(rows.map((r: any) => parseNum(r?.currentDebit ?? r?.debit))),
      bookCredit: calcSubtotal(rows.map((r: any) => parseNum(r?.currentCredit ?? r?.credit))),
    }
  } catch {
    return empty
  }
}

export function useF4VoucherCheck(options: UseF4VoucherCheckOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const lastPersisted = new Map<F4VoucherSection, string>()

  const stored: Record<F4VoucherSection, Ref<F4VoucherCheckRow[]>> = {
    debit: ref([]),
    credit: ref([]),
  }
  const auditNote = ref('')
  const auditConclusion = ref('')
  const sampleBasis = ref('')

  function rawForSection(section: F4VoucherSection): string | null | undefined {
    const current = readRowJson(allResponses.value.get(ITEM_KEYS[section]))
    if (current) return current
    for (const key of LEGACY_ITEM_KEYS[section]) {
      const legacy = readRowJson(allResponses.value.get(key))
      if (legacy) return legacy
    }
    return null
  }

  function loadSection(section: F4VoucherSection): void {
    stored[section].value = migrateF4VoucherRows(rawForSection(section), section)
    if (!stored[section].value.length) stored[section].value = [emptyF4VoucherRow(1)]
  }

  for (const section of ['debit', 'credit'] as F4VoucherSection[]) {
    watch(
      () => rawForSection(section),
      (raw) => {
        if (raw && (raw === lastPersisted.get(section) || raw === JSON.stringify(stored[section].value))) return
        loadSection(section)
      },
      { immediate: true },
    )
  }

  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
      allResponses.value.get('F4-8-debit-note')?.remark,
      allResponses.value.get('F4-8-credit-note')?.remark,
      allResponses.value.get('F4-8-sample-basis')?.remark,
    ],
    ([note, conclusion, debitNote, creditNote, basis]) => {
      auditNote.value = note || [debitNote, creditNote].filter(Boolean).join('\n\n') || ''
      auditConclusion.value = conclusion || ''
      sampleBasis.value = basis || ''
    },
    { immediate: true },
  )

  const debitRows = computed(() => stored.debit.value) as ComputedRef<F4VoucherCheckRow[]>
  const creditRows = computed(() => stored.credit.value) as ComputedRef<F4VoucherCheckRow[]>

  const debitTotal = computed(() => calcSubtotal(debitRows.value.map((r) => r.amount)))
  const creditTotal = computed(() => calcSubtotal(creditRows.value.map((r) => r.amount)))
  const debitAbnormal = computed(() => debitRows.value.filter((r) => r.isAbnormal === '是').length)
  const creditAbnormal = computed(() => creditRows.value.filter((r) => r.isAbnormal === '是').length)

  const checkRatios = computed(() => {
    const book = calcF4BookAmounts(readRowJson(allResponses.value.get(DETAIL_KEY)))
    const build = (label: string, bookAmount: number, checkedAmount: number) => ({
      label,
      bookAmount,
      checkedAmount,
      ratio: bookAmount > 0 ? Math.round((checkedAmount / bookAmount) * 10000) / 100 : 0,
    })
    return [
      build('本期借方', book.bookDebit, debitTotal.value),
      build('本期贷方', book.bookCredit, creditTotal.value),
    ]
  })

  function nextAttSlot(section: F4VoucherSection): number {
    return Math.max(0, ...stored[section].value.map((r) => Number(r.attSlot) || 0)) + 1
  }

  function addRow(section: F4VoucherSection): void {
    if (readonly.value) return
    stored[section].value.push(emptyF4VoucherRow(stored[section].value.length + 1, nextAttSlot(section)))
    persistSection(section)
  }

  function removeRow(section: F4VoucherSection, rowId: string): void {
    if (readonly.value) return
    const rows = stored[section].value
    if (rows.length <= 1) return
    const idx = rows.findIndex((r) => r.rowId === rowId)
    if (idx === -1) return
    rows.splice(idx, 1)
    rows.forEach((r, i) => { r.seq = i + 1 })
    persistSection(section)
  }

  function updateCell(section: F4VoucherSection, rowId: string, field: string, value: unknown): void {
    if (readonly.value) return
    const row = stored[section].value.find((r) => r.rowId === rowId)
    if (!row) return
    const numericFields = ['amount', 'bankAmount', 'receiptQty', 'invoiceAmount']
    ;(row as any)[field] = numericFields.includes(field)
      ? parseNum(value as string | number | null | undefined)
      : String(value ?? '')
    persistSection(section)
  }

  function saveRow(section: F4VoucherSection, patch: F4VoucherCheckRow): void {
    if (readonly.value) return
    const idx = stored[section].value.findIndex((r) => r.rowId === patch.rowId)
    if (idx === -1) return
    stored[section].value[idx] = { ...patch }
    persistSection(section)
  }

  function applySamplingResults(samples: SampledVoucher[], fillMode: FillMode = 'append'): void {
    if (readonly.value || !samples.length) return
    if (fillMode === 'replace') {
      stored.debit.value = []
      stored.credit.value = []
    }

    for (const sample of samples) {
      const debit = sample.debitAmount ? parseFloat(sample.debitAmount) : 0
      const credit = sample.creditAmount ? parseFloat(sample.creditAmount) : 0
      const base = {
        voucherDate: sample.voucherDate || '',
        voucherNo: sample.voucherNo || '',
        businessContent: sample.summary || '',
        counterAccount: sample.counterpartAccount || '',
        supplierName: '',
        sampleSource: '抽凭引擎',
      }
      if (debit > 0) {
        if (stored.debit.value.length === 1 && isBlankF4VoucherRow(stored.debit.value[0])) {
          stored.debit.value = []
        }
        stored.debit.value.push({
          ...emptyF4VoucherRow(stored.debit.value.length + 1, nextAttSlot('debit')),
          ...base,
          amount: debit,
        })
      }
      if (credit > 0) {
        if (stored.credit.value.length === 1 && isBlankF4VoucherRow(stored.credit.value[0])) {
          stored.credit.value = []
        }
        stored.credit.value.push({
          ...emptyF4VoucherRow(stored.credit.value.length + 1, nextAttSlot('credit')),
          ...base,
          amount: credit,
        })
      }
    }
    stored.debit.value.forEach((r, i) => { r.seq = i + 1 })
    stored.credit.value.forEach((r, i) => { r.seq = i + 1 })
    persistSection('debit')
    persistSection('credit')
  }

  function persistSection(section: F4VoucherSection): void {
    const json = JSON.stringify(stored[section].value)
    lastPersisted.set(section, json)
    allResponses.value.set(ITEM_KEYS[section], {
      item_id: ITEM_KEYS[section],
      conclusion: null,
      remark: json,
    })
    debounceSave()
  }

  function setText(key: string, value: string): void {
    allResponses.value.set(key, { item_id: key, conclusion: null, remark: value })
    debounceSave()
  }

  function saveAuditNote(value: string): void {
    if (readonly.value) return
    auditNote.value = value
    setText(NOTE_KEY, value)
  }

  function saveAuditConclusion(value: string): void {
    if (readonly.value) return
    auditConclusion.value = value
    setText(CONCLUSION_KEY, value)
  }

  function saveSampleBasis(value: string): void {
    if (readonly.value) return
    sampleBasis.value = value
    setText('F4-8-sample-basis', value)
  }

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      ...Object.values(ITEM_KEYS).map((key) => allResponses.value.get(key)),
      allResponses.value.get(NOTE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
      allResponses.value.get('F4-8-sample-basis'),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    debitRows,
    creditRows,
    debitTotal,
    creditTotal,
    debitAbnormal,
    creditAbnormal,
    checkRatios,
    auditNote,
    auditConclusion,
    sampleBasis,
    loadSection,
    addRow,
    removeRow,
    updateCell,
    saveRow,
    applySamplingResults,
    saveAuditNote,
    saveAuditConclusion,
    saveSampleBasis,
  }
}

export default useF4VoucherCheck
