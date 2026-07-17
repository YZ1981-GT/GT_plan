/**
 * F2-33~35 检查/核查 — 类型与公式（对齐致同源模板）
 */
import { parseNum, calcSubtotal } from './useF2InvValFormulaEngine'
import type { ChecklistResponse } from './useF2ValuationFormData'

/** 存货科目组（1401~1411） */
export const F2_INVENTORY_ACCOUNT_CODES = '1401,1402,1403,1404,1405,1406,1407,1408,1409,1410,1411'

export const F2_INSPECTION_CATEGORIES = ['原材料', '产成品', '半成品', '周转材料', '其他'] as const

/** F2-33 采购入库检查行（账→单） */
export interface PurchaseInboundRow {
  id: string
  seq: number
  party: string
  invCategory: string
  voucherNo: string
  businessContent: string
  itemName: string
  unit: string
  qty: number
  amount: number
  counterpartAccount: string
  counterpartDetail: string
  recvDateNo: string
  recvQty: number
  inspectDateNo: string
  logisticsDateNo: string
  logisticsProvider: string
  invoiceQty: number
  invoiceDateNo: string
  invoiceParty: string
  invoiceAmount: number
  indexRef: string
  isAbnormal: boolean
  abnormalOverride: boolean | null
  remark: string
  sampleSource?: string
  /** 兼容旧字段 */
  docNo?: string
}

/** F2-34 材料领用检查行（账→单，贷方） */
export interface MaterialUsageRow {
  id: string
  seq: number
  party: string
  voucherNo: string
  businessContent: string
  itemName: string
  unit: string
  qty: number
  amount: number
  counterpartAccount: string
  counterpartDetail: string
  docDateNo: string
  docQty: number
  indexRef: string
  isAbnormal: boolean
  abnormalOverride: boolean | null
  remark: string
  sampleSource?: string
  docNo?: string
}

/** @deprecated 旧基座行；新表用 PurchaseInboundRow / MaterialUsageRow */
export type InspectionCheckRow = PurchaseInboundRow | MaterialUsageRow

export interface CoverageLine {
  category: string
  bookAmount: number
  checkedAmount: number
  ratio: number
}

export function emptyPurchaseInboundRow(seq: number, sampleSource?: string): PurchaseInboundRow {
  return {
    id: `f2pi-${Date.now().toString(36)}-${seq}`,
    seq,
    party: '',
    invCategory: '原材料',
    voucherNo: '',
    businessContent: '',
    itemName: '',
    unit: '',
    qty: 0,
    amount: 0,
    counterpartAccount: '',
    counterpartDetail: '',
    recvDateNo: '',
    recvQty: 0,
    inspectDateNo: '',
    logisticsDateNo: '',
    logisticsProvider: '',
    invoiceQty: 0,
    invoiceDateNo: '',
    invoiceParty: '',
    invoiceAmount: 0,
    indexRef: '',
    isAbnormal: false,
    abnormalOverride: null,
    remark: '',
    sampleSource,
  }
}

export function emptyMaterialUsageRow(seq: number, sampleSource?: string): MaterialUsageRow {
  return {
    id: `f2mu-${Date.now().toString(36)}-${seq}`,
    seq,
    party: '',
    voucherNo: '',
    businessContent: '',
    itemName: '',
    unit: '',
    qty: 0,
    amount: 0,
    counterpartAccount: '',
    counterpartDetail: '',
    docDateNo: '',
    docQty: 0,
    indexRef: '',
    isAbnormal: false,
    abnormalOverride: null,
    remark: '',
    sampleSource,
  }
}

/** @deprecated */
export function emptyInspectionRow(seq: number, sampleSource?: string): PurchaseInboundRow {
  return emptyPurchaseInboundRow(seq, sampleSource)
}

export function calcInspectionCoverage(checkedTotal: number, bookTotal: number): number {
  return bookTotal ? (checkedTotal / bookTotal) * 100 : 0
}

export function readBookTotal(allResponses: Map<string, ChecklistResponse>, sheetCode: string): number {
  return parseNum(allResponses.get(`${sheetCode}-book-total`)?.remark)
}

/** 采购入库逐项勾稽结果状态（供引导式弹窗实时校验面板）。 */
export type PurchaseCheckStatus = 'ok' | 'mismatch' | 'missing' | 'pending'

export interface PurchaseCheckResult {
  key: string
  label: string
  status: PurchaseCheckStatus
  detail: string
}

/**
 * 采购入库逐项勾稽（账 ↔ 入库单 ↔ 发票）。返回每条检查的状态与说明，
 * 供弹窗实时面板红黄提示。规则与 assessPurchaseAbnormal 完全一致：
 * 任一条 mismatch/missing ⟺ 自动异常（在 abnormalOverride 为 null 时）。
 */
export function evaluatePurchaseInboundChecks(r: PurchaseInboundRow): PurchaseCheckResult[] {
  const hasVoucher = !!(r.voucherNo || r.amount || r.qty)
  const hasRecv = !!(r.recvDateNo || r.recvQty)
  const hasInvoice = !!(r.invoiceDateNo || r.invoiceAmount || r.invoiceQty)
  const results: PurchaseCheckResult[] = []

  // 1. 入库单/验收单存在性
  if (hasVoucher && !hasRecv) {
    results.push({ key: 'recv_exist', label: '入库单/验收单存在', status: 'missing', detail: '有账面记录但缺入库单/验收单' })
  } else if (hasRecv) {
    results.push({ key: 'recv_exist', label: '入库单/验收单存在', status: 'ok', detail: r.recvDateNo || '已登记' })
  } else {
    results.push({ key: 'recv_exist', label: '入库单/验收单存在', status: 'pending', detail: '待填写' })
  }

  // 2. 账面数量 ↔ 入库数量
  results.push(_cmpQty('qty_recv', '账面数量 ↔ 入库数量', r.qty, r.recvQty, '账', '入库'))
  // 3. 账面数量 ↔ 发票数量
  results.push(_cmpQty('qty_invoice', '账面数量 ↔ 发票数量', r.qty, r.invoiceQty, '账', '发票'))
  // 4. 账面金额 ↔ 发票金额
  if (r.amount > 0 && r.invoiceAmount > 0) {
    const diff = Math.abs(r.amount - r.invoiceAmount)
    results.push({
      key: 'amount_invoice',
      label: '账面金额 ↔ 发票金额',
      status: diff > 0.01 ? 'mismatch' : 'ok',
      detail: diff > 0.01 ? `账 ${r.amount} vs 发票 ${r.invoiceAmount}（差 ${(r.amount - r.invoiceAmount).toFixed(2)}）` : '一致',
    })
  } else {
    results.push({ key: 'amount_invoice', label: '账面金额 ↔ 发票金额', status: 'pending', detail: '待填写' })
  }
  // 5. 入库数量 ↔ 发票数量
  if (hasRecv && hasInvoice && r.recvQty > 0 && r.invoiceQty > 0) {
    const diff = Math.abs(r.recvQty - r.invoiceQty)
    results.push({
      key: 'recv_invoice_qty',
      label: '入库数量 ↔ 发票数量',
      status: diff > 0.0001 ? 'mismatch' : 'ok',
      detail: diff > 0.0001 ? `入库 ${r.recvQty} vs 发票 ${r.invoiceQty}` : '一致',
    })
  } else {
    results.push({ key: 'recv_invoice_qty', label: '入库数量 ↔ 发票数量', status: 'pending', detail: '待填写' })
  }

  return results
}

function _cmpQty(
  key: string, label: string, a: number, b: number, aName: string, bName: string,
): PurchaseCheckResult {
  if (a > 0 && b > 0) {
    const diff = Math.abs(a - b)
    return {
      key, label,
      status: diff > 0.0001 ? 'mismatch' : 'ok',
      detail: diff > 0.0001 ? `${aName} ${a} vs ${bName} ${b}` : '一致',
    }
  }
  return { key, label, status: 'pending', detail: '待填写' }
}

/** 采购入库自动异常：数量/金额勾稽不一致，或关键原始凭证 */
export function assessPurchaseAbnormal(r: PurchaseInboundRow): boolean {
  if (r.abnormalOverride !== null) return r.abnormalOverride
  const hasVoucher = !!(r.voucherNo || r.amount || r.qty)
  const hasRecv = !!(r.recvDateNo || r.recvQty)
  const hasInvoice = !!(r.invoiceDateNo || r.invoiceAmount || r.invoiceQty)
  if (hasVoucher && !hasRecv) return true
  if (r.qty > 0 && r.recvQty > 0 && Math.abs(r.qty - r.recvQty) > 0.0001) return true
  if (r.qty > 0 && r.invoiceQty > 0 && Math.abs(r.qty - r.invoiceQty) > 0.0001) return true
  if (r.amount > 0 && r.invoiceAmount > 0 && Math.abs(r.amount - r.invoiceAmount) > 0.01) return true
  if (hasRecv && hasInvoice && r.recvQty > 0 && r.invoiceQty > 0
    && Math.abs(r.recvQty - r.invoiceQty) > 0.0001) return true
  return false
}

/** 材料领用自动异常：账数量与出库/领料数量不一致，或有账无单 */
export function assessMaterialAbnormal(r: MaterialUsageRow): boolean {
  if (r.abnormalOverride !== null) return r.abnormalOverride
  const hasVoucher = !!(r.voucherNo || r.amount || r.qty)
  const hasDoc = !!(r.docDateNo || r.docQty || r.docNo)
  if (hasVoucher && !hasDoc) return true
  if (r.qty > 0 && r.docQty > 0 && Math.abs(r.qty - r.docQty) > 0.0001) return true
  return false
}

export function buildCoverageByCategory(
  rows: PurchaseInboundRow[],
  bookByCategory: Record<string, number>,
): CoverageLine[] {
  const checked: Record<string, number> = {}
  for (const r of rows) {
    const cat = r.invCategory || '其他'
    checked[cat] = (checked[cat] || 0) + (Number(r.amount) || 0)
  }
  const cats = new Set([...Object.keys(bookByCategory), ...Object.keys(checked), ...F2_INSPECTION_CATEGORIES])
  return [...cats].map((category) => {
    const bookAmount = Number(bookByCategory[category] || 0)
    const checkedAmount = Number(checked[category] || 0)
    return {
      category,
      bookAmount,
      checkedAmount,
      ratio: calcInspectionCoverage(checkedAmount, bookAmount),
    }
  }).filter((l) => l.bookAmount > 0 || l.checkedAmount > 0)
}

function parseAbnormalFlag(raw: unknown): { isAbnormal: boolean; abnormalOverride: boolean | null } {
  if (raw === true || raw === false) return { isAbnormal: raw, abnormalOverride: raw }
  const s = String(raw ?? '').trim().toLowerCase()
  if (!s) return { isAbnormal: false, abnormalOverride: null }
  if (['是', 'yes', 'y', 'true', '1'].includes(s)) return { isAbnormal: true, abnormalOverride: true }
  if (['否', 'no', 'n', 'false', '0'].includes(s)) return { isAbnormal: false, abnormalOverride: false }
  return { isAbnormal: Boolean(raw), abnormalOverride: null }
}

export function migrateLegacyInspectionRow(raw: Record<string, unknown>, kind: 'purchase' | 'material'): PurchaseInboundRow | MaterialUsageRow {
  const abn = parseAbnormalFlag(raw.isAbnormal ?? raw.abnormalOverride)
  if (kind === 'material') {
    const base = emptyMaterialUsageRow(Number(raw.seq) || 1)
    return {
      ...base,
      ...raw,
      id: String(raw.id || base.id),
      seq: Number(raw.seq) || base.seq,
      party: String(raw.party || ''),
      voucherNo: String(raw.voucherNo || ''),
      businessContent: String(raw.businessContent || ''),
      itemName: String(raw.itemName || ''),
      unit: String(raw.unit || ''),
      qty: Number(raw.qty || 0) || 0,
      amount: Number(raw.amount || 0) || 0,
      counterpartAccount: String(raw.counterpartAccount || ''),
      counterpartDetail: String(raw.counterpartDetail || ''),
      docDateNo: String(raw.docDateNo || raw.docNo || ''),
      docQty: Number(raw.docQty || 0) || 0,
      indexRef: String(raw.indexRef || ''),
      remark: String(raw.remark || ''),
      isAbnormal: abn.isAbnormal,
      abnormalOverride: (typeof raw.abnormalOverride === 'boolean' ? raw.abnormalOverride : abn.abnormalOverride),
    } as MaterialUsageRow
  }
  const base = emptyPurchaseInboundRow(Number(raw.seq) || 1)
  return {
    ...base,
    ...raw,
    id: String(raw.id || base.id),
    seq: Number(raw.seq) || base.seq,
    party: String(raw.party || ''),
    invCategory: String(raw.invCategory || ''),
    voucherNo: String(raw.voucherNo || ''),
    businessContent: String(raw.businessContent || ''),
    itemName: String(raw.itemName || ''),
    unit: String(raw.unit || ''),
    qty: Number(raw.qty || 0) || 0,
    amount: Number(raw.amount || 0) || 0,
    counterpartAccount: String(raw.counterpartAccount || ''),
    counterpartDetail: String(raw.counterpartDetail || ''),
    recvDateNo: String(raw.recvDateNo || raw.docNo || ''),
    recvQty: Number(raw.recvQty || 0) || 0,
    inspectDateNo: String(raw.inspectDateNo || ''),
    logisticsDateNo: String(raw.logisticsDateNo || ''),
    logisticsProvider: String(raw.logisticsProvider || ''),
    invoiceQty: Number(raw.invoiceQty || 0) || 0,
    invoiceDateNo: String(raw.invoiceDateNo || ''),
    invoiceParty: String(raw.invoiceParty || ''),
    invoiceAmount: Number(raw.invoiceAmount || 0) || 0,
    indexRef: String(raw.indexRef || ''),
    remark: String(raw.remark || ''),
    isAbnormal: abn.isAbnormal,
    abnormalOverride: (typeof raw.abnormalOverride === 'boolean' ? raw.abnormalOverride : abn.abnormalOverride),
  } as PurchaseInboundRow
}

export { calcSubtotal }

/* ─── F2-35 委托加工三表 ─── */

export interface SubcontractBasicRow {
  id: string
  seq: number
  year: string
  opening: number
  increase: number
  decrease: number
  closing: number
  processingFee: number
}

export interface SubcontractSupplier1Row {
  id: string
  seq: number
  year: string
  supplier: string
  processStep: string
  inboundQty: number
  inboundAmount: number
  feeAmount: number
  settlementDocs: string
  voucherNo: string
}

export interface SubcontractSupplier2Row {
  id: string
  seq: number
  processor: string
  contractNo: string
  issueDate: string
  issueCost: number
  fee: number
  recoverCost: number
  unrecoveredNote: string
  indexRef: string
  remark: string
}

export function emptySubBasic(seq: number): SubcontractBasicRow {
  return {
    id: `f2sb-${Date.now().toString(36)}-${seq}`,
    seq, year: '', opening: 0, increase: 0, decrease: 0, closing: 0, processingFee: 0,
  }
}

export function emptySubSupplier1(seq: number): SubcontractSupplier1Row {
  return {
    id: `f2s1-${Date.now().toString(36)}-${seq}`,
    seq, year: '', supplier: '', processStep: '', inboundQty: 0, inboundAmount: 0,
    feeAmount: 0, settlementDocs: '', voucherNo: '',
  }
}

export function emptySubSupplier2(seq: number): SubcontractSupplier2Row {
  return {
    id: `f2s2-${Date.now().toString(36)}-${seq}`,
    seq, processor: '', contractNo: '', issueDate: '', issueCost: 0, fee: 0,
    recoverCost: 0, unrecoveredNote: '', indexRef: '', remark: '',
  }
}

/** 期末 = 期初 + 增加 − 减少 */
export function calcSubClosing(r: Pick<SubcontractBasicRow, 'opening' | 'increase' | 'decrease'>): number {
  return (Number(r.opening) || 0) + (Number(r.increase) || 0) - (Number(r.decrease) || 0)
}

/** 委托加工计价勾稽状态：ok=正常 / unrecovered=发出未全额收回 / valuation=收回≠发出+加工费 / pending=未填 */
export type SubcontractRecoverStatus = 'ok' | 'unrecovered' | 'valuation' | 'pending'

export interface SubcontractRecoverCheck {
  /** 应收回材料成本 = 发出材料成本 + 加工费 */
  expected: number
  /** 收回 − 应收回 */
  variance: number
  status: SubcontractRecoverStatus
  detail: string
}

/**
 * 委托加工计价勾稽：收回材料成本应 ≈ 发出材料成本 + 加工费（CAS1 存货成本恒等）。
 * - 未发出（issueCost≤0）→ pending
 * - 收回 < 发出 → unrecovered（材料未全额收回，重大风险，须说明/函证）
 * - 收回 ≥ 发出但 |收回 − (发出+加工费)| > 0.01 → valuation（计价差异，收回成本未含/多含加工费）
 * - 否则 ok
 */
export function evaluateSubcontractRecover(
  r: Pick<SubcontractSupplier2Row, 'issueCost' | 'fee' | 'recoverCost'>,
): SubcontractRecoverCheck {
  const round2 = (n: number) => Math.round(n * 100) / 100
  const issue = Number(r.issueCost) || 0
  const fee = Number(r.fee) || 0
  const recover = Number(r.recoverCost) || 0
  const expected = round2(issue + fee)
  if (issue <= 0) {
    return { expected, variance: 0, status: 'pending', detail: '待填写' }
  }
  if (recover + 0.01 < issue) {
    return {
      expected,
      variance: round2(recover - expected),
      status: 'unrecovered',
      detail: `收回 ${recover} < 发出 ${issue}，未全额收回`,
    }
  }
  const variance = round2(recover - expected)
  if (Math.abs(variance) > 0.01) {
    return {
      expected,
      variance,
      status: 'valuation',
      detail: `收回 ${recover} ≠ 发出+加工费 ${expected}（差 ${variance}）`,
    }
  }
  return { expected, variance: 0, status: 'ok', detail: '收回≈发出+加工费' }
}
