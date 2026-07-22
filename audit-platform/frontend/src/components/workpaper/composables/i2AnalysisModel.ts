/**
 * i2AnalysisModel — I2-5 实质性分析纯模型
 * 对齐致同「实质性分析 I2-5」Excel：
 *   （一）研发费用构成分析表
 *   （二）费用指标同行业比较
 *   （三）人均费用同期对比
 *   （四）人均费用同行业对比
 *   三、结构化审计说明（5类异常原因）
 * 另保留（五）开发支出项目波动分析（Spec Req 4 兼容）
 */

import { calcChangeRate } from './useI2FormulaEngine'

/** 审计目标（对齐 Excel） */
export const I2_ANALYSIS_OBJECTIVES = [
  '确认利润表中记录的研发费用已发生，与被审计单位有关，且已记录于恰当之期间；研发费用相关金额及其披露已恰当记录，相关披露已得到恰当计量和描述。',
] as const

/** 构成分析默认费用项目（Excel 红色示例行） */
export const I2_ANALYSIS_DEFAULT_ITEMS = [
  '人工费',
  '材料费',
  '制造费用分摊',
  '无形资产摊销',
] as const

/** 结构化审计说明题干（Excel 三、审计说明） */
export const I2_ANALYSIS_NOTE_PROMPTS = [
  { key: 'compositionChange', label: '费用各项目近两年比重变动较大的原因' },
  { key: 'yoyAnomaly', label: '与上年同期数据相比，费用指标异常的原因' },
  { key: 'peerAnomaly', label: '与同行业数据相比，费用指标异常的原因' },
  { key: 'budgetAnomaly', label: '与预算金额及其他非财务数据相比，费用指标异常的原因' },
  { key: 'perCapitaAnomaly', label: '人均费用指标异常的原因' },
] as const

export type I2AnalysisNoteKey = (typeof I2_ANALYSIS_NOTE_PROMPTS)[number]['key']

/** 同比/结构比变动阈值（默认 30%） */
export const I2_ANALYSIS_GROWTH_THRESHOLD = 0.3
/** 占收入比变动阈值（绝对值，默认 2 个百分点 = 0.02） */
export const I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD = 0.02

/** I6-2 明细类别 → I2-5 构成项目别名映射（用于按关键字归并类别） */
export const I2_ANALYSIS_I6_CATEGORY_ALIASES: Record<string, string[]> = {
  人工费: ['职工薪酬', '人工', '工资', '人员'],
  材料费: ['材料', '原材料', '领料'],
  制造费用分摊: ['折旧', '制造费用'],
  无形资产摊销: ['摊销'],
}

// ─── （一）构成分析 ───────────────────────────────────────────────────────────

export interface I2CompositionRow {
  rowId: string
  itemName: string
  currentAmount: number
  priorAmount: number
  /** 预算金额（可选，>0 时纳入预算差异分析） */
  budgetAmount: number
  /** 变动分析（定性） */
  varianceAnalysis: string
  /** 公式：结构比 = 金额 / 合计 */
  currentStructure: number | null
  priorStructure: number | null
  /** 公式：占主营收入比 */
  currentRevRatio: number | null
  priorRevRatio: number | null
  /** 公式：增长比例 */
  growthRate: number | null
  /** 公式：占收入比变动 = 本期占比 − 上期占比 */
  revRatioChange: number | null
  /** 公式：预算差异 = 本期金额 − 预算金额 */
  budgetVariance: number | null
  /** 公式：预算差异率 = 预算差异 / 预算金额（预算≤0 时为 null） */
  budgetVarianceRate: number | null
  /** 是否超阈值 */
  isAnomaly: boolean
}

export interface I2CompositionMeta {
  /** 主营业务收入-本期 */
  revenueCurrent: number
  /** 主营业务收入-上年同期 */
  revenuePrior: number
  /** 同比/结构比变动阈值（可配置，默认 0.3） */
  growthThreshold: number
  /** 占收入比变动阈值（可配置，默认 0.02） */
  revRatioDeltaThreshold: number
}

// ─── （二）同行业费用指标 ─────────────────────────────────────────────────────

export interface I2PeerIndicatorRow {
  rowId: string
  indicator: string
  current: number | null
  peerA: number | null
  peerB: number | null
  peerC: number | null
  analysis: string
}

// ─── （三）人均同期 ───────────────────────────────────────────────────────────

export interface I2PerCapitaYoY {
  /** 研发人员薪酬总额 */
  staffCostCurrent: number
  staffCostPrior: number
  /** 研发人员人数 */
  headcountCurrent: number
  headcountPrior: number
  /** 研发经费总额（通常=构成合计） */
  rdExpenseCurrent: number
  rdExpensePrior: number
  /** 材料费总额 */
  materialCurrent: number
  materialPrior: number
  analysis: string
  /** 公式列 */
  avgSalaryCurrent: number | null
  avgSalaryPrior: number | null
  avgRdCurrent: number | null
  avgRdPrior: number | null
  avgMaterialCurrent: number | null
  avgMaterialPrior: number | null
  avgSalaryGrowth: number | null
  avgRdGrowth: number | null
  avgMaterialGrowth: number | null
}

// ─── （四）人均同行业 ─────────────────────────────────────────────────────────

export interface I2PerCapitaPeerRow {
  rowId: string
  companyName: string
  headcount: number
  avgSalary: number
  avgRdExpense: number
  avgMaterial: number
  analysis: string
  isSelf: boolean
}

// ─── 结构化说明 ───────────────────────────────────────────────────────────────

export interface I2AnalysisStructuredNotes {
  compositionChange: string
  yoyAnomaly: string
  peerAnomaly: string
  budgetAnomaly: string
  perCapitaAnomaly: string
}

export interface I2AnalysisBundle {
  compositionRows: I2CompositionRow[]
  compositionMeta: I2CompositionMeta
  peerIndicators: I2PeerIndicatorRow[]
  perCapitaYoY: I2PerCapitaYoY
  perCapitaPeers: I2PerCapitaPeerRow[]
  structuredNotes: I2AnalysisStructuredNotes
  /** Spec Req4 兼容：开发支出项目波动行（旧 I2-5-rows） */
  projectFluctuationRows?: any[]
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

function _id(prefix: string): string {
  return `${prefix}-${Date.now()}-${Math.random().toString(36).slice(2, 7)}`
}

/** 安全比率；分母≤0 返回 null（避免 #DIV/0!） */
export function safeRatio(numerator: number, denominator: number): number | null {
  if (!Number.isFinite(numerator) || !Number.isFinite(denominator)) return null
  if (Math.abs(denominator) < 1e-9) return null
  return numerator / denominator
}

export function recomputeCompositionRow(
  row: I2CompositionRow,
  totalCurrent: number,
  totalPrior: number,
  revenueCurrent: number,
  revenuePrior: number,
  growthThreshold = I2_ANALYSIS_GROWTH_THRESHOLD,
  revDeltaThreshold = I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
): I2CompositionRow {
  const currentAmount = _num(row.currentAmount)
  const priorAmount = _num(row.priorAmount)
  const budgetAmount = _num(row.budgetAmount)
  const currentStructure = safeRatio(currentAmount, totalCurrent)
  const priorStructure = safeRatio(priorAmount, totalPrior)
  const currentRevRatio = safeRatio(currentAmount, revenueCurrent)
  const priorRevRatio = safeRatio(priorAmount, revenuePrior)
  const growthRate = calcChangeRate(currentAmount, priorAmount)
  const revRatioChange =
    currentRevRatio != null && priorRevRatio != null
      ? currentRevRatio - priorRevRatio
      : null
  const budgetVariance = budgetAmount > 0 ? currentAmount - budgetAmount : null
  const budgetVarianceRate = budgetAmount > 0 ? safeRatio(budgetVariance ?? 0, budgetAmount) : null

  const isAnomaly =
    (growthRate != null && Math.abs(growthRate) > growthThreshold)
    || (revRatioChange != null && Math.abs(revRatioChange) > revDeltaThreshold)
    || (currentStructure != null && priorStructure != null
      && Math.abs(currentStructure - priorStructure) > growthThreshold)
    || (budgetVarianceRate != null && Math.abs(budgetVarianceRate) > growthThreshold)

  return {
    ...row,
    currentAmount,
    priorAmount,
    budgetAmount,
    currentStructure,
    priorStructure,
    currentRevRatio,
    priorRevRatio,
    growthRate,
    revRatioChange,
    budgetVariance,
    budgetVarianceRate,
    isAnomaly,
  }
}

export function emptyCompositionRow(partial?: Partial<I2CompositionRow>): I2CompositionRow {
  return recomputeCompositionRow({
    rowId: partial?.rowId || _id('i25c'),
    itemName: '',
    currentAmount: 0,
    priorAmount: 0,
    budgetAmount: 0,
    varianceAnalysis: '',
    currentStructure: null,
    priorStructure: null,
    currentRevRatio: null,
    priorRevRatio: null,
    growthRate: null,
    revRatioChange: null,
    budgetVariance: null,
    budgetVarianceRate: null,
    isAnomaly: false,
    ...partial,
  }, 0, 0, 0, 0)
}

export function defaultCompositionRows(): I2CompositionRow[] {
  return I2_ANALYSIS_DEFAULT_ITEMS.map((name) => emptyCompositionRow({ itemName: name }))
}

export function recomputeAllComposition(
  rows: I2CompositionRow[],
  meta: I2CompositionMeta,
): I2CompositionRow[] {
  const totalCurrent = rows.reduce((s, r) => s + _num(r.currentAmount), 0)
  const totalPrior = rows.reduce((s, r) => s + _num(r.priorAmount), 0)
  const growthThreshold = meta.growthThreshold ?? I2_ANALYSIS_GROWTH_THRESHOLD
  const revDeltaThreshold = meta.revRatioDeltaThreshold ?? I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD
  return rows.map((r) =>
    recomputeCompositionRow(
      r,
      totalCurrent,
      totalPrior,
      meta.revenueCurrent,
      meta.revenuePrior,
      growthThreshold,
      revDeltaThreshold,
    ),
  )
}

export function compositionTotals(rows: I2CompositionRow[], meta: I2CompositionMeta) {
  const totalCurrent = rows.reduce((s, r) => s + _num(r.currentAmount), 0)
  const totalPrior = rows.reduce((s, r) => s + _num(r.priorAmount), 0)
  const totalBudget = rows.reduce((s, r) => s + _num(r.budgetAmount), 0)
  const growthRate = calcChangeRate(totalCurrent, totalPrior)
  const currentRevRatio = safeRatio(totalCurrent, meta.revenueCurrent)
  const priorRevRatio = safeRatio(totalPrior, meta.revenuePrior)
  const revRatioChange =
    currentRevRatio != null && priorRevRatio != null
      ? currentRevRatio - priorRevRatio
      : null
  const budgetVariance = totalBudget > 0 ? totalCurrent - totalBudget : null
  const budgetVarianceRate = totalBudget > 0 ? safeRatio(budgetVariance ?? 0, totalBudget) : null
  return {
    totalCurrent,
    totalPrior,
    totalBudget,
    growthRate,
    currentRevRatio,
    priorRevRatio,
    revRatioChange,
    budgetVariance,
    budgetVarianceRate,
    /** 研发费用占主营业务收入比（本期） */
    rdToRevenueCurrent: currentRevRatio,
    rdToRevenuePrior: priorRevRatio,
  }
}

export function emptyPeerIndicator(partial?: Partial<I2PeerIndicatorRow>): I2PeerIndicatorRow {
  return {
    rowId: partial?.rowId || _id('i25p'),
    indicator: '研发费用占主营业务收入比率',
    current: null,
    peerA: null,
    peerB: null,
    peerC: null,
    analysis: '',
    ...partial,
  }
}

export function emptyPerCapitaYoY(partial?: Partial<I2PerCapitaYoY>): I2PerCapitaYoY {
  const base: I2PerCapitaYoY = {
    staffCostCurrent: 0,
    staffCostPrior: 0,
    headcountCurrent: 0,
    headcountPrior: 0,
    rdExpenseCurrent: 0,
    rdExpensePrior: 0,
    materialCurrent: 0,
    materialPrior: 0,
    analysis: '',
    avgSalaryCurrent: null,
    avgSalaryPrior: null,
    avgRdCurrent: null,
    avgRdPrior: null,
    avgMaterialCurrent: null,
    avgMaterialPrior: null,
    avgSalaryGrowth: null,
    avgRdGrowth: null,
    avgMaterialGrowth: null,
    ...partial,
  }
  return recomputePerCapitaYoY(base)
}

export function recomputePerCapitaYoY(data: I2PerCapitaYoY): I2PerCapitaYoY {
  const avgSalaryCurrent = safeRatio(data.staffCostCurrent, data.headcountCurrent)
  const avgSalaryPrior = safeRatio(data.staffCostPrior, data.headcountPrior)
  const avgRdCurrent = safeRatio(data.rdExpenseCurrent, data.headcountCurrent)
  const avgRdPrior = safeRatio(data.rdExpensePrior, data.headcountPrior)
  const avgMaterialCurrent = safeRatio(data.materialCurrent, data.headcountCurrent)
  const avgMaterialPrior = safeRatio(data.materialPrior, data.headcountPrior)
  return {
    ...data,
    staffCostCurrent: _num(data.staffCostCurrent),
    staffCostPrior: _num(data.staffCostPrior),
    headcountCurrent: _num(data.headcountCurrent),
    headcountPrior: _num(data.headcountPrior),
    rdExpenseCurrent: _num(data.rdExpenseCurrent),
    rdExpensePrior: _num(data.rdExpensePrior),
    materialCurrent: _num(data.materialCurrent),
    materialPrior: _num(data.materialPrior),
    avgSalaryCurrent,
    avgSalaryPrior,
    avgRdCurrent,
    avgRdPrior,
    avgMaterialCurrent,
    avgMaterialPrior,
    avgSalaryGrowth: avgSalaryCurrent != null && avgSalaryPrior != null
      ? calcChangeRate(avgSalaryCurrent, avgSalaryPrior)
      : null,
    avgRdGrowth: avgRdCurrent != null && avgRdPrior != null
      ? calcChangeRate(avgRdCurrent, avgRdPrior)
      : null,
    avgMaterialGrowth: avgMaterialCurrent != null && avgMaterialPrior != null
      ? calcChangeRate(avgMaterialCurrent, avgMaterialPrior)
      : null,
  }
}

export function defaultPerCapitaPeers(): I2PerCapitaPeerRow[] {
  return [
    emptyPerCapitaPeer({ companyName: '本公司', isSelf: true }),
    emptyPerCapitaPeer({ companyName: '可比公司1', isSelf: false }),
    emptyPerCapitaPeer({ companyName: '可比公司2', isSelf: false }),
    emptyPerCapitaPeer({ companyName: '可比公司3', isSelf: false }),
  ]
}

export function emptyPerCapitaPeer(partial?: Partial<I2PerCapitaPeerRow>): I2PerCapitaPeerRow {
  return {
    rowId: partial?.rowId || _id('i25pc'),
    companyName: '',
    headcount: 0,
    avgSalary: 0,
    avgRdExpense: 0,
    avgMaterial: 0,
    analysis: '',
    isSelf: false,
    ...partial,
  }
}

export function emptyStructuredNotes(partial?: Partial<I2AnalysisStructuredNotes>): I2AnalysisStructuredNotes {
  return {
    compositionChange: '',
    yoyAnomaly: '',
    peerAnomaly: '',
    budgetAnomaly: '',
    perCapitaAnomaly: '',
    ...partial,
  }
}

export function createDefaultCompositionMeta(): I2CompositionMeta {
  return {
    revenueCurrent: 0,
    revenuePrior: 0,
    growthThreshold: I2_ANALYSIS_GROWTH_THRESHOLD,
    revRatioDeltaThreshold: I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
  }
}

export function createDefaultBundle(): I2AnalysisBundle {
  return {
    compositionRows: defaultCompositionRows(),
    compositionMeta: createDefaultCompositionMeta(),
    peerIndicators: [emptyPeerIndicator()],
    perCapitaYoY: emptyPerCapitaYoY(),
    perCapitaPeers: defaultPerCapitaPeers(),
    structuredNotes: emptyStructuredNotes(),
  }
}

/** 从构成合计同步同行指标本期值、人均研发经费 */
export function syncDerivedFromComposition(bundle: I2AnalysisBundle): I2AnalysisBundle {
  const totals = compositionTotals(bundle.compositionRows, bundle.compositionMeta)
  const peerIndicators = bundle.peerIndicators.map((p, i) => {
    if (i === 0 || p.indicator.includes('占主营')) {
      return { ...p, current: totals.rdToRevenueCurrent }
    }
    return p
  })

  const labor = bundle.compositionRows.find((r) => r.itemName.includes('人工'))
  const material = bundle.compositionRows.find((r) => r.itemName.includes('材料'))
  let perCapitaYoY = recomputePerCapitaYoY({
    ...bundle.perCapitaYoY,
    rdExpenseCurrent: totals.totalCurrent,
    rdExpensePrior: totals.totalPrior,
    staffCostCurrent: labor ? labor.currentAmount : bundle.perCapitaYoY.staffCostCurrent,
    staffCostPrior: labor ? labor.priorAmount : bundle.perCapitaYoY.staffCostPrior,
    materialCurrent: material ? material.currentAmount : bundle.perCapitaYoY.materialCurrent,
    materialPrior: material ? material.priorAmount : bundle.perCapitaYoY.materialPrior,
  })

  // 同步「本公司」人均行
  const perCapitaPeers = bundle.perCapitaPeers.map((r) => {
    if (!r.isSelf && r.companyName !== '本公司') return r
    return {
      ...r,
      companyName: r.companyName || '本公司',
      isSelf: true,
      headcount: perCapitaYoY.headcountCurrent || r.headcount,
      avgSalary: perCapitaYoY.avgSalaryCurrent ?? r.avgSalary,
      avgRdExpense: perCapitaYoY.avgRdCurrent ?? r.avgRdExpense,
      avgMaterial: perCapitaYoY.avgMaterialCurrent ?? r.avgMaterial,
    }
  })

  return {
    ...bundle,
    compositionRows: recomputeAllComposition(bundle.compositionRows, bundle.compositionMeta),
    peerIndicators,
    perCapitaYoY,
    perCapitaPeers,
  }
}

export function normalizeBundle(raw: any): I2AnalysisBundle {
  if (!raw || typeof raw !== 'object') return createDefaultBundle()

  // 旧版仅为 AnalysisRow[] 数组
  if (Array.isArray(raw)) {
    const bundle = createDefaultBundle()
    bundle.projectFluctuationRows = raw
    return bundle
  }

  const meta: I2CompositionMeta = {
    revenueCurrent: _num(raw.compositionMeta?.revenueCurrent),
    revenuePrior: _num(raw.compositionMeta?.revenuePrior),
    growthThreshold: raw.compositionMeta?.growthThreshold != null
      ? _num(raw.compositionMeta.growthThreshold)
      : I2_ANALYSIS_GROWTH_THRESHOLD,
    revRatioDeltaThreshold: raw.compositionMeta?.revRatioDeltaThreshold != null
      ? _num(raw.compositionMeta.revRatioDeltaThreshold)
      : I2_ANALYSIS_REV_RATIO_DELTA_THRESHOLD,
  }

  let compositionRows: I2CompositionRow[]
  if (Array.isArray(raw.compositionRows) && raw.compositionRows.length) {
    compositionRows = raw.compositionRows.map((r: any) => emptyCompositionRow({
      rowId: r.rowId,
      itemName: String(r.itemName ?? ''),
      currentAmount: _num(r.currentAmount),
      priorAmount: _num(r.priorAmount),
      budgetAmount: _num(r.budgetAmount),
      varianceAnalysis: String(r.varianceAnalysis ?? ''),
    }))
  } else {
    compositionRows = defaultCompositionRows()
  }

  const peerIndicators = Array.isArray(raw.peerIndicators) && raw.peerIndicators.length
    ? raw.peerIndicators.map((p: any) => emptyPeerIndicator({
      rowId: p.rowId,
      indicator: String(p.indicator ?? '研发费用占主营业务收入比率'),
      current: p.current == null ? null : _num(p.current),
      peerA: p.peerA == null ? null : _num(p.peerA),
      peerB: p.peerB == null ? null : _num(p.peerB),
      peerC: p.peerC == null ? null : _num(p.peerC),
      analysis: String(p.analysis ?? ''),
    }))
    : [emptyPeerIndicator()]

  const perCapitaYoY = emptyPerCapitaYoY({
    ...(raw.perCapitaYoY || {}),
  })

  const perCapitaPeers = Array.isArray(raw.perCapitaPeers) && raw.perCapitaPeers.length
    ? raw.perCapitaPeers.map((p: any) => emptyPerCapitaPeer({
      rowId: p.rowId,
      companyName: String(p.companyName ?? ''),
      headcount: _num(p.headcount),
      avgSalary: _num(p.avgSalary),
      avgRdExpense: _num(p.avgRdExpense),
      avgMaterial: _num(p.avgMaterial),
      analysis: String(p.analysis ?? ''),
      isSelf: Boolean(p.isSelf) || p.companyName === '本公司',
    }))
    : defaultPerCapitaPeers()

  const structuredNotes = emptyStructuredNotes(raw.structuredNotes || {})

  return syncDerivedFromComposition({
    compositionRows,
    compositionMeta: meta,
    peerIndicators,
    perCapitaYoY,
    perCapitaPeers,
    structuredNotes,
    projectFluctuationRows: Array.isArray(raw.projectFluctuationRows)
      ? raw.projectFluctuationRows
      : undefined,
  })
}

export function summarizeAnalysisAnomalies(bundle: I2AnalysisBundle): {
  compositionAnomalyCount: number
  missingRevenue: boolean
  missingHeadcount: boolean
  peerGapCount: number
} {
  const compositionAnomalyCount = bundle.compositionRows.filter((r) => r.isAnomaly).length
  const missingRevenue = bundle.compositionMeta.revenueCurrent <= 0
  const missingHeadcount = bundle.perCapitaYoY.headcountCurrent <= 0
  const self = bundle.perCapitaPeers.find((r) => r.isSelf)
  let peerGapCount = 0
  if (self && self.avgRdExpense > 0) {
    for (const p of bundle.perCapitaPeers) {
      if (p.isSelf || p.avgRdExpense <= 0) continue
      const gap = Math.abs(p.avgRdExpense - self.avgRdExpense) / self.avgRdExpense
      if (gap > I2_ANALYSIS_GROWTH_THRESHOLD) peerGapCount++
    }
  }
  return { compositionAnomalyCount, missingRevenue, missingHeadcount, peerGapCount }
}

export function buildAnalysisConclusionDraft(bundle: I2AnalysisBundle): string {
  const totals = compositionTotals(bundle.compositionRows, bundle.compositionMeta)
  const anom = summarizeAnalysisAnomalies(bundle)
  const parts = [
    `经对研发费用执行实质性分析：本期研发费用合计 ${fmtMoney(totals.totalCurrent)} 元`,
    totals.rdToRevenueCurrent != null
      ? `，占主营业务收入 ${(totals.rdToRevenueCurrent * 100).toFixed(2)}%`
      : '（主营业务收入未填，占收入比待补）',
    '。',
  ]
  if (anom.compositionAnomalyCount) {
    parts.push(`构成分析中 ${anom.compositionAnomalyCount} 项增长/结构变动超阈值，已要求说明原因；`)
  }
  if (anom.peerGapCount) {
    parts.push(`人均指标与 ${anom.peerGapCount} 家可比公司差异较大，已关注同行业对比说明；`)
  }
  if (!anom.compositionAnomalyCount && !anom.peerGapCount && !anom.missingRevenue) {
    parts.push('抽查范围内未见重大异常波动，研发费用实质性分析结果在重大方面可接受。')
  } else {
    parts.push('详见审计说明中各类异常原因分析，结论以最终核实为准。')
  }
  return parts.join('')
}

function fmtMoney(v: number): string {
  return v.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 尝试从 I6-2 明细按类别汇总本期/上期审定金额 */
export function seedCompositionFromI6Detail(detailRows: any[]): I2CompositionRow[] {
  const cur = new Map<string, number>()
  const prior = new Map<string, number>()
  for (const r of detailRows ?? []) {
    const cat = String(r.category || r.itemName || r.name || '').trim()
    if (!cat || cat === '合计') continue
    const amt = _num(r.auditedAmount ?? r.yearTotal ?? r.unadjTotal ?? r.amount ?? r.currentAmount)
    const priorAmt = _num(r.priorAudited ?? r.priorUnadj ?? r.priorAmount)
    cur.set(cat, (cur.get(cat) || 0) + amt)
    prior.set(cat, (prior.get(cat) || 0) + priorAmt)
  }
  if (!cur.size) return defaultCompositionRows()

  const used = new Set<string>()
  const rows: I2CompositionRow[] = []
  for (const name of I2_ANALYSIS_DEFAULT_ITEMS) {
    const aliases = I2_ANALYSIS_I6_CATEGORY_ALIASES[name] || []
    const hitKey = [...cur.keys()].find(
      (k) => k.includes(name) || name.includes(k) || k.includes(name.replace(/费|分摊|摊销/g, ''))
        || aliases.some((a) => k.includes(a)),
    )
    if (hitKey) used.add(hitKey)
    rows.push(emptyCompositionRow({
      itemName: name,
      currentAmount: hitKey ? (cur.get(hitKey) || 0) : 0,
      priorAmount: hitKey ? (prior.get(hitKey) || 0) : 0,
    }))
  }
  for (const [cat, amt] of cur) {
    if (used.has(cat)) continue
    rows.push(emptyCompositionRow({
      itemName: cat,
      currentAmount: amt,
      priorAmount: prior.get(cat) || 0,
    }))
  }
  return rows
}
