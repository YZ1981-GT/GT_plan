/**
 * H2-12 监盘计划 — 数据结构与默认值
 *
 * 对齐致同模板「在建工程监盘计划」编制逻辑（与固定资产 H1-9 同构）：
 * 风险评估 → 了解期末状况/内控/以前年度 → 胜任能力 → 计划安排（范围/方法/抽样/推算）→ 结论
 *
 * CIP 差异：二(一)为期末余额+主要工程项目表；保留 selectedProjects 供 H2-13 带入。
 */

export type RiskLevel = '' | '低' | '中' | '高'

/** 二(一) 主要工程项目情况 */
export interface PlanMajorProjectRow {
  rowId: string
  seq: number
  name: string
  originalCost: number
  impairment: number
  netBookValue: number
  location: string
  note: string
}

/** 四(三) 类别/工程范围 */
export interface PlanCategoryScopeRow {
  rowId: string
  seq: number
  category: string
  endingBalance: number
  impairment: number
  netBookValue: number
  unit: string
  quantity: number
  planQty: number
  planAmount: number
  /** 监盘比例(%)，可由 planAmount/netBookValue 推算 */
  coverageRate: number
}

/** 拟抽盘工程（CIP 专用，回填 H2-13） */
export interface StocktakeProjectSelection {
  rowId: string
  name: string
  reason: string
  plannedContent: string
}

export interface H2StocktakePlanForm {
  /** 一、存在性认定重大错报风险 */
  existenceRiskLevel: RiskLevel
  existenceRiskNote: string

  /** 二(一) 期末状况 */
  endingBalanceNote: string
  majorProjects: PlanMajorProjectRow[]

  /** 二(二) 定期盘点内控 */
  icSystemName: string
  icSystemIndex: string
  icFrequency: string
  icResponsible: string
  clientPlanArrange: string
  clientMeetingNote: string
  clientHeadcountEstimate: string
  clientPlanEvaluation: string

  /** 二(三) 以前年度 */
  priorYearDate: string
  priorYearStaff: string
  priorYearScope: string
  priorYearSampleRate: string
  priorYearIssues: string

  /** 三、专业胜任能力 */
  competenceNote: string

  /** 四、盘点计划安排 */
  plannedDate: string
  plannedTimeNote: string
  plannedHeadcount: number | null
  plannedLead: string
  categoryScopes: PlanCategoryScopeRow[]
  locationScopeNote: string
  /** 拟抽盘工程项目（金额重大/异常/随机） */
  selectedProjects: StocktakeProjectSelection[]
  method: string
  methodDetail: string
  mgmtCommTime: string
  mgmtCommNames: string
  mgmtCommAuditors: string
  specialRequirements: string
  sampleBookToFloorMethod: string
  sampleBookToFloorQty: number | null
  sampleFloorToBookMethod: string
  sampleFloorToBookQty: number | null
  rollForwardMethod: string
  /** 预计拟要求的盘点复盘比例(%)，合理区间 0~100 */
  plannedRecountRatio: number | null

  /** 结论与签署 */
  planConclusion: string
  preparedBy: string
  preparedDate: string
  reviewedBy: string
  reviewedDate: string
}

/** 旧版五字段+工程选取，供 H2-13 兼容 */
export interface H2LegacyStocktakePlan {
  inspectionDate: string
  location: string
  participants: string
  scope: string
  selectedProjects: StocktakeProjectSelection[]
  schedule: string
}

function _id(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function newMajorProjectRow(partial?: Partial<PlanMajorProjectRow>): PlanMajorProjectRow {
  return {
    rowId: `pmaj-${_id()}`,
    seq: 1,
    name: '',
    originalCost: 0,
    impairment: 0,
    netBookValue: 0,
    location: '',
    note: '',
    ...partial,
  }
}

export function newCategoryScopeRow(partial?: Partial<PlanCategoryScopeRow>): PlanCategoryScopeRow {
  return {
    rowId: `pcat-${_id()}`,
    seq: 1,
    category: '',
    endingBalance: 0,
    impairment: 0,
    netBookValue: 0,
    unit: '项',
    quantity: 0,
    planQty: 0,
    planAmount: 0,
    coverageRate: 0,
    ...partial,
  }
}

export function newSelectedProject(partial?: Partial<StocktakeProjectSelection>): StocktakeProjectSelection {
  return {
    rowId: `psel-${_id()}`,
    name: '',
    reason: '',
    plannedContent: '',
    ...partial,
  }
}

export function createEmptyPlanForm(): H2StocktakePlanForm {
  return {
    existenceRiskLevel: '',
    existenceRiskNote: '',
    endingBalanceNote: '',
    majorProjects: [],
    icSystemName: '',
    icSystemIndex: '',
    icFrequency: '',
    icResponsible: '',
    clientPlanArrange: '',
    clientMeetingNote: '',
    clientHeadcountEstimate: '',
    clientPlanEvaluation: '',
    priorYearDate: '',
    priorYearStaff: '',
    priorYearScope: '',
    priorYearSampleRate: '',
    priorYearIssues: '',
    competenceNote: '',
    plannedDate: '',
    plannedTimeNote: '',
    plannedHeadcount: null,
    plannedLead: '',
    categoryScopes: [
      newCategoryScopeRow({ seq: 1, category: '自营工程' }),
      newCategoryScopeRow({ seq: 2, category: '出包工程' }),
      newCategoryScopeRow({ seq: 3, category: '安装工程' }),
    ],
    locationScopeNote: '',
    selectedProjects: [],
    method: '抽样盘点',
    methodDetail: '',
    mgmtCommTime: '',
    mgmtCommNames: '',
    mgmtCommAuditors: '',
    specialRequirements: '',
    sampleBookToFloorMethod: '从会计明细账/工程台账选取样本追查至现场工程',
    sampleBookToFloorQty: null,
    sampleFloorToBookMethod: '从现场在建工程选取样本追查至明细账/台账',
    sampleFloorToBookQty: null,
    rollForwardMethod: '',
    plannedRecountRatio: null,
    planConclusion: '',
    preparedBy: '',
    preparedDate: '',
    reviewedBy: '',
    reviewedDate: '',
  }
}

/** 单行：净值 = 原值 − 减值；比例 = 计划金额 / 净值 */
export function recalcCategoryScopeRow(row: PlanCategoryScopeRow): PlanCategoryScopeRow {
  const ending = Number(row.endingBalance) || 0
  const impair = Number(row.impairment) || 0
  const net = row.netBookValue != null && row.netBookValue !== 0
    ? Number(row.netBookValue)
    : Math.max(0, ending - impair)
  const planAmt = Number(row.planAmount) || 0
  const rate = net > 0 ? Math.round((planAmt / net) * 1000) / 10 : 0
  return {
    ...row,
    endingBalance: ending,
    impairment: impair,
    netBookValue: net,
    quantity: Number(row.quantity) || 0,
    planQty: Number(row.planQty) || 0,
    planAmount: planAmt,
    coverageRate: rate,
  }
}

export function recalcMajorProjectRow(row: PlanMajorProjectRow): PlanMajorProjectRow {
  const cost = Number(row.originalCost) || 0
  const impair = Number(row.impairment) || 0
  const net = row.netBookValue != null && row.netBookValue !== 0
    ? Number(row.netBookValue)
    : Math.max(0, cost - impair)
  return {
    ...row,
    originalCost: cost,
    impairment: impair,
    netBookValue: net,
  }
}

export function calcCategoryScopeTotals(rows: PlanCategoryScopeRow[]): {
  endingBalance: number
  impairment: number
  netBookValue: number
  quantity: number
  planQty: number
  planAmount: number
  coverageRate: number
} {
  const endingBalance = rows.reduce((s, r) => s + (Number(r.endingBalance) || 0), 0)
  const impairment = rows.reduce((s, r) => s + (Number(r.impairment) || 0), 0)
  const netBookValue = rows.reduce((s, r) => s + (Number(r.netBookValue) || 0), 0)
  const quantity = rows.reduce((s, r) => s + (Number(r.quantity) || 0), 0)
  const planQty = rows.reduce((s, r) => s + (Number(r.planQty) || 0), 0)
  const planAmount = rows.reduce((s, r) => s + (Number(r.planAmount) || 0), 0)
  const coverageRate = netBookValue > 0 ? Math.round((planAmount / netBookValue) * 1000) / 10 : 0
  return { endingBalance, impairment, netBookValue, quantity, planQty, planAmount, coverageRate }
}

export function isPlannedRecountRatioValid(v: number | null | undefined): boolean {
  if (v == null || Number.isNaN(Number(v))) return true
  const n = Number(v)
  return n >= 0 && n <= 100
}

function isLegacyPlanShape(raw: any): boolean {
  if (!raw || typeof raw !== 'object') return false
  if (Array.isArray(raw.categoryScopes) || 'existenceRiskLevel' in raw || 'plannedDate' in raw) {
    return false
  }
  return 'inspectionDate' in raw || 'selectedProjects' in raw || 'participants' in raw
}

/** 合并已存 JSON，兼容旧版五字段计划 */
export function normalizePlanForm(raw: any): H2StocktakePlanForm {
  const base = createEmptyPlanForm()
  if (!raw || typeof raw !== 'object') return base

  if (isLegacyPlanShape(raw)) {
    return applyLegacyInfo(base, {
      inspectionDate: raw.inspectionDate,
      location: raw.location,
      participants: raw.participants,
      scope: raw.scope,
      schedule: raw.schedule,
      selectedProjects: raw.selectedProjects,
    })
  }

  const out: H2StocktakePlanForm = { ...base, ...raw }

  out.majorProjects = Array.isArray(raw.majorProjects)
    ? raw.majorProjects.map((r: any, i: number) =>
      recalcMajorProjectRow({
        rowId: r.rowId ?? `pmaj-${_id()}`,
        seq: r.seq ?? i + 1,
        name: r.name ?? '',
        originalCost: Number(r.originalCost) || 0,
        impairment: Number(r.impairment) || 0,
        netBookValue: Number(r.netBookValue) || 0,
        location: r.location ?? '',
        note: r.note ?? '',
      }),
    )
    : []

  out.categoryScopes = Array.isArray(raw.categoryScopes) && raw.categoryScopes.length
    ? raw.categoryScopes.map((r: any, i: number) =>
      recalcCategoryScopeRow({
        rowId: r.rowId ?? `pcat-${_id()}`,
        seq: r.seq ?? i + 1,
        category: r.category ?? '',
        endingBalance: Number(r.endingBalance) || 0,
        impairment: Number(r.impairment) || 0,
        netBookValue: Number(r.netBookValue) || 0,
        unit: r.unit ?? '项',
        quantity: Number(r.quantity) || 0,
        planQty: Number(r.planQty) || Number(r.sampleSize) || 0,
        planAmount: Number(r.planAmount) || Number(r.coverageAmount) || 0,
        coverageRate: Number(r.coverageRate) || 0,
      }),
    )
    : base.categoryScopes

  out.selectedProjects = Array.isArray(raw.selectedProjects)
    ? raw.selectedProjects.map((p: any) => ({
        rowId: p.rowId ?? `psel-${_id()}`,
        name: p.name ?? '',
        reason: p.reason ?? '',
        plannedContent: p.plannedContent ?? '',
      }))
    : []

  if (!isPlannedRecountRatioValid(out.plannedRecountRatio)) {
    out.plannedRecountRatio = null
  }

  return out
}

function applyLegacyInfo(
  form: H2StocktakePlanForm,
  legacy?: Partial<H2LegacyStocktakePlan>,
): H2StocktakePlanForm {
  if (!legacy) return form
  if (!form.plannedDate && legacy.inspectionDate) form.plannedDate = legacy.inspectionDate
  if (!form.locationScopeNote && legacy.location) form.locationScopeNote = legacy.location
  if (!form.plannedLead && legacy.participants) form.plannedLead = legacy.participants
  if (!form.methodDetail && legacy.scope) form.methodDetail = legacy.scope
  if (!form.plannedTimeNote && legacy.schedule) form.plannedTimeNote = legacy.schedule
  if (Array.isArray(legacy.selectedProjects) && legacy.selectedProjects.length && !form.selectedProjects.length) {
    form.selectedProjects = legacy.selectedProjects.map((p, i) => ({
      rowId: p.rowId ?? `psel-${_id()}`,
      name: p.name ?? '',
      reason: p.reason ?? '',
      plannedContent: p.plannedContent ?? '',
    }))
  }
  return form
}

/** 从类别范围推算双向抽查预计数量（仅填空） */
export function draftSampleQtyFromScopes(rows: PlanCategoryScopeRow[]): {
  sampleBookToFloorQty: number | null
  sampleFloorToBookQty: number | null
} {
  const planQty = rows.reduce((s, r) => s + (Number(r.planQty) || 0), 0)
  return {
    sampleBookToFloorQty: planQty > 0 ? planQty : null,
    sampleFloorToBookQty: planQty > 0 ? Math.max(1, Math.round(planQty * 0.3)) : null,
  }
}

/** 拼装写入检查表「抽样方法」的叙述 */
export function buildSamplingMethodNarrative(form: H2StocktakePlanForm): string {
  const parts: string[] = []
  if (form.method) parts.push(`按监盘计划（H2-12）采用${form.method}`)
  const b2f = form.sampleBookToFloorQty != null
    ? `${form.sampleBookToFloorMethod || '账面→现场'}（预计 ${form.sampleBookToFloorQty}）`
    : (form.sampleBookToFloorMethod || '')
  const f2b = form.sampleFloorToBookQty != null
    ? `${form.sampleFloorToBookMethod || '现场→账面'}（预计 ${form.sampleFloorToBookQty}）`
    : (form.sampleFloorToBookMethod || '')
  if (b2f || f2b) parts.push([b2f, f2b].filter(Boolean).join('；'))
  else parts.push('从账面至现场、从现场至账面双向抽查')
  if (form.plannedRecountRatio != null && isPlannedRecountRatioValid(form.plannedRecountRatio)) {
    parts.push(`预计复盘比例 ${form.plannedRecountRatio}%`)
  }
  return parts.filter(Boolean).join('。') + (parts.length ? '。' : '')
}

/** 计划逻辑告警（编制/复核用） */
export function calcPlanLogicWarnings(form: H2StocktakePlanForm): string[] {
  const warnings: string[] = []
  if (!form.existenceRiskLevel) {
    warnings.push('尚未评估在建工程存在性认定的重大错报风险程度')
  }
  if (!form.majorProjects.length && !form.endingBalanceNote && !form.locationScopeNote) {
    warnings.push('未填写期末状况（余额说明或主要工程项目）')
  }
  if (!form.plannedDate) warnings.push('未填写预计监盘时间')
  if (!form.plannedLead) warnings.push('未指定监盘程序负责人')
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  const hasScope = form.categoryScopes.some((r) => r.planAmount > 0 || r.planQty > 0)
  if (!hasScope) warnings.push('类别范围尚未填写计划监盘数量/金额')
  if (totals.netBookValue > 0 && totals.coverageRate < 30) {
    warnings.push(`计划监盘金额覆盖率 ${totals.coverageRate}% 偏低，请结合风险水平评估是否充分`)
  }
  if (!form.selectedProjects.length) {
    warnings.push('尚未选取拟现场踏勘的工程项目（H2-13 将据此带入样本）')
  }
  if (!isPlannedRecountRatioValid(form.plannedRecountRatio)) {
    warnings.push('预计复盘比例异常（应为 0~100%），请更正')
  } else if (form.plannedRecountRatio != null && form.plannedRecountRatio < 5) {
    warnings.push('预计复盘比例偏低，请按准则评估样本量是否充分')
  }
  if (!form.clientPlanEvaluation && form.clientPlanArrange) {
    warnings.push('已记录企业盘点安排，但尚未评价其盘点计划是否适当')
  }
  if (!form.competenceNote) {
    warnings.push('尚未评估审计人员专业胜任能力（特殊工程尤需关注）')
  }
  return warnings
}

/** 导出兼容旧版 H2-12-plan 视图，供 H2-13 带入 */
export function toLegacyPlan(form: H2StocktakePlanForm): H2LegacyStocktakePlan {
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  const loc = form.locationScopeNote
    || form.majorProjects.map((l) => l.location).filter(Boolean).join('、')
  const scopeParts = [
    form.methodDetail,
    form.locationScopeNote,
    totals.planAmount > 0
      ? `计划监盘金额 ${totals.planAmount.toLocaleString('zh-CN')}（覆盖率 ${totals.coverageRate}%）`
      : '',
    form.endingBalanceNote,
  ].filter(Boolean)
  return {
    inspectionDate: form.plannedDate,
    location: loc,
    participants: [form.plannedLead, form.mgmtCommAuditors].filter(Boolean).join('；'),
    scope: scopeParts.join('；'),
    selectedProjects: form.selectedProjects,
    schedule: [form.plannedTimeNote, form.specialRequirements].filter(Boolean).join('；'),
  }
}
