/**
 * i4TargetedCheckModel — I4-5 长期待摊费用针对性检查表纯函数
 *
 * 对齐致同 Excel「针对性检查表 I4-5」，镜像 I3-5 抽凭骨架：
 *   一、测试目标 → 二、样本选取（测试原因/总体）→ 三、测试（凭证核对 1~5）
 *   → 合计/本期发生额/检查比例 → 四、说明 → 五、结论
 *
 * Excel 模板缺口（平台已补强）：
 *   - 第 5 项核对内容为空「…」→ 补全为 I4-2 入账/受益期一致性
 *   - 检查比例 #DIV/0! → 总体为 0 时返回 null / 显示 N/A
 *   - 目标仅写「所有权」→ 改为资本化归属 + 计价分摊（受益期）
 *   - 无特定/抽样分层 → 表内可标特定样本并分层计算覆盖率
 *
 * 原段落型「大额新增核查 / 受益期变更 / 提前终止处理」保留为可选专项风险关注。
 */

export const I4_5_DEFAULT_COVERAGE_THRESHOLD = 20

/**
 * Excel「测试内容说明」1~5。
 * 1~4 对齐模板原文；第 3 项按长期待摊高风险点细化资本化判断；
 * 第 5 项补全 Excel 空缺，勾稽 I4-2。
 */
export const I4_5_TEST_CONTENT = [
  '原始凭证是否齐全',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确（资本化/费用化判断是否满足资产确认条件）',
  '是否记录于恰当的会计期间',
  '入账价值、摊销起点与受益期与 I4-2 明细表一致',
] as const

export const I4_5_TEST_REASONS = [
  '大额',
  '关联方',
  '受益期变更',
  '提前终止',
  '其他',
] as const

export const I4_5_SAMPLE_METHODS = [
  '随机抽样',
  '系统抽样',
  '货币单元抽样',
  '随意抽样',
  '全部检查',
] as const

export const I4_5_CHECK_OPTIONS = ['√', '×', 'N/A', ''] as const

export const I4_5_ABNORMAL_OPTIONS = [
  '否',
  '是',
  '入账差异',
  '资本化不当',
  '跨期',
  '受益期不一致',
  '其他',
] as const

/**
 * 对齐 Excel「存在/发生、所有权、计价和分摊」，并落到长期待摊实质认定：
 * 所有权→资本化归属；计价和分摊→入账价值与受益期/摊销。
 */
export const I4_5_OBJECTIVES = [
  '通过针对性测试，验证长期待摊费用的存在/发生、权利和义务（资本化归属）、计价和分摊（入账价值与受益期）。',
  '抽查长期待摊费用相关记账凭证与支持性文件，评价资本化判断、期间归属及与 I4-2 明细一致性是否恰当。',
] as const

export type I4TargetedCheckMark = (typeof I4_5_CHECK_OPTIONS)[number]

export interface I4TargetedCheckRow {
  rowId: string
  /** 长期待摊费用项目明细 */
  projectName: string
  voucherDate: string
  voucherNo: string
  businessDesc: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  supportingDocs: string
  check1: I4TargetedCheckMark | string
  check2: I4TargetedCheckMark | string
  check3: I4TargetedCheckMark | string
  check4: I4TargetedCheckMark | string
  check5: I4TargetedCheckMark | string
  indexRef: string
  isAbnormal: string
  remark: string
  isSpecific: boolean
  selectionReason: string
}

export interface I4TargetedSampleMeta {
  populationCount: number
  /** 测试总体金额（借方口径，用于检查比例） */
  populationAmount: number
  /** 本期贷方发生额（终止摊销/转出等，展示用） */
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

/** 原段落型风险关注（兼容旧 I4-5-major-addition 等分散字段） */
export interface I4TargetedRiskFocus {
  majorAddition: string
  benefitChange: string
  earlyTermination: string
  majorAdditionConclusion: string
  benefitChangeConclusion: string
  earlyTerminationConclusion: string
}

export interface I4TargetedSummary {
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

export interface I4PeriodMovement {
  /** 本期借方代理：当期新增长期待摊费用 */
  debitTotal: number
  /** 本期贷方：本期减少（提前终止/转出）合计 */
  creditTotal: number
  /** 原始金额合计（存在性测试总体备选） */
  originalTotal: number
  source: string
}

export function emptyI4TargetedRow(partial?: Partial<I4TargetedCheckRow>): I4TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i45-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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

export function emptyI4TargetedSampleMeta(partial?: Partial<I4TargetedSampleMeta>): I4TargetedSampleMeta {
  return {
    populationCount: 0,
    populationAmount: 0,
    populationCreditAmount: 0,
    populationDesc: '本期长期待摊费用借方发生额总体（新增确认，记账凭证总体）',
    populationManual: false,
    testReasons: [],
    specificSample: '大额、关联方新增及受益期变更/提前终止事项作为特定样本 100% 检查',
    specificAmount: 0,
    samplingPopulationDesc: '剔除特定样本后的剩余总体',
    sampleSize: 0,
    sampleMethod: '系统抽样',
    sampleProcess: '',
    coverageThreshold: I4_5_DEFAULT_COVERAGE_THRESHOLD,
    ...partial,
  }
}

export function emptyI4TargetedRiskFocus(partial?: Partial<I4TargetedRiskFocus>): I4TargetedRiskFocus {
  return {
    majorAddition: '',
    benefitChange: '',
    earlyTermination: '',
    majorAdditionConclusion: '',
    benefitChangeConclusion: '',
    earlyTerminationConclusion: '',
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

export function normalizeI4TargetedRow(raw: any): I4TargetedCheckRow {
  return emptyI4TargetedRow({
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

export function normalizeI4TargetedSampleMeta(raw: any): I4TargetedSampleMeta {
  if (!raw || typeof raw !== 'object') return emptyI4TargetedSampleMeta()
  const reasons = Array.isArray(raw.testReasons)
    ? raw.testReasons.map(_str).filter(Boolean)
    : []
  return emptyI4TargetedSampleMeta({
    populationCount: _num(raw.populationCount),
    populationAmount: _num(raw.populationAmount),
    populationCreditAmount: _num(raw.populationCreditAmount),
    populationDesc: _str(raw.populationDesc) || emptyI4TargetedSampleMeta().populationDesc,
    populationManual: !!raw.populationManual,
    testReasons: reasons,
    specificSample: _str(raw.specificSample) || emptyI4TargetedSampleMeta().specificSample,
    specificAmount: _num(raw.specificAmount),
    samplingPopulationDesc: _str(raw.samplingPopulationDesc) || emptyI4TargetedSampleMeta().samplingPopulationDesc,
    sampleSize: _num(raw.sampleSize),
    sampleMethod: _str(raw.sampleMethod) || '系统抽样',
    sampleProcess: _str(raw.sampleProcess),
    coverageThreshold: Math.min(100, Math.max(1, _num(raw.coverageThreshold) || I4_5_DEFAULT_COVERAGE_THRESHOLD)),
  })
}

/**
 * raw 既可为新结构 { majorAddition, benefitChange, ... }，
 * 也可为 useI4TargetedCheck 组装的旧分散字段对象
 * { majorAddition, majorAdditionConclusion, benefitChange, benefitChangeConclusion,
 *   earlyTermination, earlyTerminationConclusion }（旧 I4-5-major-addition 等 key 拼装而来）。
 */
export function normalizeI4TargetedRiskFocus(raw: any): I4TargetedRiskFocus {
  if (!raw || typeof raw !== 'object') return emptyI4TargetedRiskFocus()
  return emptyI4TargetedRiskFocus({
    majorAddition: _str(raw.majorAddition),
    benefitChange: _str(raw.benefitChange),
    earlyTermination: _str(raw.earlyTermination),
    majorAdditionConclusion: _str(raw.majorAdditionConclusion),
    benefitChangeConclusion: _str(raw.benefitChangeConclusion),
    earlyTerminationConclusion: _str(raw.earlyTerminationConclusion),
  })
}

export function isAbnormalFlag(v: string): boolean {
  const s = (v || '').trim()
  return s !== '' && s !== '否' && s !== 'N' && s !== '无'
}

export function hasFailedCheck(row: I4TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].some((c) => c === '×')
}

export function isRowChecksComplete(row: I4TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].every((c) => !!c && c !== '')
}

export function summarizeI4Targeted(
  rows: I4TargetedCheckRow[],
  periodDebitTotal: number,
  periodCreditTotal = 0,
): I4TargetedSummary {
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

export function formatLayeredCoverageLabel(summary: I4TargetedSummary): string {
  if (summary.coverageRate == null) return 'N/A'
  const sp = summary.specificCoverageRate != null ? summary.specificCoverageRate.toFixed(2) : '0.00'
  const sa = summary.samplingCoverageRate != null ? summary.samplingCoverageRate.toFixed(2) : '0.00'
  return `借方 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

/** Excel 表尾三行：合计 / 本期发生额 / 检查比例（避免 #DIV/0!） */
export interface I4CoverageFooter {
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodDebitTotal: number
  periodCreditTotal: number
  debitCoverageLabel: string
  creditCoverageLabel: string
  layeredCoverageLabel: string
}

export function buildI4CoverageFooter(
  summary: I4TargetedSummary,
  periodCreditTotal = 0,
): I4CoverageFooter {
  return {
    checkedDebitTotal: summary.checkedDebitTotal,
    checkedCreditTotal: summary.checkedCreditTotal,
    periodDebitTotal: summary.periodTotal,
    periodCreditTotal,
    debitCoverageLabel: formatCoverageLabel(summary.coverageRate),
    creditCoverageLabel: formatCoverageLabel(summary.creditCoverageRate),
    layeredCoverageLabel: formatLayeredCoverageLabel(summary),
  }
}

/** 核对× → 建议「是否异常」取值（便于编制人快速标注） */
export function suggestAbnormalFromFailedChecks(row: I4TargetedCheckRow): string {
  if (row.check3 === '×') return '资本化不当'
  if (row.check4 === '×') return '跨期'
  if (row.check5 === '×') return '受益期不一致'
  if (row.check1 === '×' || row.check2 === '×') return '入账差异'
  return '是'
}

/** 用表内特定样本借方合计回写第二节「特定样本金额」 */
export function syncSpecificAmountFromRows(rows: I4TargetedCheckRow[]): number {
  const specific = rows.filter((r) => r.isSpecific || !!r.selectionReason)
  return Math.round(specific.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
}

function _parseI42Rows(raw: unknown): any[] {
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
 * 从 I4-2 明细推算本期发生额：
 * 优先 unadjIncrease/auditedIncrease（滚动字段）或 currentIncrease；
 * 减少优先 unadjOtherDecrease / currentDecrease；
 * 无滚动字段时回退按 occurDate 年份代理 originalAmount。
 */
export function extractI4PeriodMovement(raw: unknown, asOfYear?: number): I4PeriodMovement {
  const rows = _parseI42Rows(raw)
  let debitTotal = 0
  let creditTotal = 0
  let originalTotal = 0
  let usedRoll = false
  for (const r of rows) {
    if ((r?.projectName || r?.name) === '合计') continue
    const original = _num(r?.originalAmount)
    originalTotal += original
    const costInc = _num(
      r?.unadjIncrease ?? r?.auditedIncrease ?? r?.currentIncrease ?? r?.costIncrease ?? r?.increase,
    )
    const costDec = _num(
      r?.unadjOtherDecrease ?? r?.auditedOtherDecrease ?? r?.currentDecrease ?? r?.costDecrease ?? r?.decrease,
    )
    const amort = _num(r?.unadjAmortization ?? r?.auditedAmortization ?? r?.currentAmortization)

    if (costInc > 0 || costDec > 0 || amort > 0) {
      usedRoll = true
      debitTotal += costInc
      // 贷方检查口径：其他减少（终止/转出）；摊销单独在 I4-6 勾稽
      creditTotal += costDec
      continue
    }
    const y = _yearOf(_str(r?.occurDate || r?.date))
    if (asOfYear == null || y === asOfYear) {
      debitTotal += original
    }
  }
  return {
    debitTotal: Math.round(debitTotal * 100) / 100,
    creditTotal: Math.round(creditTotal * 100) / 100,
    originalTotal: Math.round(originalTotal * 100) / 100,
    source: usedRoll ? 'I4-2本期发生额' : 'I4-2',
  }
}

export function buildI4TargetedConclusionDraft(opts: {
  sampleCount: number
  coverageLabel: string
  creditCoverageLabel?: string
  anomalyCount: number
  failCheckCount: number
  testReasons?: string[]
  riskFocus?: I4TargetedRiskFocus
  expansionAdvice?: I4CoverageExpansionAdvice | null
  creditExpansionAdvice?: I4CoverageExpansionAdvice | null
  i44CrossSummary?: string
}): string {
  const reasonText = opts.testReasons?.length
    ? `测试原因：${opts.testReasons.join('、')}。`
    : ''
  const parts = [
    `经抽查长期待摊费用相关记账凭证 ${opts.sampleCount} 笔，借方检查覆盖率 ${opts.coverageLabel}。`,
  ]
  if (opts.creditCoverageLabel && opts.creditCoverageLabel !== 'N/A') {
    parts.push(`贷方（转出/终止摊销）检查覆盖率 ${opts.creditCoverageLabel}。`)
  }
  if (reasonText) parts.push(reasonText)
  const expansionList = [
    opts.expansionAdvice,
    opts.creditExpansionAdvice,
  ].filter((a): a is I4CoverageExpansionAdvice => !!a?.needed)
  for (const adv of expansionList) {
    const sideLabel = adv.side === 'credit' ? '贷方' : '借方'
    parts.push(
      `${sideLabel}检查比例低于阈值 ${adv.threshold}%（缺口约 ${adv.gapPct.toFixed(2)} 个百分点），`
      + `建议至少再覆盖${sideLabel} ${adv.additionalDebitNeeded.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
      + (adv.suggestedExtraSamples != null ? `（约 ${adv.suggestedExtraSamples} 笔）` : '')
      + '，或在审计说明中解释未扩样原因。',
    )
  }
  if (opts.failCheckCount > 0) {
    parts.push(`其中 ${opts.failCheckCount} 笔核对内容存在「×」，已在表内标注并需跟进。`)
  } else if (opts.anomalyCount > 0) {
    parts.push(`发现异常 ${opts.anomalyCount} 笔，详见「是否异常」及备注。`)
  } else {
    parts.push('所抽样本原始凭证齐全、账证相符，资本化判断、期间归属及与 I4-2 明细一致性未见重大异常。')
  }
  const rf = opts.riskFocus
  if (rf) {
    const riskBits = [
      rf.majorAdditionConclusion && `大额新增：${rf.majorAdditionConclusion}`,
      rf.benefitChangeConclusion && `受益期变更：${rf.benefitChangeConclusion}`,
      rf.earlyTerminationConclusion && `提前终止：${rf.earlyTerminationConclusion}`,
    ].filter(Boolean)
    if (riskBits.length) parts.push(`专项风险关注—${riskBits.join('；')}。`)
  }
  if (opts.i44CrossSummary) {
    parts.push(opts.i44CrossSummary)
  }
  parts.push('长期待摊费用在重大方面列报适当（请结合 I4-2 明细表、I4-4 摊销政策检查结论综合判断）。')
  return parts.join('')
}

/** 检查比例偏低 → 强制扩样建议（金额/笔数/动作） */
export interface I4CoverageExpansionAdvice {
  needed: boolean
  side: 'debit' | 'credit'
  currentRate: number | null
  threshold: number
  gapPct: number
  checkedAmount: number
  periodAmount: number
  /** @deprecated 兼容旧字段名 → checkedAmount */
  checkedDebit: number
  /** @deprecated 兼容旧字段名 → periodAmount */
  periodDebit: number
  /** 达到阈值还需覆盖的金额 */
  additionalAmountNeeded: number
  /** @deprecated → additionalAmountNeeded */
  additionalDebitNeeded: number
  suggestedExtraSamples: number | null
  actions: string[]
  noteTemplate: string
  title: string
}

function _buildSideExpansionAdvice(
  side: 'debit' | 'credit',
  rate: number | null,
  periodAmount: number,
  checkedAmount: number,
  sampleCount: number,
  threshold: number,
): I4CoverageExpansionAdvice {
  const th = Math.min(100, Math.max(1, threshold || I4_5_DEFAULT_COVERAGE_THRESHOLD))
  const sideLabel = side === 'debit' ? '借方' : '贷方（转出/终止）'
  const base: I4CoverageExpansionAdvice = {
    needed: false,
    side,
    currentRate: rate,
    threshold: th,
    gapPct: 0,
    checkedAmount,
    periodAmount,
    checkedDebit: checkedAmount,
    periodDebit: periodAmount,
    additionalAmountNeeded: 0,
    additionalDebitNeeded: 0,
    suggestedExtraSamples: null,
    actions: [],
    noteTemplate: '',
    title: `${sideLabel}检查比例达标`,
  }
  if (rate == null || !(periodAmount > 0) || rate >= th) return base

  const gapPct = Math.round((th - rate) * 100) / 100
  const target = Math.round((periodAmount * th) / 100 * 100) / 100
  const additionalAmountNeeded = Math.max(0, Math.round((target - checkedAmount) * 100) / 100)
  const avg = sampleCount > 0 ? checkedAmount / sampleCount : 0
  const suggestedExtraSamples = avg > 0
    ? Math.max(1, Math.ceil(additionalAmountNeeded / avg))
    : null

  const actions = side === 'debit'
    ? [
        '打开抽凭引擎，扩大抽样总体覆盖（方向可含借方）',
        '将大额/关联方/受益期变更/提前终止事项标为特定样本 100% 检查',
        suggestedExtraSamples != null
          ? `建议至少再抽约 ${suggestedExtraSamples} 笔（或再覆盖借方 ${additionalAmountNeeded.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}）`
          : `建议再覆盖借方金额不少于 ${additionalAmountNeeded.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
        '若因总体已基本抽完或风险可接受而不扩样，须在「四、审计说明」写明理由',
      ]
    : [
        '打开抽凭引擎，方向筛选「贷方」或「全部」，覆盖终止摊销/转出凭证',
        '将「提前终止」事项标为特定样本 100% 检查',
        suggestedExtraSamples != null
          ? `建议至少再抽约 ${suggestedExtraSamples} 笔贷方样本（或再覆盖贷方 ${additionalAmountNeeded.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}）`
          : `建议再覆盖贷方金额不少于 ${additionalAmountNeeded.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`,
        '若本期贷方已全查或风险可接受，须在审计说明写明理由',
      ]

  const tag = side === 'debit' ? '检查比例偏低—扩样说明' : '贷方检查比例偏低—扩样说明'
  const noteTemplate = [
    `【${tag}】`,
    `当前${sideLabel}检查比例 ${rate.toFixed(2)}%，低于阈值 ${th}%（缺口 ${gapPct.toFixed(2)} 个百分点）。`,
    `已检查${sideLabel} ${checkedAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} / 总体 ${periodAmount.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，`,
    `达到阈值尚需约 ${additionalAmountNeeded.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
      + (suggestedExtraSamples != null ? `（约 ${suggestedExtraSamples} 笔）` : '')
      + '。',
    '拟采取：□继续抽凭扩样  □增加特定样本  □接受并说明理由：________',
  ].join('')

  return {
    needed: true,
    side,
    currentRate: rate,
    threshold: th,
    gapPct,
    checkedAmount,
    periodAmount,
    checkedDebit: checkedAmount,
    periodDebit: periodAmount,
    additionalAmountNeeded,
    additionalDebitNeeded: additionalAmountNeeded,
    suggestedExtraSamples,
    actions,
    noteTemplate,
    title: `${sideLabel}检查比例偏低（${rate.toFixed(2)}% < ${th}%）— 请扩样或说明`,
  }
}

/** 借方检查比例偏低 → 强制扩样建议 */
export function buildI4CoverageExpansionAdvice(
  summary: I4TargetedSummary,
  threshold: number,
): I4CoverageExpansionAdvice {
  return _buildSideExpansionAdvice(
    'debit',
    summary.coverageRate,
    summary.periodTotal,
    summary.checkedDebitTotal,
    summary.sampleCount,
    threshold,
  )
}

/** 贷方检查比例偏低 → 对称扩样建议（终止/转出） */
export function buildI4CreditCoverageExpansionAdvice(
  summary: I4TargetedSummary,
  periodCreditTotal: number,
  threshold: number,
  creditRowCount?: number,
): I4CoverageExpansionAdvice {
  let n = creditRowCount
  if (n == null) {
    // 无行数时按借贷金额占比粗估笔数
    const tot = summary.checkedDebitTotal + summary.checkedCreditTotal
    n = summary.checkedCreditTotal > 0 && tot > 0
      ? Math.max(1, Math.round(summary.sampleCount * summary.checkedCreditTotal / tot))
      : (summary.checkedCreditTotal > 0 ? Math.max(1, summary.sampleCount) : 0)
  }
  return _buildSideExpansionAdvice(
    'credit',
    summary.creditCoverageRate,
    periodCreditTotal,
    summary.checkedCreditTotal,
    n,
    threshold,
  )
}

/** 审计说明是否已回应覆盖率偏低（借/贷任一侧需要时均需回应） */
export function isCoverageNoteSatisfied(
  note: string,
  debitAdvice?: I4CoverageExpansionAdvice | null,
  creditAdvice?: I4CoverageExpansionAdvice | null,
): boolean {
  const s = (note || '').trim()
  if (debitAdvice?.needed) {
    if (!s) return false
    if (!/检查比例偏低|扩样|覆盖率不足|未扩样|接受.*比例|比例.*说明|借方/.test(s)) return false
  }
  if (creditAdvice?.needed) {
    if (!s) return false
    // 须明确点到贷方/转出/终止，避免仅写借方扩样即过闸
    if (!/贷方|转出|终止/.test(s)) return false
  }
  return true
}

/** 特定样本金额 vs 表内特定借方容差校验 */
export const I4_5_SPECIFIC_ABS_TOL = 0.05
export const I4_5_SPECIFIC_PCT_TOL = 0.01 // 1%

export interface I4SpecificAmountCheck {
  ok: boolean
  metaAmount: number
  tableAmount: number
  diff: number
  diffPct: number | null
  severity: 'ok' | 'info' | 'warning'
  message: string
}

export function checkI4SpecificAmountConsistency(
  metaSpecificAmount: number,
  tableSpecificDebit: number,
  opts?: { absTol?: number; pctTol?: number },
): I4SpecificAmountCheck {
  const meta = Math.round((_num(metaSpecificAmount)) * 100) / 100
  const table = Math.round((_num(tableSpecificDebit)) * 100) / 100
  const absTol = opts?.absTol ?? I4_5_SPECIFIC_ABS_TOL
  const pctTol = opts?.pctTol ?? I4_5_SPECIFIC_PCT_TOL
  const diff = Math.round((meta - table) * 100) / 100
  const base = Math.max(Math.abs(meta), Math.abs(table))
  const diffPct = base > 0 ? Math.round((Math.abs(diff) / base) * 10000) / 100 : null
  const tol = Math.max(absTol, base * pctTol)

  if (!(meta > 0) && !(table > 0)) {
    return { ok: true, metaAmount: meta, tableAmount: table, diff: 0, diffPct: null, severity: 'ok', message: '' }
  }
  if (meta > 0 && !(table > 0)) {
    return {
      ok: false,
      metaAmount: meta,
      tableAmount: table,
      diff,
      diffPct,
      severity: 'warning',
      message: `第二节特定样本金额 ${meta.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 已填，但表内尚无特定样本借方；请标记选取原因或清空第二节金额。`,
    }
  }
  if (!(meta > 0) && table > 0) {
    return {
      ok: false,
      metaAmount: meta,
      tableAmount: table,
      diff,
      diffPct,
      severity: 'info',
      message: `表内特定借方 ${table.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，建议点「从表内特定样本同步」回写第二节。`,
    }
  }
  if (Math.abs(diff) <= tol) {
    return {
      ok: true,
      metaAmount: meta,
      tableAmount: table,
      diff,
      diffPct,
      severity: 'ok',
      message: '特定样本金额与表内特定借方一致',
    }
  }
  return {
    ok: false,
    metaAmount: meta,
    tableAmount: table,
    diff,
    diffPct,
    severity: 'warning',
    message: `特定样本金额 ${meta.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 与表内特定借方 ${table.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 差 ${diff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}`
      + (diffPct != null ? `（${diffPct}%）` : '')
      + '，请同步或核查分层标记。',
  }
}

/** 测试原因 → 抽凭引擎预填（高值/关键词/方向） */
export interface I4SamplingPreset {
  defaultMethod: 'random' | 'systematic' | 'mus' | 'specific_item' | 'stratified'
  summaryKeyword: string
  directionFilter: 'debit' | 'credit' | 'all'
  materialityThreshold?: string
  selectionReasonHints: string[]
  hintText: string
}

export function buildI4SamplingPresetFromTestReasons(reasons: string[]): I4SamplingPreset {
  const set = new Set((reasons || []).filter(Boolean))
  const keywords: string[] = []
  const hints: string[] = []
  let method: I4SamplingPreset['defaultMethod'] = 'random'
  let direction: I4SamplingPreset['directionFilter'] = 'all'
  let materialityThreshold: string | undefined

  if (set.has('大额')) {
    method = 'mus'
    hints.push('大额')
    materialityThreshold = undefined // MUS 用间隔识别高值
  }
  if (set.has('关联方')) {
    keywords.push('关联')
    hints.push('关联方')
    // 关键词过滤即可；避免无重要性阈值时 specific_item 校验失败
  }
  if (set.has('受益期变更')) {
    keywords.push('受益期', '变更', '摊销年限')
    hints.push('受益期变更')
  }
  if (set.has('提前终止')) {
    keywords.push('终止', '转出', '核销', '报废')
    hints.push('提前终止')
    direction = set.has('大额') || set.has('关联方') || set.has('受益期变更') ? 'all' : 'credit'
  }
  if (set.has('其他') && !hints.length) {
    hints.push('其他')
  }

  const summaryKeyword = [...new Set(keywords)].join('|')
  const hintParts = [
    hints.length ? `已按测试原因预填：${hints.join('、')}` : '未勾选测试原因，使用默认随机抽样',
    method === 'mus' ? '方法=货币单元抽样（高值必选）' : method === 'specific_item' ? '方法=特定项目' : `方法=${method}`,
    summaryKeyword ? `摘要关键词「${summaryKeyword}」` : '',
    direction !== 'all' ? `方向=${direction === 'credit' ? '贷方' : '借方'}` : '',
  ].filter(Boolean)

  return {
    defaultMethod: method,
    summaryKeyword,
    directionFilter: direction,
    materialityThreshold,
    selectionReasonHints: hints.length ? hints : [...set],
    hintText: hintParts.join('；'),
  }
}

/**
 * 回填样本若无选取原因，按测试原因/摘要自动标注（高值规则）
 */
export function applyI4SelectionReasonsToSamples(
  samples: Array<{ selectionReason?: string; isHighValue?: boolean; summary?: string | null; remark?: string }>,
  reasons: string[],
): number {
  const preset = buildI4SamplingPresetFromTestReasons(reasons)
  const hints = preset.selectionReasonHints
  if (!hints.length) return 0
  let n = 0
  for (const s of samples) {
    if ((s.selectionReason || '').trim()) continue
    const summary = `${s.summary || ''}${s.remark || ''}`
    let picked = ''
    if (s.isHighValue && hints.includes('大额')) picked = '大额'
    else if (/关联/.test(summary) && hints.includes('关联方')) picked = '关联方'
    else if (/(受益期|变更|摊销年限)/.test(summary) && hints.includes('受益期变更')) picked = '受益期变更'
    else if (/(终止|转出|核销|报废)/.test(summary) && hints.includes('提前终止')) picked = '提前终止'
    else if (hints.length === 1) picked = hints[0]
    else if (s.isHighValue) picked = hints.includes('大额') ? '大额' : hints[0]
    if (picked) {
      s.selectionReason = picked
      n++
    }
  }
  return n
}

/** I4-4 快照（供 I4-5 交叉印证） */
export interface I44PolicySnapshot {
  casItems: Array<{ key: string; label: string; conclusion: string; explanationIfNo?: string }>
  policyParams: Array<{
    category: string
    hasChange: string
    changeReasonable: string
    meetsStandards: string
  }>
  overallConclusion: string
}

export interface I45I44CrossFinding {
  id: string
  severity: 'info' | 'warning' | 'error'
  title: string
  detail: string
}

export interface I45I44CrossResult {
  findings: I45I44CrossFinding[]
  summaryText: string
  hasWarning: boolean
  hasError: boolean
  empty: boolean
}

function _casOf(snap: I44PolicySnapshot, key: string) {
  return snap.casItems.find((c) => c.key === key)
}

/**
 * I4-5 抽凭结果 × I4-4 摊销政策结论自动交叉印证
 */
export function crossCheckI45WithI44(opts: {
  rows: I4TargetedCheckRow[]
  testReasons: string[]
  riskFocus: I4TargetedRiskFocus
  i44: I44PolicySnapshot | null
}): I45I44CrossResult {
  const findings: I45I44CrossFinding[] = []
  const i44 = opts.i44
  if (!i44 || (!i44.casItems.length && !i44.overallConclusion && !i44.policyParams.length)) {
    return {
      findings: [{
        id: 'i44-missing',
        severity: 'info',
        title: 'I4-4 尚未取数',
        detail: '请先编制摊销政策检查表 I4-4，再回来做交叉印证。',
      }],
      summaryText: '尚未与 I4-4 摊销政策结论交叉印证。',
      hasWarning: false,
      hasError: false,
      empty: true,
    }
  }

  const hasCheckFail = (n: 1 | 2 | 3 | 4 | 5) =>
    opts.rows.some((r) => (r as any)[`check${n}`] === '×')
  const hasAbnormalType = (t: string) =>
    opts.rows.some((r) => (r.isAbnormal || '').includes(t))
  const reasons = opts.testReasons || []
  const rf = opts.riskFocus

  const cap = _casOf(i44, 'capitalize-boundary')
  if (cap?.conclusion === '否') {
    if (hasCheckFail(3) || hasAbnormalType('资本化')) {
      findings.push({
        id: 'cap-aligned',
        severity: 'info',
        title: '资本化边界：两表已呼应',
        detail: `I4-4「${cap.label}」结论为否；I4-5 抽凭核对3/异常已标注资本化问题。`,
      })
    } else {
      findings.push({
        id: 'cap-gap',
        severity: 'warning',
        title: '资本化边界未在抽凭中落实',
        detail: `I4-4「${cap.label}」结论为否${cap.explanationIfNo ? `（${cap.explanationIfNo}）` : ''}，但 I4-5 未见核对3「×」或「资本化不当」异常，建议补抽或专项说明。`,
      })
    }
  }

  const benefit = _casOf(i44, 'benefit-period')
  if (benefit?.conclusion === '否') {
    if (hasCheckFail(5) || hasAbnormalType('受益期')) {
      findings.push({
        id: 'benefit-aligned',
        severity: 'info',
        title: '受益期限：两表已呼应',
        detail: `I4-4「${benefit.label}」结论为否；I4-5 核对5/异常已标注。`,
      })
    } else {
      findings.push({
        id: 'benefit-gap',
        severity: 'warning',
        title: '受益期限问题未在抽凭中落实',
        detail: `I4-4「${benefit.label}」结论为否，请在 I4-5 核对5（与 I4-2 受益期一致）中跟进或写入专项风险。`,
      })
    }
  }

  const changedCats = (i44.policyParams || [])
    .filter((p) => p.hasChange === 'Y')
    .map((p) => p.category)
    .filter(Boolean)
  const estimate = _casOf(i44, 'estimate-change')
  const hasBenefitReason = reasons.includes('受益期变更')
    || !!(rf.benefitChange || rf.benefitChangeConclusion)
    || opts.rows.some((r) => (r.selectionReason || '').includes('受益期'))

  if (changedCats.length || estimate?.conclusion === '否') {
    if (hasBenefitReason) {
      findings.push({
        id: 'change-aligned',
        severity: 'info',
        title: '估计变更：两表已呼应',
        detail: changedCats.length
          ? `I4-4 存在变更类别（${changedCats.join('、')}）；I4-5 已关注受益期变更。`
          : 'I4-4 估计变更结论为否；I4-5 已关注受益期变更。',
      })
    } else {
      findings.push({
        id: 'change-gap',
        severity: 'warning',
        title: '受益期/估计变更未纳入抽凭关注',
        detail: changedCats.length
          ? `I4-4 表A 显示变更：${changedCats.join('、')}。建议在 I4-5 勾选测试原因「受益期变更」并抽查相关凭证。`
          : `I4-4「${estimate?.label || '会计估计变更'}」结论为否，建议在 I4-5 专项风险「受益期变更」中回应。`,
      })
    }
  }

  const amortStart = _casOf(i44, 'amort-start')
  if (amortStart?.conclusion === '否') {
    const hasTerm = !!(rf.earlyTermination || rf.earlyTerminationConclusion)
      || reasons.includes('提前终止')
      || opts.rows.some((r) => (r.selectionReason || '').includes('提前终止') || (r.creditAmount || 0) > 0)
    if (!hasTerm) {
      findings.push({
        id: 'start-gap',
        severity: 'warning',
        title: '摊销起始/终止时点未在抽凭中落实',
        detail: `I4-4「${amortStart.label}」结论为否，请抽查贷方转出/提前终止样本，或填写专项风险「提前终止处理」。`,
      })
    }
  }

  const method = _casOf(i44, 'amort-method')
  if (method?.conclusion === '否') {
    findings.push({
      id: 'method-info',
      severity: 'info',
      title: '摊销方法需结合 I4-6/I4-7',
      detail: `I4-4「${method.label}」结论为否；抽凭侧重发生与资本化，方法恰当性请在摊销测算表复核。`,
    })
  }

  if (!i44.overallConclusion?.trim()) {
    findings.push({
      id: 'i44-no-conclusion',
      severity: 'info',
      title: 'I4-4 总体结论未填',
      detail: '建议完成 I4-4 总体结论后再终稿 I4-5。',
    })
  } else {
    findings.push({
      id: 'i44-conclusion',
      severity: 'info',
      title: '已读取 I4-4 总体结论',
      detail: i44.overallConclusion.trim().slice(0, 120) + (i44.overallConclusion.trim().length > 120 ? '…' : ''),
    })
  }

  const hasWarning = findings.some((f) => f.severity === 'warning')
  const hasError = findings.some((f) => f.severity === 'error')
  const warnTitles = findings.filter((f) => f.severity === 'warning').map((f) => f.title)
  const summaryText = warnTitles.length
    ? `与 I4-4 交叉印证发现待跟进：${warnTitles.join('；')}。`
    : '与 I4-4 摊销政策结论交叉印证未见需跟进的缺口。'

  return { findings, summaryText, hasWarning, hasError, empty: false }
}

export function buildI44CrossNoteBlock(result: I45I44CrossResult): string {
  const lines = result.findings.map((f) => {
    const tag = f.severity === 'warning' ? '⚠' : f.severity === 'error' ? '✖' : '·'
    return `${tag} ${f.title}：${f.detail}`
  })
  return `【I4-5×I4-4 交叉印证】\n${lines.join('\n')}\n${result.summaryText}`
}

export function parseI44PolicySnapshot(map: Map<string, any> | null | undefined): I44PolicySnapshot | null {
  if (!map) return null
  const readText = (raw: unknown): string => {
    if (raw == null) return ''
    if (typeof raw === 'string') return raw
    if (typeof raw === 'object') return String((raw as any).remark ?? (raw as any).conclusion ?? '')
    return ''
  }
  const parseJson = <T>(raw: unknown, fallback: T): T => {
    if (raw == null) return fallback
    if (Array.isArray(raw)) return raw as T
    if (typeof raw === 'object') {
      const inner = (raw as any).remark ?? (raw as any).conclusion ?? raw
      if (Array.isArray(inner)) return inner as T
      if (typeof inner === 'string' && inner) {
        try { return JSON.parse(inner) as T } catch { return fallback }
      }
      return fallback
    }
    if (typeof raw === 'string' && raw) {
      try { return JSON.parse(raw) as T } catch { return fallback }
    }
    return fallback
  }

  const casItems = parseJson<any[]>(map.get('I4-4-cas-items'), [])
  const policyParams = parseJson<any[]>(map.get('I4-4-policy-params'), [])
  const overallConclusion = readText(map.get('I4-4-overall-conclusion'))
    || readText(map.get('I4-4-conclusion'))
    || readText(map.get('I4-policycheck-audit-conclusion'))

  if (!casItems.length && !policyParams.length && !overallConclusion) return null

  return {
    casItems: (Array.isArray(casItems) ? casItems : []).map((c) => ({
      key: String(c?.key || ''),
      label: String(c?.label || c?.key || ''),
      conclusion: String(c?.conclusion || ''),
      explanationIfNo: String(c?.explanationIfNo || ''),
    })),
    policyParams: (Array.isArray(policyParams) ? policyParams : []).map((p) => ({
      category: String(p?.category || ''),
      hasChange: String(p?.hasChange || ''),
      changeReasonable: String(p?.changeReasonable || ''),
      meetsStandards: String(p?.meetsStandards || ''),
    })),
    overallConclusion,
  }
}

/** 抽凭引擎 SampledVoucher → I4-5 行（可挂接 I4-2 项目名） */
export function mapSampledToI4TargetedRow(
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
  catalog?: I42ProjectRef[],
): I4TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  const rawName = _str(s.accountName)
  const matched = catalog?.length
    ? matchI42ProjectName(
      { projectName: rawName, businessDesc: _str(s.summary), accountName: rawName, counterpartAccount: _str(s.counterpartAccount) },
      catalog,
    )
    : null
  // 账户名常为「长期待摊费用」总账名，优先用 I4-2 匹配结果
  const projectName = matched?.projectName
    || (rawName && !/长期待摊|1801/.test(rawName) ? rawName : '')
  return emptyI4TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    projectName,
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? '高值必选' : ''),
    isAbnormal: s.abnormal ? '是' : '',
    remark: [_str(s.remark), matched ? `[挂接I4-2:${matched.method}]` : ''].filter(Boolean).join(' '),
  })
}

/** I4-2 项目目录（供抽凭行挂接） */
export interface I42ProjectRef {
  projectName: string
  expenseType?: string
  increase?: number
}

export function extractI42ProjectCatalog(raw: unknown): I42ProjectRef[] {
  const rows = _parseI42Rows(raw)
  const out: I42ProjectRef[] = []
  const seen = new Set<string>()
  for (const r of rows) {
    const name = _str(r?.projectName || r?.name).trim()
    if (!name || name === '合计' || seen.has(name)) continue
    seen.add(name)
    out.push({
      projectName: name,
      expenseType: _str(r?.expenseType || r?.category),
      increase: _num(r?.unadjIncrease ?? r?.auditedIncrease ?? r?.currentIncrease),
    })
  }
  return out
}

function _normText(s: string): string {
  return (s || '').replace(/\s+/g, '').toLowerCase()
}

/**
 * 用凭证摘要/科目名模糊匹配 I4-2 项目名。
 * 优先：精确 → 摘要包含项目名 → 项目名包含摘要片段。
 */
export function matchI42ProjectName(
  hints: {
    projectName?: string
    businessDesc?: string
    accountName?: string
    counterpartAccount?: string
  },
  catalog: I42ProjectRef[],
): { projectName: string; score: number; method: 'exact' | 'contains' | 'token' } | null {
  if (!catalog.length) return null
  const hintName = _str(hints.projectName).trim()
  if (hintName) {
    const exact = catalog.find((c) => c.projectName === hintName)
    if (exact) return { projectName: exact.projectName, score: 100, method: 'exact' }
  }

  const blob = _normText([hints.businessDesc, hints.accountName, hints.counterpartAccount, hints.projectName].filter(Boolean).join('|'))
  if (!blob) return null

  let best: { projectName: string; score: number; method: 'exact' | 'contains' | 'token' } | null = null
  for (const c of catalog) {
    const pn = c.projectName
    const np = _normText(pn)
    if (!np || np.length < 2) continue
    if (blob.includes(np)) {
      const score = 60 + Math.min(30, np.length)
      if (!best || score > best.score) best = { projectName: pn, score, method: 'contains' }
      continue
    }
    // 去掉常见后缀后再比
    const stem = np.replace(/(费用|支出|摊销|改良|装修)$/g, '')
    if (stem.length >= 2 && blob.includes(stem)) {
      const score = 45 + Math.min(20, stem.length)
      if (!best || score > best.score) best = { projectName: pn, score, method: 'token' }
    }
  }
  return best && best.score >= 45 ? best : null
}

/** 为空的 projectName 批量挂接 I4-2；overwrite=false 时不覆盖已有名称 */
export function enrichRowsWithI42Projects(
  rows: I4TargetedCheckRow[],
  catalog: I42ProjectRef[],
  overwrite = false,
): { rows: I4TargetedCheckRow[]; linked: number } {
  let linked = 0
  const next = rows.map((row) => {
    if (!overwrite && (row.projectName || '').trim()) return row
    const m = matchI42ProjectName(
      {
        projectName: row.projectName,
        businessDesc: row.businessDesc,
        accountName: row.projectName,
        counterpartAccount: row.counterpartAccount,
      },
      catalog,
    )
    if (!m) return row
    linked += 1
    return { ...row, projectName: m.projectName }
  })
  return { rows: next, linked }
}

export interface I4TargetedAdjDraft {
  voucherNo: string
  projectName: string
  debitAmount: number
  creditAmount: number
  failedChecks: string[]
  suggestedEntry: string
  suggestedNote: string
  /** 可推 I4-3 的草稿类型 */
  draftKind: 'expense_reclass' | 'cutoff' | 'doc_only'
  amount: number
}

/** 核对× → 调整建议草稿 */
export function buildI4TargetedAdjDrafts(rows: I4TargetedCheckRow[]): I4TargetedAdjDraft[] {
  const labels = I4_5_TEST_CONTENT
  const out: I4TargetedAdjDraft[] = []
  for (const row of rows) {
    if (!hasFailedCheck(row)) continue
    const failedChecks: string[] = []
    const marks = [row.check1, row.check2, row.check3, row.check4, row.check5]
    marks.forEach((m, i) => {
      if (m === '×') failedChecks.push(`${i + 1}.${labels[i]}`)
    })
    const amt = row.debitAmount || row.creditAmount
    const capitalization = failedChecks.some((c) => c.startsWith('3.') || c.startsWith('5.'))
    const cutoff = failedChecks.some((c) => c.startsWith('4.'))
    let draftKind: I4TargetedAdjDraft['draftKind'] = 'doc_only'
    let suggestedEntry = `建议复核凭证 ${row.voucherNo || '—'}（${amt.toFixed(2)}）`
    if (capitalization) {
      draftKind = 'expense_reclass'
      suggestedEntry += '：核对资本化判断依据及受益期确定，必要时费用化重分类（可推 I4-3）'
    } else if (cutoff) {
      draftKind = 'cutoff'
      suggestedEntry += '：可能跨期确认，草拟跨期调整分录（可推 I4-3）'
    } else {
      suggestedEntry += '：补齐合同/发票/验收单等原始资料或更正账证不符后重测'
    }
    out.push({
      voucherNo: row.voucherNo,
      projectName: row.projectName,
      debitAmount: row.debitAmount,
      creditAmount: row.creditAmount,
      failedChecks,
      suggestedEntry,
      suggestedNote: `I4-5 核对×：${failedChecks.join('；')}`,
      draftKind,
      amount: amt,
    })
  }
  return out
}

/** 可推送至 I4-3 的分录行（与 I4AdjustmentRow 字段对齐的轻量结构） */
export interface I45ToI43Line {
  description: string
  projectName: string
  category: '账项调整'
  entryType: 'AJE'
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

/** I4-5 调整草稿 → I4-3 分录行（费用化重分类 / 跨期） */
export function buildI43LinesFromTargetedDrafts(drafts: I4TargetedAdjDraft[]): I45ToI43Line[] {
  const lines: I45ToI43Line[] = []
  for (const d of drafts) {
    if (d.draftKind === 'doc_only' || !(d.amount > 0.005)) continue
    const projectName = d.projectName || d.voucherNo || '未命名项目'
    const idx = `I4-5/${d.voucherNo || '—'}`
    if (d.draftKind === 'expense_reclass') {
      const desc = `长期待摊费用化重分类-${projectName}`
      lines.push(
        {
          description: desc,
          projectName,
          category: '账项调整',
          entryType: 'AJE',
          reportItem: '管理费用',
          accountCode: '6602',
          accountName: '管理费用',
          noteItem: '长期待摊费用',
          debitAmount: d.amount,
          creditAmount: 0,
          indexRef: idx,
          remark: d.suggestedNote,
        },
        {
          description: desc,
          projectName,
          category: '账项调整',
          entryType: 'AJE',
          reportItem: '长期待摊费用',
          accountCode: '1801',
          accountName: '长期待摊费用',
          noteItem: '长期待摊费用',
          debitAmount: 0,
          creditAmount: d.amount,
          indexRef: idx,
          remark: '冲减长期待摊账面（I4-5 资本化不当）',
        },
      )
    } else if (d.draftKind === 'cutoff') {
      const desc = `长期待摊跨期调整-${projectName}`
      // 冲回本期不当确认：贷记资产 / 借记费用（简化：与费用化同向，备注标明跨期）
      lines.push(
        {
          description: desc,
          projectName,
          category: '账项调整',
          entryType: 'AJE',
          reportItem: '管理费用',
          accountCode: '6602',
          accountName: '管理费用',
          noteItem: '长期待摊费用',
          debitAmount: d.amount,
          creditAmount: 0,
          indexRef: idx,
          remark: `${d.suggestedNote}（跨期）`,
        },
        {
          description: desc,
          projectName,
          category: '账项调整',
          entryType: 'AJE',
          reportItem: '长期待摊费用',
          accountCode: '1801',
          accountName: '长期待摊费用',
          noteItem: '长期待摊费用',
          debitAmount: 0,
          creditAmount: d.amount,
          indexRef: idx,
          remark: '冲回跨期确认的长期待摊',
        },
      )
    }
  }
  return lines
}

/** 合并进既有 I4-3 行：按 description+accountCode 去重（同一说明可保留借贷两行） */
export function mergeI43LinesSkippingExisting(
  existing: any[],
  incoming: I45ToI43Line[],
): { merged: any[]; added: number } {
  const keys = new Set(
    (existing || []).map((r) => {
      const desc = String(r?.description || r?.summary || '').trim()
      const code = String(r?.accountCode || '').trim()
      return `${desc}||${code}`
    }).filter((k) => k !== '||'),
  )
  const toAdd: any[] = []
  for (const line of incoming) {
    const key = `${line.description}||${line.accountCode}`
    if (keys.has(key)) continue
    toAdd.push({
      ...line,
      rowId: `i45-i43-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    })
    keys.add(key)
  }
  return { merged: [...(existing || []), ...toAdd], added: toAdd.length }
}
