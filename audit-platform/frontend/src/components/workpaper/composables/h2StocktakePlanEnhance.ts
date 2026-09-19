/**
 * H2-12 监盘计划 — 增强能力
 * H2-2 带入 / 风险建议 / 门禁 / 计划vs执行 / 结论草稿 / 上年带入
 */
import {
  calcCategoryScopeTotals,
  calcPlanLogicWarnings,
  isPlannedRecountRatioValid,
  newCategoryScopeRow,
  newMajorProjectRow,
  newSelectedProject,
  recalcCategoryScopeRow,
  recalcMajorProjectRow,
  type H2StocktakePlanForm,
  type PlanCategoryScopeRow,
  type PlanMajorProjectRow,
  type RiskLevel,
} from './h2StocktakePlanModel'

// ─── H2-2 → 主要工程 / 类别范围 ─────────────────────────────────────────────

export interface H22DetailLike {
  name?: string
  category?: string
  cipEnd?: number
  endAudited?: number
  netValue?: number
  impairmentEnd?: number
  location?: string
  contractor?: string
  completionRate?: number | null
}

/** 按工程类别汇总 H2-2 明细为类别范围行（保留已有 planQty/planAmount） */
export function aggregateH22ToCategoryScopes(
  detailRows: H22DetailLike[],
  existing?: PlanCategoryScopeRow[],
): PlanCategoryScopeRow[] {
  const map = new Map<string, {
    endingBalance: number
    impairment: number
    netBookValue: number
    quantity: number
  }>()

  for (const r of detailRows) {
    const name = String(r.name ?? '').trim()
    if (!name || name.includes('合计')) continue
    const cat = (r.category || '').trim() || '未分类'
    const cur = map.get(cat) || {
      endingBalance: 0,
      impairment: 0,
      netBookValue: 0,
      quantity: 0,
    }
    const ending = Number(r.cipEnd ?? r.endAudited ?? r.netValue) || 0
    const impair = Number(r.impairmentEnd) || 0
    const net = Number(r.netValue) || Math.max(0, ending - impair)
    cur.endingBalance += ending
    cur.impairment += impair
    cur.netBookValue += net
    cur.quantity += 1
    map.set(cat, cur)
  }

  const existingByCat = new Map((existing || []).map((r) => [r.category, r]))
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
      unit: prev?.unit || '项',
      planQty: prev?.planQty ?? 0,
      planAmount: prev?.planAmount ?? 0,
    })))
  }
  return rows.length
    ? rows
    : (existing?.length
      ? existing
      : [newCategoryScopeRow({ seq: 1, category: '自营工程' })])
}

/** 从 H2-2 生成主要工程项目行（按余额降序，默认最多 20） */
export function draftMajorProjectsFromH22(
  detailRows: H22DetailLike[],
  opts?: { maxRows?: number },
): PlanMajorProjectRow[] {
  const maxRows = opts?.maxRows ?? 20
  const mapped = detailRows
    .map((r) => {
      const name = String(r.name ?? '').trim()
      if (!name || name.includes('合计')) return null
      const ending = Number(r.cipEnd ?? r.endAudited ?? r.netValue) || 0
      const impair = Number(r.impairmentEnd) || 0
      const net = Number(r.netValue) || Math.max(0, ending - impair)
      return recalcMajorProjectRow(newMajorProjectRow({
        name,
        originalCost: ending,
        impairment: impair,
        netBookValue: net,
        location: String(r.location || r.contractor || ''),
        note: r.completionRate != null ? `账面完工进度约 ${r.completionRate}%` : '',
      }))
    })
    .filter(Boolean) as PlanMajorProjectRow[]
  mapped.sort((a, b) => (b.netBookValue || 0) - (a.netBookValue || 0))
  return mapped.slice(0, maxRows).map((r, i) => ({ ...r, seq: i + 1 }))
}

export function draftEndingBalanceNoteFromH22(detailRows: H22DetailLike[]): string {
  const rows = detailRows.filter((r) => {
    const name = String(r.name ?? '').trim()
    return name && !name.includes('合计')
  })
  if (!rows.length) return ''
  const total = rows.reduce((s, r) => {
    return s + (Number(r.cipEnd ?? r.endAudited ?? r.netValue) || 0)
  }, 0)
  return `期末在建工程共 ${rows.length} 项，账面余额合计 ${total.toLocaleString('zh-CN', { minimumFractionDigits: 2 })} 元（来源 H2-2）。`
}

export function draftLocationScopeFromH22(detailRows: H22DetailLike[]): string {
  const set = new Set<string>()
  for (const r of detailRows) {
    const loc = String(r.location || r.contractor || '').trim()
    if (loc) set.add(loc)
  }
  return [...set].join('、')
}

/** 按余额重大自动生成拟抽盘工程（仅在 selectedProjects 为空时使用） */
export function draftSelectedProjectsFromMajor(
  majors: PlanMajorProjectRow[],
  opts?: { maxRows?: number; minAmount?: number },
): ReturnType<typeof newSelectedProject>[] {
  const maxRows = opts?.maxRows ?? 8
  const minAmount = opts?.minAmount ?? 0
  return majors
    .filter((m) => m.name && (Number(m.netBookValue) || 0) >= minAmount)
    .slice(0, maxRows)
    .map((m) =>
      newSelectedProject({
        name: m.name,
        reason: '金额重大',
        plannedContent: m.note || '察看形象进度、施工状态、是否停工/达可使用状态',
      }),
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

export function applyRiskSuggestions(
  form: H2StocktakePlanForm,
  opts?: { overwrite?: boolean },
): H2StocktakePlanForm {
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

export function isCoverageAdequateForRisk(form: H2StocktakePlanForm): boolean {
  if (!form.existenceRiskLevel) return true
  const sug = suggestCoverageByRisk(form.existenceRiskLevel)
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  if (totals.netBookValue <= 0) return true
  return totals.coverageRate >= sug.minCoverageRate
}

// ─── 进 H2-13 软门禁 ─────────────────────────────────────────────────────────

export function getPlanGateBlockers(form: H2StocktakePlanForm): string[] {
  const blockers: string[] = []
  if (!form.existenceRiskLevel) blockers.push('未评估存在性认定重大错报风险')
  if (!form.plannedDate) blockers.push('未填写预计监盘时间')
  if (!form.plannedLead) blockers.push('未指定监盘程序负责人')
  const hasScope = form.categoryScopes.some((r) => r.planAmount > 0 || r.planQty > 0)
  if (!hasScope) blockers.push('类别范围未填写计划监盘数量/金额')
  if (!form.selectedProjects.some((p) => p.name.trim())) {
    blockers.push('未选取拟踏勘工程项目')
  }
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

export function isPlanReadyForCheck(form: H2StocktakePlanForm): boolean {
  return getPlanGateBlockers(form).length === 0
}

// ─── 计划 vs 执行勾稽 ───────────────────────────────────────────────────────

export interface PlanVsCheckInput {
  bookToFloorCount: number
  floorToBookCount: number
  checkedAmount: number
}

export function calcPlanVsCheckWarnings(
  form: H2StocktakePlanForm,
  check: PlanVsCheckInput,
): string[] {
  const warnings: string[] = []
  if (form.sampleBookToFloorQty != null && form.sampleBookToFloorQty > 0) {
    if (check.bookToFloorCount < form.sampleBookToFloorQty) {
      warnings.push(
        `账面→现场抽盘 ${check.bookToFloorCount} 项，低于计划预计 ${form.sampleBookToFloorQty} 项`,
      )
    }
  }
  if (form.sampleFloorToBookQty != null && form.sampleFloorToBookQty > 0) {
    if (check.floorToBookCount < form.sampleFloorToBookQty) {
      warnings.push(
        `现场→账面抽盘 ${check.floorToBookCount} 项，低于计划预计 ${form.sampleFloorToBookQty} 项`,
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

export function draftPlanConclusion(form: H2StocktakePlanForm): string {
  const totals = calcCategoryScopeTotals(form.categoryScopes)
  const sug = suggestCoverageByRisk(form.existenceRiskLevel)
  const loc = form.locationScopeNote
    || form.majorProjects.map((l) => l.location).filter(Boolean).join('、')
    || '（地点待补充）'
  const sel = form.selectedProjects.filter((p) => p.name.trim())
  const lines = [
    `经评估，在建工程存在性认定重大错报风险为「${form.existenceRiskLevel || '未评'}」。${form.existenceRiskNote || ''}`,
    `拟于 ${form.plannedDate || '（日期待定）'} 对 ${loc} 实施现场监盘，方法为${form.method || '抽样盘点'}，程序负责人 ${form.plannedLead || '（待指定）'}。`,
    `计划监盘金额 ${totals.planAmount.toLocaleString('zh-CN')}，账面净值 ${totals.netBookValue.toLocaleString('zh-CN')}，覆盖率 ${totals.coverageRate}%` +
      (form.existenceRiskLevel ? `（${sug.label}）` : '') + '。',
    sel.length
      ? `拟踏勘工程 ${sel.length} 项：${sel.slice(0, 5).map((p) => `${p.name}（${p.reason || '—'}）`).join('、')}${sel.length > 5 ? '等' : ''}。`
      : '',
    `双向抽查：账面→现场预计 ${form.sampleBookToFloorQty ?? '—'} 项，现场→账面预计 ${form.sampleFloorToBookQty ?? '—'} 项` +
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
  lines.push('综上，本监盘计划范围、人员与抽样安排适当，可进入 H2-13 执行盘点检查。')
  return lines.filter(Boolean).join('\n')
}

export function extractPriorYearPlanHints(
  priorForm: Partial<H2StocktakePlanForm> | null | undefined,
): Partial<H2StocktakePlanForm> {
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

export function calcPlanLogicWarningsEnhanced(form: H2StocktakePlanForm): string[] {
  const base = calcPlanLogicWarnings(form)
  const extra: string[] = []
  if (form.existenceRiskLevel && !isCoverageAdequateForRisk(form)) {
    const sug = suggestCoverageByRisk(form.existenceRiskLevel)
    const t = calcCategoryScopeTotals(form.categoryScopes)
    extra.push(`覆盖率 ${t.coverageRate}% 未达${form.existenceRiskLevel}风险建议 ${sug.minCoverageRate}%`)
  }
  return [...base, ...extra]
}

export const PLAN_TO_SUMMARY_FIELD_MAP: {
  planField: string
  planLabel: string
  summarySection: string
  summaryField: string
}[] = [
  { planField: 'plannedDate', planLabel: '预计监盘时间', summarySection: '三、实际现场察看时间', summaryField: 'actualDate' },
  { planField: 'plannedLead', planLabel: '程序负责人', summarySection: '三、参与人员', summaryField: 'auditorPersonnel' },
  { planField: 'clientPlanArrange', planLabel: '企业盘点安排', summarySection: '二、盘前了解', summaryField: 'engDept' },
  { planField: 'specialRequirements', planLabel: '特殊要求', summarySection: '二、盘前了解', summaryField: 'policyIndex' },
  { planField: 'method+samples', planLabel: '方法/双向抽查', summarySection: '四、总体核对', summaryField: 'overallSituation' },
  { planField: 'rollForwardMethod', planLabel: '推算方法', summarySection: '一、资产负债表日', summaryField: 'bsDateNote' },
  { planField: 'selectedProjects', planLabel: '拟抽盘工程', summarySection: '四、逐项察看', summaryField: 'projectObservations' },
]
