/**
 * H1-9 监盘计划 — 增强能力
 * H1-2 带入 / H1-4 闲置 / 风险建议 / 门禁 / 计划vs执行 / 结论草稿 / 字段映射 / 上年带入
 */
import {
  calcCategoryScopeTotals,
  calcPlanLogicWarnings,
  isPlannedRecountRatioValid,
  newCategoryScopeRow,
  recalcCategoryScopeRow,
  type H1StocktakePlanForm,
  type PlanCategoryScopeRow,
  type RiskLevel,
} from './h1StocktakePlanModel'

// ─── H1-2 → 类别范围 ─────────────────────────────────────────────────────────

export interface H12DetailLike {
  category?: string
  originalCostEnd?: number
  impairmentEnd?: number
  netValue?: number
  quantity?: number
  unit?: string
  location?: string
}

/** 按分类汇总 H1-2 明细为类别范围行（保留已有 planQty/planAmount） */
export function aggregateH12ToCategoryScopes(
  detailRows: H12DetailLike[],
  existing?: PlanCategoryScopeRow[],
): PlanCategoryScopeRow[] {
  const map = new Map<string, {
    endingBalance: number
    impairment: number
    netBookValue: number
    quantity: number
    unit: string
  }>()

  for (const r of detailRows) {
    const cat = (r.category || '').trim() || '未分类'
    const cur = map.get(cat) || {
      endingBalance: 0,
      impairment: 0,
      netBookValue: 0,
      quantity: 0,
      unit: '',
    }
    cur.endingBalance += Number(r.originalCostEnd) || 0
    cur.impairment += Number(r.impairmentEnd) || 0
    cur.netBookValue += Number(r.netValue) || 0
    cur.quantity += Number(r.quantity) || 0
    if (!cur.unit && r.unit) cur.unit = String(r.unit)
    map.set(cat, cur)
  }

  const existingByCat = new Map(
    (existing || []).map((r) => [r.category, r]),
  )

  const rows: PlanCategoryScopeRow[] = []
  let seq = 1
  for (const [category, agg] of map) {
    const prev = existingByCat.get(category)
    rows.push(recalcCategoryScopeRow(newCategoryScopeRow({
      seq: seq++,
      category,
      endingBalance: agg.endingBalance,
      impairment: agg.impairment,
      netBookValue: agg.netBookValue,
      quantity: agg.quantity,
      unit: agg.unit || prev?.unit || '台/套',
      planQty: prev?.planQty ?? 0,
      planAmount: prev?.planAmount ?? 0,
    })))
  }
  return rows.length ? rows : (existing?.length ? existing : [
    newCategoryScopeRow({ seq: 1, category: '房屋及建筑物' }),
  ])
}

/** 从 H1-2 地点去重生成地点范围说明草稿 */
export function draftLocationScopeFromH12(detailRows: H12DetailLike[]): string {
  const set = new Set<string>()
  for (const r of detailRows) {
    const loc = (r.location || '').trim()
    if (loc) set.add(loc)
  }
  return [...set].join('、')
}

// ─── H1-4 → 闲置说明 ─────────────────────────────────────────────────────────

export interface H14IdleLike {
  name?: string
  assetNo?: string
  netValue?: number
  originalCost?: number
  idleReason?: string
  impairmentAmount?: number
}

export function draftIdleNoteFromH4(rows: H14IdleLike[]): string {
  if (!rows.length) return '本期 H1-4 暂无闲置固定资产记录。'
  const totalNet = rows.reduce((s, r) => s + (Number(r.netValue) || 0), 0)
  const totalCost = rows.reduce((s, r) => s + (Number(r.originalCost) || 0), 0)
  const impair = rows.reduce((s, r) => s + (Number(r.impairmentAmount) || 0), 0)
  const top = rows
    .slice(0, 5)
    .map((r) => {
      const bits = [r.name || r.assetNo || '未命名']
      if (r.netValue != null) bits.push(`净值${Number(r.netValue).toLocaleString('zh-CN')}`)
      if (r.idleReason) bits.push(r.idleReason)
      return bits.join('，')
    })
    .join('；')
  return (
    `期末闲置固定资产共 ${rows.length} 项，原值合计 ${totalCost.toLocaleString('zh-CN')}，` +
    `净值合计 ${totalNet.toLocaleString('zh-CN')}，已计提减值 ${impair.toLocaleString('zh-CN')}。` +
    (top ? `主要项目：${top}${rows.length > 5 ? '等' : ''}。` : '')
  )
}

// ─── 风险 → 样本量建议 ───────────────────────────────────────────────────────

export interface RiskSampleSuggestion {
  riskLevel: RiskLevel
  minCoverageRate: number
  suggestedRecountRatio: number
  bookToFloorRatio: number
  floorToBookRatio: number
  label: string
}

export function suggestCoverageByRisk(risk: RiskLevel): RiskSampleSuggestion {
  if (risk === '高') {
    return {
      riskLevel: risk,
      minCoverageRate: 70,
      suggestedRecountRatio: 20,
      bookToFloorRatio: 0.4,
      floorToBookRatio: 0.15,
      label: '高风险：建议金额覆盖≥70%，复盘比例约20%',
    }
  }
  if (risk === '中') {
    return {
      riskLevel: risk,
      minCoverageRate: 50,
      suggestedRecountRatio: 10,
      bookToFloorRatio: 0.25,
      floorToBookRatio: 0.1,
      label: '中风险：建议金额覆盖≥50%，复盘比例约10%',
    }
  }
  if (risk === '低') {
    return {
      riskLevel: risk,
      minCoverageRate: 30,
      suggestedRecountRatio: 5,
      bookToFloorRatio: 0.15,
      floorToBookRatio: 0.05,
      label: '低风险：建议金额覆盖≥30%，复盘比例约5%',
    }
  }
  return {
    riskLevel: '',
    minCoverageRate: 30,
    suggestedRecountRatio: 10,
    bookToFloorRatio: 0.2,
    floorToBookRatio: 0.08,
    label: '请先评估存在性风险后再套用建议样本量',
  }
}

/** 按风险建议回填计划监盘金额/数量与复盘比例（可覆盖） */
export function applyRiskSuggestions(
  form: H1StocktakePlanForm,
  opts?: { overwrite?: boolean },
): H1StocktakePlanForm {
  const overwrite = opts?.overwrite === true
  const sug = suggestCoverageByRisk(form.existenceRiskLevel)
  if (!form.existenceRiskLevel) return form

  const next = { ...form, categoryScopes: form.categoryScopes.map((r) => ({ ...r })) }
  for (const row of next.categoryScopes) {
    const net = Number(row.netBookValue) || 0
    const qty = Number(row.quantity) || 0
    if (overwrite || !row.planAmount) {
      row.planAmount = Math.round(net * (sug.minCoverageRate / 100) * 100) / 100
    }
    if (overwrite || !row.planQty) {
      row.planQty = qty > 0 ? Math.max(1, Math.round(qty * sug.bookToFloorRatio)) : row.planQty
    }
    Object.assign(row, recalcCategoryScopeRow(row))
  }

  if (overwrite || next.plannedRecountRatio == null) {
    next.plannedRecountRatio = sug.suggestedRecountRatio
  }

  const totals = calcCategoryScopeTotals(next.categoryScopes)
  if (overwrite || next.sampleBookToFloorQty == null) {
    next.sampleBookToFloorQty = totals.planQty > 0 ? totals.planQty : null
  }
  if (overwrite || next.sampleFloorToBookQty == null) {
    next.sampleFloorToBookQty = totals.quantity > 0
      ? Math.max(1, Math.round(totals.quantity * sug.floorToBookRatio))
      : (totals.planQty > 0 ? Math.max(1, Math.round(totals.planQty * 0.3)) : null)
  }
  return next
}

/** 覆盖率是否达到风险建议下限 */
export function isCoverageAdequateForRisk(form: H1StocktakePlanForm): boolean {
  if (!form.existenceRiskLevel) return true
  const sug = suggestCoverageByRisk(form.existenceRiskLevel)
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  if (totals.netBookValue <= 0) return true
  return totals.coverageRate >= sug.minCoverageRate
}

// ─── 进 H1-10 软门禁 ─────────────────────────────────────────────────────────

export function getPlanGateBlockers(form: H1StocktakePlanForm): string[] {
  const blockers: string[] = []
  if (!form.existenceRiskLevel) blockers.push('未评估存在性认定重大错报风险')
  if (!form.plannedDate) blockers.push('未填写预计监盘时间')
  if (!form.plannedLead) blockers.push('未指定监盘程序负责人')
  const hasScope = form.categoryScopes.some((r) => r.planAmount > 0 || r.planQty > 0)
  if (!hasScope) blockers.push('类别范围未填写计划监盘数量/金额')
  if (!isPlannedRecountRatioValid(form.plannedRecountRatio)) {
    blockers.push('预计复盘比例异常（须为 0~100%）')
  }
  if (!isCoverageAdequateForRisk(form)) {
    const sug = suggestCoverageByRisk(form.existenceRiskLevel)
    const t = calcCategoryScopeTotals(form.categoryScopes)
    blockers.push(
      `计划覆盖率 ${t.coverageRate}% 低于${form.existenceRiskLevel}风险建议下限 ${sug.minCoverageRate}%`,
    )
  }
  return blockers
}

export function isPlanReadyForCheck(form: H1StocktakePlanForm): boolean {
  return getPlanGateBlockers(form).length === 0
}

// ─── 计划 vs 执行勾稽 ───────────────────────────────────────────────────────

export interface PlanVsCheckInput {
  bookToFloorCount: number
  floorToBookCount: number
  checkedAmount: number
}

export function calcPlanVsCheckWarnings(
  form: H1StocktakePlanForm,
  check: PlanVsCheckInput,
): string[] {
  const warnings: string[] = []
  if (form.sampleBookToFloorQty != null && form.sampleBookToFloorQty > 0) {
    if (check.bookToFloorCount < form.sampleBookToFloorQty) {
      warnings.push(
        `账面→实物抽盘 ${check.bookToFloorCount} 项，低于计划预计 ${form.sampleBookToFloorQty} 项`,
      )
    }
  }
  if (form.sampleFloorToBookQty != null && form.sampleFloorToBookQty > 0) {
    if (check.floorToBookCount < form.sampleFloorToBookQty) {
      warnings.push(
        `实物→账面抽盘 ${check.floorToBookCount} 项，低于计划预计 ${form.sampleFloorToBookQty} 项`,
      )
    }
  }
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  if (totals.planAmount > 0 && check.checkedAmount > 0 && check.checkedAmount < totals.planAmount * 0.8) {
    warnings.push(
      `已抽盘金额 ${check.checkedAmount.toLocaleString('zh-CN')} 明显低于计划监盘金额 ${totals.planAmount.toLocaleString('zh-CN')}`,
    )
  }
  return warnings
}

// ─── 结论草稿 ───────────────────────────────────────────────────────────────

export function draftPlanConclusion(form: H1StocktakePlanForm): string {
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  const sug = suggestCoverageByRisk(form.existenceRiskLevel)
  const loc = form.locationScopeNote
    || form.locations.map((l) => l.place || l.warehouse).filter(Boolean).join('、')
    || '（地点待补充）'
  const lines = [
    `经评估，固定资产存在性认定重大错报风险为「${form.existenceRiskLevel || '未评'}」。${form.existenceRiskNote ? form.existenceRiskNote : ''}`,
    `拟于 ${form.plannedDate || '（日期待定）'} 对 ${loc} 实施监盘，方法为${form.method || '抽样盘点'}，程序负责人 ${form.plannedLead || '（待指定）'}。`,
    `计划监盘金额 ${totals.planAmount.toLocaleString('zh-CN')}，账面净值 ${totals.netBookValue.toLocaleString('zh-CN')}，覆盖率 ${totals.coverageRate}%` +
      (form.existenceRiskLevel ? `（${sug.label}）` : '') + '。',
    `双向抽查：账面→实物预计 ${form.sampleBookToFloorQty ?? '—'} 项，实物→账面预计 ${form.sampleFloorToBookQty ?? '—'} 项` +
      (form.plannedRecountRatio != null ? `；预计复盘比例 ${form.plannedRecountRatio}%` : '') + '。',
  ]
  if (form.clientPlanEvaluation) {
    lines.push(`对企业盘点计划的评价：${form.clientPlanEvaluation}`)
  }
  if (form.rollForwardMethod) {
    lines.push(`监盘日与资产负债表日推算：${form.rollForwardMethod}`)
  }
  if (form.competenceNote) {
    lines.push(`专业胜任能力：${form.competenceNote}`)
  }
  lines.push('综上，本监盘计划范围、人员与抽样安排适当，可进入 H1-10 执行盘点检查。')
  return lines.filter(Boolean).join('\n')
}

// ─── 字段映射（H1-9 → H1-11）────────────────────────────────────────────────

export const PLAN_TO_SUMMARY_FIELD_MAP: {
  planField: string
  planLabel: string
  summarySection: string
  summaryField: string
}[] = [
  { planField: 'plannedDate', planLabel: '预计监盘时间', summarySection: '六、实际盘点时间', summaryField: 'actualDate' },
  { planField: 'locations', planLabel: '存放地点表', summarySection: '二、主要资产存放情况', summaryField: 'locations' },
  { planField: 'plannedLead', planLabel: '程序负责人', summarySection: '四、参与盘点人员', summaryField: 'auditorPersonnel' },
  { planField: 'clientPlanArrange', planLabel: '企业盘点安排', summarySection: '七、企业实际盘点情况', summaryField: 'companyPersonnelNote' },
  { planField: 'specialRequirements', planLabel: '特殊要求', summarySection: '七、企业实际盘点情况', summaryField: 'companySpecialNote' },
  { planField: 'method+samples', planLabel: '方法/双向抽查', summarySection: '八、审计人员复盘记录', summaryField: 'samplingMethod' },
  { planField: 'methodDetail', planLabel: '方法说明', summarySection: '八、审计人员复盘记录', summaryField: 'observationMethod' },
  { planField: 'rollForwardMethod', planLabel: '推算方法', summarySection: '一、资产负债表日', summaryField: 'bsDateNote' },
  { planField: 'sampleBookToFloorQty', planLabel: '账面→实物预计数量', summarySection: '十、复盘记录与统计', summaryField: 'recountSampleUnits' },
]

// ─── 上年计划字段抽取 ────────────────────────────────────────────────────────

/** 从上年 H1-9-form JSON 抽取可带入字段（不覆盖策略由调用方决定） */
export function extractPriorYearPlanHints(priorForm: Partial<H1StocktakePlanForm> | null | undefined): Partial<H1StocktakePlanForm> {
  if (!priorForm || typeof priorForm !== 'object') return {}
  return {
    priorYearDate: priorForm.plannedDate || priorForm.priorYearDate || '',
    priorYearStaff: priorForm.plannedLead || priorForm.priorYearStaff || '',
    priorYearScope: priorForm.locationScopeNote
      || (priorForm.categoryScopes || []).map((c) => c.category).filter(Boolean).join('、')
      || priorForm.priorYearScope
      || '',
    priorYearSampleRate: priorForm.plannedRecountRatio != null
      ? `${priorForm.plannedRecountRatio}%`
      : (priorForm.priorYearSampleRate || ''),
    priorYearIssues: priorForm.planConclusion || priorForm.priorYearIssues || '',
  }
}

/** 增强版逻辑告警（含风险覆盖） */
export function calcPlanLogicWarningsEnhanced(form: H1StocktakePlanForm): string[] {
  const base = calcPlanLogicWarnings(form)
  const extra: string[] = []
  if (form.existenceRiskLevel && !isCoverageAdequateForRisk(form)) {
    const sug = suggestCoverageByRisk(form.existenceRiskLevel)
    const t = calcCategoryScopeTotals(form.categoryScopes)
    extra.push(`覆盖率 ${t.coverageRate}% 未达${form.existenceRiskLevel}风险建议 ${sug.minCoverageRate}%`)
  }
  return [...base, ...extra]
}
