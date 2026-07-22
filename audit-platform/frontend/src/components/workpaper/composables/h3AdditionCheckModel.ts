/**
 * H3-5 投资性房地产增减检查表 — 对齐致同模板（成本/公允双模式）
 *
 * 编制逻辑：目标认定 → 样本选取 → 测试内容说明 → 逐笔检查（账→证）
 *          → 合计/检查比例 → 审计说明/结论
 */
import { calcSubtotal } from './useH3FormulaEngine'

export type H3AdditionMode = 'cost' | 'fair_value'

export type H3ChangeType =
  | '外购'
  | '在建转入'
  | '自用转入'
  | '存货转入'
  | '后续支出'
  | '处置'
  | '转出'
  | '其他'

export type H3TestReason = 'largeAmount' | 'relatedParty' | 'abnormal' | 'conversion' | 'other'

export const H3_CHANGE_TYPE_OPTS: H3ChangeType[] = [
  '外购',
  '在建转入',
  '自用转入',
  '存货转入',
  '后续支出',
  '处置',
  '转出',
  '其他',
]

export const H3_CATEGORY_OPTS = ['房屋建筑物', '土地使用权', '在建工程', '其他'] as const

export const SAMPLING_METHOD_OPTS = [
  '货币单元抽样',
  '随机抽样',
  '系统抽样',
  '判断抽样',
] as const

/** 测试内容说明（核对内容 1–5 列标题） */
export const H3_TEST_CONTENT_ITEMS = [
  '原始凭证是否齐全',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确',
  '是否记录于恰当会计期间',
  '其他（如资本性/收益性支出划分）',
] as const

export interface H3VerificationChecks {
  check1: boolean
  check2: boolean
  check3: boolean
  check4: boolean
  check5: boolean
}

export interface H3AdditionCostRow {
  rowId: string
  seq: number
  category: string
  assetName: string
  date: string
  changeType: string
  voucherNo: string
  creditAccount: string
  originalCost: number
  accDep: number
  impairment: number
  netValue: number
  supportingDocs: string
  checks: H3VerificationChecks
  indexRef: string
  isAbnormal: string
  remark: string
  // 兼容旧字段
  contract: boolean
  invoice: boolean
  appraisal: boolean
  titleCert: boolean
  approvalDoc: boolean
  debitAccount: string
  plImpact: number
  conclusion: string
}

export interface H3AdditionFairRow {
  rowId: string
  seq: number
  category: string
  assetName: string
  date: string
  changeType: string
  voucherNo: string
  creditAccount: string
  fairValue: number
  fairValueChange: number
  endBalance: number
  appraisalBasis: string
  supportingDocs: string
  checks: H3VerificationChecks
  indexRef: string
  isAbnormal: string
  remark: string
  // 兼容旧字段
  contract: boolean
  invoice: boolean
  appraisal: boolean
  titleCert: boolean
  plImpact: number
  conclusion: string
}

export interface H3SamplingParams {
  totalPopulation: number
  samplingMethod: string
  sampleSize: number
}

export interface H3AdditionSummary {
  checkedCount: number
  checkedAmount: number
  increaseTotal: number
  coverageRate: number
  anomalyCount: number
  incompleteCheckCount: number
  traceCount: number
  traceUnrecordedCount: number
}

/** 证→账追查行（完整性认定） */
export interface H3TraceRow {
  rowId: string
  seq: number
  sourceType: string
  sourceRef: string
  sourceDate: string
  sourceParty: string
  sourceAmount: number
  recordedInBooks: string
  bookVoucherNo: string
  bookAssetName: string
  bookAmount: number
  amountDiff: number
  checkResult: string
  remark: string
  indexRef: string
  /** 行级联动 H3-12 产权核对 */
  linkedTitleRowId: string
}

export const H3_TRACE_SOURCE_OPTS = ['发票', '合同', '验收报告', '产权证', '评估报告', '其他'] as const

export interface H3LinkedMovement {
  increaseAmount: number
  decreaseAmount: number
  source: 'H3-1' | 'H3-2' | ''
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _bool(v: unknown): boolean {
  return v === true || v === 'Y' || v === 'true' || v === 1
}

function _emptyChecks(): H3VerificationChecks {
  return { check1: false, check2: false, check3: false, check4: false, check5: false }
}

function _normChecks(raw: unknown): H3VerificationChecks {
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

function _normChecksFromRow(raw: any): H3VerificationChecks {
  if (raw?.checks) return _normChecks(raw.checks)
  return _normChecks({
    check1: raw?.check1,
    check2: raw?.check2,
    check3: raw?.check3,
    check4: raw?.check4,
    check5: raw?.check5,
  })
}

/** 旧增减类型 → 致同模板口径 */
export function normalizeChangeType(raw: string): string {
  const m = (raw || '').trim()
  const map: Record<string, string> = {
    购入: '外购',
    自建转入: '在建转入',
    自用转入: '自用转入',
    处置: '处置',
    转出: '转出',
  }
  return map[m] || m
}

export function normalizeCostRow(raw: any, idx?: number): H3AdditionCostRow {
  const originalCost = _num(raw.originalCost)
  const accDep = _num(raw.accDep)
  const impairment = _num(raw.impairment)
  const netValue = originalCost - accDep - impairment
  return {
    rowId: raw.rowId ?? `ac-${Math.random().toString(36).slice(2, 8)}`,
    seq: raw.seq ?? (idx != null ? idx + 1 : 1),
    category: String(raw.category ?? ''),
    assetName: String(raw.assetName ?? ''),
    date: String(raw.date ?? ''),
    changeType: normalizeChangeType(raw.changeType),
    voucherNo: String(raw.voucherNo ?? ''),
    creditAccount: String(raw.creditAccount ?? ''),
    originalCost,
    accDep,
    impairment,
    netValue,
    supportingDocs: String(raw.supportingDocs ?? ''),
    checks: _normChecksFromRow(raw),
    indexRef: String(raw.indexRef ?? ''),
    isAbnormal: String(raw.isAbnormal ?? (raw.conclusion === '有问题' ? 'Y' : raw.conclusion === '需关注' ? 'Y' : 'N')),
    remark: String(raw.remark ?? ''),
    contract: _bool(raw.contract),
    invoice: _bool(raw.invoice),
    appraisal: _bool(raw.appraisal),
    titleCert: _bool(raw.titleCert),
    approvalDoc: _bool(raw.approvalDoc),
    debitAccount: String(raw.debitAccount ?? ''),
    plImpact: _num(raw.plImpact),
    conclusion: String(raw.conclusion ?? ''),
  }
}

export function normalizeFairRow(raw: any, idx?: number): H3AdditionFairRow {
  const fairValue = _num(raw.fairValue)
  const fairValueChange = _num(raw.fairValueChange)
  const endBalance = _num(raw.endBalance) || fairValue
  return {
    rowId: raw.rowId ?? `af-${Math.random().toString(36).slice(2, 8)}`,
    seq: raw.seq ?? (idx != null ? idx + 1 : 1),
    category: String(raw.category ?? ''),
    assetName: String(raw.assetName ?? ''),
    date: String(raw.date ?? ''),
    changeType: normalizeChangeType(raw.changeType),
    voucherNo: String(raw.voucherNo ?? ''),
    creditAccount: String(raw.creditAccount ?? ''),
    fairValue,
    fairValueChange,
    endBalance,
    appraisalBasis: String(raw.appraisalBasis ?? ''),
    supportingDocs: String(raw.supportingDocs ?? ''),
    checks: _normChecksFromRow(raw),
    indexRef: String(raw.indexRef ?? ''),
    isAbnormal: String(raw.isAbnormal ?? (raw.conclusion === '有问题' ? 'Y' : raw.conclusion === '需关注' ? 'Y' : 'N')),
    remark: String(raw.remark ?? ''),
    contract: _bool(raw.contract),
    invoice: _bool(raw.invoice),
    appraisal: _bool(raw.appraisal),
    titleCert: _bool(raw.titleCert),
    plImpact: _num(raw.plImpact),
    conclusion: String(raw.conclusion ?? ''),
  }
}

export function calcCostNetValue(row: Pick<H3AdditionCostRow, 'originalCost' | 'accDep' | 'impairment'>): number {
  return _num(row.originalCost) - _num(row.accDep) - _num(row.impairment)
}

export function isIncreaseChangeType(changeType: string): boolean {
  const t = normalizeChangeType(changeType)
  return !['处置', '转出'].includes(t)
}

export function calcCoverageRate(checkedAmount: number, population: number): number {
  if (population <= 0) return 0
  return Math.min(100, (checkedAmount / population) * 100)
}

export function calcCostSummary(rows: H3AdditionCostRow[]): H3AdditionSummary {
  const checkedAmount = calcSubtotal(rows.map((r) => r.originalCost))
  const increaseRows = rows.filter((r) => isIncreaseChangeType(r.changeType))
  const increaseTotal = calcSubtotal(increaseRows.map((r) => r.originalCost))
  return {
    checkedCount: rows.length,
    checkedAmount,
    increaseTotal,
    coverageRate: 0,
    anomalyCount: rows.filter((r) => r.isAbnormal === 'Y').length,
    incompleteCheckCount: rows.filter((r) => !r.checks.check1 || !r.checks.check2 || !r.checks.check3 || !r.checks.check4).length,
    traceCount: 0,
    traceUnrecordedCount: 0,
  }
}

export function calcFairSummary(rows: H3AdditionFairRow[]): H3AdditionSummary {
  const checkedAmount = calcSubtotal(rows.map((r) => r.fairValue))
  const increaseRows = rows.filter((r) => isIncreaseChangeType(r.changeType))
  const increaseTotal = calcSubtotal(increaseRows.map((r) => r.fairValue))
  return {
    checkedCount: rows.length,
    checkedAmount,
    increaseTotal,
    coverageRate: 0,
    anomalyCount: rows.filter((r) => r.isAbnormal === 'Y').length,
    incompleteCheckCount: rows.filter((r) => !r.checks.check1 || !r.checks.check2 || !r.checks.check3 || !r.checks.check4).length,
    traceCount: 0,
    traceUnrecordedCount: 0,
  }
}

export function enrichSummaryWithTrace(
  base: H3AdditionSummary,
  traceRows: H3TraceRow[],
  population: number,
): H3AdditionSummary {
  const traceUnrecordedCount = traceRows.filter(
    (r) => r.recordedInBooks === 'N' || r.checkResult === 'ERR',
  ).length
  return {
    ...base,
    coverageRate: calcCoverageRate(base.checkedAmount, population),
    traceCount: traceRows.length,
    traceUnrecordedCount,
  }
}

/** 按增减方式提示应关注的证据（编制提示联动） */
export function getEvidenceHint(changeType: string): string {
  const t = normalizeChangeType(changeType)
  switch (t) {
    case '外购':
      return '合同/发票/验收报告/产权证/审批'
    case '自用转入':
    case '存货转入':
      return '转换依据/审批/转换日成本计量'
    case '在建转入':
      return '竣工决算/验收/转换审批'
    case '后续支出':
      return '支出原始记录/资本化与费用化划分'
    case '处置':
    case '转出':
      return '处置协议/收款凭证/权属转移'
    default:
      return '合同/发票/评估/产权证'
  }
}

export function calcTraceDiff(row: Pick<H3TraceRow, 'sourceAmount' | 'bookAmount'>): number {
  return Math.round((_num(row.sourceAmount) - _num(row.bookAmount)) * 100) / 100
}

export function normalizeTraceRow(raw: any, idx?: number): H3TraceRow {
  const row: H3TraceRow = {
    rowId: raw.rowId ?? `h3tr-${Math.random().toString(36).slice(2, 8)}`,
    seq: raw.seq ?? (idx != null ? idx + 1 : 1),
    sourceType: String(raw.sourceType ?? ''),
    sourceRef: String(raw.sourceRef ?? ''),
    sourceDate: String(raw.sourceDate ?? ''),
    sourceParty: String(raw.sourceParty ?? ''),
    sourceAmount: _num(raw.sourceAmount),
    recordedInBooks: String(raw.recordedInBooks ?? ''),
    bookVoucherNo: String(raw.bookVoucherNo ?? ''),
    bookAssetName: String(raw.bookAssetName ?? ''),
    bookAmount: _num(raw.bookAmount),
    amountDiff: 0,
    checkResult: String(raw.checkResult ?? ''),
    remark: String(raw.remark ?? ''),
    indexRef: String(raw.indexRef ?? ''),
    linkedTitleRowId: String(raw.linkedTitleRowId ?? ''),
  }
  row.amountDiff = calcTraceDiff(row)
  if (row.checkResult === '异常' || row.checkResult === '有异常') row.checkResult = 'ERR'
  if (row.checkResult === '无异常') row.checkResult = 'OK'
  return row
}
