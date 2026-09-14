/**
 * H4-4 抽凭回填 / OCR → 支持性文件 字段映射
 *
 * 抽凭：业务内容 ← summary；对方科目/明细 ← counterpartAccount（可拆分）
 * OCR：支持性文件 ← 合同/发票/入库单等单据号拼接；并回填供应商、发票金额等
 */

import type { H4AdditionCheckRow } from './h4AdditionCheckModel'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 抽凭引擎 SampledVoucher 及历史兼容字段 */
export interface H4VoucherSampleLike {
  voucherNo?: string | null
  voucher_no?: string | null
  voucherDate?: string | null
  voucher_date?: string | null
  date?: string | null
  entryDate?: string | null
  summary?: string | null
  abstract?: string | null
  description?: string | null
  /** 对方科目（抽凭引擎标准字段） */
  counterpartAccount?: string | null
  counterpart_account?: string | null
  oppositeAccount?: string | null
  /** 对方明细 */
  counterpartDetail?: string | null
  oppositeDetail?: string | null
  detailAccount?: string | null
  accountName?: string | null
  accountCode?: string | null
  debitAmount?: string | number | null
  creditAmount?: string | number | null
  amount?: string | number | null
  debit?: string | number | null
  credit?: string | number | null
  abnormal?: boolean | null
  selectionReason?: string | null
  remark?: string | null
}

/** 可回填到 H4-4 行的补丁（均为可选） */
export type H4AdditionSamplePatch = Partial<Pick<
  H4AdditionCheckRow,
  | 'name'
  | 'voucherDate'
  | 'voucherNo'
  | 'businessContent'
  | 'oppositeAccount'
  | 'oppositeDetail'
  | 'amount'
  | 'supportingDocs'
  | 'supplier'
  | 'contractNo'
  | 'inboundNo'
  | 'invoiceNo'
  | 'invoiceAmount'
  | 'isAbnormal'
  | 'remark'
  | 'voucherResult'
>>

export interface H4OcrMapResult {
  patch: H4AdditionSamplePatch
  /** 用于确认弹窗的可读预览行 */
  previewLines: string[]
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _str(v: unknown): string {
  if (v == null) return ''
  return String(v).trim()
}

function _num(v: unknown): number {
  if (v == null || v === '') return 0
  if (typeof v === 'number') return Number.isFinite(v) ? v : 0
  const n = Number(String(v).replace(/,/g, ''))
  return Number.isFinite(n) ? n : 0
}

function _pick(obj: Record<string, unknown>, keys: string[]): string {
  for (const k of keys) {
    const v = obj[k]
    if (v != null && String(v).trim() !== '' && String(v) !== '0') return String(v).trim()
  }
  return ''
}

function _pickNum(obj: Record<string, unknown>, keys: string[]): number {
  for (const k of keys) {
    const n = _num(obj[k])
    if (n !== 0) return n
  }
  return 0
}

/**
 * 拆分对方科目：
 * 「应付账款/某某供应商」「应付账款-某某」→ account + detail
 */
export function splitCounterpartAccount(raw: string): { account: string; detail: string } {
  const s = _str(raw)
  if (!s) return { account: '', detail: '' }
  const parts = s.split(/[/／\-—|｜]/).map(p => p.trim()).filter(Boolean)
  if (parts.length >= 2) {
    return { account: parts[0], detail: parts.slice(1).join('/') }
  }
  return { account: s, detail: '' }
}

/** 合并支持性文件片段，去重 */
export function mergeSupportingDocs(existing: string, addition: string): string {
  const a = _str(existing)
  const b = _str(addition)
  if (!b) return a
  if (!a) return b
  const existParts = a.split(/\s*\/\s*/).map(p => p.trim()).filter(Boolean)
  const addParts = b.split(/\s*\/\s*/).map(p => p.trim()).filter(Boolean)
  const merged = [...existParts]
  for (const p of addParts) {
    const dup = merged.some(m => m === p || m.includes(p) || p.includes(m))
    if (!dup) merged.push(p)
  }
  return merged.join(' / ')
}

/** 借方优先（增加检查），否则取绝对值 amount */
export function resolveAdditionDebitAmount(sample: H4VoucherSampleLike): number {
  const debit = _num(sample.debitAmount ?? sample.debit)
  if (debit !== 0) return Math.abs(debit)
  const amt = _num(sample.amount)
  if (amt !== 0) return Math.abs(amt)
  const credit = _num(sample.creditAmount ?? sample.credit)
  return credit !== 0 ? Math.abs(credit) : 0
}

export function resolveVoucherDate(sample: H4VoucherSampleLike): string {
  return _str(sample.voucherDate ?? sample.voucher_date ?? sample.date ?? sample.entryDate)
}

export function resolveBusinessContent(sample: H4VoucherSampleLike): string {
  return _str(sample.summary ?? sample.abstract ?? sample.description)
}

export function resolveOppositeRaw(sample: H4VoucherSampleLike): string {
  return _str(
    sample.counterpartAccount
    ?? sample.counterpart_account
    ?? sample.oppositeAccount,
  )
}

// ─── 抽凭映射 ────────────────────────────────────────────────────────────────

/**
 * 将单笔抽凭样本映射为 H4-4 行补丁。
 * - 业务内容 ← 摘要（不再误写入支持性文件）
 * - 对方科目/明细 ← counterpartAccount（可拆分）
 * - 借方金额 ← debitAmount 优先
 */
export function mapVoucherSampleToAdditionPatch(sample: H4VoucherSampleLike): H4AdditionSamplePatch {
  const patch: H4AdditionSamplePatch = {}

  const voucherNo = _str(sample.voucherNo ?? sample.voucher_no)
  if (voucherNo) patch.voucherNo = voucherNo

  const voucherDate = resolveVoucherDate(sample)
  if (voucherDate) patch.voucherDate = voucherDate

  const businessContent = resolveBusinessContent(sample)
  if (businessContent) {
    patch.businessContent = businessContent
    // 名称空时可用摘要作默认物资名（调用方按需覆盖）
    patch.name = businessContent.slice(0, 40)
  }

  const oppositeRaw = resolveOppositeRaw(sample)
  if (oppositeRaw) {
    const { account, detail } = splitCounterpartAccount(oppositeRaw)
    if (account) patch.oppositeAccount = account
    if (detail) patch.oppositeDetail = detail
  } else {
    // 无对方科目时，不把本科目 accountName 当作对方
    const detailOnly = _str(sample.counterpartDetail ?? sample.oppositeDetail ?? sample.detailAccount)
    if (detailOnly) patch.oppositeDetail = detailOnly
  }

  const amount = resolveAdditionDebitAmount(sample)
  if (amount > 0) patch.amount = amount

  if (sample.abnormal === true) patch.isAbnormal = '是'

  const reason = _str(sample.selectionReason ?? sample.remark)
  if (reason) patch.remark = reason

  patch.voucherResult = '已抽凭'

  return patch
}

/**
 * 规范化抽凭引擎 emit 载荷：支持 `{ samples }` / 裸数组 / `{ rows }`
 */
export function normalizeFilledSamples(payload: unknown): H4VoucherSampleLike[] {
  if (payload == null) return []
  if (Array.isArray(payload)) return payload as H4VoucherSampleLike[]
  if (typeof payload === 'object') {
    const o = payload as Record<string, unknown>
    if (Array.isArray(o.samples)) return o.samples as H4VoucherSampleLike[]
    if (Array.isArray(o.rows)) return o.rows as H4VoucherSampleLike[]
  }
  return []
}

/**
 * 将补丁应用到现有行：
 * - forceKeys：始终覆盖（抽凭核心字段）
 * - 其余：仅当目标为空时写入（避免冲掉手工录入的名称等）
 */
export function applyAdditionSamplePatch(
  row: H4AdditionCheckRow,
  patch: H4AdditionSamplePatch,
  opts?: { forceKeys?: (keyof H4AdditionSamplePatch)[]; skipNameIfFilled?: boolean },
): void {
  const force = new Set<keyof H4AdditionSamplePatch>(opts?.forceKeys ?? [
    'voucherNo', 'voucherDate', 'businessContent', 'oppositeAccount', 'oppositeDetail',
    'amount', 'voucherResult', 'isAbnormal',
  ])
  const skipNameIfFilled = opts?.skipNameIfFilled !== false

  for (const [key, val] of Object.entries(patch) as [keyof H4AdditionSamplePatch, unknown][]) {
    if (val == null || val === '') continue
    if (key === 'name' && skipNameIfFilled && _str(row.name)) continue
    if (key === 'supportingDocs') {
      row.supportingDocs = mergeSupportingDocs(row.supportingDocs, String(val))
      continue
    }
    const cur = (row as any)[key]
    const empty = cur == null || cur === '' || (typeof cur === 'number' && cur === 0)
    if (force.has(key) || empty) {
      ;(row as any)[key] = val
    }
  }
  if (patch.voucherDate && !row.inboundDate) row.inboundDate = patch.voucherDate
}

// ─── OCR 映射 ────────────────────────────────────────────────────────────────

/**
 * 从 OCR extracted_fields 组装支持性文件描述，并映射供应商/合同/发票等。
 * 兼容 d4/contract-ocr 英文字段与中文键名。
 */
export function mapOcrToAdditionPatch(fields: Record<string, unknown>): H4OcrMapResult {
  const f = fields || {}
  const patch: H4AdditionSamplePatch = {}
  const previewLines: string[] = []

  const contractNo = _pick(f, ['contractNo', 'contract_no', '合同编号', '合同号'])
  const invoiceNo = _pick(f, ['invoiceNo', 'invoice_no', '发票号', '发票号码', 'invoiceRef'])
  const inboundNo = _pick(f, [
    'inboundNo', 'receiptNo', 'acceptanceRef', 'acceptance_no',
    '入库单号', '验收单号', 'controlTransferDoc',
  ])
  const supplier = _pick(f, [
    'counterparty', 'supplier', 'seller', 'vendor', '交易对方名称', '供应商', '对方单位',
  ])
  const serviceContent = _pick(f, [
    'serviceContent', 'productName', '物资名称', '品名', '货物名称', 'name',
  ])
  const signDate = _pick(f, ['signDate', 'date', 'deliveryTime', '签订日期', '日期', '入库日期'])
  const amount = _pickNum(f, [
    'contractAmount', 'invoiceAmount', 'amount', '合同金额', '发票金额', '金额',
  ])

  const docParts: string[] = []
  if (contractNo) docParts.push(`合同:${contractNo}`)
  if (invoiceNo) docParts.push(`发票:${invoiceNo}`)
  if (inboundNo) {
    // 若已是「合同:」风格则直接用；controlTransferDoc 可能是单据名称
    if (inboundNo.includes(':') || inboundNo.includes('：')) docParts.push(inboundNo)
    else docParts.push(`${_pick(f, ['acceptanceRef', 'acceptance_no']) ? '验收单' : '单据'}:${inboundNo}`)
  }
  if (serviceContent) docParts.push(`标的:${serviceContent.slice(0, 30)}`)

  const supportingDocs = docParts.join(' / ')
  if (supportingDocs) {
    patch.supportingDocs = supportingDocs
    previewLines.push(`支持性文件: ${supportingDocs}`)
  }

  if (contractNo) {
    patch.contractNo = contractNo
    previewLines.push(`合同编号: ${contractNo}`)
  }
  if (invoiceNo) {
    patch.invoiceNo = invoiceNo
    previewLines.push(`发票号: ${invoiceNo}`)
  }
  if (inboundNo && !inboundNo.includes(':')) {
    patch.inboundNo = inboundNo
    previewLines.push(`入库/验收单: ${inboundNo}`)
  }
  if (supplier) {
    patch.supplier = supplier
    previewLines.push(`供应商: ${supplier}`)
  }
  if (amount > 0) {
    patch.invoiceAmount = amount
    previewLines.push(`发票/合同金额: ${amount}`)
  }
  if (signDate) {
    patch.voucherDate = signDate
    previewLines.push(`日期: ${signDate}`)
  }
  if (serviceContent) {
    patch.name = serviceContent.slice(0, 40)
    previewLines.push(`物资名称: ${serviceContent.slice(0, 40)}`)
  }

  return { patch, previewLines }
}

/** 从 OCR 接口响应中取出 extracted_fields */
export function extractOcrFields(rawResponse: unknown): { fields: Record<string, unknown>; confidence: number } {
  if (!rawResponse || typeof rawResponse !== 'object') {
    return { fields: {}, confidence: 0 }
  }
  const root = rawResponse as Record<string, unknown>
  const data = (root.data && typeof root.data === 'object' ? root.data : root) as Record<string, unknown>
  const fields = (data.extracted_fields ?? data.fields ?? data) as Record<string, unknown>
  if (!fields || typeof fields !== 'object' || Array.isArray(fields)) {
    return { fields: {}, confidence: 0 }
  }
  // 若误把整包当 fields，去掉非字段元数据
  const cleaned = { ...fields }
  delete cleaned.extracted_fields
  delete cleaned.ocr_text
  delete cleaned.attachment_id
  delete cleaned.confidence
  delete cleaned.data
  const confidence = _num(data.confidence ?? root.confidence)
  return { fields: cleaned, confidence }
}

/**
 * 将 OCR 补丁合并到行：支持性文件做合并；金额/供应商等仅填空。
 */
export function applyOcrPatchToAdditionRow(row: H4AdditionCheckRow, patch: H4AdditionSamplePatch): void {
  if (patch.supportingDocs) {
    row.supportingDocs = mergeSupportingDocs(row.supportingDocs, patch.supportingDocs)
  }
  const fillEmpty = (key: keyof H4AdditionCheckRow, val: unknown) => {
    if (val == null || val === '') return
    const cur = (row as any)[key]
    const empty = cur == null || cur === '' || (typeof cur === 'number' && cur === 0)
    if (empty) (row as any)[key] = val
  }
  fillEmpty('contractNo', patch.contractNo)
  fillEmpty('invoiceNo', patch.invoiceNo)
  fillEmpty('inboundNo', patch.inboundNo)
  fillEmpty('supplier', patch.supplier)
  fillEmpty('invoiceAmount', patch.invoiceAmount)
  fillEmpty('voucherDate', patch.voucherDate)
  fillEmpty('name', patch.name)
  if (patch.voucherDate && !row.inboundDate) row.inboundDate = patch.voucherDate
}
