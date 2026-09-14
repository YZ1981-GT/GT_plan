/**
 * useG4SppiFormulaEngine — G4 债权投资(SPPI组) 公式引擎
 *
 * 对齐 Excel《G4 债权投资.xlsx》G4-5~G4-8
 */

export function parseNum(v: unknown): number {
  if (v === null || v === undefined || v === '') return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ══════════════════════════════════════════════════════════
// G4-5 业务模式 — 对齐模板问卷（否定筛查题：全「否」→ AC）
// ══════════════════════════════════════════════════════════

/**
 * Excel《业务模式分析G4-5》问题映射：
 * q1  大额且频繁出售
 * q2  持有目的是交易性的
 * q2_1~2_3  交易性三项判定
 * q3  基于公允价值决策并管理
 * q4  未来预期大额且频繁出售
 * q5  未来预期交易性或基于公允价值管理
 */
export interface BusinessModelAnswers {
  q1: boolean | null
  q2: boolean | null
  q2_1: boolean | null
  q2_2: boolean | null
  q2_3: boolean | null
  q3: boolean | null
  q4: boolean | null
  q5: boolean | null
}

export type BusinessModelResult = 'AC' | 'FVOCI' | 'FVTPL' | 'INCOMPLETE'

/**
 * 业务模式决策 — 对齐 Excel《业务模式分析G4-5》A23 判定链，并按 CAS22 补强：
 * 1) 当前大额出售 + 非交易 + 非FV管理 → FVOCI
 * 2) 当前大额出售 + (交易性 或 FV管理) → FVTPL（其他）
 * 3) 未来大额出售 + 非未来交易/FV → FVOCI
 * 4) 未来交易性/FV → FVTPL
 * 5) 仅基于公允价值管理（无出售信号）→ FVTPL（CAS：其他业务模式；强于模板落到 AC）
 * 6) 否则 → AC
 * 题2 有效值 = q2 ∨ q2_1 ∨ q2_2 ∨ q2_3
 */
export function determineBusinessModel(answers: BusinessModelAnswers): BusinessModelResult {
  const required = [
    answers.q1,
    answers.q2_1,
    answers.q2_2,
    answers.q2_3,
    answers.q3,
    answers.q4,
    answers.q5,
  ]
  if (required.some((v) => v === null || v === undefined)) return 'INCOMPLETE'

  const tradingNow =
    answers.q2 === true ||
    answers.q2_1 === true ||
    answers.q2_2 === true ||
    answers.q2_3 === true
  const q1 = answers.q1 === true
  const q3 = answers.q3 === true
  const q4 = answers.q4 === true
  const q5 = answers.q5 === true

  // Excel A23 链路
  if (q1 && !tradingNow && !q3) return 'FVOCI'
  if ((q1 && tradingNow) || (q1 && q3)) return 'FVTPL'
  if (q4 && !q5) return 'FVOCI'
  if (q5) return 'FVTPL'
  // CAS 补强：单独公允价值管理（模板在无出售时会落到 AC）
  if (q3) return 'FVTPL'
  if (tradingNow) return 'FVTPL'
  return 'AC'
}

/** 回答一致性提示（不阻断结论，供编制人核对） */
export function detectBusinessModelInconsistencies(
  answers: BusinessModelAnswers,
): string[] {
  const hints: string[] = []
  const tradingKids =
    answers.q2_1 === true || answers.q2_2 === true || answers.q2_3 === true
  const tradingKidsNo =
    answers.q2_1 === false && answers.q2_2 === false && answers.q2_3 === false

  if (answers.q2 === true && tradingKidsNo) {
    hints.push('题2勾选「是」，但 2.1～2.3 均为「否」——请核对或改填子题。')
  }
  if (answers.q2 === false && tradingKids) {
    hints.push('题2勾选「否」，但 2.1～2.3 存在「是」——系统将按子题汇总为交易性。')
  }
  if (answers.q3 === true && answers.q5 === false && answers.q4 === true) {
    hints.push(
      '当前基于公允价值管理（题3=是），同时预期未来大额频繁出售（题4=是）且题5=否：按模板结论倾向「收取+出售」(FVOCI)；请确认「公允价值管理」是历史还是持续意图。',
    )
  }
  if (answers.q1 === true && answers.q4 === false) {
    hints.push('历史上存在大额频繁出售（题1=是），但预期未来不再（题4=否）——请在说明中解释预期变化原因。')
  }
  if (answers.q1 === true && answers.q5 === true && answers.q2 !== true && answers.q3 !== true) {
    hints.push(
      '题1=是且题5=是：模板结论链优先按「当前大额出售→收取+出售」(FVOCI)，题5不再改写结论——请确认是否应同时认定交易性（勾选2.1～2.3或题3）。',
    )
  }
  if (answers.q3 === true && answers.q1 === false && answers.q4 === false && answers.q5 === false) {
    hints.push('仅题3「基于公允价值管理」为是：按 CAS22 归入其他业务模式(FVTPL)，即使模板字面可能落 AC。')
  }
  return hints
}

/** 兼容旧版 5 问问卷（正问句）：映射到新语义后再判定 */
export function determineBusinessModelLegacy(answers: {
  q1: boolean | null
  q2: boolean | null
  q3: boolean | null
  q4: boolean | null
  q5: boolean | null
}): BusinessModelResult {
  // 旧：q1=收取现金流? q2=存在出售? q3=频繁重大出售? q4=收取+出售? q5=公允价值?
  const { q1, q2, q3, q4, q5 } = answers
  if ([q1, q2, q3, q4, q5].some((v) => v === null || v === undefined)) return 'INCOMPLETE'
  if (q5) return 'FVTPL'
  if (q3) return 'FVOCI' // 旧逻辑把频繁出售当 FVTPL，模板口径应为 FVOCI；此处按模板修正
  if (q4) return 'FVOCI'
  if (q1 && !q2) return 'AC'
  if (!q1 && !q2 && !q3 && !q4 && !q5) return 'AC' // 全否 → AC（模板）
  return 'FVTPL'
}

// ══════════════════════════════════════════════════════════
// G4-6 SPPI
// ══════════════════════════════════════════════════════════

export type SPPIResult = 'PASS' | 'FAIL' | 'FURTHER_ANALYSIS'

/**
 * SPPI：权益转换/杠杆 → FAIL；仅回售/展期 → FURTHER_ANALYSIS；其余 → PASS
 * （对应模板「直接判断通过/不通过/进一步分析」）
 */
export function determineSPPIConclusion(
  hasEarlyRedemption: boolean,
  hasExtension: boolean,
  hasEquityConversion: boolean,
  hasLeverage: boolean,
): SPPIResult {
  if (hasEquityConversion || hasLeverage) return 'FAIL'
  if (hasEarlyRedemption || hasExtension) return 'FURTHER_ANALYSIS'
  return 'PASS'
}

/**
 * ABS 级次启发式：次级默认不通过；优先级默认通过（用户可覆盖）。
 * 中间级 / 未填 → null（不自动改写）。
 */
export function suggestAbsSppiByTranche(tranche: string | null | undefined): SPPIResult | null {
  const t = (tranche || '').trim()
  if (!t) return null
  if (/次级|劣后|equity|junior/i.test(t)) return 'FAIL'
  if (/优先|senior|优先级/i.test(t)) return 'PASS'
  return null
}

/**
 * 理财第一步（保本保收益）启发式：
 * - 不保本 → FAIL
 * - 保本且仅固定收益（无浮动）→ PASS
 * - 保本且有浮动 → null（依赖第二步「是否不现实」）
 */
export function suggestFinancialStep1Conclusion(input: {
  guaranteesPrincipal: boolean
  hasFixedReturn: boolean
  hasFloatingReturn: boolean
}): 'PASS' | 'FAIL' | null {
  if (!input.guaranteesPrincipal) return 'FAIL'
  if (input.hasFloatingReturn) return null
  if (input.hasFixedReturn) return 'PASS'
  return null
}

/**
 * 理财第二步：浮动收益「不现实」→ PASS；明确「现实」→ FAIL；未判断 → null
 */
export function suggestFinancialStep2Conclusion(isUnrealistic: boolean | null | undefined): 'PASS' | 'FAIL' | null {
  if (isUnrealistic === true) return 'PASS'
  if (isUnrealistic === false) return 'FAIL'
  return null
}

// ─── 修正货币时间价值 — 基准测试 ───────────────────────────────────────────

export interface BenchmarkPeriodRow {
  period: number
  contractCf: number
  benchmarkCf: number
}

/** 单期差异 = 合同现金流 − 基准现金流 */
export function calcBenchmarkPeriodDiff(contractCf: number, benchmarkCf: number): number {
  return Math.round((parseNum(contractCf) - parseNum(benchmarkCf)) * 100) / 100
}

/** 未折现累计绝对差异 / 基准合计绝对值 → 差异率（%） */
export function calcBenchmarkDiffRate(rows: BenchmarkPeriodRow[]): number {
  if (!rows?.length) return 0
  let absDiff = 0
  let absBench = 0
  for (const r of rows) {
    absDiff += Math.abs(calcBenchmarkPeriodDiff(r.contractCf, r.benchmarkCf))
    absBench += Math.abs(parseNum(r.benchmarkCf))
  }
  if (absBench < 1e-9) return absDiff > 0 ? 100 : 0
  return Math.round((absDiff / absBench) * 10000) / 100
}

/**
 * 差异是否重大。默认阈值 10%（实务常用定性门槛，可在底稿中调整）。
 * 不重大 → 仍可通过 SPPI；重大 → 通不过。
 */
export function isBenchmarkDiffMaterial(diffRatePct: number, thresholdPct = 10): boolean {
  return parseNum(diffRatePct) > parseNum(thresholdPct)
}

export function determineBenchmarkSppiConclusion(
  diffRatePct: number,
  thresholdPct = 10,
): SPPIResult {
  return isBenchmarkDiffMaterial(diffRatePct, thresholdPct) ? 'FAIL' : 'PASS'
}

// ══════════════════════════════════════════════════════════
// G4-7 / G4-8 盘点公式
// ══════════════════════════════════════════════════════════

export function calcInventoryTotal(faceValue: number, quantity: number): number {
  return Math.round(parseNum(faceValue) * parseNum(quantity) * 100) / 100
}

/**
 * 报表日实存数量（倒轧）：
 *   报表日 = 盘点日 − 增加 + 减少
 * 增减口径为「资产负债表日 → 盘点日」（盘点通常在期后）。
 *
 * 兼容旧签名 calcReportDateQuantity(count, netChange)：
 *   若只传 2 个参数，视为「盘点日 − 净增加」（净增加=增加−减少）。
 */
export function calcReportDateQuantity(
  countDateQty: number,
  increaseOrNetChange: number,
  decrease?: number,
): number {
  if (decrease === undefined) {
    // 旧口径兼容：report = count − netChange（netChange = 资产负责表日→盘点日净增加）
    return parseNum(countDateQty) - parseNum(increaseOrNetChange)
  }
  return parseNum(countDateQty) - parseNum(increaseOrNetChange) + parseNum(decrease)
}

export function calcReportDateTotal(reportFaceValue: number, reportQuantity: number): number {
  return Math.round(parseNum(reportFaceValue) * parseNum(reportQuantity) * 100) / 100
}

export function calcReconciliationVariance(reportDateTotal: number, bookTotal: number): number {
  return Math.round((parseNum(reportDateTotal) - parseNum(bookTotal)) * 100) / 100
}

/** 数量差异 = 报表日推算数量 − 账面结存数量 */
export function calcQuantityVariance(reportQuantity: number, bookQuantity: number): number {
  return parseNum(reportQuantity) - parseNum(bookQuantity)
}

export function isReconciliationBalanced(reportDateTotal: number, bookTotal: number): boolean {
  return Math.abs(parseNum(reportDateTotal) - parseNum(bookTotal)) < 0.01
}

/** 数量与面值总额均勾稽时才视为平衡 */
export function isReconciliationFullyBalanced(
  reportQuantity: number,
  bookQuantity: number,
  reportTotal: number,
  bookTotal: number,
): boolean {
  return (
    Math.abs(parseNum(reportQuantity) - parseNum(bookQuantity)) < 0.01 &&
    Math.abs(parseNum(reportTotal) - parseNum(bookTotal)) < 0.01
  )
}

export function calcSumColumn(values: number[]): number {
  if (!values || values.length === 0) return 0
  return values.reduce((sum, v) => sum + parseNum(v), 0)
}

export const FINAL_CLASSIFICATION_LABELS: Record<string, string> = {
  AC: '以摊余成本计量的金融资产',
  FVOCI: '以公允价值计量且其变动计入其他综合收益的金融资产',
  FVTPL: '以公允价值计量且其变动计入当期损益的金融资产',
}

export function determineFinalClassification(
  businessModel: 'AC' | 'FVOCI' | 'FVTPL',
  sppiResult: SPPIResult,
): string {
  if (sppiResult === 'FAIL') return FINAL_CLASSIFICATION_LABELS.FVTPL
  if (sppiResult === 'PASS' && businessModel === 'AC') return FINAL_CLASSIFICATION_LABELS.AC
  if (sppiResult === 'PASS' && businessModel === 'FVOCI') return FINAL_CLASSIFICATION_LABELS.FVOCI
  return FINAL_CLASSIFICATION_LABELS.FVTPL
}
