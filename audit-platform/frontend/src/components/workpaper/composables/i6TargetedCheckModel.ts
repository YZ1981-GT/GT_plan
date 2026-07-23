/**
 * i6TargetedCheckModel — I6-4 研发费用针对性检查表纯函数
 *
 * 对齐致同 Excel「其他针对性检查表 I6-4」：
 *   一、测试目标 → 二、样本选取（测试原因/总体）→ 三、测试（凭证核对 1~5）
 *   → 合计/本期发生额/检查比例 → 四、说明 → 五、结论
 *
 * Excel 模板缺口（平台已补强）：
 *   - 第 5 项核对内容为空「…」→ 补全为 I6-2/I2 项目归集与费用化划分一致性
 *   - 检查比例 #DIV/0! → 总体为 0 时返回 null / 显示 N/A
 *   - 加计扣除测算不属于本表 → 见 N5-6-1 / I2 政策检查
 *
 * 原段落型「费用归集/人员分摊/I2划分」保留为可选专项风险关注。
 */

import {
  type I6AdjRow,
  mergeI63LinesSkippingExisting,
  normalizeI63Row,
  parseI63Rows,
  I63_ROWS_KEY,
} from './i6AdjDraftHelpers'

export { mergeI63LinesSkippingExisting, parseI63Rows, I63_ROWS_KEY } from './i6AdjDraftHelpers'
export type { I6AdjRow } from './i6AdjDraftHelpers'

export const I6_4_DEFAULT_COVERAGE_THRESHOLD = 20

/** Excel「测试内容说明」1~5；第 5 项补全研发费用特有核对 */
export const I6_4_TEST_CONTENT = [
  '原始凭证是否齐全',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确（费用化/资本化判断、归集科目恰当）',
  '是否记录于恰当的会计期间',
  '研发项目归集与 I6-2 明细一致，费用化与 I2 资本化划分恰当',
] as const

export const I6_4_TEST_REASONS = [
  '大额',
  '关联方',
  '委外研发',
  '资本化相关',
  '异常',
  '其他',
] as const

export const I6_4_SAMPLE_METHODS = [
  '随机抽样',
  '系统抽样',
  '货币单元抽样',
  '随意抽样',
  '全部检查',
] as const

export const I6_4_CHECK_OPTIONS = ['√', '×', 'N/A', ''] as const

export const I6_4_ABNORMAL_OPTIONS = [
  '否',
  '是',
  '归集差异',
  '资本化不当',
  '跨期',
  '项目不一致',
  '其他',
] as const

/** 对齐 Excel 一、测试目标（与 I2 人员认定表同源表述） */
export const I6_4_OBJECTIVES = [
  '确认利润表中记录的研发费用已发生，与被审计单位有关，且已记录于恰当的账户（发生、权利和义务、分类）。',
  '确认与研发费用有关的金额及其他数据已恰当记录，相关披露已得到恰当计量和描述（准确性、计价和分摊、列报）。',
] as const

export type I6TargetedCheckMark = (typeof I6_4_CHECK_OPTIONS)[number]

export interface I6TargetedCheckRow {
  rowId: string
  /** 研发项目明细 */
  projectName: string
  voucherDate: string
  voucherNo: string
  businessDesc: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  supportingDocs: string
  check1: I6TargetedCheckMark | string
  check2: I6TargetedCheckMark | string
  check3: I6TargetedCheckMark | string
  check4: I6TargetedCheckMark | string
  check5: I6TargetedCheckMark | string
  indexRef: string
  isAbnormal: string
  remark: string
  isSpecific: boolean
  selectionReason: string
}

export interface I6TargetedSampleMeta {
  populationCount: number
  populationAmount: number
  populationCreditAmount: number
  populationDesc: string
  populationManual: boolean
  testReasons: string[]
  specificSample: string
  specificAmount: number
  samplingPopulationDesc: string
  sampleSize: number
  sampleMethod: string
  sampleProcess: string
  coverageThreshold: number
}

/** 原段落型风险关注（兼容旧 I6-4 四维度检查） */
export interface I6TargetedRiskFocus {
  completeness: string
  allocation: string
  i2Consistency: string
  completenessConclusion: string
  allocationConclusion: string
  i2ConsistencyConclusion: string
  /** 旧版误入的加计扣除数据迁移提示 */
  legacyDeductionNote: string
}

export interface I6TargetedSummary {
  sampleCount: number
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodTotal: number
  coverageRate: number | null
  creditCoverageRate: number | null
  anomalyCount: number
  failCheckCount: number
  pendingCount: number
  completedCheckCount: number
  specificCount: number
  specificDebitTotal: number
  samplingDebitTotal: number
  specificCoverageRate: number | null
  samplingCoverageRate: number | null
}

export interface I6PeriodMovement {
  /** 本期借方发生额代理：I6-2 审定合计 */
  debitTotal: number
  creditTotal: number
  originalTotal: number
  source: string
}

export interface I6CoverageFooter {
  checkedDebitTotal: number
  periodDebitTotal: number
  debitCoverageLabel: string
  layeredCoverageLabel: string
}

export interface I62ProjectRef {
  projectName: string
  auditedAmount: number
}

export function emptyI6TargetedRow(partial?: Partial<I6TargetedCheckRow>): I6TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i64-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    projectName: '',
    voucherDate: '',
    voucherNo: '',
    businessDesc: '',
    counterpartAccount: '',
    counterpartDetail: '',
    debitAmount: 0,
    creditAmount: 0,
    supportingDocs: '',
    check1: '',
    check2: '',
    check3: '',
    check4: '',
    check5: '',
    indexRef: '',
    isAbnormal: '',
    remark: '',
    isSpecific: false,
    selectionReason: '',
    ...partial,
  }
}

export function emptyI6TargetedSampleMeta(partial?: Partial<I6TargetedSampleMeta>): I6TargetedSampleMeta {
  return {
    populationCount: 0,
    populationAmount: 0,
    populationCreditAmount: 0,
    populationDesc: '本期研发费用（6602）借方发生额总体（记账凭证总体）',
    populationManual: false,
    testReasons: [],
    specificSample: '大额、关联方、委外研发及资本化相关事项作为特定样本 100% 检查',
    specificAmount: 0,
    samplingPopulationDesc: '剔除特定样本后的剩余总体',
    sampleSize: 0,
    sampleMethod: '系统抽样',
    sampleProcess: '',
    coverageThreshold: I6_4_DEFAULT_COVERAGE_THRESHOLD,
    ...partial,
  }
}

export function emptyI6TargetedRiskFocus(partial?: Partial<I6TargetedRiskFocus>): I6TargetedRiskFocus {
  return {
    completeness: '',
    allocation: '',
    i2Consistency: '',
    completenessConclusion: '',
    allocationConclusion: '',
    i2ConsistencyConclusion: '',
    legacyDeductionNote: '',
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

export function normalizeI6TargetedRow(raw: any): I6TargetedCheckRow {
  return emptyI6TargetedRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName || raw?.rdProject || raw?.name),
    voucherDate: _str(raw?.voucherDate || raw?.date),
    voucherNo: _str(raw?.voucherNo),
    businessDesc: _str(raw?.businessDesc || raw?.description),
    counterpartAccount: _str(raw?.counterpartAccount),
    counterpartDetail: _str(raw?.counterpartDetail),
    debitAmount: _num(raw?.debitAmount ?? raw?.amount),
    creditAmount: _num(raw?.creditAmount),
    supportingDocs: _str(raw?.supportingDocs || raw?.supportDocs),
    check1: _str(raw?.check1),
    check2: _str(raw?.check2),
    check3: _str(raw?.check3),
    check4: _str(raw?.check4),
    check5: _str(raw?.check5),
    indexRef: _str(raw?.indexRef),
    isAbnormal: _str(raw?.isAbnormal),
    remark: _str(raw?.remark),
    isSpecific: !!(raw?.isSpecific || raw?.isHighValue),
    selectionReason: _str(raw?.selectionReason),
  })
}

export function normalizeI6TargetedSampleMeta(raw: any): I6TargetedSampleMeta {
  if (!raw || typeof raw !== 'object') return emptyI6TargetedSampleMeta()
  const reasons = Array.isArray(raw.testReasons)
    ? raw.testReasons.map(_str).filter(Boolean)
    : []
  return emptyI6TargetedSampleMeta({
    populationCount: _num(raw.populationCount),
    populationAmount: _num(raw.populationAmount),
    populationCreditAmount: _num(raw.populationCreditAmount),
    populationDesc: _str(raw.populationDesc) || emptyI6TargetedSampleMeta().populationDesc,
    populationManual: !!raw.populationManual,
    testReasons: reasons,
    specificSample: _str(raw.specificSample) || emptyI6TargetedSampleMeta().specificSample,
    specificAmount: _num(raw.specificAmount),
    samplingPopulationDesc: _str(raw.samplingPopulationDesc) || emptyI6TargetedSampleMeta().samplingPopulationDesc,
    sampleSize: _num(raw.sampleSize),
    sampleMethod: _str(raw.sampleMethod) || '系统抽样',
    sampleProcess: _str(raw.sampleProcess),
    coverageThreshold: Math.min(100, Math.max(1, _num(raw.coverageThreshold) || I6_4_DEFAULT_COVERAGE_THRESHOLD)),
  })
}

export function normalizeI6TargetedRiskFocus(raw: any): I6TargetedRiskFocus {
  if (!raw || typeof raw !== 'object') return emptyI6TargetedRiskFocus()
  return emptyI6TargetedRiskFocus({
    completeness: _str(raw.completeness),
    allocation: _str(raw.allocation),
    i2Consistency: _str(raw.i2Consistency || raw.i2consistency),
    completenessConclusion: _str(raw.completenessConclusion),
    allocationConclusion: _str(raw.allocationConclusion),
    i2ConsistencyConclusion: _str(raw.i2ConsistencyConclusion || raw.i2consistencyConclusion),
    legacyDeductionNote: _str(raw.legacyDeductionNote),
  })
}

export function isAbnormalFlag(v: string): boolean {
  const s = (v || '').trim()
  return s !== '' && s !== '否' && s !== 'N' && s !== '无'
}

export function hasFailedCheck(row: I6TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].some((c) => c === '×')
}

export function isRowChecksComplete(row: I6TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].every((c) => !!c && c !== '')
}

export function summarizeI6Targeted(
  rows: I6TargetedCheckRow[],
  periodDebitTotal: number,
  periodCreditTotal = 0,
): I6TargetedSummary {
  const sampleCount = rows.length
  const checkedDebitTotal = Math.round(rows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const checkedCreditTotal = Math.round(rows.reduce((s, r) => s + _num(r.creditAmount), 0) * 100) / 100
  const anomalyCount = rows.filter((r) => isAbnormalFlag(r.isAbnormal) || hasFailedCheck(r)).length
  const failCheckCount = rows.filter(hasFailedCheck).length
  const pendingCount = rows.filter((r) => !isRowChecksComplete(r)).length
  const completedCheckCount = rows.filter(isRowChecksComplete).length

  const specificRows = rows.filter((r) => r.isSpecific || !!r.selectionReason)
  const samplingRows = rows.filter((r) => !(r.isSpecific || !!r.selectionReason))
  const specificCount = specificRows.length
  const specificDebitTotal = Math.round(specificRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
  const samplingDebitTotal = Math.round(samplingRows.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100

  let coverageRate: number | null = null
  let creditCoverageRate: number | null = null
  let specificCoverageRate: number | null = null
  let samplingCoverageRate: number | null = null
  if (periodDebitTotal > 0) {
    coverageRate = Math.round((checkedDebitTotal / periodDebitTotal) * 10000) / 100
    specificCoverageRate = Math.round((specificDebitTotal / periodDebitTotal) * 10000) / 100
    samplingCoverageRate = Math.round((samplingDebitTotal / periodDebitTotal) * 10000) / 100
  }
  if (periodCreditTotal > 0) {
    creditCoverageRate = Math.round((checkedCreditTotal / periodCreditTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedDebitTotal,
    checkedCreditTotal,
    periodTotal: periodDebitTotal,
    coverageRate,
    creditCoverageRate,
    anomalyCount,
    failCheckCount,
    pendingCount,
    completedCheckCount,
    specificCount,
    specificDebitTotal,
    samplingDebitTotal,
    specificCoverageRate,
    samplingCoverageRate,
  }
}

export function formatCoverageLabel(rate: number | null): string {
  if (rate == null) return 'N/A'
  return `${rate.toFixed(2)}%`
}

export function formatLayeredCoverageLabel(summary: I6TargetedSummary): string {
  if (summary.coverageRate == null) return 'N/A'
  const sp = summary.specificCoverageRate != null ? summary.specificCoverageRate.toFixed(2) : '0.00'
  const sa = summary.samplingCoverageRate != null ? summary.samplingCoverageRate.toFixed(2) : '0.00'
  return `借方 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

export function buildI6CoverageFooter(
  summary: I6TargetedSummary,
  periodCreditTotal = 0,
): I6CoverageFooter {
  return {
    checkedDebitTotal: summary.checkedDebitTotal,
    periodDebitTotal: summary.periodTotal,
    debitCoverageLabel: formatCoverageLabel(summary.coverageRate),
    layeredCoverageLabel: formatLayeredCoverageLabel(summary),
  }
}

function _parseI62Rows(raw: unknown): any[] {
  if (Array.isArray(raw)) return raw
  if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch { return [] }
  }
  if (raw && typeof raw === 'object') {
    const obj = raw as any
    const remark = obj.remark ?? obj.conclusion
    if (typeof remark === 'string' && remark) {
      try {
        const p = JSON.parse(remark)
        return Array.isArray(p) ? p : []
      } catch { return [] }
    }
    if (Array.isArray(remark)) return remark
  }
  return []
}

/**
 * 从 I6-2 明细推算本期发生额（对齐 Excel G32='明细表I6-2'!Q19 审定合计）。
 */
export function extractI6PeriodMovement(raw: unknown): I6PeriodMovement {
  const rows = _parseI62Rows(raw)
  let auditedTotal = 0
  for (const r of rows) {
    const cat = _str(r?.category).trim()
    if (!cat || cat === '合计') continue
    const months = Array.isArray(r?.months) ? r.months : []
    const unadj = months.reduce((s: number, m: unknown) => s + _num(m), 0)
    const audited = unadj + _num(r?.aje) + _num(r?.rje)
    auditedTotal += audited
  }
  auditedTotal = Math.round(auditedTotal * 100) / 100
  return {
    debitTotal: auditedTotal,
    creditTotal: 0,
    originalTotal: auditedTotal,
    source: auditedTotal > 0 ? 'I6-2审定合计' : '',
  }
}

export function extractI62ProjectCatalog(raw: unknown): I62ProjectRef[] {
  const rows = _parseI62Rows(raw)
  const out: I62ProjectRef[] = []
  const seen = new Set<string>()
  for (const r of rows) {
    const name = _str(r?.category).trim()
    if (!name || name === '合计' || seen.has(name)) continue
    seen.add(name)
    const months = Array.isArray(r?.months) ? r.months : []
    const unadj = months.reduce((s: number, m: unknown) => s + _num(m), 0)
    const audited = unadj + _num(r?.aje) + _num(r?.rje)
    out.push({ projectName: name, auditedAmount: Math.round(audited * 100) / 100 })
  }
  return out
}

function _normText(s: string): string {
  return (s || '').replace(/\s+/g, '').toLowerCase()
}

export function matchI62ProjectName(
  hints: { projectName?: string; businessDesc?: string; accountName?: string },
  catalog: I62ProjectRef[],
): { projectName: string; method: 'exact' | 'contains' } | null {
  if (!catalog.length) return null
  const hintName = _str(hints.projectName).trim()
  if (hintName) {
    const exact = catalog.find((c) => c.projectName === hintName)
    if (exact) return { projectName: exact.projectName, method: 'exact' }
  }
  const blob = _normText([hints.businessDesc, hints.accountName, hints.projectName].join(' '))
  if (!blob) return null
  for (const c of catalog) {
    const n = _normText(c.projectName)
    if (n && blob.includes(n)) return { projectName: c.projectName, method: 'contains' }
  }
  return null
}

export function enrichRowsWithI62Projects(
  rows: I6TargetedCheckRow[],
  catalog: I62ProjectRef[],
  overwrite = false,
): { rows: I6TargetedCheckRow[]; linked: number } {
  let linked = 0
  const next = rows.map((row) => {
    if (!overwrite && row.projectName) return row
    const matched = matchI62ProjectName(
      { projectName: row.projectName, businessDesc: row.businessDesc, accountName: row.counterpartDetail },
      catalog,
    )
    if (!matched) return row
    linked++
    return {
      ...row,
      projectName: matched.projectName,
      remark: row.remark
        ? row.remark
        : `[挂接I6-2:${matched.method}]`,
    }
  })
  return { rows: next, linked }
}

/** I6-4 样本研发项目与 I6-2 明细交叉校验报告 */
export interface I62ProjectConsistencyReport {
  catalogCount: number
  sampleCount: number
  rowsWithProject: number
  unmatchedCount: number
  missingProjectCount: number
  check5FailCount: number
  orphanNames: string[]
}

export function analyzeI62ProjectConsistency(
  rows: I6TargetedCheckRow[],
  catalog: I62ProjectRef[],
): I62ProjectConsistencyReport {
  const catalogNames = new Set(catalog.map((c) => c.projectName))
  const orphans = new Set<string>()
  let rowsWithProject = 0
  let unmatchedCount = 0
  let missingProjectCount = 0
  let check5FailCount = 0

  for (const row of rows) {
    if (row.check5 === '×') check5FailCount++
    const name = _str(row.projectName).trim()
    if (!name) {
      if (catalog.length) missingProjectCount++
      continue
    }
    rowsWithProject++
    if (catalog.length && !catalogNames.has(name)) {
      unmatchedCount++
      orphans.add(name)
    }
  }

  return {
    catalogCount: catalog.length,
    sampleCount: rows.length,
    rowsWithProject,
    unmatchedCount,
    missingProjectCount,
    check5FailCount,
    orphanNames: [...orphans],
  }
}

export function syncSpecificAmountFromRows(rows: I6TargetedCheckRow[]): number {
  return Math.round(
    rows
      .filter((r) => r.isSpecific || !!r.selectionReason)
      .reduce((s, r) => s + _num(r.debitAmount), 0) * 100,
  ) / 100
}

export function suggestAbnormalFromFailedChecks(row: I6TargetedCheckRow): string {
  if (row.check3 === '×') return '资本化不当'
  if (row.check4 === '×') return '跨期'
  if (row.check5 === '×') return '项目不一致'
  if (row.check1 === '×' || row.check2 === '×') return '归集差异'
  return '是'
}

export function buildI6TargetedConclusionDraft(opts: {
  sampleCount: number
  coverageLabel: string
  creditCoverageLabel?: string
  anomalyCount: number
  failCheckCount: number
  testReasons?: string[]
  riskFocus?: I6TargetedRiskFocus
}): string {
  const reasonText = opts.testReasons?.length
    ? `测试原因：${opts.testReasons.join('、')}。`
    : ''
  const parts = [
    `经抽查研发费用相关记账凭证 ${opts.sampleCount} 笔，借方检查覆盖率 ${opts.coverageLabel}。`,
  ]
  if (opts.creditCoverageLabel && opts.creditCoverageLabel !== 'N/A') {
    parts.push(`贷方（冲回/重分类等）检查覆盖率 ${opts.creditCoverageLabel}。`)
  }
  if (reasonText) parts.push(reasonText)
  if (opts.failCheckCount > 0) {
    parts.push(`其中 ${opts.failCheckCount} 笔核对内容存在「×」，已在表内标注并需跟进。`)
  } else if (opts.anomalyCount > 0) {
    parts.push(`发现异常 ${opts.anomalyCount} 笔，详见「是否异常」及备注。`)
  } else {
    parts.push('所抽样本原始凭证齐全、账证相符、会计处理及期间归属未见重大异常。')
  }
  const rf = opts.riskFocus
  if (rf) {
    const riskBits = [
      rf.completenessConclusion && `费用归集：${rf.completenessConclusion}`,
      rf.allocationConclusion && `人员分摊：${rf.allocationConclusion}`,
      rf.i2ConsistencyConclusion && `I2划分：${rf.i2ConsistencyConclusion}`,
    ].filter(Boolean)
    if (riskBits.length) parts.push(`专项风险关注—${riskBits.join('；')}。`)
  }
  parts.push('研发费用在重大方面列报适当（请结合 I6-2 明细、I2 资本化划分及 I6-1 审定结论综合判断）。')
  return parts.join('')
}

export function mapSampledToI6TargetedRow(
  s: {
    voucherNo?: string
    voucherDate?: string
    summary?: string | null
    debitAmount?: string | number | null
    creditAmount?: string | number | null
    counterpartAccount?: string | null
    accountName?: string | null
    isHighValue?: boolean
    selectionReason?: string
    abnormal?: boolean
    remark?: string
  },
  catalog?: I62ProjectRef[],
): I6TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  const rawName = _str(s.accountName)
  const matched = catalog?.length
    ? matchI62ProjectName(
      { projectName: rawName, businessDesc: _str(s.summary), accountName: rawName },
      catalog,
    )
    : null
  const projectName = matched?.projectName
    || (rawName && !/研发费用|6602/.test(rawName) ? rawName : '')
  return emptyI6TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    counterpartDetail: rawName,
    projectName,
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? '高值必选' : ''),
    isAbnormal: s.abnormal ? '是' : '',
    remark: [_str(s.remark), matched ? `[挂接I6-2:${matched.method}]` : ''].filter(Boolean).join(' '),
  })
}

export interface I6TargetedAdjDraft {
  voucherNo: string
  projectName: string
  debitAmount: number
  creditAmount: number
  failedChecks: string[]
  suggestedEntry: string
  suggestedNote: string
  /** 可推 I6-3 的草稿类型 */
  draftKind: 'capitalize' | 'cutoff' | 'doc_only'
  amount: number
}

export function buildI6TargetedAdjDrafts(rows: I6TargetedCheckRow[]): I6TargetedAdjDraft[] {
  const labels = I6_4_TEST_CONTENT
  const out: I6TargetedAdjDraft[] = []
  for (const row of rows) {
    if (!hasFailedCheck(row)) continue
    const failedChecks: string[] = []
    const marks = [row.check1, row.check2, row.check3, row.check4, row.check5]
    marks.forEach((m, i) => {
      if (m === '×') failedChecks.push(`${i + 1}.${labels[i]}`)
    })
    const amt = row.debitAmount || row.creditAmount
    const classification = failedChecks.some((c) => c.startsWith('3.') || c.startsWith('5.'))
    const cutoff = failedChecks.some((c) => c.startsWith('4.'))
    let draftKind: I6TargetedAdjDraft['draftKind'] = 'doc_only'
    let suggestedEntry = `建议复核凭证 ${row.voucherNo || '—'}（${amt.toFixed(2)}）`
    if (classification) {
      draftKind = 'capitalize'
      suggestedEntry += '：核对费用化/资本化划分及项目归集，必要时转入 I2 开发支出（可推 I6-3）'
    } else if (cutoff) {
      draftKind = 'cutoff'
      suggestedEntry += '：可能跨期确认，草拟跨期调整分录（可推 I6-3）'
    } else {
      suggestedEntry += '：补齐立项/合同/工时记录等原始资料或更正账证不符后重测'
    }
    out.push({
      voucherNo: row.voucherNo,
      projectName: row.projectName,
      debitAmount: row.debitAmount,
      creditAmount: row.creditAmount,
      failedChecks,
      suggestedEntry,
      suggestedNote: `I6-4 核对×：${failedChecks.join('；')}`,
      draftKind,
      amount: amt,
    })
  }
  return out
}

function _i63DraftLine(partial: Partial<I6AdjRow> & Pick<I6AdjRow, 'description' | 'accountCode' | 'accountName' | 'debitAmount' | 'creditAmount'>): I6AdjRow {
  return normalizeI63Row({
    rowId: '',
    category: '账项调整',
    entryType: 'AJE',
    reportItem: partial.reportItem ?? (partial.accountCode?.startsWith('1717') ? '开发支出' : '研发费用'),
    noteItem: partial.noteItem ?? '',
    indexRef: partial.indexRef ?? 'I6-4',
    remark: partial.remark ?? '',
    ...partial,
  })
}

/** I6-4 调整草稿 → I6-3 借贷两行（与 useI6Adjustment 行结构对齐） */
export function buildI63LinesFromTargetedDrafts(drafts: I6TargetedAdjDraft[]): I6AdjRow[] {
  const lines: I6AdjRow[] = []
  for (const d of drafts) {
    if (d.draftKind === 'doc_only' || !(d.amount > 0.005)) continue
    const projectName = d.projectName || d.voucherNo || '未命名项目'
    const idx = `I6-4/${d.voucherNo || '—'}`
    const noteItem = projectName
    if (d.draftKind === 'capitalize') {
      const desc = `研发费用资本化重分类-${projectName}`
      lines.push(
        _i63DraftLine({
          description: desc,
          reportItem: '开发支出',
          accountCode: '1717',
          accountName: '开发支出',
          noteItem,
          debitAmount: d.amount,
          creditAmount: 0,
          indexRef: idx,
          remark: d.suggestedNote,
        }),
        _i63DraftLine({
          description: desc,
          reportItem: '研发费用',
          accountCode: '6602',
          accountName: '研发费用',
          noteItem,
          debitAmount: 0,
          creditAmount: d.amount,
          indexRef: idx,
          remark: '冲减费用化金额，转入 I2（请核对资本化五条件）',
        }),
      )
    } else if (d.draftKind === 'cutoff') {
      const desc = `研发费用跨期调整-${projectName}`
      lines.push(
        _i63DraftLine({
          description: desc,
          reportItem: '研发费用',
          accountCode: '6602',
          accountName: '研发费用',
          noteItem,
          debitAmount: 0,
          creditAmount: d.amount,
          indexRef: idx,
          remark: `${d.suggestedNote}（跨期冲回，请核对应付/预付科目）`,
        }),
        _i63DraftLine({
          description: desc,
          reportItem: '其他应付款',
          accountCode: '2241',
          accountName: '其他应付款',
          noteItem,
          debitAmount: d.amount,
          creditAmount: 0,
          indexRef: idx,
          remark: '跨期调整对方科目（请按实际业务替换）',
        }),
      )
    }
  }
  return lines
}

