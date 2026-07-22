/**
 * H4-5 工程物资减少检查表 — 对齐致同「减少检查表H4-5」
 *
 * 编制逻辑：目标认定 → 样本选取 → 测试（原值/减值/净值/清理损益 + 核对内容1–5）
 *          → 检查比例（防 #DIV/0!）→ 说明/结论
 * 平台增强：领用出库 ↔ H2 在建工程勾稽；关联方预埋 → H4-9
 */

import { calcSubtotal } from './useH4FormulaEngine'

// ─── Options ─────────────────────────────────────────────────────────────────

/** 减少方式（对齐致同「减少方式」+ 领用出库平台联动） */
export const DISPOSAL_METHOD_OPTS = [
  '领用出库',
  '退货',
  '报废',
  '盘亏',
  '出售',
  '其他',
] as const

export type DisposalMethod = (typeof DISPOSAL_METHOD_OPTS)[number] | ''

/** @deprecated 兼容旧名 */
export const DISPOSAL_REASON_OPTIONS = DISPOSAL_METHOD_OPTS

export type DisposalReason = DisposalMethod

export const SAMPLING_METHOD_OPTS = [
  '货币单元抽样',
  '随机抽样',
  '系统抽样',
  '判断抽样',
] as const

/**
 * 测试内容说明（核对内容 1–5）
 * 第5项补全致同模板空白：H2勾稽 + 清理净损益
 */
export const H4_DISPOSAL_TEST_CONTENT_ITEMS = [
  '原始凭证是否齐全（领料单/出库单/报废审批/处置合同等）',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确（对方科目、减值结转、损益确认）',
  '是否记录于恰当的会计期间（截止测试）',
  '领用出库与在建工程（H2）勾稽一致；处置/报废清理净损益计算正确',
] as const

// ─── Types ───────────────────────────────────────────────────────────────────

export interface H4DisposalChecks {
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
}

export interface H4DisposalCheckRow {
  rowId: string
  seq: number
  /** 工程物资类别 */
  category: string
  /** 工程物资名称 */
  name: string
  /** 规格型号（旧字段兼容，可并入类别说明） */
  spec: string
  /** 入账凭证号 */
  voucherNo: string
  /** 减少方式 */
  disposalMethod: DisposalMethod
  /** @deprecated 兼容旧字段，等同 disposalMethod */
  reason: DisposalMethod
  /** 对方科目 */
  oppositeAccount: string
  quantity: number
  /** 原值（贷记工程物资金额） */
  originalCost: number
  /** @deprecated 兼容旧字段，等同 originalCost；跨表勾稽仍读 amount */
  amount: number
  /** 减值准备（随原值结转） */
  impairment: number
  /** 净值 = 原值 − 减值准备（公式） */
  netValue: number
  /** 清理费用 */
  disposalCost: number
  /** 清理收入 */
  disposalIncome: number
  /** 清理净损益 = 清理收入 − 清理费用 − 净值（公式） */
  disposalNetPl: number
  /** 减少日期 */
  disposalDate: string
  /** 支持性文件 */
  supportingDocs: string
  /** 领料单号（领用场景） */
  pickingNo: string
  department: string
  projectName: string
  approver: string
  /** 对应 H2 编号（领用出库必填） */
  h2Ref: string
  checks: H4DisposalChecks
  indexRef: string
  isAbnormal: string
  conclusion: string
  remark: string
  isRelatedParty: string
  relatedPartyName: string
  relationship: string
  voucherResult: string
}

export interface H4DisposalSamplingParams {
  /** 本期减少工程物资贷方合计（总体） */
  populationAmount: number
  samplingMethod: string
  specificSampleNote: string
  materialityLevel: number
}

export interface H4DisposalSummary {
  checkedCount: number
  checkedAmount: number
  coverageRate: number
  anomalyCount: number
  incompleteCheckCount: number
  missingH2Count: number
  issueCount: number
}

export interface LinkedDisposalTotal {
  amount: number
  usage: number
  returnAmt: number
  scrap: number
  other: number
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

function _emptyChecks(): H4DisposalChecks {
  return { check1: false, check2: false, check3: false, check4: false, check5: false }
}

function _normChecks(raw: unknown): H4DisposalChecks {
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

function _normChecksFromRow(raw: any): H4DisposalChecks {
  if (raw?.checks) return _normChecks(raw.checks)
  return _normChecks({
    check1: raw?.check1,
    check2: raw?.check2,
    check3: raw?.check3,
    check4: raw?.check4,
    check5: raw?.check5,
  })
}

/** 旧减少原因 → 规范减少方式 */
export function normalizeDisposalMethod(raw: string): DisposalMethod {
  const m = (raw || '').trim()
  if ((DISPOSAL_METHOD_OPTS as readonly string[]).includes(m)) return m as DisposalMethod
  const map: Record<string, DisposalMethod> = {
    领用: '领用出库',
    出库: '领用出库',
    转入在建: '领用出库',
    转出: '领用出库',
    退回: '退货',
    毁损: '报废',
    处置: '出售',
    销售: '出售',
  }
  return map[m] ?? (m ? '其他' : '')
}

/** 净值 = 原值 − 减值准备 */
export function calcNetValue(row: Pick<H4DisposalCheckRow, 'originalCost' | 'impairment'>): number {
  return Math.round((_num(row.originalCost) - _num(row.impairment)) * 100) / 100
}

/**
 * 清理净损益 = 清理收入 − 清理费用 − 净值
 * 对齐致同公式 M = L − K − J
 *
 * 领用出库/退货：成本转入在建或冲回，无清理收支时净损益记 0（避免误显 −净值）
 */
export function calcDisposalNetPl(row: Pick<H4DisposalCheckRow, 'disposalIncome' | 'disposalCost' | 'netValue' | 'originalCost' | 'impairment' | 'disposalMethod' | 'reason'>): number {
  const method = normalizeDisposalMethod(row.disposalMethod || row.reason || '')
  const income = _num(row.disposalIncome)
  const cost = _num(row.disposalCost)
  if ((method === '领用出库' || method === '退货') && income === 0 && cost === 0) {
    return 0
  }
  const net = row.netValue != null && Number.isFinite(Number(row.netValue))
    ? _num(row.netValue)
    : calcNetValue(row)
  return Math.round((income - cost - net) * 100) / 100
}

/** 检查比例：总体≤0 时返回 0，避免 #DIV/0! */
export function calcCoverageRate(checkedAmount: number, population: number): number {
  if (population <= 0) return 0
  return Math.min(100, Math.round((checkedAmount / population) * 10000) / 100)
}

export function createEmptySamplingParams(): H4DisposalSamplingParams {
  return {
    populationAmount: 0,
    samplingMethod: '货币单元抽样',
    specificSampleNote: '',
    materialityLevel: 0,
  }
}

export function normalizeSamplingParams(raw: unknown): H4DisposalSamplingParams {
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

export function getEvidenceHint(method: string): string {
  switch (normalizeDisposalMethod(method)) {
    case '领用出库':
      return '领料单/出库单/审批 + 对应H2编号'
    case '退货':
      return '退货单/红字发票/供应商确认'
    case '报废':
      return '报废审批/技术鉴定/处置记录'
    case '盘亏':
      return '盘点差异报告/审批/责任认定'
    case '出售':
      return '出售合同/发票/收款凭证/审批'
    default:
      return '充分、适当的原始凭证与审批'
  }
}

/** 领用出库且未填 H2 编号 */
export function needsH2Ref(row: Pick<H4DisposalCheckRow, 'disposalMethod' | 'reason' | 'h2Ref'>): boolean {
  const method = normalizeDisposalMethod(row.disposalMethod || row.reason || '')
  return method === '领用出库' && !String(row.h2Ref ?? '').trim()
}

/** 核对内容 1–4 是否齐全（第5项视减少方式可选） */
export function isCheckIncomplete(row: Pick<H4DisposalCheckRow, 'checks'>): boolean {
  const c = row.checks
  return !c.check1 || !c.check2 || !c.check3 || !c.check4
}

export function normalizeDisposalRow(raw: any, idx = 0): H4DisposalCheckRow {
  const method = normalizeDisposalMethod(String(raw.disposalMethod ?? raw.reason ?? ''))
  const originalCost = _num(raw.originalCost ?? raw.amount)
  const impairment = _num(raw.impairment)
  const netValue = calcNetValue({ originalCost, impairment })
  const disposalCost = _num(raw.disposalCost)
  const disposalIncome = _num(raw.disposalIncome)
  const supportingDocs = String(
    raw.supportingDocs
    ?? [raw.pickingNo, raw.department, raw.projectName].filter(Boolean).join(' / ')
    ?? '',
  )

  const row: H4DisposalCheckRow = {
    rowId: raw.rowId ?? `h45-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 6)}`,
    seq: raw.seq ?? idx + 1,
    category: String(raw.category ?? raw.spec ?? ''),
    name: String(raw.name ?? ''),
    spec: String(raw.spec ?? ''),
    voucherNo: String(raw.voucherNo ?? ''),
    disposalMethod: method,
    reason: method,
    oppositeAccount: String(raw.oppositeAccount ?? ''),
    quantity: _num(raw.quantity),
    originalCost,
    amount: originalCost,
    impairment,
    netValue,
    disposalCost,
    disposalIncome,
    disposalNetPl: 0,
    disposalDate: String(raw.disposalDate ?? ''),
    supportingDocs,
    pickingNo: String(raw.pickingNo ?? ''),
    department: String(raw.department ?? ''),
    projectName: String(raw.projectName ?? ''),
    approver: String(raw.approver ?? ''),
    h2Ref: String(raw.h2Ref ?? raw.h2Reference ?? ''),
    checks: _normChecksFromRow(raw),
    indexRef: String(raw.indexRef ?? raw.refIndex ?? ''),
    isAbnormal: String(raw.isAbnormal ?? ''),
    conclusion: String(raw.conclusion ?? ''),
    remark: String(raw.remark ?? ''),
    isRelatedParty: String(raw.isRelatedParty ?? ''),
    relatedPartyName: String(raw.relatedPartyName ?? ''),
    relationship: String(raw.relationship ?? ''),
    voucherResult: String(raw.voucherResult ?? ''),
  }
  row.disposalNetPl = calcDisposalNetPl(row)
  return row
}

export function recalcDisposalRow(row: H4DisposalCheckRow): void {
  row.netValue = calcNetValue(row)
  row.disposalNetPl = calcDisposalNetPl(row)
  row.amount = row.originalCost
  row.reason = row.disposalMethod
}

export function calcDisposalSummary(
  rows: H4DisposalCheckRow[],
  population: number,
): H4DisposalSummary {
  const checkedAmount = calcSubtotal(rows.map(r => r.originalCost))
  const missingH2Count = rows.filter(needsH2Ref).length
  const anomalyCount = rows.filter(r => r.isAbnormal === '是' || r.isAbnormal === 'Y').length
  const incompleteCheckCount = rows.filter(isCheckIncomplete).length
  return {
    checkedCount: rows.length,
    checkedAmount,
    coverageRate: calcCoverageRate(checkedAmount, population),
    anomalyCount,
    incompleteCheckCount,
    missingH2Count,
    issueCount: anomalyCount + missingH2Count + incompleteCheckCount,
  }
}

/** 从 H4-2 明细行汇总本期减少（贷方） */
export function sumDetailDecrease(detailRows: any[]): LinkedDisposalTotal {
  let usage = 0
  let returnAmt = 0
  let scrap = 0
  let other = 0
  for (const r of detailRows) {
    usage += _num(r.usageAmount)
    returnAmt += _num(r.returnAmount)
    scrap += _num(r.scrapAmount)
    other += _num(r.otherDecrease)
  }
  const amount = Math.round((usage + returnAmt + scrap + other) * 100) / 100
  return {
    amount,
    usage,
    returnAmt,
    scrap,
    other,
    source: amount > 0 ? 'H4-2' : '',
  }
}

export function buildNoteDraft(summary: H4DisposalSummary, population: number): string {
  const lines = [
    `本期减少检查样本 ${summary.checkedCount} 笔，检查原值合计 ${summary.checkedAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，总体（本期贷方） ${population.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，检查比例 ${summary.coverageRate.toFixed(2)}%。`,
  ]
  if (population > 0 && summary.coverageRate < 20) {
    lines.push('检查比例偏低：已/拟扩大样本量，或说明判断抽样理由：________。')
  }
  if (summary.missingH2Count > 0) {
    lines.push(`其中 ${summary.missingH2Count} 笔「领用出库」尚未填写对应 H2 编号，须补齐并与在建工程核对。`)
  }
  if (summary.anomalyCount > 0) {
    lines.push(`标记异常 ${summary.anomalyCount} 笔，详见备注及拟调整事项（→ H4-3）。`)
  }
  if (summary.incompleteCheckCount > 0) {
    lines.push(`核对内容 1–4 未全部勾选 ${summary.incompleteCheckCount} 笔，请补充测试记录。`)
  }
  lines.push('领用出库关注与 H2 在建工程物资消耗勾稽；报废/出售关注减值结转与清理净损益。')
  return lines.join('\n')
}

export function buildConclusionDraft(summary: H4DisposalSummary): string {
  if (summary.checkedCount === 0) {
    return '本期尚未抽取减少样本。完成样本选取与测试后，再就是否实现审计目标发表结论。'
  }
  if (summary.issueCount === 0) {
    return `基于上述检查（样本 ${summary.checkedCount} 笔，检查比例 ${summary.coverageRate.toFixed(2)}%），本期抽查的工程物资减少在发生、计价及截止方面未见重大异常，可为相关认定提供充分、适当的审计证据。`
  }
  return `基于上述检查（样本 ${summary.checkedCount} 笔，检查比例 ${summary.coverageRate.toFixed(2)}%），发现关注事项 ${summary.issueCount} 项（含异常/H2缺口/核对未完），详见审计说明；除已识别事项外，其余抽查项目未见重大异常。`
}
