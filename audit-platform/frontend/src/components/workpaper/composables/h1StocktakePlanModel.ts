/**
 * H1-9 监盘计划 — 数据结构与默认值
 * 对齐致同模板「固定资产监盘计划」编制逻辑：
 * 风险评估 → 了解状况/内控/以前年度 → 胜任能力 → 计划安排（范围/方法/抽样/推算）→ 结论
 * 字段设计便于向 H1-11 监盘小结回填。
 */

export type RiskLevel = '' | '低' | '中' | '高'

export interface PlanLocationRow {
  rowId: string
  seq: number
  category: string
  warehouse: string
  place: string
  note: string
}

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

export interface H1StocktakePlanForm {
  /** 一、存在性认定重大错报风险 */
  existenceRiskLevel: RiskLevel
  existenceRiskNote: string

  /** 二(一) 期末状况 */
  idleAssetsNote: string
  locations: PlanLocationRow[]

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

function _id(): string {
  return `${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 8)}`
}

export function newPlanLocationRow(partial?: Partial<PlanLocationRow>): PlanLocationRow {
  return {
    rowId: `ploc-${_id()}`,
    seq: 1,
    category: '',
    warehouse: '',
    place: '',
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
    unit: '台/套',
    quantity: 0,
    planQty: 0,
    planAmount: 0,
    coverageRate: 0,
    ...partial,
  }
}

export function createEmptyPlanForm(): H1StocktakePlanForm {
  return {
    existenceRiskLevel: '',
    existenceRiskNote: '',
    idleAssetsNote: '',
    locations: [],
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
      newCategoryScopeRow({ seq: 1, category: '房屋及建筑物' }),
      newCategoryScopeRow({ seq: 2, category: '机器设备' }),
      newCategoryScopeRow({ seq: 3, category: '运输设备' }),
    ],
    locationScopeNote: '',
    method: '抽样盘点',
    methodDetail: '',
    mgmtCommTime: '',
    mgmtCommNames: '',
    mgmtCommAuditors: '',
    specialRequirements: '',
    sampleBookToFloorMethod: '从会计明细账/卡片选取样本追查至实物',
    sampleBookToFloorQty: null,
    sampleFloorToBookMethod: '从实物选取样本追查至明细账/卡片',
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

/**
 * 校验复盘比例：Excel 模板曾出现 23500% 等异常占位。
 * 合法：null/空，或 0~100（含一位小数）。
 */
export function isPlannedRecountRatioValid(v: number | null | undefined): boolean {
  if (v == null || Number.isNaN(Number(v))) return true
  const n = Number(v)
  return n >= 0 && n <= 100
}

/** 合并已存 JSON，兼容旧版仅 StocktakePlanInfo 五字段 */
export function normalizePlanForm(raw: any, legacyInfo?: {
  stocktakeDate?: string
  location?: string
  participants?: string
  scope?: string
  method?: string
}): H1StocktakePlanForm {
  const base = createEmptyPlanForm()
  if (!raw || typeof raw !== 'object') {
    return applyLegacyInfo(base, legacyInfo)
  }

  const out: H1StocktakePlanForm = { ...base, ...raw }

  out.locations = Array.isArray(raw.locations)
    ? raw.locations.map((r: any, i: number) => ({
        rowId: r.rowId ?? `ploc-${_id()}`,
        seq: r.seq ?? i + 1,
        category: r.category ?? '',
        warehouse: r.warehouse ?? '',
        place: r.place ?? r.storageLocation ?? '',
        note: r.note ?? '',
      }))
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
        unit: r.unit ?? '台/套',
        quantity: Number(r.quantity) || 0,
        planQty: Number(r.planQty) || Number(r.sampleSize) || 0,
        planAmount: Number(r.planAmount) || Number(r.coverageAmount) || 0,
        coverageRate: Number(r.coverageRate) || 0,
      }),
    )
    : base.categoryScopes

  // 异常复盘比例（如 Excel 23500%）清零，避免污染小结
  if (!isPlannedRecountRatioValid(out.plannedRecountRatio)) {
    out.plannedRecountRatio = null
  }

  return applyLegacyInfo(out, legacyInfo)
}

function applyLegacyInfo(
  form: H1StocktakePlanForm,
  legacy?: {
    stocktakeDate?: string
    location?: string
    participants?: string
    scope?: string
    method?: string
  },
): H1StocktakePlanForm {
  if (!legacy) return form
  if (!form.plannedDate && legacy.stocktakeDate) form.plannedDate = legacy.stocktakeDate
  if (!form.locationScopeNote && legacy.location) form.locationScopeNote = legacy.location
  if (!form.plannedLead && legacy.participants) form.plannedLead = legacy.participants
  if (!form.methodDetail && legacy.scope) form.methodDetail = legacy.scope
  if (legacy.method && (form.method === '抽样盘点' || !form.method)) form.method = legacy.method
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

/** 拼装写入 H1-11「抽样方法」的叙述 */
export function buildSamplingMethodNarrative(form: H1StocktakePlanForm): string {
  const parts: string[] = []
  if (form.method) parts.push(`按监盘计划（H1-9）采用${form.method}`)
  const b2f = form.sampleBookToFloorQty != null
    ? `${form.sampleBookToFloorMethod || '账面→实物'}（预计 ${form.sampleBookToFloorQty}）`
    : (form.sampleBookToFloorMethod || '')
  const f2b = form.sampleFloorToBookQty != null
    ? `${form.sampleFloorToBookMethod || '实物→账面'}（预计 ${form.sampleFloorToBookQty}）`
    : (form.sampleFloorToBookMethod || '')
  if (b2f || f2b) parts.push([b2f, f2b].filter(Boolean).join('；'))
  else parts.push('从账面至实物、从实物至账面双向抽查')
  if (form.plannedRecountRatio != null && isPlannedRecountRatioValid(form.plannedRecountRatio)) {
    parts.push(`预计复盘比例 ${form.plannedRecountRatio}%`)
  }
  return parts.filter(Boolean).join('。') + (parts.length ? '。' : '')
}

/** 计划逻辑告警（编制/复核用） */
export function calcPlanLogicWarnings(form: H1StocktakePlanForm): string[] {
  const warnings: string[] = []
  if (!form.existenceRiskLevel) {
    warnings.push('尚未评估固定资产存在性认定的重大错报风险程度')
  }
  if (!form.locations.length && !form.locationScopeNote) {
    warnings.push('未填写资产存放地点（表或地点范围说明）')
  }
  if (!form.plannedDate) warnings.push('未填写预计监盘时间')
  if (!form.plannedLead) warnings.push('未指定监盘程序负责人')
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  const hasScope = form.categoryScopes.some((r) => (r.planAmount > 0 || r.planQty > 0))
  if (!hasScope) warnings.push('类别范围尚未填写计划监盘数量/金额')
  if (totals.netBookValue > 0 && totals.coverageRate < 30) {
    warnings.push(`计划监盘金额覆盖率 ${totals.coverageRate}% 偏低，请结合风险水平评估是否充分`)
  }
  if (!isPlannedRecountRatioValid(form.plannedRecountRatio)) {
    warnings.push('预计复盘比例异常（应为 0~100%），请更正（原 Excel 曾出现超大百分比占位）')
  } else if (form.plannedRecountRatio != null && form.plannedRecountRatio < 5) {
    warnings.push('预计复盘比例偏低，请按准则评估样本量是否充分')
  }
  if (!form.clientPlanEvaluation && form.clientPlanArrange) {
    warnings.push('已记录企业盘点安排，但尚未评价其盘点计划是否适当')
  }
  if (!form.competenceNote) {
    warnings.push('尚未评估审计人员专业胜任能力（特殊资产尤需关注）')
  }
  return warnings
}

/** 导出兼容旧 StocktakePlanInfo 视图 */
export function toLegacyPlanInfo(form: H1StocktakePlanForm): {
  stocktakeDate: string
  location: string
  participants: string
  scope: string
  method: string
} {
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  const scopeParts = [
    form.methodDetail,
    form.locationScopeNote,
    totals.planAmount > 0 ? `计划监盘金额 ${totals.planAmount.toLocaleString('zh-CN')}（覆盖率 ${totals.coverageRate}%）` : '',
  ].filter(Boolean)
  return {
    stocktakeDate: form.plannedDate,
    location: form.locationScopeNote || form.locations.map((l) => l.place || l.warehouse).filter(Boolean).join('、'),
    participants: [form.plannedLead, form.mgmtCommAuditors].filter(Boolean).join('；'),
    scope: scopeParts.join('；'),
    method: form.method || '抽样盘点',
  }
}
