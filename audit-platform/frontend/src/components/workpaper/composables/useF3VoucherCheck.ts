/**
 * useF3VoucherCheck — F3-7 应付票据检查表
 *
 * 对齐源表三个检查区：
 *  1. 本期借方金额检查（票据减少·兑付）：记账凭证 + 付款审批单 + 银行回单
 *  2. 本期贷方金额检查（票据增加·开票）：记账凭证 + 入库单/验收单 + 采购发票
 *  3. 资产负债表日后借方检查：结构同借方区，关注应计未计
 * 每笔通过弹窗逐单据上传OCR核对（参照F2-56模式），并计算检查比例。
 * 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读走共享回填函数 `useVoucherCheckFill`：一个对方科目一行
 * （后端配对），按分录指纹去重，行元数据 `_gt` 随行 JSON 落库（spec voucher-identity-writeback-and-audit-phase 任务 11）。
 */
import { ref, computed, watch, onBeforeUnmount, type ComputedRef } from 'vue'
import { calcSubtotal, parseNum } from './useF3FormulaEngine'
import {
  F3_ROW_ID_PREFIX,
  resolveF3RowId,
  type F3RowIdentityMintStats,
} from './f3RowIdentity'
import type { UseF3BaseOptions } from './useF3Adjudication'
import {
  metaOf, sideTableOf, useVoucherCheckFill, withRowMeta,
  type EngineFilledPayload, type FillSample, type PreparedItem,
} from './shared/voucherCheckFill'
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

function migrateRow(
  raw: any,
  i: number,
  section: F3VoucherSection,
  stats?: F3RowIdentityMintStats,
): F3VoucherCheckRow {
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
  return withRowMeta({
    ...base,
    // 🔴 缺 rowId 时铸新并记数（委托 f3RowIdentity 单源）；`loadSection` 据此立即回写。
    rowId: resolveF3RowId(raw, F3_ROW_ID_PREFIX.voucher, stats),
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
  }, raw)
}

export function safeParseVoucherRows(
  jsonStr: string | null | undefined,
  section: F3VoucherSection,
  stats?: F3RowIdentityMintStats,
): F3VoucherCheckRow[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    if (!Array.isArray(parsed)) return []
    const rows = parsed.map((raw, i) => migrateRow(raw, i, section, stats))
    const pruned = rows.filter((row) => !isBlankVoucherRow(row))
    const kept = pruned.length ? pruned : rows.slice(0, 1)
    return kept.map((row, i) => ({ ...row, seq: i + 1 }))
  } catch {
    return []
  }
}

/** 待写入项进哪区：按分录自己的借贷栏（`sideTableOf`，贷方红字进本期贷方区、带符号照记） */
export function f3SectionOf(item: Pick<PreparedItem, 'debitAmount' | 'creditAmount'>): F3VoucherSection {
  return sideTableOf(item)
}

/** 共享回填函数的待写入项 → 检查行：金额取样本自己那一栏，对方科目 = 编码、明细科目 = 名称（配不上写「多科目」） */
export function mapPreparedToF3Row(item: PreparedItem): F3VoucherCheckRow {
  const s = item.sample as PreparedItem['sample'] & { summary?: string | null }
  const code = item.counterpartAccount
  const name = item.counterpartAccountName
  const amount = f3SectionOf(item) === 'credit'
    ? parseNum(item.creditAmount)
    : (parseNum(item.debitAmount) || parseNum(item.creditAmount))
  return {
    ...emptyVoucherRow(0, 0),
    voucherDate: s.voucherDate || '',
    voucherNo: s.voucherNo || '',
    businessContent: s.summary || '',
    counterAccount: code,
    detailAccount: name && name !== code ? name : '',
    amount,
    sampleSource: item.meta.src.includes('attach') ? '挂凭' : '抽凭引擎',
  }
}

/** 行上已填票据类别、审批 / 回单 / 入库 / 发票、其他证据、索引、异常判断或说明（替换与撤销抽凭时据此先确认） */
export function hasF3VoucherContent(r: F3VoucherCheckRow): boolean {
  return [r.noteType, r.approvalDateNo, r.approvalProper, r.bankReceiptDate, r.bankPayee, r.receiptDateNo,
    r.receiptProduct, r.receiptUnit, r.invoiceDateNo, r.invoiceCounterparty, r.otherEvidence, r.indexNo,
    r.isAbnormal, r.issueDesc].some((v) => String(v ?? '').trim() !== '')
    || [r.bankAmount, r.receiptQty, r.invoiceAmount].some((n) => Number(n) !== 0)
}

const SECTIONS: readonly F3VoucherSection[] = ['debit', 'credit', 'subsequent']

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

  // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读：共享回填函数（三区各一张表）
  /** 已在某区的分录（按指纹）：再次回填 / 挂凭导入仍进那区 */
  function sectionHolding(lfp: string | null): F3VoucherSection | null {
    if (!lfp) return null
    for (const section of SECTIONS) {
      if ((stored[section].value ?? []).some((r) => metaOf(r)?.lfp === lfp)) return section
    }
    return null
  }
  /**
   * 一区一张表：写入时去掉空白占位行（区里没有行时补的那行空行，原实现追加时留着它），区空了补一行空白行；
   * 序号重排，新行的附件位按区内现有最大位顺延
   */
  const sectionTable = (section: F3VoucherSection) => computed<F3VoucherCheckRow[]>({
    get: () => stored[section].value ?? [],
    set: (list) => {
      const kept = list.filter((r) => !!metaOf(r) || !isBlankVoucherRow(r))
      const next = kept.length ? kept : [emptyVoucherRow(1)]
      let slot = Math.max(0, ...next.map((r) => Number(r.attSlot) || 0))
      next.forEach((r, i) => {
        r.seq = i + 1
        if (!r.attSlot) r.attSlot = ++slot
      })
      stored[section].value = next
    },
  })
  const sectionTables = { debit: sectionTable('debit'), credit: sectionTable('credit'), subsequent: sectionTable('subsequent') }
  const voucherFill = useVoucherCheckFill<F3VoucherCheckRow>({
    projectId: () => options.projectId?.value,
    tables: sectionTables,
    tableOf: (item) => sectionHolding(item.meta.lfp) ?? f3SectionOf(item),
    mapSampleToRow: (item) => mapPreparedToF3Row(item),
    persist: () => persistRows(),
    hasUserContent: hasF3VoucherContent,
    readonly: () => readonly.value,
  })
  /** 年审阶段的预审行只读（不可改、不可删） */
  function lockedIn(section: F3VoucherSection, rowId: string): boolean {
    const row = (stored[section].value ?? []).find((r) => r.rowId === rowId)
    return !!row && voucherFill.isRowLocked(row)
  }

  function loadSection(section: F3VoucherSection): void {
    // 🔴 铸了新行身份就立即回写（spec f3-sync-coverage-and-first-canary Task 14）：
    // 不回写则下次载入再铸新 rowId，行身份每次都变，破坏 OO↔HTML roundtrip。
    const stats: F3RowIdentityMintStats = { minted: 0 }
    const target = stored[section]
    target.value = safeParseVoucherRows(
      allResponses.value.get(ITEM_KEYS[section])?.remark,
      section,
      stats,
    )
    voucherFill.markLoaded()
    if (!target.value || target.value.length === 0) {
      target.value = [emptyVoucherRow(1)]
      return
    }
    if (stats.minted > 0 && !readonly.value) persistRows()
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
    if (readonly.value || lockedIn(section, rowId)) return
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
    if (readonly.value || lockedIn(section, rowId)) return
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
    if (readonly.value || lockedIn(section, patch.rowId)) return
    const rows = stored[section].value ?? []
    const idx = rows.findIndex((r) => r.rowId === patch.rowId)
    if (idx === -1) return
    rows[idx] = withRowMeta({ ...patch }, rows[idx])
    persistRows()
  }

  /**
   * 抽凭引擎回填：分录按借贷方向进本期借方 / 贷方区（贷方有正数且借方没有正数进贷方区，其余进借方区），
   * 一个对方科目一行（后端配对），按分录指纹去重；「替换本阶段抽凭行」只动这两区。
   * 原实现借贷双填拆两行、红字进贷方区且金额记 0、不去重，已删除。
   */
  function onEngineFilled(payload: EngineFilledPayload) {
    return voucherFill.onEngineFilled(payload, { tables: ['debit', 'credit'] })
  }

  /** 从序时账挂入导入：幂等追加，与抽凭命中同一分录只留一行 */
  function onAttachImported(samples: FillSample[]) {
    return voucherFill.onAttachImported(samples, { tables: ['debit', 'credit'] })
  }

  function persistRows(): void {
    for (const section of SECTIONS) {
      const key = ITEM_KEYS[section]
      allResponses.value.set(key, {
        item_id: key, conclusion: null, remark: JSON.stringify(voucherFill.guardPersist(stored[section].value ?? [], section)),
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
    // 抽凭回填 / 挂凭导入 / 撤销 / 年审阶段预审行只读（共享回填函数）
    onEngineFilled, onAttachImported, onUndoRequest: voucherFill.onUndoRequest,
    voucherRowClass: voucherFill.rowClass, isVoucherRowLocked: voucherFill.isRowLocked,
    voucherFillReady: voucherFill.ready,
  }
}

export default useF3VoucherCheck
