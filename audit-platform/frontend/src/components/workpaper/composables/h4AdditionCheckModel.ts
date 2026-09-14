/**
 * H4-4 工程物资增加检查表 — 对齐致同「增加检查表H4-4」
 *
 * 编制逻辑：目标认定 → 样本选取 → 测试（记账凭证六列 + 核对内容1–5）
 *          → 检查比例（勾稽 H4-2 本期增加，防 #DIV/0!）→ 说明/结论
 * 平台增强：入库单/发票/合同三方核对（差异列）；关联方预埋 → H4-9
 */

import { calcSubtotal } from './useH4FormulaEngine'

// ─── Options ─────────────────────────────────────────────────────────────────

export const SAMPLING_METHOD_OPTS = [
  '货币单元抽样',
  '随机抽样',
  '系统抽样',
  '判断抽样',
] as const

/**
 * 测试内容说明（核对内容 1–5）
 * 第5项补全致同模板「……」：三方核对
 */
export const H4_ADDITION_TEST_CONTENT_ITEMS = [
  '原始凭证是否齐全（合同/发票/入库单/验收单等）',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确（对方科目、进项税、资本化归属等）',
  '是否记录于恰当的会计期间（截止测试）',
  '入库单、发票与合同在金额及供应商信息上三方一致',
] as const

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H4AdditionChecks {
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
}

export interface H4AdditionCheckRow {
  rowId: string
  seq: number
  /** 工程物资类别 */
  category: string
  /** 工程物资名称 */
  name: string
  /** @deprecated 兼容旧字段，可并入类别 */
  spec: string
  /** 记账凭证日期 */
  voucherDate: string
  /** 凭证编号 */
  voucherNo: string
  /** 业务内容 */
  businessContent: string
  /** 对方科目 */
  oppositeAccount: string
  /** 对方明细科目 */
  oppositeDetail: string
  /** 借方金额（=amount，跨表/关联方仍读 amount） */
  amount: number
  /** 支持性文件 */
  supportingDocs: string
  /** 供应商（平台增强 / 关联方带入） */
  supplier: string
  /** 合同编号 */
  contractNo: string
  /** 入库日期（兼容旧数据；新表优先用 voucherDate） */
  inboundDate: string
  /** 入库单号 */
  inboundNo: string
  /** 发票号 */
  invoiceNo: string
  /** 发票金额 */
  invoiceAmount: number
  /** 差异 = 借方金额 − 发票金额（公式） */
  diff: number
  /** 验收人 */
  inspector: string
  checks: H4AdditionChecks
  indexRef: string
  /** @deprecated 等同 indexRef */
  refIndex: string
  isAbnormal: string
  conclusion: string
  remark: string
  isRelatedParty: string
  relatedPartyName: string
  relationship: string
  voucherResult: string
  hasAttachment: boolean
}

export interface H4AdditionSamplingParams {
  /** 本期新增工程物资合计（总体，对应 H4-2 审定本期增加） */
  populationAmount: number
  samplingMethod: string
  specificSampleNote: string
  materialityLevel: number
}

export interface H4AdditionSummary {
  checkedCount: number
  checkedAmount: number
  coverageRate: number
  anomalyCount: number
  incompleteCheckCount: number
  diffCount: number
  issueCount: number
}

export interface LinkedAdditionTotal {
  amount: number
  purchase: number
  otherIncrease: number
  source: 'H4-2' | ''
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _bool(v: unknown): boolean {
  return v === true || v === 'Y' || v === 'y' || v === '是' || v === 1 || v === '1'
}

function _emptyChecks(): H4AdditionChecks {
  return { check1: false, check2: false, check3: false, check4: false, check5: false }
}

function _normChecks(raw: unknown): H4AdditionChecks {
  const base = _emptyChecks()
  if (!raw || typeof raw !== 'object') return base
  const o = raw as Record<string, unknown>
  return {
    check1: _bool(o.check1),
    check2: _bool(o.check2),
    check3: _bool(o.check3),
    check4: _bool(o.check4),
    check5: _bool(o.check5),
  }
}

function _normChecksFromRow(raw: any): H4AdditionChecks {
  if (raw?.checks) return _normChecks(raw.checks)
  return _normChecks({
    check1: raw?.check1,
    check2: raw?.check2,
    check3: raw?.check3,
    check4: raw?.check4,
    check5: raw?.check5,
  })
}

/** 差异 = 借方金额 − 发票金额 */
export function calcInvoiceDiff(row: Pick<H4AdditionCheckRow, 'amount' | 'invoiceAmount'>): number {
  return Math.round((_num(row.amount) - _num(row.invoiceAmount)) * 100) / 100
}

/** 检查比例：总体≤0 时返回 0，避免 #DIV/0! */
export function calcCoverageRate(checkedAmount: number, population: number): number {
  if (population <= 0) return 0
  return Math.min(100, Math.round((checkedAmount / population) * 10000) / 100)
}

export function createEmptySamplingParams(): H4AdditionSamplingParams {
  return {
    populationAmount: 0,
    samplingMethod: '货币单元抽样',
    specificSampleNote: '',
    materialityLevel: 0,
  }
}

export function normalizeSamplingParams(raw: unknown): H4AdditionSamplingParams {
  const base = createEmptySamplingParams()
  if (!raw || typeof raw !== 'object') return base
  const o = raw as Record<string, unknown>
  return {
    populationAmount: _num(o.populationAmount),
    samplingMethod: String(o.samplingMethod ?? base.samplingMethod),
    specificSampleNote: String(o.specificSampleNote ?? ''),
    materialityLevel: _num(o.materialityLevel),
  }
}

/** 核对内容 1–4 是否齐全（第5项为三方核对增强项） */
export function isCheckIncomplete(row: Pick<H4AdditionCheckRow, 'checks'>): boolean {
  const c = row.checks
  return !c.check1 || !c.check2 || !c.check3 || !c.check4
}

export function normalizeAdditionRow(raw: any, idx = 0): H4AdditionCheckRow {
  const name = String(raw.name ?? raw.materialName ?? '')
  const category = String(raw.category ?? raw.spec ?? raw.specModel ?? '')
  const amount = _num(raw.amount ?? raw.debitAmount)
  const invoiceAmount = _num(raw.invoiceAmount)
  const voucherDate = String(raw.voucherDate ?? raw.inboundDate ?? raw.receiptDate ?? '')
  const inboundDate = String(raw.inboundDate ?? raw.receiptDate ?? voucherDate)
  const voucherNo = String(raw.voucherNo ?? '')
  const inboundNo = String(raw.inboundNo ?? raw.receiptNo ?? '')
  const supportingDocs = String(
    raw.supportingDocs
    ?? [inboundNo, raw.invoiceNo, raw.contractNo, raw.inspector].filter(Boolean).join(' / ')
    ?? '',
  )

  const row: H4AdditionCheckRow = {
    rowId: raw.rowId ?? `h44-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    seq: raw.seq ?? idx + 1,
    category,
    name,
    spec: String(raw.spec ?? raw.specModel ?? category),
    voucherDate,
    voucherNo,
    businessContent: String(raw.businessContent ?? ''),
    oppositeAccount: String(raw.oppositeAccount ?? ''),
    oppositeDetail: String(raw.oppositeDetail ?? ''),
    amount,
    supportingDocs,
    supplier: String(raw.supplier ?? ''),
    contractNo: String(raw.contractNo ?? ''),
    inboundDate,
    inboundNo,
    invoiceNo: String(raw.invoiceNo ?? ''),
    invoiceAmount,
    diff: 0,
    inspector: String(raw.inspector ?? ''),
    checks: _normChecksFromRow(raw),
    indexRef: String(raw.indexRef ?? raw.refIndex ?? ''),
    refIndex: String(raw.refIndex ?? raw.indexRef ?? ''),
    isAbnormal: String(raw.isAbnormal ?? ''),
    conclusion: String(raw.conclusion ?? ''),
    remark: String(raw.remark ?? ''),
    isRelatedParty: String(raw.isRelatedParty ?? ''),
    relatedPartyName: String(raw.relatedPartyName ?? ''),
    relationship: String(raw.relationship ?? ''),
    voucherResult: String(raw.voucherResult ?? ''),
    hasAttachment: Boolean(raw.hasAttachment),
  }
  row.diff = calcInvoiceDiff(row)
  row.refIndex = row.indexRef
  return row
}

export function recalcAdditionRow(row: H4AdditionCheckRow): void {
  row.diff = calcInvoiceDiff(row)
  row.refIndex = row.indexRef
  if (!row.inboundDate && row.voucherDate) row.inboundDate = row.voucherDate
  if (!row.spec && row.category) row.spec = row.category
}

export function calcAdditionSummary(
  rows: H4AdditionCheckRow[],
  population: number,
): H4AdditionSummary {
  const checkedAmount = calcSubtotal(rows.map(r => r.amount))
  const anomalyCount = rows.filter(r => r.isAbnormal === '是' || r.isAbnormal === 'Y').length
  const incompleteCheckCount = rows.filter(isCheckIncomplete).length
  const diffCount = rows.filter(r => Math.abs(r.diff) > 0.01 && _num(r.invoiceAmount) > 0).length
  return {
    checkedCount: rows.length,
    checkedAmount,
    coverageRate: calcCoverageRate(checkedAmount, population),
    anomalyCount,
    incompleteCheckCount,
    diffCount,
    issueCount: anomalyCount + incompleteCheckCount + diffCount,
  }
}

/** 从 H4-2 明细行汇总本期增加（采购+其他增加） */
export function sumDetailIncrease(detailRows: any[]): LinkedAdditionTotal {
  let purchase = 0
  let otherIncrease = 0
  for (const r of detailRows) {
    purchase += _num(r.purchaseAmount)
    otherIncrease += _num(r.otherIncrease)
    // 兼容已算好的入库小计（若无分项则用小计）
    if (!_num(r.purchaseAmount) && !_num(r.otherIncrease) && _num(r.increaseSubtotal)) {
      purchase += _num(r.increaseSubtotal)
    }
  }
  const amount = Math.round((purchase + otherIncrease) * 100) / 100
  return {
    amount,
    purchase: Math.round(purchase * 100) / 100,
    otherIncrease: Math.round(otherIncrease * 100) / 100,
    source: amount > 0 ? 'H4-2' : '',
  }
}

export function buildNoteDraft(summary: H4AdditionSummary, population: number): string {
  const lines = [
    `本期增加检查样本 ${summary.checkedCount} 笔，检查借方合计 ${summary.checkedAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，总体（本期新增） ${population.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，检查比例 ${summary.coverageRate.toFixed(2)}%。`,
  ]
  if (population > 0 && summary.coverageRate < 20) {
    lines.push('检查比例偏低：已/拟扩大样本量，或说明判断抽样理由：________。')
  }
  if (summary.diffCount > 0) {
    lines.push(`入账金额与发票金额存在差异 ${summary.diffCount} 笔，已/拟核实原因并记录于备注。`)
  }
  if (summary.anomalyCount > 0) {
    lines.push(`标记异常 ${summary.anomalyCount} 笔，详见备注及拟调整事项（→ H4-3）。`)
  }
  if (summary.incompleteCheckCount > 0) {
    lines.push(`核对内容 1–4 未全部勾选 ${summary.incompleteCheckCount} 笔，请补充测试记录。`)
  }
  lines.push('关注大额采购、关联方采购及跨期入库的截止；三方核对见核对内容第 5 项。')
  return lines.join('\n')
}

export function buildConclusionDraft(summary: H4AdditionSummary): string {
  if (summary.checkedCount === 0) {
    return '本期尚未抽取增加样本。完成样本选取与测试后，再就是否实现审计目标发表结论。'
  }
  if (summary.issueCount === 0) {
    return `基于上述检查（样本 ${summary.checkedCount} 笔，检查比例 ${summary.coverageRate.toFixed(2)}%），本期抽查的工程物资增加在存在、计价及截止方面未见重大异常，可为相关认定提供充分、适当的审计证据。`
  }
  return `基于上述检查（样本 ${summary.checkedCount} 笔，检查比例 ${summary.coverageRate.toFixed(2)}%），发现关注事项 ${summary.issueCount} 项（含异常/三方差异/核对未完），详见审计说明；除已识别事项外，其余抽查项目未见重大异常。`
}
