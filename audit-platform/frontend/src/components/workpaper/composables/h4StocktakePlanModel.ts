/**
 * H4-6A 工程物资监盘计划 — 参照 H1-9 / H2-12，精简贴合工程物资场景
 */
export type H4RiskLevel = '低' | '中' | '高' | ''

export interface H4StocktakeLocationRow {
  rowId: string
  location: string
  materialTypes: string
  estimatedAmount: number
  remark: string
}

export interface H4StocktakePlanForm {
  existenceRiskLevel: H4RiskLevel
  existenceRiskNote: string
  storageOverview: string
  controlOverview: string
  priorYearFindings: string
  locations: H4StocktakeLocationRow[]
  stocktakeDate: string
  participants: string
  method: string
  scope: string
  sampleSizeNote: string
  bidirectionalNote: string
  plannedCoveragePct: number | null
  managementCommunication: string
  planConclusion: string
}

export interface H4StocktakeSummaryForm {
  balanceSheetDate: string
  preCountCheck: string
  staffAndTime: string
  walkthroughNote: string
  overallReconcile: string
  abnormalNote: string
  followUp: string
  summaryConclusion: string
  lastAutoSyncAt: string
}

export const H4_PLAN_KEY = 'H4-6A-plan'
export const H4_SUMMARY_KEY = 'H4-6B-summary'

export function createEmptyPlanForm(): H4StocktakePlanForm {
  return {
    existenceRiskLevel: '',
    existenceRiskNote: '',
    storageOverview: '',
    controlOverview: '',
    priorYearFindings: '',
    locations: [],
    stocktakeDate: '',
    participants: '',
    method: '抽盘',
    scope: '',
    sampleSizeNote: '',
    bidirectionalNote: '计划执行账面→实物（存在性）与实物→账面（完整性）双向抽盘。',
    plannedCoveragePct: null,
    managementCommunication: '',
    planConclusion: '',
  }
}

export function createEmptySummaryForm(): H4StocktakeSummaryForm {
  return {
    balanceSheetDate: '',
    preCountCheck: '',
    staffAndTime: '',
    walkthroughNote: '',
    overallReconcile: '',
    abnormalNote: '',
    followUp: '',
    summaryConclusion: '',
    lastAutoSyncAt: '',
  }
}

function _num(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function normalizePlanForm(raw: unknown): H4StocktakePlanForm {
  const base = createEmptyPlanForm()
  if (!raw || typeof raw !== 'object') return base
  const o = raw as Record<string, unknown>
  const locs = Array.isArray(o.locations) ? o.locations : []
  return {
    existenceRiskLevel: (['低', '中', '高'].includes(String(o.existenceRiskLevel))
      ? String(o.existenceRiskLevel)
      : '') as H4RiskLevel,
    existenceRiskNote: String(o.existenceRiskNote ?? ''),
    storageOverview: String(o.storageOverview ?? ''),
    controlOverview: String(o.controlOverview ?? ''),
    priorYearFindings: String(o.priorYearFindings ?? ''),
    locations: locs.map((l: any, i: number) => ({
      rowId: String(l?.rowId ?? `loc-${i}`),
      location: String(l?.location ?? ''),
      materialTypes: String(l?.materialTypes ?? ''),
      estimatedAmount: _num(l?.estimatedAmount),
      remark: String(l?.remark ?? ''),
    })),
    stocktakeDate: String(o.stocktakeDate ?? ''),
    participants: String(o.participants ?? ''),
    method: String(o.method ?? base.method),
    scope: String(o.scope ?? ''),
    sampleSizeNote: String(o.sampleSizeNote ?? ''),
    bidirectionalNote: String(o.bidirectionalNote ?? base.bidirectionalNote),
    plannedCoveragePct: o.plannedCoveragePct == null || o.plannedCoveragePct === ''
      ? null
      : _num(o.plannedCoveragePct),
    managementCommunication: String(o.managementCommunication ?? ''),
    planConclusion: String(o.planConclusion ?? ''),
  }
}

export function normalizeSummaryForm(raw: unknown): H4StocktakeSummaryForm {
  const base = createEmptySummaryForm()
  if (!raw || typeof raw !== 'object') return base
  const o = raw as Record<string, unknown>
  return {
    balanceSheetDate: String(o.balanceSheetDate ?? ''),
    preCountCheck: String(o.preCountCheck ?? ''),
    staffAndTime: String(o.staffAndTime ?? ''),
    walkthroughNote: String(o.walkthroughNote ?? ''),
    overallReconcile: String(o.overallReconcile ?? ''),
    abnormalNote: String(o.abnormalNote ?? ''),
    followUp: String(o.followUp ?? ''),
    summaryConclusion: String(o.summaryConclusion ?? ''),
    lastAutoSyncAt: String(o.lastAutoSyncAt ?? ''),
  }
}

/** 风险等级 → 建议覆盖率下限 */
export function suggestedCoverage(level: H4RiskLevel): number {
  if (level === '高') return 50
  if (level === '中') return 30
  if (level === '低') return 15
  return 20
}

export function planGateBlockers(form: H4StocktakePlanForm): string[] {
  const blockers: string[] = []
  if (!form.existenceRiskLevel) blockers.push('未评估存在性风险程度')
  if (!form.stocktakeDate.trim()) blockers.push('未填计划盘点日期')
  if (!form.scope.trim()) blockers.push('未填监盘范围')
  if (!form.method.trim()) blockers.push('未填监盘方法')
  if (!form.bidirectionalNote.trim()) blockers.push('未说明双向抽盘安排')
  return blockers
}

export function draftPlanConclusion(form: H4StocktakePlanForm): string {
  const cov = form.plannedCoveragePct != null
    ? `计划覆盖率约 ${form.plannedCoveragePct}%`
    : `建议覆盖率不低于 ${suggestedCoverage(form.existenceRiskLevel)}%`
  return [
    `工程物资存在性认定重大错报风险评为「${form.existenceRiskLevel || '____'}」。`,
    `拟于 ${form.stocktakeDate || '____'} 执行监盘，方法：${form.method || '____'}；范围：${form.scope || '____'}。`,
    form.bidirectionalNote || '将执行双向抽盘。',
    `${cov}。详见 H4-6 盘点检查表执行记录，监盘小结见 H4-6B。`,
  ].join('\n')
}

export function draftSummaryFromCheck(ctx: {
  location: string
  countTime: string
  clientStaff: string
  auditors: string
  total: number
  matchCount: number
  surplusCount: number
  deficitCount: number
  varianceCount: number
  concernCount: number
  matchRate: number
  coveragePct: number | null
  auditNote: string
  auditConclusion: string
}): H4StocktakeSummaryForm {
  const form = createEmptySummaryForm()
  form.staffAndTime = [
    ctx.countTime ? `时间：${ctx.countTime}` : '',
    ctx.location ? `地点：${ctx.location}` : '',
    ctx.clientStaff ? `企业人员：${ctx.clientStaff}` : '',
    ctx.auditors ? `监盘：${ctx.auditors}` : '',
  ].filter(Boolean).join('；') || ''

  form.walkthroughNote =
    `本次共抽盘 ${ctx.total} 项，账实相符 ${ctx.matchCount}（相符率 ${ctx.matchRate.toFixed(1)}%），` +
    `盘盈 ${ctx.surplusCount}、盘亏 ${ctx.deficitCount}，三数量差异 ${ctx.varianceCount} 项，` +
    `品质/盘亏关注 ${ctx.concernCount} 项。`

  form.overallReconcile = ctx.coveragePct != null
    ? `抽盘样本占期末工程物资余额约 ${ctx.coveragePct.toFixed(2)}%。`
    : '期末余额合计未填，覆盖率待补算。'

  if (ctx.varianceCount > 0 || ctx.concernCount > 0) {
    form.abnormalNote = ctx.auditNote || '存在账实差异或品质异常，详见 H4-6 差异原因及品质状况列。'
    form.followUp = '差异须追查企业处理；闲置/毁损/盘亏已（或应）推送 H4-7 减值测算。'
  } else if (ctx.total > 0) {
    form.abnormalNote = '未发现重大账实不符或品质异常。'
    form.followUp = '按计划归档监盘证据；如后续发现积压/毁损，补充推送 H4-7。'
  }

  form.summaryConclusion = ctx.auditConclusion || (
    ctx.total === 0
      ? '尚未执行抽盘明细记录，本节结论待补。'
      : ctx.deficitCount > 0 || ctx.varianceCount > 0
        ? '存在账实差异，已在 H4-6 记录；工程物资存在性/完整性认定需结合差异处理结论。'
        : '双向抽盘未发现重大账实不符，工程物资存在性与完整性认定可获合理保证。'
  )
  form.lastAutoSyncAt = new Date().toISOString()
  return form
}
