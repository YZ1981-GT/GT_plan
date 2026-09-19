/**
 * i5TargetedCheckModel — I5-4 其他非流动资产针对性检查表纯函数
 *
 * 对齐致同 Excel「针对性检查表 I5-4」，镜像 I3-5 抽凭骨架：
 *   一、测试目标 → 二、样本选取（测试原因/总体）→ 三、测试（凭证核对 1~5）
 *   → 合计/本期发生额/检查比例 → 四、说明 → 五、结论
 *
 * Excel 模板缺口（平台已补强）：
 *   - 第 5 项核对内容为空「…」→ 补全为与 I5-2 分类/期限/可回收性一致性
 *   - 检查比例 #DIV/0! → 总体为 0 时返回 null / 显示 N/A
 *   - 目标仅写「计价和分摊」→ 落到分类科目、期限归属、可回收性
 *   - 无特定/抽样分层 → 表内可标选取原因并分层计算覆盖率
 *   - 特定样本金额与表内脱节 → 可一键同步并容差校验
 *
 * 原段落型「分类正确性 / 期限适当性 / 可回收性评估」保留为专项风险关注（建议填报）。
 */

import { extractI5CurrentPortionCandidates } from './i5AdjudicationModel'

export const I5_4_DEFAULT_COVERAGE_THRESHOLD = 20

/** 第二节特定样本金额 vs 表内特定借方：绝对容差 / 比例容差 */
export const I5_4_SPECIFIC_ABS_TOL = 0.05
export const I5_4_SPECIFIC_PCT_TOL = 0.001

/**
 * Excel「测试内容说明」1~5。
 * 1~4 对齐模板原文；第 3 项按其他非流动资产高风险点细化分类判断；
 * 第 5 项补全 Excel 空缺，勾稽 I5-2。
 */
export const I5_4_TEST_CONTENT = [
  '原始凭证是否齐全',
  '记账凭证与原始凭证是否相符',
  '账务处理是否正确（分类科目是否恰当，应否归入长期待摊/无形/流动资产）',
  '是否记录于恰当的会计期间',
  '分类、期限与可回收性判断与 I5-2 明细表一致',
] as const

export const I5_4_TEST_REASONS = [
  '大额',
  '关联方',
  '分类变更',
  '期限临近到期',
  '可回收性疑虑',
  '其他',
] as const

export const I5_4_SAMPLE_METHODS = [
  '随机抽样',
  '系统抽样',
  '货币单元抽样',
  '随意抽样',
  '全部检查',
] as const

export const I5_4_CHECK_OPTIONS = ['√', '×', 'N/A', ''] as const

export const I5_4_ABNORMAL_OPTIONS = [
  '否',
  '是',
  '入账差异',
  '分类不当',
  '期限未重分类',
  '跨期',
  '可回收性疑虑',
  '其他',
] as const

/**
 * 对齐 Excel「存在/发生、计价和分摊」，并落到其他非流动资产实质认定：
 * 计价和分摊 → 分类科目、期限归属（流动/非流动）、可回收性。
 */
export const I5_4_OBJECTIVES = [
  '通过针对性测试，验证其他非流动资产的存在/发生、计价和分摊（分类科目、期限归属及可回收性）。',
  '抽查其他非流动资产相关记账凭证与支持性文件，评价账证相符、期间归属及与 I5-2 明细一致性是否恰当。',
] as const

export type I5TargetedCheckMark = (typeof I5_4_CHECK_OPTIONS)[number]

export interface I5TargetedCheckRow {
  rowId: string
  /** 其他非流动资产项目明细 */
  projectName: string
  voucherDate: string
  voucherNo: string
  businessDesc: string
  counterpartAccount: string
  counterpartDetail: string
  debitAmount: number
  creditAmount: number
  supportingDocs: string
  check1: I5TargetedCheckMark | string
  check2: I5TargetedCheckMark | string
  check3: I5TargetedCheckMark | string
  check4: I5TargetedCheckMark | string
  check5: I5TargetedCheckMark | string
  indexRef: string
  isAbnormal: string
  remark: string
  isSpecific: boolean
  selectionReason: string
}

export interface I5TargetedSampleMeta {
  populationCount: number
  /** 测试总体金额（借方口径，用于检查比例） */
  populationAmount: number
  /** 本期贷方发生额（减少/转出等，展示用） */
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

/** 原段落型风险关注（兼容旧分类正确性/期限适当性/可回收性 radio+textarea） */
export interface I5TargetedRiskFocus {
  classification: string
  maturity: string
  recoverability: string
  classificationConclusion: string
  maturityConclusion: string
  recoverabilityConclusion: string
}

export interface I5TargetedSummary {
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

export interface I5PeriodMovement {
  /** 本期借方代理：当期新增其他非流动资产 */
  debitTotal: number
  /** 本期贷方：本期减少（转出/重分类/清理）合计 */
  creditTotal: number
  /** 原始金额合计（存在性测试总体备选） */
  originalTotal: number
  source: string
}

export function emptyI5TargetedRow(partial?: Partial<I5TargetedCheckRow>): I5TargetedCheckRow {
  return {
    rowId: partial?.rowId || `i54-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
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

export function emptyI5TargetedSampleMeta(partial?: Partial<I5TargetedSampleMeta>): I5TargetedSampleMeta {
  return {
    populationCount: 0,
    populationAmount: 0,
    populationCreditAmount: 0,
    populationDesc: '本期其他非流动资产借方发生额总体（新增确认，记账凭证总体）',
    populationManual: false,
    testReasons: [],
    specificSample: '大额、关联方、分类变更、期限临近到期及可回收性疑虑事项作为特定样本 100% 检查',
    specificAmount: 0,
    samplingPopulationDesc: '剔除特定样本后的剩余总体',
    sampleSize: 0,
    sampleMethod: '系统抽样',
    sampleProcess: '',
    coverageThreshold: I5_4_DEFAULT_COVERAGE_THRESHOLD,
    ...partial,
  }
}

export function emptyI5TargetedRiskFocus(partial?: Partial<I5TargetedRiskFocus>): I5TargetedRiskFocus {
  return {
    classification: '',
    maturity: '',
    recoverability: '',
    classificationConclusion: '',
    maturityConclusion: '',
    recoverabilityConclusion: '',
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

export function normalizeI5TargetedRow(raw: any): I5TargetedCheckRow {
  return emptyI5TargetedRow({
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

export function normalizeI5TargetedSampleMeta(raw: any): I5TargetedSampleMeta {
  if (!raw || typeof raw !== 'object') return emptyI5TargetedSampleMeta()
  const reasons = Array.isArray(raw.testReasons)
    ? raw.testReasons.map(_str).filter(Boolean)
    : []
  return emptyI5TargetedSampleMeta({
    populationCount: _num(raw.populationCount),
    populationAmount: _num(raw.populationAmount),
    populationCreditAmount: _num(raw.populationCreditAmount),
    populationDesc: _str(raw.populationDesc) || emptyI5TargetedSampleMeta().populationDesc,
    populationManual: !!raw.populationManual,
    testReasons: reasons,
    specificSample: _str(raw.specificSample) || emptyI5TargetedSampleMeta().specificSample,
    specificAmount: _num(raw.specificAmount),
    samplingPopulationDesc: _str(raw.samplingPopulationDesc) || emptyI5TargetedSampleMeta().samplingPopulationDesc,
    sampleSize: _num(raw.sampleSize),
    sampleMethod: _str(raw.sampleMethod) || '系统抽样',
    sampleProcess: _str(raw.sampleProcess),
    coverageThreshold: Math.min(100, Math.max(1, _num(raw.coverageThreshold) || I5_4_DEFAULT_COVERAGE_THRESHOLD)),
  })
}

/**
 * raw 既可为新结构 { classification, maturity, recoverability, ...Conclusion }，
 * 也可为 useI5TargetedCheck 组装的旧分散字段迁移对象：
 * { classificationItems: string[], classificationText, maturityItems, maturityText,
 *   recoverabilityItems, recoverabilityText }（旧 radio + textarea 拼装而来）。
 */
export function normalizeI5TargetedRiskFocus(raw: any): I5TargetedRiskFocus {
  if (!raw || typeof raw !== 'object') return emptyI5TargetedRiskFocus()
  const join = (...parts: string[]) => parts.filter(Boolean).join('\n')
  const hasLegacyShape = 'classificationItems' in raw || 'maturityItems' in raw || 'recoverabilityItems' in raw
  if (hasLegacyShape) {
    return emptyI5TargetedRiskFocus({
      classification: join(_str(raw.classificationItems), _str(raw.classificationText)),
      maturity: join(_str(raw.maturityItems), _str(raw.maturityText)),
      recoverability: join(_str(raw.recoverabilityItems), _str(raw.recoverabilityText)),
      classificationConclusion: _str(raw.classificationConclusion),
      maturityConclusion: _str(raw.maturityConclusion),
      recoverabilityConclusion: _str(raw.recoverabilityConclusion),
    })
  }
  return emptyI5TargetedRiskFocus({
    classification: _str(raw.classification),
    maturity: _str(raw.maturity),
    recoverability: _str(raw.recoverability),
    classificationConclusion: _str(raw.classificationConclusion),
    maturityConclusion: _str(raw.maturityConclusion),
    recoverabilityConclusion: _str(raw.recoverabilityConclusion),
  })
}

export function isAbnormalFlag(v: string): boolean {
  const s = (v || '').trim()
  return s !== '' && s !== '否' && s !== 'N' && s !== '无'
}

export function hasFailedCheck(row: I5TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].some((c) => c === '×')
}

export function isRowChecksComplete(row: I5TargetedCheckRow): boolean {
  return [row.check1, row.check2, row.check3, row.check4, row.check5].every((c) => !!c && c !== '')
}

export function summarizeI5Targeted(
  rows: I5TargetedCheckRow[],
  periodDebitTotal: number,
  periodCreditTotal = 0,
): I5TargetedSummary {
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

export function formatLayeredCoverageLabel(summary: I5TargetedSummary): string {
  if (summary.coverageRate == null) return 'N/A'
  const sp = summary.specificCoverageRate != null ? summary.specificCoverageRate.toFixed(2) : '0.00'
  const sa = summary.samplingCoverageRate != null ? summary.samplingCoverageRate.toFixed(2) : '0.00'
  return `借方 ${summary.coverageRate.toFixed(2)}%（特定 ${sp}% + 抽样 ${sa}%）`
}

/** Excel 表尾三行：合计 / 本期发生额 / 检查比例（避免 #DIV/0!） */
export interface I5CoverageFooter {
  checkedDebitTotal: number
  checkedCreditTotal: number
  periodDebitTotal: number
  periodCreditTotal: number
  debitCoverageLabel: string
  creditCoverageLabel: string
  layeredCoverageLabel: string
}

export function buildI5CoverageFooter(
  summary: I5TargetedSummary,
  periodCreditTotal = 0,
): I5CoverageFooter {
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
export function suggestAbnormalFromFailedChecks(row: I5TargetedCheckRow): string {
  if (row.check3 === '×') return '分类不当'
  if (row.check4 === '×') return '跨期'
  if (row.check5 === '×') return '期限未重分类'
  if (row.check1 === '×' || row.check2 === '×') return '入账差异'
  return '是'
}

/** 用表内特定样本借方合计回写第二节「特定样本金额」 */
export function syncSpecificAmountFromRows(rows: I5TargetedCheckRow[]): number {
  const specific = rows.filter((r) => r.isSpecific || !!r.selectionReason)
  return Math.round(specific.reduce((s, r) => s + _num(r.debitAmount), 0) * 100) / 100
}

export interface I5SpecificAmountCheck {
  ok: boolean
  metaAmount: number
  tableAmount: number
  diff: number
  diffPct: number | null
  severity: 'ok' | 'warning'
  message: string
}

/** 第二节特定样本金额 vs 表内特定借方容差校验 */
export function checkI5SpecificAmountConsistency(
  metaSpecificAmount: number,
  tableSpecificDebit: number,
  opts?: { absTol?: number; pctTol?: number },
): I5SpecificAmountCheck {
  const meta = Math.round((_num(metaSpecificAmount)) * 100) / 100
  const table = Math.round((_num(tableSpecificDebit)) * 100) / 100
  const absTol = opts?.absTol ?? I5_4_SPECIFIC_ABS_TOL
  const pctTol = opts?.pctTol ?? I5_4_SPECIFIC_PCT_TOL
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
      severity: 'warning',
      message: `表内特定样本借方 ${table.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，第二节特定样本金额未填；可一键同步。`,
    }
  }
  if (Math.abs(diff) <= tol) {
    return { ok: true, metaAmount: meta, tableAmount: table, diff: 0, diffPct: 0, severity: 'ok', message: '' }
  }
  return {
    ok: false,
    metaAmount: meta,
    tableAmount: table,
    diff,
    diffPct,
    severity: 'warning',
    message: `第二节特定样本金额与表内特定借方差 ${diff.toLocaleString('zh-CN', { minimumFractionDigits: 2 })}，建议同步或复核。`,
  }
}

export interface I52ProjectRef {
  projectName: string
  category: string
  increase: number
}

/** 从 I5-2 明细提取项目名目录（抽凭挂接 / 下拉） */
export function extractI52ProjectCatalog(raw: unknown): I52ProjectRef[] {
  const rows = _parseI52Rows(raw)
  const out: I52ProjectRef[] = []
  const seen = new Set<string>()
  for (const r of rows) {
    const name = _str(r?.projectName || r?.name).trim()
    if (!name || name === '合计' || seen.has(name)) continue
    seen.add(name)
    out.push({
      projectName: name,
      category: _str(r?.category || r?.assetType || r?.type),
      increase: _num(r?.increase ?? r?.currentIncrease ?? r?.costIncrease),
    })
  }
  return out
}

function _normText(s: string): string {
  return (s || '').replace(/\s+/g, '').toLowerCase()
}

/**
 * 用凭证摘要/科目名模糊匹配 I5-2 项目名。
 * 优先：精确 → 摘要包含项目名 → 项目名包含摘要片段。
 */
export function matchI52ProjectName(
  catalog: I52ProjectRef[],
  hints: { summary?: string; accountName?: string },
): string {
  if (!catalog.length) return ''
  const hay = _normText([hints.summary, hints.accountName].filter(Boolean).join(' '))
  if (!hay) return ''
  for (const p of catalog) {
    const n = _normText(p.projectName)
    if (n && n === hay) return p.projectName
  }
  for (const p of catalog) {
    const n = _normText(p.projectName)
    if (n && n.length >= 2 && hay.includes(n)) return p.projectName
  }
  for (const p of catalog) {
    const n = _normText(p.projectName)
    if (n.length >= 4 && n.includes(hay.slice(0, Math.min(8, hay.length)))) return p.projectName
  }
  return ''
}

/** 有样本但专项风险结论全空时提示（分类/期限/可回收性为核心认定） */
export function riskFocusIncomplete(risk: I5TargetedRiskFocus, sampleCount: number): boolean {
  if (sampleCount <= 0) return false
  return !risk.classificationConclusion && !risk.maturityConclusion && !risk.recoverabilityConclusion
}

function _parseI52Rows(raw: unknown): any[] {
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
 * 从 I5-2 明细推算本期发生额：
 * 优先 increase（本期增加=借方）/ decrease（本期减少=贷方）；
 * 无滚动字段时回退按 incurredDate 年份代理 originalAmount。
 */
export function extractI5PeriodMovement(raw: unknown, asOfYear?: number): I5PeriodMovement {
  const rows = _parseI52Rows(raw)
  let debitTotal = 0
  let creditTotal = 0
  let originalTotal = 0
  let usedRoll = false
  for (const r of rows) {
    if ((r?.projectName || r?.name) === '合计') continue
    const original = _num(r?.originalAmount)
    originalTotal += original
    const inc = _num(r?.increase ?? r?.currentIncrease ?? r?.costIncrease)
    const dec = _num(r?.decrease ?? r?.currentDecrease ?? r?.costDecrease)

    if (inc > 0 || dec > 0) {
      usedRoll = true
      debitTotal += inc
      creditTotal += dec
      continue
    }
    // 旧代理：按发生日年份
    const y = _yearOf(_str(r?.incurredDate || r?.occurDate || r?.date))
    if (asOfYear == null || y === asOfYear) {
      debitTotal += original
    }
  }
  return {
    debitTotal: Math.round(debitTotal * 100) / 100,
    creditTotal: Math.round(creditTotal * 100) / 100,
    originalTotal: Math.round(originalTotal * 100) / 100,
    source: usedRoll ? 'I5-2本期发生额' : 'I5-2',
  }
}

export function buildI5TargetedConclusionDraft(opts: {
  sampleCount: number
  coverageLabel: string
  creditCoverageLabel?: string
  anomalyCount: number
  failCheckCount: number
  testReasons?: string[]
  riskFocus?: I5TargetedRiskFocus
}): string {
  const reasonText = opts.testReasons?.length
    ? `测试原因：${opts.testReasons.join('、')}。`
    : ''
  const parts = [
    `经抽查其他非流动资产相关记账凭证 ${opts.sampleCount} 笔，借方检查覆盖率 ${opts.coverageLabel}。`,
  ]
  if (opts.creditCoverageLabel && opts.creditCoverageLabel !== 'N/A') {
    parts.push(`贷方（减少/转出）检查覆盖率 ${opts.creditCoverageLabel}。`)
  }
  if (reasonText) parts.push(reasonText)
  if (opts.failCheckCount > 0) {
    parts.push(`其中 ${opts.failCheckCount} 笔核对内容存在「×」，已在表内标注并需跟进。`)
  } else if (opts.anomalyCount > 0) {
    parts.push(`发现异常 ${opts.anomalyCount} 笔，详见「是否异常」及备注。`)
  } else {
    parts.push('所抽样本原始凭证齐全、账证相符、分类及期间归属未见重大异常。')
  }
  const rf = opts.riskFocus
  if (rf) {
    const riskBits = [
      rf.classificationConclusion && `分类正确性：${rf.classificationConclusion}`,
      rf.maturityConclusion && `期限适当性：${rf.maturityConclusion}`,
      rf.recoverabilityConclusion && `可回收性：${rf.recoverabilityConclusion}`,
    ].filter(Boolean)
    if (riskBits.length) parts.push(`专项风险关注—${riskBits.join('；')}。`)
  }
  parts.push('其他非流动资产在重大方面列报适当（请结合 I5-2 明细表分类、期限及减值迹象结论综合判断）。')
  return parts.join('')
}

/** 抽凭引擎 SampledVoucher → I5-4 行 */
export function mapSampledToI5TargetedRow(
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
  catalog?: I52ProjectRef[],
): I5TargetedCheckRow {
  const reason = _str(s.selectionReason)
  const isSpecific = !!(s.isHighValue || reason)
  const matched = catalog?.length
    ? matchI52ProjectName(catalog, {
        summary: _str(s.summary),
        accountName: _str(s.accountName),
      })
    : ''
  return emptyI5TargetedRow({
    voucherDate: _str(s.voucherDate),
    voucherNo: _str(s.voucherNo),
    businessDesc: _str(s.summary),
    counterpartAccount: _str(s.counterpartAccount),
    projectName: matched || _str(s.accountName),
    debitAmount: _num(s.debitAmount),
    creditAmount: _num(s.creditAmount),
    isSpecific,
    selectionReason: reason || (s.isHighValue ? '大额' : ''),
    isAbnormal: s.abnormal ? '是' : '',
    remark: _str(s.remark),
  })
}

export interface I5TargetedAdjDraft {
  voucherNo: string
  projectName: string
  debitAmount: number
  creditAmount: number
  failedChecks: string[]
  suggestedEntry: string
  suggestedNote: string
  /** 可推 I5-3 的草稿类型 */
  draftKind: 'expense_reclass' | 'cutoff' | 'impairment' | 'current_reclass' | 'doc_only'
  amount: number
}

export interface I5TargetedAdjDraftContext {
  detailRows?: any[]
  auditYear?: number
}

/** check5 失败且 I5-2 显示一年内到期 → 重分类草稿 */
export function isI5CurrentPortionForProject(
  projectName: string,
  detailRows: any[],
  auditYear?: number,
): boolean {
  const pn = _normText(projectName)
  if (!pn || !detailRows?.length) return false
  const candidates = extractI5CurrentPortionCandidates(detailRows, auditYear)
  return candidates.some((c) => {
    const cn = _normText(c.projectName)
    return cn === pn || (cn.length >= 2 && pn.includes(cn)) || (pn.length >= 2 && cn.includes(pn))
  })
}

/** 核对× → 调整建议草稿 */
export function buildI5TargetedAdjDrafts(
  rows: I5TargetedCheckRow[],
  ctx?: I5TargetedAdjDraftContext,
): I5TargetedAdjDraft[] {
  const labels = I5_4_TEST_CONTENT
  const detailRows = ctx?.detailRows ?? []
  const auditYear = ctx?.auditYear
  const out: I5TargetedAdjDraft[] = []
  for (const row of rows) {
    if (!hasFailedCheck(row)) continue
    const failedChecks: string[] = []
    const marks = [row.check1, row.check2, row.check3, row.check4, row.check5]
    marks.forEach((m, i) => {
      if (m === '×') failedChecks.push(`${i + 1}.${labels[i]}`)
    })
    const amt = row.debitAmount || row.creditAmount
    const classification = failedChecks.some((c) => c.startsWith('3.'))
    const cutoff = failedChecks.some((c) => c.startsWith('4.'))
    const termOrRecover = failedChecks.some((c) => c.startsWith('5.'))
    const resolvedProject = row.projectName
      || matchI52ProjectName(extractI52ProjectCatalog(detailRows), {
        summary: row.businessDesc,
        accountName: row.counterpartAccount,
      })
    let draftKind: I5TargetedAdjDraft['draftKind'] = 'doc_only'
    let suggestedEntry = `建议复核凭证 ${row.voucherNo || '—'}（${amt.toFixed(2)}）`
    if (classification) {
      draftKind = 'expense_reclass'
      suggestedEntry += '：分类科目不当，草拟费用化/冲减其他非流动资产（可推 I5-3）'
    } else if (cutoff) {
      draftKind = 'cutoff'
      suggestedEntry += '：可能跨期确认，草拟跨期调整分录（可推 I5-3）'
    } else if (termOrRecover) {
      if (isI5CurrentPortionForProject(resolvedProject, detailRows, auditYear)) {
        draftKind = 'current_reclass'
        suggestedEntry += '：期限临近到期，草拟一年内到期重分类 RJE（可推 I5-3）'
      } else {
        draftKind = 'impairment'
        suggestedEntry += '：可回收性/减值判断存疑，草拟减值调整（可推 I5-3）'
      }
    } else {
      suggestedEntry += '：补齐合同/协议等原始资料或更正账证不符后重测'
    }
    out.push({
      voucherNo: row.voucherNo,
      projectName: resolvedProject || row.projectName,
      debitAmount: row.debitAmount,
      creditAmount: row.creditAmount,
      failedChecks,
      suggestedEntry,
      suggestedNote: `I5-4 核对×：${failedChecks.join('；')}`,
      draftKind,
      amount: amt,
    })
  }
  return out
}

/** 可推送至 I5-3 的分录行（与 I5AdjustmentRow 字段对齐） */
export interface I54ToI53Line {
  description: string
  projectName: string
  category: '账项调整' | '报表调整'
  entryType: 'AJE' | 'RJE'
  reportItem: string
  accountCode: string
  accountName: string
  noteItem: string
  debitAmount: number
  creditAmount: number
  indexRef: string
  remark: string
}

/** I5-4 调整草稿 → I5-3 分录行 */
export function buildI53LinesFromTargetedDrafts(drafts: I5TargetedAdjDraft[]): I54ToI53Line[] {
  const lines: I54ToI53Line[] = []
  for (const d of drafts) {
    if (d.draftKind === 'doc_only' || !(d.amount > 0.005)) continue
    const projectName = d.projectName || d.voucherNo || '未命名项目'
    const idx = `I5-4/${d.voucherNo || '—'}`
    if (d.draftKind === 'expense_reclass') {
      const desc = `其他非流动资产费用化-${projectName}`
      lines.push(
        {
          description: desc,
          projectName,
          category: '账项调整',
          entryType: 'AJE',
          reportItem: '管理费用',
          accountCode: '6602',
          accountName: '管理费用',
          noteItem: '其他非流动资产',
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
          reportItem: '其他非流动资产',
          accountCode: '1911',
          accountName: '其他非流动资产',
          noteItem: '其他非流动资产',
          debitAmount: 0,
          creditAmount: d.amount,
          indexRef: idx,
          remark: '冲减其他非流动资产账面（I5-4 分类不当）',
        },
      )
    } else if (d.draftKind === 'cutoff') {
      const desc = `其他非流动资产跨期调整-${projectName}`
      lines.push(
        {
          description: desc,
          projectName,
          category: '账项调整',
          entryType: 'AJE',
          reportItem: '管理费用',
          accountCode: '6602',
          accountName: '管理费用',
          noteItem: '其他非流动资产',
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
          reportItem: '其他非流动资产',
          accountCode: '1911',
          accountName: '其他非流动资产',
          noteItem: '其他非流动资产',
          debitAmount: 0,
          creditAmount: d.amount,
          indexRef: idx,
          remark: '冲回跨期确认的其他非流动资产',
        },
      )
    } else if (d.draftKind === 'impairment') {
      const desc = `其他非流动资产减值-${projectName}`
      lines.push(
        {
          description: desc,
          projectName,
          category: '账项调整',
          entryType: 'AJE',
          reportItem: '资产减值损失',
          accountCode: '6701',
          accountName: '资产减值损失',
          noteItem: '其他非流动资产',
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
          reportItem: '其他非流动资产',
          accountCode: '1911',
          accountName: '其他非流动资产',
          noteItem: '其他非流动资产',
          debitAmount: 0,
          creditAmount: d.amount,
          indexRef: idx,
          remark: '计提/补提减值（I5-4 可回收性）',
        },
      )
    } else if (d.draftKind === 'current_reclass') {
      const desc = `一年内到期重分类-${projectName}`
      lines.push(
        {
          description: desc,
          projectName,
          category: '报表调整',
          entryType: 'RJE',
          reportItem: '一年内到期的非流动资产',
          accountCode: '1461',
          accountName: '一年内到期的非流动资产',
          noteItem: '其他非流动资产',
          debitAmount: d.amount,
          creditAmount: 0,
          indexRef: idx,
          remark: d.suggestedNote,
        },
        {
          description: desc,
          projectName,
          category: '报表调整',
          entryType: 'RJE',
          reportItem: '其他非流动资产',
          accountCode: '1911',
          accountName: '其他非流动资产',
          noteItem: '其他非流动资产',
          debitAmount: 0,
          creditAmount: d.amount,
          indexRef: idx,
          remark: '报表重分类转出（I5-4 期限）',
        },
      )
    }
  }
  return lines
}

/** 合并进既有 I5-3 行：按 description+accountCode 去重 */
export function mergeI53LinesSkippingExisting(
  existing: any[],
  incoming: I54ToI53Line[],
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
      rowId: `i54-i53-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`,
    })
    keys.add(key)
  }
  return { merged: [...(existing || []), ...toAdd], added: toAdd.length }
}
