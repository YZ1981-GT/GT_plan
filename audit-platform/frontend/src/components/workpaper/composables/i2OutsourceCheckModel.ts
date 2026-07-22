import { sumI27Outsource } from './i2EnhancementHelpers'

/**
 * I2-11 委外研发检查表 — 纯模型
 * 对齐致同 Excel：测试原因 → 合同/受托方/凭证/验收四栏核对 → 检查比例（防 #DIV/0!）
 */

export const I2_OUTSOURCE_DEFAULT_COVERAGE_THRESHOLD = 20

export const I2_OUTSOURCE_TEST_CONTENT = [
  '检查原始凭证是否齐全（委外合同、结算单、验收单）',
  '检查记账凭证与原始凭证是否相符（金额、项目、受托方）',
  '检查会计处理是否正确（资本化/费用化归集、对方科目）',
  '检查是否记录于正确的会计期间（截止）',
  '关注受托方资质、知识产权归属及交付物实质性',
] as const

export const I2_OUTSOURCE_TEST_REASONS = [
  '大额',
  '关联方',
  '大额交易频繁',
  '异常',
  '其他',
] as const

export const I2_OUTSOURCE_SAMPLE_METHODS = [
  '随机抽样',
  '系统抽样',
  '货币单元抽样',
  '随意抽样',
  '全部检查',
] as const

export type I2OutsourceAbnormal =
  | ''
  | '否'
  | '是'
  | '金额不符'
  | '缺验收'
  | '资质未核'
  | '关联方未披露'
  | 'IP归属不清'
  | '其他'

export interface I2OutsourceCheckRow {
  rowId: string
  /** 研发项目 */
  projectName: string
  /** 委外研发原因 */
  outsourceReason: string
  /** 合同日期 */
  contractDate: string
  /** 合同号 */
  contractNo: string
  /** 受托方 */
  entrustedParty: string
  /** 研发内容 */
  rdContent: string
  /** 研发成果知识产权归属 */
  ipOwnership: string
  /** 受托方资质 */
  qualification: string
  /** 注册资本 */
  registeredCapital: string
  /** 参保人数 */
  insuredCount: string
  /** 记账凭证日期 */
  voucherDate: string
  /** 凭证编号 */
  voucherNo: string
  /** 业务内容 */
  businessDesc: string
  /** 记账金额 */
  amount: number
  /** 验收日期 */
  acceptanceDate: string
  /** 验收金额 */
  acceptanceAmount: number
  /** 验收结论/交付物 */
  acceptanceResult: string
  /** 是否异常 */
  isAbnormal: I2OutsourceAbnormal | string
  /** 索引号 */
  indexRef: string
  /** 审核结论 */
  conclusion: string
  /** 备注 */
  remark: string
}

export interface I2OutsourceSampleMeta {
  /** 测试原因勾选 */
  testReasons: string[]
  /** 测试原因-其他说明 */
  testReasonOther: string
  populationDesc: string
  populationAmount: number
  populationManual: boolean
  specificSample: string
  sampleMethod: string
  sampleProcess: string
  coverageThreshold: number
}

export interface I2OutsourceSummary {
  sampleCount: number
  checkedTotal: number
  periodTotal: number
  /** null 表示总体为 0，展示 N/A，避免 #DIV/0! */
  coverageRate: number | null
  anomalyCount: number
  amountMismatchCount: number
  missingAcceptanceCount: number
  pendingCount: number
}

export function emptyI2OutsourceRow(partial?: Partial<I2OutsourceCheckRow>): I2OutsourceCheckRow {
  return {
    rowId: partial?.rowId || `i211-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: '',
    outsourceReason: '',
    contractDate: '',
    contractNo: '',
    entrustedParty: '',
    rdContent: '',
    ipOwnership: '',
    qualification: '',
    registeredCapital: '',
    insuredCount: '',
    voucherDate: '',
    voucherNo: '',
    businessDesc: '',
    amount: 0,
    acceptanceDate: '',
    acceptanceAmount: 0,
    acceptanceResult: '',
    isAbnormal: '',
    indexRef: '',
    conclusion: '',
    remark: '',
    ...partial,
  }
}

export function emptyI2OutsourceSampleMeta(partial?: Partial<I2OutsourceSampleMeta>): I2OutsourceSampleMeta {
  return {
    testReasons: [],
    testReasonOther: '',
    populationDesc: '账面记录的委外研发借方发生额（凭证总体）',
    populationAmount: 0,
    populationManual: false,
    specificSample: '选取大额、关联方、频繁大额及异常委外作为特定样本；其余从剩余总体中抽样',
    sampleMethod: '系统抽样',
    sampleProcess: '',
    coverageThreshold: I2_OUTSOURCE_DEFAULT_COVERAGE_THRESHOLD,
    ...partial,
  }
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _str(v: unknown): string {
  return v == null ? '' : String(v)
}

/** 兼容旧版精简字段：supplier/deliverable/projectName/amount/conclusion */
export function normalizeI2OutsourceRow(raw: any): I2OutsourceCheckRow {
  const amount = _num(raw?.amount)
  return emptyI2OutsourceRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName),
    outsourceReason: _str(raw?.outsourceReason),
    contractDate: _str(raw?.contractDate),
    contractNo: _str(raw?.contractNo),
    entrustedParty: _str(raw?.entrustedParty || raw?.supplier),
    rdContent: _str(raw?.rdContent || raw?.deliverable),
    ipOwnership: _str(raw?.ipOwnership),
    qualification: _str(raw?.qualification),
    registeredCapital: _str(raw?.registeredCapital),
    insuredCount: _str(raw?.insuredCount),
    voucherDate: _str(raw?.voucherDate),
    voucherNo: _str(raw?.voucherNo),
    businessDesc: _str(raw?.businessDesc),
    amount,
    acceptanceDate: _str(raw?.acceptanceDate),
    acceptanceAmount: raw?.acceptanceAmount != null ? _num(raw.acceptanceAmount) : 0,
    acceptanceResult: _str(raw?.acceptanceResult || raw?.deliverable),
    isAbnormal: _str(raw?.isAbnormal),
    indexRef: _str(raw?.indexRef),
    conclusion: _str(raw?.conclusion),
    remark: _str(raw?.remark),
  })
}

export function normalizeI2OutsourceSampleMeta(raw: any): I2OutsourceSampleMeta {
  if (!raw || typeof raw !== 'object') return emptyI2OutsourceSampleMeta()
  const reasons = Array.isArray(raw.testReasons)
    ? raw.testReasons.map((r: unknown) => _str(r)).filter(Boolean)
    : []
  return emptyI2OutsourceSampleMeta({
    testReasons: reasons,
    testReasonOther: _str(raw.testReasonOther),
    populationDesc: _str(raw.populationDesc) || emptyI2OutsourceSampleMeta().populationDesc,
    populationAmount: _num(raw.populationAmount),
    populationManual: !!raw.populationManual,
    specificSample: _str(raw.specificSample) || emptyI2OutsourceSampleMeta().specificSample,
    sampleMethod: _str(raw.sampleMethod) || '系统抽样',
    sampleProcess: _str(raw.sampleProcess),
    coverageThreshold: Math.min(100, Math.max(1, _num(raw.coverageThreshold) || I2_OUTSOURCE_DEFAULT_COVERAGE_THRESHOLD)),
  })
}

/** 记账金额 vs 验收金额是否不符（两侧均有值时才判） */
export function hasAmountMismatch(row: I2OutsourceCheckRow): boolean {
  if (!row.amount && !row.acceptanceAmount) return false
  if (row.acceptanceAmount === 0) return false
  return Math.abs(row.amount - row.acceptanceAmount) > 0.005
}

/** 已入账但缺验收日期/结论 */
export function hasMissingAcceptance(row: I2OutsourceCheckRow): boolean {
  if (!(row.amount > 0)) return false
  return !row.acceptanceDate.trim() && !row.acceptanceResult.trim()
}

export function suggestOutsourceAbnormal(row: I2OutsourceCheckRow): I2OutsourceAbnormal | '' {
  if (hasAmountMismatch(row)) return '金额不符'
  if (hasMissingAcceptance(row)) return '缺验收'
  if (row.amount > 0 && !row.qualification.trim()) return '资质未核'
  if (row.amount > 0 && !row.ipOwnership.trim()) return 'IP归属不清'
  return ''
}

export function summarizeI2Outsource(
  rows: I2OutsourceCheckRow[],
  periodTotal: number,
): I2OutsourceSummary {
  const sampleCount = rows.length
  const checkedTotal = Math.round(rows.reduce((s, r) => s + _num(r.amount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => {
    const v = (r.isAbnormal || '').trim()
    return v !== '' && v !== '否'
  }).length
  const amountMismatchCount = rows.filter(hasAmountMismatch).length
  const missingAcceptanceCount = rows.filter(hasMissingAcceptance).length
  const pendingCount = rows.filter((r) => !r.conclusion || r.conclusion === '待查' || r.conclusion === '待验收').length

  let coverageRate: number | null = null
  if (periodTotal > 0) {
    coverageRate = Math.round((checkedTotal / periodTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedTotal,
    periodTotal,
    coverageRate,
    anomalyCount,
    amountMismatchCount,
    missingAcceptanceCount,
    pendingCount,
  }
}

/** 从 I2-7 项目构成明细提取委外相关本期发生额 */
export function extractI27OutsourceTotal(raw: unknown): number {
  return sumI27Outsource(raw)
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 'N/A'
  return `${rate.toFixed(2)}%`
}
