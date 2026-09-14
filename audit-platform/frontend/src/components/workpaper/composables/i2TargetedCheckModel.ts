/**
 * i2TargetedCheckModel — I2-12 开（研）发支出针对性检查表纯函数
 *
 * 对齐致同 Excel「针对性检查表 I2-12」：
 *   一、测试目标 → 二、样本选取标准与规模 → 三、测试（凭证核对 1~5）→ 四、说明 → 五、结论
 *
 * Spec Req 13 原「段落型」风险主题保留为可选补充区（加计扣除/资本化比例/进度），
 * 主路径以凭证抽查为准（与 I2-8/截止测试同构）。
 */

export const I2_12_DEFAULT_COVERAGE_THRESHOLD = 20

/** Excel「测试内容说明」1~5 */
export const I2_12_TEST_CONTENT = [
  '原始凭证是否齐全',
  '记账凭证与原始凭证是否相符',
  '会计处理是否正确（科目、金额、资本化/费用化）',
  '是否记录于正确的会计期间（截止）',
  '项目归属及资本化五项条件支撑是否充分（对照 I2-6）',
] as const

export const I2_12_SAMPLE_METHODS = [
  '随机抽样',
  '系统抽样',
  '货币单元抽样',
  '随意抽样',
  '全部检查',
] as const

export const I2_12_CHECK_OPTIONS = ['√', '×', 'N/A', ''] as const

export const I2_12_OBJECTIVES = [
  '核实开发支出的存在/发生、权利义务、计价与分摊是否恰当。',
  '检查人工成本、材料、制造费用分摊及委外研发等支出的真实性与归集正确性。',
] as const

export type I2TargetedCheckMark = (typeof I2_12_CHECK_OPTIONS)[number]

export interface I2TargetedCheckRow {
  rowId: string
  /** 开发支出项目明细 */
  projectName: string
  /** 记账凭证：日期 */
  voucherDate: string
  /** 记账凭证：凭证号 */
  voucherNo: string
  /** 业务内容 */
  businessDesc: string
  /** 对方科目 */
  counterpartAccount: string
  /** 对方明细科目 */
  counterpartDetail: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
  /** 支持性文件 */
  supportingDocs: string
  /** 核对内容 1~5 */
  check1: I2TargetedCheckMark | string
  check2: I2TargetedCheckMark | string
  check3: I2TargetedCheckMark | string
  check4: I2TargetedCheckMark | string
  check5: I2TargetedCheckMark | string
  /** 索引号 */
  indexRef: string
  /** 是否异常 */
  isAbnormal: string
  /** 备注说明 */
  remark: string
  /** 是否特定样本（大额/关联方等 100% 检查） */
  isSpecific: boolean
  /** 选取原因（抽凭引擎 selectionReason） */
  selectionReason: string
}

export interface I2TargetedSampleMeta {
  /** 测试总体：凭证笔数 */
  populationCount: number
  /** 测试总体：金额 */
  populationAmount: number
  /** 总体说明 */
  populationDesc: string
  /** 是否手工覆盖总体金额 */
  populationManual: boolean
  /** 特定样本（大额/关联方/异常，100%检查） */
  specificSample: string
  /** 特定样本金额合计（可选） */
  specificAmount: number
  /** 抽样总体说明（剔除特定样本后） */
  samplingPopulationDesc: string
  /** 确定的抽样样本量 */
  sampleSize: number
  /** 抽样方法 */
  sampleMethod: string
  /** 抽样过程 / 索引 */
  sampleProcess: string
  /** 检查比例告警阈值 % */
  coverageThreshold: number
}

/** 原段落型风险关注（Req 13 兼容） */
export interface I2TargetedRiskFocus {
  deductionCompliance: string
  capitalizationRatio: string
  projectProgress: string
  deductionConclusion: string
  capitalizationConclusion: string
  progressConclusion: string
}

export interface I2TargetedSummary {
  sampleCount: number
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodTotal: number
  coverageRate: number | null
  anomalyCount: number
  failCheckCount: number
  pendingCount: number
  completedCheckCount: number
  /** 特定样本行数（selectionReason / isSpecific） */
  specificCount: number
  /** 特定样本借方合计 */
  specificDebitTotal: number
  /** 抽样样本借方合计（非特定） */
  samplingDebitTotal: number
  /** 分层覆盖：特定金额占比% */
  specificCoverageRate: number | null
  /** 分层覆盖：抽样金额占比% */
  samplingCoverageRate: number | null
}

export function emptyI2TargetedRow(partial?: Partial<I2TargetedCheckRow>): I2TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i212-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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

export function emptyI2TargetedSampleMeta(partial?: Partial<I2TargetedSampleMeta>): I2TargetedSampleMeta {
  return {
    populationCount: 0,
    populationAmount: 0,
    populationDesc: '本期开发支出借方发生额（记账凭证总体）',
    populationManual: false,
    specificSample: '大额（超重要性水平）、关联方及异常事项作为特定样本 100% 检查',
    specificAmount: 0,
    samplingPopulationDesc: '剔除特定样本后的剩余总体',
    sampleSize: 0,
    sampleMethod: '系统抽样',
    sampleProcess: '',
    coverageThreshold: I2_12_DEFAULT_COVERAGE_THRESHOLD,
    ...partial,
  }
}

export function emptyI2TargetedRiskFocus(partial?: Partial<I2TargetedRiskFocus>): I2TargetedRiskFocus {
  return {
    deductionCompliance: '',
    capitalizationRatio: '',
    projectProgress: '',
    deductionConclusion: '',
    capitalizationConclusion: '',
    progressConclusion: '',
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

export function normalizeI2TargetedRow(raw: any): I2TargetedCheckRow {
  return emptyI2TargetedRow({
    rowId: _str(raw?.rowId) || undefined,
    projectName: _str(raw?.projectName || raw?.name),
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

export function normalizeI2TargetedSampleMeta(raw: any): I2TargetedSampleMeta {
  if (!raw || typeof raw !== 'object') return emptyI2TargetedSampleMeta()
  return emptyI2TargetedSampleMeta({
    populationCount: _num(raw.populationCount),
    populationAmount: _num(raw.populationAmount),
    populationDesc: _str(raw.populationDesc) || emptyI2TargetedSampleMeta().populationDesc,
    populationManual: !!raw.populationManual,
    specificSample: _str(raw.specificSample) || emptyI2TargetedSampleMeta().specificSample,
    specificAmount: _num(raw.specificAmount),
    samplingPopulationDesc: _str(raw.samplingPopulationDesc) || emptyI2TargetedSampleMeta().samplingPopulationDesc,
    sampleSize: _num(raw.sampleSize),
    sampleMethod: _str(raw.sampleMethod) || '系统抽样',
    sampleProcess: _str(raw.sampleProcess),
    coverageThreshold: Math.min(100, Math.max(1, _num(raw.coverageThreshold) || I2_12_DEFAULT_COVERAGE_THRESHOLD)),
  })
}

export function normalizeI2TargetedRiskFocus(raw: any): I2TargetedRiskFocus {
  if (!raw || typeof raw !== 'object') return emptyI2TargetedRiskFocus()
  // 兼容旧 I2-12-targeted：{ sections, conclusions }
  const sections = raw.sections || {}
  const conclusions = raw.conclusions || {}
  return emptyI2TargetedRiskFocus({
    deductionCompliance: _str(raw.deductionCompliance || sections.deductionCompliance),
    capitalizationRatio: _str(raw.capitalizationRatio || sections.capitalizationRatio),
    projectProgress: _str(raw.projectProgress || sections.projectProgress),
    deductionConclusion: _str(raw.deductionConclusion || conclusions.deductionCompliance),
    capitalizationConclusion: _str(raw.capitalizationConclusion || conclusions.capitalizationRatio),
    progressConclusion: _str(raw.progressConclusion || conclusions.projectProgress),
  })
}

export function isAbnormalFlag(v: string): boolean {
  const s = (v || '').trim()
  return s !== '' && s !== '否' && s !== 'N' && s !== '无'
}

export function hasFailedCheck(row: I2TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].some((c) => c === '×')
}

export function isRowChecksComplete(row: I2TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].every((c) => !!c && c !== '')
}

export function summarizeI2Targeted(
  rows: I2TargetedCheckRow[],
  periodTotal: number,
): I2TargetedSummary {
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
  let specificCoverageRate: number | null = null
  let samplingCoverageRate: number | null = null
  if (periodTotal > 0) {
    coverageRate = Math.round((checkedDebitTotal / periodTotal) * 10000) / 100
    specificCoverageRate = Math.round((specificDebitTotal / periodTotal) * 10000) / 100
    samplingCoverageRate = Math.round((samplingDebitTotal / periodTotal) * 10000) / 100
  }

  return {
    sampleCount,
    checkedDebitTotal,
    checkedCreditTotal,
    periodTotal,
    coverageRate,
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

/** 从 I2-2 明细汇总本期资本化增加，作为测试总体金额候选 */
export function extractI2CapIncreaseTotal(raw: unknown): number {
  let rows: any[] = []
  if (Array.isArray(raw)) rows = raw
  else if (typeof raw === 'string' && raw) {
    try {
      const p = JSON.parse(raw)
      rows = Array.isArray(p) ? p : []
    } catch { return 0 }
  } else if (raw && typeof raw === 'object') {
    const obj = raw as any
    const remark = obj.remark ?? obj.conclusion
    if (typeof remark === 'string' && remark) {
      try {
        const p = JSON.parse(remark)
        rows = Array.isArray(p) ? p : []
      } catch { return 0 }
    } else if (Array.isArray(remark)) {
      rows = remark
    }
  }
  return Math.round(rows.reduce((s, r) => {
    if ((r?.projectName || r?.name) === '合计') return s
    return s + _num(r?.capIncrease)
  }, 0) * 100) / 100
}

export function buildI2TargetedConclusionDraft(opts: {
  sampleCount: number
  coverageLabel: string
  anomalyCount: number
  failCheckCount: number
  riskFocus?: I2TargetedRiskFocus
}): string {
  const parts = [
    `经抽查开发支出相关记账凭证 ${opts.sampleCount} 笔，检查覆盖率 ${opts.coverageLabel}。`,
  ]
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
      rf.deductionConclusion && `加计扣除：${rf.deductionConclusion}`,
      rf.capitalizationConclusion && `资本化比例：${rf.capitalizationConclusion}`,
      rf.progressConclusion && `项目进度：${rf.progressConclusion}`,
    ].filter(Boolean)
    if (riskBits.length) parts.push(`专项风险关注—${riskBits.join('；')}。`)
  }
  parts.push('开发支出在重大方面列报适当（请结合 I2-6/I2-13~15 结论综合判断）。')
  return parts.join('')
}

/** 抽凭引擎 SampledVoucher → I2-12 行 */
export function mapSampledToI2TargetedRow(s: {
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
}): I2TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  return emptyI2TargetedRow({
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

export interface I2TargetedAdjDraft {
  voucherNo: string
  projectName: string
  debitAmount: number
  failedChecks: string[]
  suggestedEntry: string
  suggestedNote: string
}

/** 核对× → 调整建议草稿（供写入 I2-3 / 审计说明） */
export function buildI2TargetedAdjDrafts(rows: I2TargetedCheckRow[]): I2TargetedAdjDraft[] {
  const labels = I2_12_TEST_CONTENT
  const out: I2TargetedAdjDraft[] = []
  for (const row of rows) {
    if (!hasFailedCheck(row)) continue
    const failedChecks: string[] = []
    const marks = [row.check1, row.check2, row.check3, row.check4, row.check5]
    marks.forEach((m, i) => {
      if (m === '×') failedChecks.push(`${i + 1}.${labels[i]}`)
    })
    const amt = row.debitAmount || row.creditAmount
    const reclass = failedChecks.some((c) => c.startsWith('3.') || c.startsWith('5.'))
    const cutoff = failedChecks.some((c) => c.startsWith('4.'))
    let suggestedEntry = `建议复核凭证 ${row.voucherNo || '—'}（${amt.toFixed(2)}）`
    if (reclass) {
      suggestedEntry += '：可能需将资本化调至费用化（或反之），草拟：借：研发费用 / 贷：开发支出（或反向）'
    } else if (cutoff) {
      suggestedEntry += '：可能跨期，草拟：借/贷：开发支出（或费用）与往来/损益跨期调整'
    } else {
      suggestedEntry += '：补齐原始凭证或更正账证不符后重测'
    }
    out.push({
      voucherNo: row.voucherNo,
      projectName: row.projectName,
      debitAmount: row.debitAmount,
      failedChecks,
      suggestedEntry,
      suggestedNote: `I2-12 核对×：${failedChecks.join('；')}`,
    })
  }
  return out
}

export function formatLayeredCoverageLabel(summary: I2TargetedSummary): string {
  if (summary.coverageRate == null) return 'N/A'
  const sp = summary.specificCoverageRate != null ? summary.specificCoverageRate.toFixed(2) : '0.00'
  const sa = summary.samplingCoverageRate != null ? summary.samplingCoverageRate.toFixed(2) : '0.00'
  return `合计 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

