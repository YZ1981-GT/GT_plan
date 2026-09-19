/**
 * i3TargetedCheckModel — I3-5 商誉针对性检查表纯函数
 *
 * 对齐致同 Excel「针对性检查表 I3-5」：
 *   一、测试目标 → 二、样本选取（测试原因/总体）→ 三、测试（凭证核对 1~5）
 *   → 合计/本期发生额/检查比例 → 四、说明 → 五、结论
 *
 * 原段落型「减值迹象 / CGU 分摊 / 划分一致性」保留为可选专项风险关注
 * （主减值程序见 I3-6~I3-8）。
 */

export const I3_5_DEFAULT_COVERAGE_THRESHOLD = 20

/** Excel「测试内容说明」1~5；第 5 项补全商誉特有核对 */
export const I3_5_TEST_CONTENT = [
  '原始凭证是否齐全',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确（初始确认/后续计量）',
  '是否记录于恰当的会计期间',
  '入账价值与 I3-4 一致，且商誉分摊至 CGU 恰当（对照 I3-2/I3-6）',
] as const

export const I3_5_TEST_REASONS = [
  '大额',
  '关联方',
  '大额交易频繁',
  '异常',
  '其他',
] as const

export const I3_5_SAMPLE_METHODS = [
  '随机抽样',
  '系统抽样',
  '货币单元抽样',
  '随意抽样',
  '全部检查',
] as const

export const I3_5_CHECK_OPTIONS = ['√', '×', 'N/A', ''] as const

export const I3_5_OBJECTIVES = [
  '通过针对性测试，验证商誉的存在/发生、计价和分摊。',
  '抽查商誉相关记账凭证与支持性文件，评价会计处理及期间归属是否恰当。',
] as const

export type I3TargetedCheckMark = (typeof I3_5_CHECK_OPTIONS)[number]

export interface I3TargetedCheckRow {
  rowId: string
  /** 商誉项目明细（被投资单位 / CGU） */
  projectName: string
  voucherDate: string
  voucherNo: string
  businessDesc: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  supportingDocs: string
  check1: I3TargetedCheckMark | string
  check2: I3TargetedCheckMark | string
  check3: I3TargetedCheckMark | string
  check4: I3TargetedCheckMark | string
  check5: I3TargetedCheckMark | string
  indexRef: string
  isAbnormal: string
  remark: string
  isSpecific: boolean
  selectionReason: string
}

export interface I3TargetedSampleMeta {
  populationCount: number
  /** 测试总体金额（借方口径，用于检查比例） */
  populationAmount: number
  /** 本期贷方发生额（减值等，展示用） */
  populationCreditAmount: number
  populationDesc: string
  populationManual: boolean
  /** Excel「测试原因」多选 */
  testReasons: string[]
  specificSample: string
  specificAmount: number
  samplingPopulationDesc: string
  sampleSize: number
  sampleMethod: string
  sampleProcess: string
  coverageThreshold: number
}

/** 原段落型风险关注（兼容旧 I3-5-targeted） */
export interface I3TargetedRiskFocus {
  externalIndicators: string
  internalIndicators: string
  cguAllocation: string
  cguConsistency: string
  externalConclusion: string
  internalConclusion: string
  allocationConclusion: string
  consistencyConclusion: string
}

export interface I3TargetedSummary {
  sampleCount: number
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodTotal: number
  coverageRate: number | null
  /** 贷方检查比例（样本贷方 ÷ 本期贷方发生额） */
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

export interface I3PeriodMovement {
  /** 本期借方代理：当年新确认商誉原值合计 */
  debitTotal: number
  /** 本期贷方：本期减值合计 */
  creditTotal: number
  /** 商誉原值合计（存在性测试备选总体） */
  originalTotal: number
  source: string
}

export function emptyI3TargetedRow(partial?: Partial<I3TargetedCheckRow>): I3TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i35-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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

export function emptyI3TargetedSampleMeta(partial?: Partial<I3TargetedSampleMeta>): I3TargetedSampleMeta {
  return {
    populationCount: 0,
    populationAmount: 0,
    populationCreditAmount: 0,
    populationDesc: '本期商誉借方发生额（新并购确认，记账凭证总体）',
    populationManual: false,
    testReasons: [],
    specificSample: '大额、关联方并购及异常减值/处置事项作为特定样本 100% 检查',
    specificAmount: 0,
    samplingPopulationDesc: '剔除特定样本后的剩余总体',
    sampleSize: 0,
    sampleMethod: '系统抽样',
    sampleProcess: '',
    coverageThreshold: I3_5_DEFAULT_COVERAGE_THRESHOLD,
    ...partial,
  }
}

export function emptyI3TargetedRiskFocus(partial?: Partial<I3TargetedRiskFocus>): I3TargetedRiskFocus {
  return {
    externalIndicators: '',
    internalIndicators: '',
    cguAllocation: '',
    cguConsistency: '',
    externalConclusion: '',
    internalConclusion: '',
    allocationConclusion: '',
    consistencyConclusion: '',
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

function _yearOf(dateStr: string): number | null {
  const m = /^(\d{4})/.exec((dateStr || '').trim())
  return m ? Number(m[1]) : null
}

export function normalizeI3TargetedRow(raw: any): I3TargetedCheckRow {
  return emptyI3TargetedRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName || raw?.investee || raw?.name),
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

export function normalizeI3TargetedSampleMeta(raw: any): I3TargetedSampleMeta {
  if (!raw || typeof raw !== 'object') return emptyI3TargetedSampleMeta()
  const reasons = Array.isArray(raw.testReasons)
    ? raw.testReasons.map(_str).filter(Boolean)
    : []
  return emptyI3TargetedSampleMeta({
    populationCount: _num(raw.populationCount),
    populationAmount: _num(raw.populationAmount),
    populationCreditAmount: _num(raw.populationCreditAmount),
    populationDesc: _str(raw.populationDesc) || emptyI3TargetedSampleMeta().populationDesc,
    populationManual: !!raw.populationManual,
    testReasons: reasons,
    specificSample: _str(raw.specificSample) || emptyI3TargetedSampleMeta().specificSample,
    specificAmount: _num(raw.specificAmount),
    samplingPopulationDesc: _str(raw.samplingPopulationDesc) || emptyI3TargetedSampleMeta().samplingPopulationDesc,
    sampleSize: _num(raw.sampleSize),
    sampleMethod: _str(raw.sampleMethod) || '系统抽样',
    sampleProcess: _str(raw.sampleProcess),
    coverageThreshold: Math.min(100, Math.max(1, _num(raw.coverageThreshold) || I3_5_DEFAULT_COVERAGE_THRESHOLD)),
  })
}

export function normalizeI3TargetedRiskFocus(raw: any): I3TargetedRiskFocus {
  if (!raw || typeof raw !== 'object') return emptyI3TargetedRiskFocus()
  // 兼容旧 I3-5-targeted：{ sections, conclusions }
  const sections = raw.sections || {}
  const conclusions = raw.conclusions || {}
  const join = (...parts: string[]) => parts.filter(Boolean).join('\n')
  return emptyI3TargetedRiskFocus({
    externalIndicators: _str(raw.externalIndicators || sections.externalIndicators),
    internalIndicators: _str(raw.internalIndicators || sections.internalIndicators),
    cguAllocation: _str(
      raw.cguAllocation
      || join(sections.mergerCostAllocation, sections.synergyEffect, sections.managementBasis),
    ),
    cguConsistency: _str(
      raw.cguConsistency
      || join(sections.priorYearConsistency, sections.internalReportConsistency, sections.cguChangeStatus),
    ),
    externalConclusion: _str(raw.externalConclusion || conclusions.externalIndicators),
    internalConclusion: _str(raw.internalConclusion || conclusions.internalIndicators),
    allocationConclusion: _str(
      raw.allocationConclusion
      || conclusions.mergerCostAllocation
      || conclusions.synergyEffect
      || conclusions.managementBasis,
    ),
    consistencyConclusion: _str(
      raw.consistencyConclusion
      || conclusions.priorYearConsistency
      || conclusions.internalReportConsistency
      || conclusions.cguChangeStatus,
    ),
  })
}

export function isAbnormalFlag(v: string): boolean {
  const s = (v || '').trim()
  return s !== '' && s !== '否' && s !== 'N' && s !== '无'
}

export function hasFailedCheck(row: I3TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].some((c) => c === '×')
}

export function isRowChecksComplete(row: I3TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].every((c) => !!c && c !== '')
}

export function summarizeI3Targeted(
  rows: I3TargetedCheckRow[],
  periodDebitTotal: number,
  periodCreditTotal = 0,
): I3TargetedSummary {
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

export function formatLayeredCoverageLabel(summary: I3TargetedSummary): string {
  if (summary.coverageRate == null) return 'N/A'
  const sp = summary.specificCoverageRate != null ? summary.specificCoverageRate.toFixed(2) : '0.00'
  const sa = summary.samplingCoverageRate != null ? summary.samplingCoverageRate.toFixed(2) : '0.00'
  return `借方 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

function _parseI32Rows(raw: unknown): any[] {
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
 * 从 I3-2 明细推算本期发生额：
 * 优先 costIncrease（原值本期增加=借方）/ currentImpairment|impIncrease（贷方）；
 * 无滚动字段时回退并购日年份代理。
 */
export function extractI3PeriodMovement(raw: unknown, asOfYear?: number): I3PeriodMovement {
  const rows = _parseI32Rows(raw)
  let debitTotal = 0
  let creditTotal = 0
  let originalTotal = 0
  let usedRoll = false
  for (const r of rows) {
    if ((r?.investee || r?.projectName || r?.name) === '合计') continue
    const original = _num(r?.goodwillOriginal ?? r?.costAudited)
    originalTotal += original
    const costInc = _num(r?.costIncrease)
    const periodDebit = _num(r?.periodDebit)
    const costDec = _num(r?.costDecrease)
    const periodCredit = _num(r?.periodCredit)
    const hasRoll = r?.costIncrease != null || r?.periodDebit != null
      || r?.periodCredit != null || r?.impIncrease != null || r?.costDecrease != null

    if (hasRoll) {
      usedRoll = true
      debitTotal += periodDebit > 0 ? periodDebit : costInc
      const curImpRoll = _num(r?.impIncrease ?? r?.currentImpairment)
      creditTotal += periodCredit > 0 ? periodCredit : (curImpRoll + costDec)
      continue
    }
    // 旧代理：按并购日年份 + currentImpairment
    creditTotal += _num(r?.currentImpairment)
    const y = _yearOf(_str(r?.mergerDate || r?.acquisitionDate))
    if (asOfYear == null || y === asOfYear) {
      debitTotal += original
    }
  }
  return {
    debitTotal: Math.round(debitTotal * 100) / 100,
    creditTotal: Math.round(creditTotal * 100) / 100,
    originalTotal: Math.round(originalTotal * 100) / 100,
    source: usedRoll ? 'I3-2本期发生额' : 'I3-2',
  }
}

export function buildI3TargetedConclusionDraft(opts: {
  sampleCount: number
  coverageLabel: string
  creditCoverageLabel?: string
  anomalyCount: number
  failCheckCount: number
  testReasons?: string[]
  riskFocus?: I3TargetedRiskFocus
}): string {
  const reasonText = opts.testReasons?.length
    ? `测试原因：${opts.testReasons.join('、')}。`
    : ''
  const parts = [
    `经抽查商誉相关记账凭证 ${opts.sampleCount} 笔，借方检查覆盖率 ${opts.coverageLabel}。`,
  ]
  if (opts.creditCoverageLabel && opts.creditCoverageLabel !== 'N/A') {
    parts.push(`贷方（减值等）检查覆盖率 ${opts.creditCoverageLabel}。`)
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
      rf.externalConclusion && `外部迹象：${rf.externalConclusion}`,
      rf.internalConclusion && `内部迹象：${rf.internalConclusion}`,
      rf.allocationConclusion && `CGU分摊：${rf.allocationConclusion}`,
      rf.consistencyConclusion && `CGU一致性：${rf.consistencyConclusion}`,
    ].filter(Boolean)
    if (riskBits.length) parts.push(`专项风险关注—${riskBits.join('；')}。`)
  }
  parts.push('商誉在重大方面列报适当（请结合 I3-4 入账价值、I3-6~I3-8 减值测试结论综合判断）。')
  return parts.join('')
}

/** 抽凭引擎 SampledVoucher → I3-5 行 */
export function mapSampledToI3TargetedRow(s: {
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
}): I3TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  return emptyI3TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    projectName: _str(s.accountName),
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? '高值必选' : ''),
    isAbnormal: s.abnormal ? '是' : '',
    remark: _str(s.remark),
  })
}

export interface I3TargetedAdjDraft {
  voucherNo: string
  projectName: string
  debitAmount: number
  failedChecks: string[]
  suggestedEntry: string
  suggestedNote: string
}

/** 核对× → 调整建议草稿 */
export function buildI3TargetedAdjDrafts(rows: I3TargetedCheckRow[]): I3TargetedAdjDraft[] {
  const labels = I3_5_TEST_CONTENT
  const out: I3TargetedAdjDraft[] = []
  for (const row of rows) {
    if (!hasFailedCheck(row)) continue
    const failedChecks: string[] = []
    const marks = [row.check1, row.check2, row.check3, row.check4, row.check5]
    marks.forEach((m, i) => {
      if (m === '×') failedChecks.push(`${i + 1}.${labels[i]}`)
    })
    const amt = row.debitAmount || row.creditAmount
    const valuation = failedChecks.some((c) => c.startsWith('3.') || c.startsWith('5.'))
    const cutoff = failedChecks.some((c) => c.startsWith('4.'))
    let suggestedEntry = `建议复核凭证 ${row.voucherNo || '—'}（${amt.toFixed(2)}）`
    if (valuation) {
      suggestedEntry += '：核对合并成本/可辨认净资产公允及 CGU 分摊，必要时调整商誉入账或减值（草拟写入 I3-3）'
    } else if (cutoff) {
      suggestedEntry += '：可能跨期确认，草拟跨期调整分录'
    } else {
      suggestedEntry += '：补齐并购协议/评估报告/付款凭证等原始资料或更正账证不符后重测'
    }
    out.push({
      voucherNo: row.voucherNo,
      projectName: row.projectName,
      debitAmount: row.debitAmount,
      failedChecks,
      suggestedEntry,
      suggestedNote: `I3-5 核对×：${failedChecks.join('；')}`,
    })
  }
  return out
}
