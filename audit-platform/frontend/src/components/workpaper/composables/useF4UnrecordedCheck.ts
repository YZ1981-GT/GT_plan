/**
 * useF4UnrecordedCheck — F4-7 未入账应付账款检查
 *
 * 五段源表逻辑：
 * 1. 平均付款期与期后付款；2. 料到单未到暂估入库；3. 未处理供应商发票；
 * 4. 期后付款反查；5. 期后增加额反查。
 */
import { computed, onBeforeUnmount, ref, watch, type ComputedRef, type Ref } from 'vue'
import { calcCreditBalance, calcSubtotal, parseNum } from './useF4AccPayFormulaEngine'
import { readRowJson, type ChecklistResponse } from './useF4FormData'
import type { F4ImportableSheet } from './useF4ImportExport'

export type UnrecordedSection =
  | 'payment-window'
  | 'estimated-inbound'
  | 'unprocessed-invoice'
  | 'subsequent-payment'
  | 'subsequent-increase'

export type UnrecordedInputType = 'text' | 'textarea' | 'date' | 'number' | 'select' | 'formula'

export interface UnrecordedColumnConfig {
  prop: keyof F4UnrecordedStoredRow | 'closingBalance' | 'averagePaymentDays' | 'difference' | 'estimatedAmount'
  label: string
  minWidth?: number
  width?: number
  inputType: UnrecordedInputType
  options?: readonly string[]
  tooltip?: string
}

export interface UnrecordedSectionConfig {
  key: UnrecordedSection
  storageKey: string
  legacyStorageKeys?: string[]
  sheet: F4ImportableSheet
  title: string
  purpose: string
  ocrDocumentType: string
  evidenceHint: string
  columns: UnrecordedColumnConfig[]
}

const YES_NO_OPTIONS = ['是', '否'] as const

export const SECTION_CONFIGS: UnrecordedSectionConfig[] = [
  {
    key: 'payment-window',
    storageKey: 'F4-7-payment-window-rows',
    sheet: 'F4-7-payment-window',
    title: '（一）期后付款是否在平均付款天数内',
    purpose: '分析大额供应商平均付款期，核对期后付款是否异常超过期末余额或偏离正常付款周期。',
    ocrDocumentType: 'unrecorded-payment-window',
    evidenceHint: '建议上传供应商明细账、期后付款凭证、银行回单或对账单。',
    columns: [
      { prop: 'supplierName', label: '供应商名称', minWidth: 150, inputType: 'text' },
      { prop: 'openingBalance', label: '期初余额', width: 125, inputType: 'number' },
      { prop: 'currentDebit', label: '本期借方', width: 125, inputType: 'number' },
      { prop: 'currentCredit', label: '本期贷方', width: 125, inputType: 'number' },
      { prop: 'closingBalance', label: '期末余额', width: 125, inputType: 'formula', tooltip: '期初余额＋本期贷方－本期借方' },
      { prop: 'averagePaymentDays', label: '平均付款天数', width: 125, inputType: 'formula', tooltip: '365×期末余额÷本期贷方' },
      { prop: 'postPaymentAmount', label: '期后付款金额', width: 130, inputType: 'number' },
      { prop: 'difference', label: '差异', width: 120, inputType: 'formula', tooltip: '期后付款金额－期末余额' },
      { prop: 'withinAverageDays', label: '是否在平均付款天数内', width: 165, inputType: 'select', options: YES_NO_OPTIONS },
      { prop: 'remark', label: '备注', minWidth: 170, inputType: 'textarea' },
    ],
  },
  {
    key: 'estimated-inbound',
    storageKey: 'F4-7-estimated-inbound-rows',
    legacyStorageKeys: ['F4-7-receipt', 'F4-7-inbound-rows'],
    sheet: 'F4-7-estimated-inbound',
    title: '（二）料到单未到——存货暂估入库',
    purpose: '将入库单数量与合同不含税单价计算的暂估金额，同记账凭证日期、编号及金额核对。',
    ocrDocumentType: 'unrecorded-estimated-inbound',
    evidenceHint: '建议上传入库单/验收单、采购合同或订单、暂估入账记账凭证。',
    columns: [
      { prop: 'receiptDate', label: '入库单日期', width: 125, inputType: 'date' },
      { prop: 'receiptNo', label: '入库单编号', width: 135, inputType: 'text' },
      { prop: 'quantity', label: '数量', width: 105, inputType: 'number' },
      { prop: 'contractUnitPrice', label: '合同单价（不含税）', width: 145, inputType: 'number' },
      { prop: 'estimatedAmount', label: '暂估金额', width: 125, inputType: 'formula', tooltip: '数量×合同不含税单价' },
      { prop: 'voucherDate', label: '记账凭证日期', width: 125, inputType: 'date' },
      { prop: 'voucherNo', label: '记账凭证号', width: 130, inputType: 'text' },
      { prop: 'voucherAmount', label: '凭证金额', width: 125, inputType: 'number' },
      { prop: 'shouldAdjust', label: '是否应调整', width: 110, inputType: 'select', options: YES_NO_OPTIONS },
      { prop: 'remark', label: '备注', minWidth: 170, inputType: 'textarea' },
    ],
  },
  {
    key: 'unprocessed-invoice',
    storageKey: 'F4-7-unprocessed-invoice-rows',
    legacyStorageKeys: ['F4-7-invoice', 'F4-7-invoice-rows'],
    sheet: 'F4-7-unprocessed-invoice',
    title: '（三）截止现场结束日未处理的供应商发票',
    purpose: '检查尚未处理发票对应货物或服务是否在报告期取得，判断是否应计入报告期负债。',
    ocrDocumentType: 'unrecorded-unprocessed-invoice',
    evidenceHint: '建议上传供应商发票、入库/验收资料、合同及现场截止日未处理发票清单。',
    columns: [
      { prop: 'invoiceDate', label: '购货发票日期', width: 125, inputType: 'date' },
      { prop: 'invoiceNo', label: '购货发票编号', width: 140, inputType: 'text' },
      { prop: 'quantity', label: '数量', width: 100, inputType: 'number' },
      { prop: 'invoiceContent', label: '发票内容', minWidth: 160, inputType: 'text' },
      { prop: 'amount', label: '金额', width: 125, inputType: 'number' },
      { prop: 'supplierName', label: '供应商名称', minWidth: 150, inputType: 'text' },
      { prop: 'shouldIncludeReportPeriod', label: '是否应计入报告期', width: 145, inputType: 'select', options: YES_NO_OPTIONS },
      { prop: 'reportPeriodAmount', label: '应计入报告期金额', width: 145, inputType: 'number' },
      { prop: 'remark', label: '备注', minWidth: 170, inputType: 'textarea' },
    ],
  },
  {
    key: 'subsequent-payment',
    storageKey: 'F4-7-subsequent-payment-rows',
    sheet: 'F4-7-subsequent-payment',
    title: '（四）应付账款期后付款核对',
    purpose: '将期后付款记账凭证与银行付款凭单逐笔核对，并反查相关负债是否应计入报告期。',
    ocrDocumentType: 'unrecorded-subsequent-payment',
    evidenceHint: '建议上传期后付款记账凭证、银行回单/银行对账单、付款审批及供应商资料。',
    columns: [
      { prop: 'voucherDate', label: '记账凭证日期', width: 125, inputType: 'date' },
      { prop: 'voucherNo', label: '记账凭证编号', width: 135, inputType: 'text' },
      { prop: 'bankDocumentDate', label: '银行付款凭单日期', width: 140, inputType: 'date' },
      { prop: 'bankDocumentNo', label: '银行付款凭单编号', width: 150, inputType: 'text' },
      { prop: 'amount', label: '金额', width: 125, inputType: 'number' },
      { prop: 'supplierName', label: '供应商名称', minWidth: 150, inputType: 'text' },
      { prop: 'shouldIncludeReportPeriod', label: '是否应计入报告期', width: 145, inputType: 'select', options: YES_NO_OPTIONS },
      { prop: 'reportPeriodAmount', label: '应计入报告期金额', width: 145, inputType: 'number' },
      { prop: 'remark', label: '备注', minWidth: 170, inputType: 'textarea' },
    ],
  },
  {
    key: 'subsequent-increase',
    storageKey: 'F4-7-subsequent-increase-rows',
    legacyStorageKeys: ['F4-7-purchase', 'F4-7-purchase-rows'],
    sheet: 'F4-7-subsequent-increase',
    title: '（五）应付账款期后增加额核对',
    purpose: '将期后应付账款增加凭证与购货发票逐笔核对，检查发票日期及入账期间是否合理。',
    ocrDocumentType: 'unrecorded-subsequent-increase',
    evidenceHint: '建议上传期后增加记账凭证、购货发票、入库/验收资料及采购合同。',
    columns: [
      { prop: 'voucherDate', label: '记账凭证日期', width: 125, inputType: 'date' },
      { prop: 'voucherNo', label: '记账凭证编号', width: 135, inputType: 'text' },
      { prop: 'purchaseInvoiceDate', label: '购货发票日期', width: 125, inputType: 'date' },
      { prop: 'purchaseInvoiceNo', label: '购货发票编号', width: 140, inputType: 'text' },
      { prop: 'amount', label: '金额', width: 125, inputType: 'number' },
      { prop: 'supplierName', label: '供应商名称', minWidth: 150, inputType: 'text' },
      { prop: 'shouldIncludeReportPeriod', label: '是否应计入报告期', width: 145, inputType: 'select', options: YES_NO_OPTIONS },
      { prop: 'reportPeriodAmount', label: '应计入报告期金额', width: 145, inputType: 'number' },
      { prop: 'remark', label: '备注', minWidth: 170, inputType: 'textarea' },
    ],
  },
]

export interface F4UnrecordedStoredRow {
  rowId: string
  seq: number
  attSlot: number
  supplierName: string
  openingBalance: number
  currentDebit: number
  currentCredit: number
  postPaymentAmount: number
  withinAverageDays: string
  receiptDate: string
  receiptNo: string
  quantity: number
  contractUnitPrice: number
  estimatedAmount: number
  voucherDate: string
  voucherNo: string
  voucherAmount: number
  shouldAdjust: string
  invoiceDate: string
  invoiceNo: string
  invoiceContent: string
  amount: number
  shouldIncludeReportPeriod: string
  reportPeriodAmount: number
  bankDocumentDate: string
  bankDocumentNo: string
  purchaseInvoiceDate: string
  purchaseInvoiceNo: string
  remark: string
}

export interface F4UnrecordedRow extends F4UnrecordedStoredRow {
  closingBalance: number
  averagePaymentDays: number | null
  difference: number
  riskFlags: string[]
  riskLevel: 'none' | 'warning' | 'danger'
}

export interface F4UnrecordedOcrFields extends Partial<F4UnrecordedStoredRow> {}

export interface SectionSubtotal {
  primaryTotal: number
  comparisonTotal: number
  reportPeriodTotal: number
  adjustmentTotal: number
  flaggedCount: number
  filledCount: number
}

export interface UseF4UnrecordedCheckOptions {
  wpId: Ref<string>
  projectId: Ref<string>
  allResponses: Ref<Map<string, ChecklistResponse>>
  isReadonly?: Ref<boolean>
}

const NOTE_KEY = 'F4-7-audit-note'
const CONCLUSION_KEY = 'F4-7-audit-conclusion'
const LEGACY_NOTE_KEY = 'F4-7-note'
const TOLERANCE = 0.005

function generateRowId(): string {
  return `f4uc-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 9)}`
}

function emptyRow(seq: number, attSlot = seq): F4UnrecordedStoredRow {
  return {
    rowId: generateRowId(), seq, attSlot, supplierName: '', openingBalance: 0,
    currentDebit: 0, currentCredit: 0, postPaymentAmount: 0, withinAverageDays: '',
    receiptDate: '', receiptNo: '', quantity: 0, contractUnitPrice: 0, estimatedAmount: 0,
    voucherDate: '', voucherNo: '', voucherAmount: 0, shouldAdjust: '', invoiceDate: '',
    invoiceNo: '', invoiceContent: '', amount: 0, shouldIncludeReportPeriod: '',
    reportPeriodAmount: 0, bankDocumentDate: '', bankDocumentNo: '',
    purchaseInvoiceDate: '', purchaseInvoiceNo: '', remark: '',
  }
}

function nextAttSlot(rows: F4UnrecordedStoredRow[]): number {
  return Math.max(0, ...rows.map((row) => Number(row.attSlot) || 0)) + 1
}

function migrateLegacyGeneric(
  raw: any,
  section: UnrecordedSection,
): Partial<F4UnrecordedStoredRow> {
  const date = String(raw?.date ?? '')
  const supplierName = String(raw?.supplierName ?? raw?.counterparty ?? raw?.vendor ?? '')
  const docNo = String(raw?.documentNo ?? raw?.docNo ?? '')
  const should = String(raw?.shouldIncludeReportPeriod ?? raw?.shouldRecordCurrent ?? raw?.shouldCurrent ?? '')
  const remark = [raw?.remark, raw?.suggestion ? `原入账建议：${raw.suggestion}` : '']
    .filter(Boolean).join('；')
  if (section === 'estimated-inbound') {
    return {
      receiptDate: String(raw?.receiptDate ?? date),
      receiptNo: String(raw?.receiptNo ?? docNo),
      estimatedAmount: parseNum(raw?.estimatedAmount ?? raw?.amount),
      voucherAmount: parseNum(raw?.voucherAmount),
      shouldAdjust: String(raw?.shouldAdjust ?? should),
      remark,
    }
  }
  if (section === 'unprocessed-invoice') {
    return {
      invoiceDate: String(raw?.invoiceDate ?? date),
      invoiceNo: String(raw?.invoiceNo ?? docNo),
      invoiceContent: String(raw?.invoiceContent ?? raw?.description ?? raw?.servicePeriod ?? ''),
      amount: parseNum(raw?.amount),
      supplierName,
      shouldIncludeReportPeriod: should,
      reportPeriodAmount: parseNum(raw?.reportPeriodAmount ?? (should === '是' ? raw?.amount : 0)),
      remark,
    }
  }
  if (section === 'subsequent-increase') {
    return {
      voucherDate: String(raw?.voucherDate ?? date),
      voucherNo: String(raw?.voucherNo ?? ''),
      purchaseInvoiceNo: String(raw?.purchaseInvoiceNo ?? docNo),
      amount: parseNum(raw?.amount),
      supplierName,
      shouldIncludeReportPeriod: should,
      reportPeriodAmount: parseNum(raw?.reportPeriodAmount ?? (should === '是' ? raw?.amount : 0)),
      remark,
    }
  }
  return {}
}

function migrateRow(raw: any, index: number, section: UnrecordedSection): F4UnrecordedStoredRow {
  const base = emptyRow(index + 1, Number(raw?.attSlot) || index + 1)
  const legacy = migrateLegacyGeneric(raw, section)
  const numericFields: Array<keyof F4UnrecordedStoredRow> = [
    'openingBalance', 'currentDebit', 'currentCredit', 'postPaymentAmount', 'quantity',
    'contractUnitPrice', 'estimatedAmount', 'voucherAmount', 'amount', 'reportPeriodAmount',
  ]
  const result: F4UnrecordedStoredRow = {
    ...base,
    ...legacy,
    ...raw,
    rowId: String(raw?.rowId ?? raw?.id ?? generateRowId()),
    seq: Number(raw?.seq) || index + 1,
    attSlot: Number(raw?.attSlot) || index + 1,
  }
  for (const field of numericFields) result[field] = parseNum(result[field]) as never
  return result
}

export function migrateF4UnrecordedRows(
  value: string | null | undefined,
  section: UnrecordedSection,
): F4UnrecordedStoredRow[] {
  if (!value) return []
  try {
    const parsed = JSON.parse(value)
    return Array.isArray(parsed) ? parsed.map((row, index) => migrateRow(row, index, section)) : []
  } catch {
    return []
  }
}

function isBlank(row: F4UnrecordedStoredRow, config: UnrecordedSectionConfig): boolean {
  return config.columns.every((column) => {
    if (['closingBalance', 'averagePaymentDays', 'difference'].includes(String(column.prop))) return true
    const value = row[column.prop as keyof F4UnrecordedStoredRow]
    return value === '' || value === 0 || value == null
  })
}

export function computeF4UnrecordedRow(
  stored: F4UnrecordedStoredRow,
  section: UnrecordedSection,
): F4UnrecordedRow {
  const closingBalance = calcCreditBalance(
    stored.openingBalance,
    stored.currentCredit,
    stored.currentDebit,
  )
  const averagePaymentDays = Math.abs(stored.currentCredit) >= TOLERANCE
    ? 365 * closingBalance / stored.currentCredit
    : null
  const difference = stored.postPaymentAmount - closingBalance
  const estimatedAmount = Math.abs(stored.quantity) >= TOLERANCE
    || Math.abs(stored.contractUnitPrice) >= TOLERANCE
    ? stored.quantity * stored.contractUnitPrice
    : stored.estimatedAmount
  const row = { ...stored, estimatedAmount }
  const riskFlags: string[] = []

  if (section === 'payment-window') {
    if (stored.supplierName && averagePaymentDays == null) riskFlags.push('本期贷方为零，付款天数无法计算')
    if (closingBalance < -TOLERANCE) riskFlags.push('期末余额为负')
    if (difference > TOLERANCE) riskFlags.push('期后付款超过期末余额')
    if (stored.postPaymentAmount > TOLERANCE && !stored.withinAverageDays) riskFlags.push('付款周期结论待填写')
    if (stored.withinAverageDays === '否') riskFlags.push('不在平均付款天数内')
  } else if (section === 'estimated-inbound') {
    if (estimatedAmount > TOLERANCE && !stored.receiptNo) riskFlags.push('入库单信息不完整')
    if (estimatedAmount > TOLERANCE && !stored.voucherNo) riskFlags.push('暂估凭证待核对')
    if (Math.abs(estimatedAmount - stored.voucherAmount) >= TOLERANCE) riskFlags.push('暂估与凭证金额不一致')
    if (stored.shouldAdjust === '是') riskFlags.push('存在建议调整')
  } else {
    if (stored.amount > TOLERANCE && !stored.supplierName) riskFlags.push('供应商信息缺失')
    if (stored.shouldIncludeReportPeriod === '是') riskFlags.push('应计入报告期')
    if (stored.shouldIncludeReportPeriod === '是'
      && Math.abs(stored.reportPeriodAmount) < TOLERANCE) riskFlags.push('报告期金额待填写')
    if (stored.reportPeriodAmount - stored.amount > TOLERANCE) riskFlags.push('报告期金额超过单据金额')
    if (section === 'subsequent-payment' && stored.amount > TOLERANCE
      && (!stored.voucherNo || !stored.bankDocumentNo)) riskFlags.push('凭证与银行单据未完整匹配')
    if (section === 'subsequent-increase' && stored.amount > TOLERANCE
      && (!stored.voucherNo || !stored.purchaseInvoiceNo)) riskFlags.push('凭证与发票未完整匹配')
  }

  const dangerFlags = new Set([
    '期后付款超过期末余额', '暂估与凭证金额不一致', '存在建议调整',
    '应计入报告期', '报告期金额超过单据金额',
  ])
  const riskLevel: F4UnrecordedRow['riskLevel'] = riskFlags.some((flag) => dangerFlags.has(flag))
    ? 'danger'
    : riskFlags.length ? 'warning' : 'none'
  return { ...row, closingBalance, averagePaymentDays, difference, riskFlags, riskLevel }
}

function calcSubtotalForSection(
  rows: F4UnrecordedRow[],
  section: UnrecordedSection,
): SectionSubtotal {
  if (section === 'payment-window') {
    return {
      primaryTotal: calcSubtotal(rows.map((row) => row.closingBalance)),
      comparisonTotal: calcSubtotal(rows.map((row) => row.postPaymentAmount)),
      reportPeriodTotal: 0,
      adjustmentTotal: 0,
      flaggedCount: rows.filter((row) => row.riskFlags.length).length,
      filledCount: rows.filter((row) => row.supplierName).length,
    }
  }
  if (section === 'estimated-inbound') {
    return {
      primaryTotal: calcSubtotal(rows.map((row) => row.estimatedAmount)),
      comparisonTotal: calcSubtotal(rows.map((row) => row.voucherAmount)),
      reportPeriodTotal: 0,
      adjustmentTotal: calcSubtotal(rows
        .filter((row) => row.shouldAdjust === '是')
        .map((row) => row.estimatedAmount - row.voucherAmount)),
      flaggedCount: rows.filter((row) => row.riskFlags.length).length,
      filledCount: rows.filter((row) => row.receiptNo || row.estimatedAmount).length,
    }
  }
  return {
    primaryTotal: calcSubtotal(rows.map((row) => row.amount)),
    comparisonTotal: 0,
    reportPeriodTotal: calcSubtotal(rows.map((row) => row.reportPeriodAmount)),
    adjustmentTotal: calcSubtotal(rows
      .filter((row) => row.shouldIncludeReportPeriod === '是')
      .map((row) => row.reportPeriodAmount)),
    flaggedCount: rows.filter((row) => row.riskFlags.length).length,
    filledCount: rows.filter((row) => row.amount || row.supplierName).length,
  }
}

export function useF4UnrecordedCheck(options: UseF4UnrecordedCheckOptions) {
  const { allResponses, isReadonly } = options
  const readonly = isReadonly ?? ref(false)
  const stored = Object.fromEntries(
    SECTION_CONFIGS.map((config) => [config.key, ref<F4UnrecordedStoredRow[]>([])]),
  ) as Record<UnrecordedSection, Ref<F4UnrecordedStoredRow[]>>
  let debounceTimer: ReturnType<typeof setTimeout> | null = null
  const lastPersisted = new Map<UnrecordedSection, string>()
  const auditNote = ref('')
  const auditConclusion = ref('')

  function rawForConfig(config: UnrecordedSectionConfig): string | null | undefined {
    const current = readRowJson(allResponses.value.get(config.storageKey))
    if (current) return current
    for (const key of config.legacyStorageKeys ?? []) {
      const legacy = readRowJson(allResponses.value.get(key))
      if (legacy) return legacy
    }
    return null
  }

  function loadSection(section: UnrecordedSection): void {
    const config = SECTION_CONFIGS.find((item) => item.key === section)!
    stored[section].value = migrateF4UnrecordedRows(rawForConfig(config), section)
    if (!stored[section].value.length) stored[section].value = [emptyRow(1)]
  }

  for (const config of SECTION_CONFIGS) {
    watch(
      () => rawForConfig(config),
      (raw) => {
        if (raw && (raw === lastPersisted.get(config.key)
          || raw === JSON.stringify(stored[config.key].value))) return
        loadSection(config.key)
      },
      { immediate: true },
    )
  }
  watch(
    () => [
      allResponses.value.get(NOTE_KEY)?.remark,
      allResponses.value.get(CONCLUSION_KEY)?.remark,
      allResponses.value.get(LEGACY_NOTE_KEY)?.remark,
    ],
    ([note, conclusion, legacy]) => {
      auditNote.value = note || ''
      auditConclusion.value = conclusion || legacy || ''
    },
    { immediate: true },
  )

  const rows = Object.fromEntries(SECTION_CONFIGS.map((config) => [
    config.key,
    computed(() => stored[config.key].value.map((row) => computeF4UnrecordedRow(row, config.key))),
  ])) as Record<UnrecordedSection, ComputedRef<F4UnrecordedRow[]>>

  const subtotals = Object.fromEntries(SECTION_CONFIGS.map((config) => [
    config.key,
    computed(() => calcSubtotalForSection(rows[config.key].value, config.key)),
  ])) as Record<UnrecordedSection, ComputedRef<SectionSubtotal>>

  const overallSummary = computed(() => {
    const reportSections: UnrecordedSection[] = [
      'unprocessed-invoice', 'subsequent-payment', 'subsequent-increase',
    ]
    // 同一负债可能同时出现在发票、付款和期后增加测试中，跨区合计只能作为未去重候选数。
    const candidateKeys = reportSections.flatMap((section) => rows[section].value
      .filter((row) => row.shouldIncludeReportPeriod === '是'
        && Math.abs(row.reportPeriodAmount) >= TOLERANCE)
      .map((row) =>
        `${row.supplierName.trim().toLocaleLowerCase('zh-CN')}|${Math.abs(row.reportPeriodAmount).toFixed(2)}`,
      ))
    const seen = new Set<string>()
    const duplicateRiskCount = candidateKeys.reduce((count, key) => {
      if (!key.startsWith('|') && seen.has(key)) return count + 1
      seen.add(key)
      return count
    }, 0)
    return {
      testedCount: SECTION_CONFIGS.reduce(
        (sum, config) => sum + subtotals[config.key].value.filledCount,
        0,
      ),
      riskCount: SECTION_CONFIGS.reduce(
        (sum, config) => sum + subtotals[config.key].value.flaggedCount,
        0,
      ),
      candidateAdjustment: SECTION_CONFIGS.reduce(
        (sum, config) => sum + subtotals[config.key].value.adjustmentTotal,
        0,
      ),
      reportPeriodAmount: reportSections.reduce(
        (sum, section) => sum + subtotals[section].value.reportPeriodTotal,
        0,
      ),
      duplicateRiskCount,
    }
  })

  function getRows(section: UnrecordedSection): F4UnrecordedRow[] {
    return rows[section].value
  }

  function getSubtotal(section: UnrecordedSection): SectionSubtotal {
    return subtotals[section].value
  }

  function addRow(section: UnrecordedSection): void {
    if (readonly.value) return
    const sectionRows = stored[section].value
    sectionRows.push(emptyRow(sectionRows.length + 1, nextAttSlot(sectionRows)))
    persistSection(section)
  }

  function removeRow(section: UnrecordedSection, rowId: string): void {
    if (readonly.value) return
    const sectionRows = stored[section].value
    const index = sectionRows.findIndex((row) => row.rowId === rowId)
    if (index === -1) return
    sectionRows.splice(index, 1)
    if (!sectionRows.length) sectionRows.push(emptyRow(1))
    sectionRows.forEach((row, i) => { row.seq = i + 1 })
    persistSection(section)
  }

  function updateCell(
    section: UnrecordedSection,
    rowId: string,
    field: string,
    value: unknown,
  ): void {
    if (readonly.value) return
    const row = stored[section].value.find((item) => item.rowId === rowId)
    if (!row) return
    const numeric = new Set([
      'openingBalance', 'currentDebit', 'currentCredit', 'postPaymentAmount', 'quantity',
      'contractUnitPrice', 'estimatedAmount', 'voucherAmount', 'amount', 'reportPeriodAmount',
    ])
    ;(row as any)[field] = numeric.has(field)
      ? parseNum(value as string | number | null | undefined)
      : String(value ?? '')
    persistSection(section)
  }

  function mergeOcrFields(
    section: UnrecordedSection,
    rowId: string,
    fields: F4UnrecordedOcrFields,
    overwrite = false,
  ): void {
    if (readonly.value) return
    const row = stored[section].value.find((item) => item.rowId === rowId)
    if (!row) return
    const config = SECTION_CONFIGS.find((item) => item.key === section)!
    const numeric = new Set([
      'openingBalance', 'currentDebit', 'currentCredit', 'postPaymentAmount', 'quantity',
      'contractUnitPrice', 'estimatedAmount', 'voucherAmount', 'amount', 'reportPeriodAmount',
    ])
    for (const column of config.columns) {
      const field = String(column.prop)
      if (['closingBalance', 'averagePaymentDays', 'difference'].includes(field)) continue
      const value = (fields as any)[field]
      if (value == null || value === '') continue
      const current = (row as any)[field]
      if (!overwrite && current !== '' && current !== 0) continue
      ;(row as any)[field] = numeric.has(field)
        ? parseNum(value as string | number | null | undefined)
        : String(value)
    }
    persistSection(section)
  }

  /** 序时账自动提取只用于期后付款/增加额；未处理发票和未到票入库不能从账内推断。 */
  function distributeCutoffSamples(vouchers: Array<{
    voucherNo: string
    voucherDate: string
    summary: string | null
    debitAmount: string | null
    creditAmount: string | null
  }>): { payments: number; increases: number } {
    if (readonly.value) return { payments: 0, increases: 0 }
    let payments = 0
    let increases = 0
    for (const voucher of vouchers) {
      const debit = parseNum(voucher.debitAmount)
      const credit = parseNum(voucher.creditAmount)
      const section: UnrecordedSection = Math.abs(debit) >= Math.abs(credit)
        ? 'subsequent-payment'
        : 'subsequent-increase'
      const sectionRows = stored[section].value
      if (sectionRows.length === 1) {
        const config = SECTION_CONFIGS.find((item) => item.key === section)!
        if (isBlank(sectionRows[0], config)) sectionRows.splice(0, 1)
      }
      sectionRows.push({
        ...emptyRow(sectionRows.length + 1, nextAttSlot(sectionRows)),
        voucherDate: voucher.voucherDate || '',
        voucherNo: voucher.voucherNo || '',
        amount: Math.max(Math.abs(debit), Math.abs(credit)),
        remark: ['截止自动提取', voucher.summary || ''].filter(Boolean).join('：'),
      })
      if (section === 'subsequent-payment') payments += 1
      else increases += 1
    }
    if (payments) persistSection('subsequent-payment')
    if (increases) persistSection('subsequent-increase')
    return { payments, increases }
  }

  function persistSection(section: UnrecordedSection): void {
    const config = SECTION_CONFIGS.find((item) => item.key === section)!
    const serialized = stored[section].value.map((row) => {
      const computedRow = computeF4UnrecordedRow(row, section)
      return {
        ...row,
        closingBalance: computedRow.closingBalance,
        averagePaymentDays: computedRow.averagePaymentDays,
        difference: computedRow.difference,
        estimatedAmount: computedRow.estimatedAmount,
      }
    })
    const json = JSON.stringify(serialized)
    lastPersisted.set(section, json)
    allResponses.value.set(config.storageKey, {
      item_id: config.storageKey,
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

  function debounceSave(): void {
    if (debounceTimer) clearTimeout(debounceTimer)
    debounceTimer = setTimeout(() => {
      debounceTimer = null
      flushSave()
    }, 1200)
  }

  function flushSave(): void {
    const items = [
      ...SECTION_CONFIGS.map((config) => allResponses.value.get(config.storageKey)),
      allResponses.value.get(NOTE_KEY),
      allResponses.value.get(CONCLUSION_KEY),
    ].filter(Boolean)
    if (items.length) {
      window.dispatchEvent(new CustomEvent('f4:save-items', { detail: { items } }))
    }
  }

  function rowClassName({ row }: { row: F4UnrecordedRow }): string {
    if (row.riskLevel === 'danger') return 'unrecorded-risk-danger'
    if (row.riskLevel === 'warning') return 'unrecorded-risk-warning'
    return ''
  }

  onBeforeUnmount(() => {
    if (debounceTimer) {
      clearTimeout(debounceTimer)
      debounceTimer = null
      flushSave()
    }
  })

  return {
    rows,
    subtotals,
    overallSummary,
    auditNote,
    auditConclusion,
    loadSection,
    getRows,
    getSubtotal,
    addRow,
    removeRow,
    updateCell,
    mergeOcrFields,
    distributeCutoffSamples,
    saveAuditNote,
    saveAuditConclusion,
    rowClassName,
    sectionConfigs: SECTION_CONFIGS,
  }
}

export default useF4UnrecordedCheck
