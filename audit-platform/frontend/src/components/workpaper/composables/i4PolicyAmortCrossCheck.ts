/**
 * i4PolicyAmortCrossCheck — I4-4 表A 与 I4-6/I4-7 测算差异自动勾稽（纯函数）
 *
 * 勾稽维度：
 * 1) 摊销方法：表A vs 测算行众数
 * 2) 受益期限：表A vs 测算使用年限/月限众数（允许同义表述）
 * 3) 重大差异：测算累计/本期差异合计超阈值时，若表A仍判「符合准则/受益模式=Y」则告警
 */
export type CrossSeverity = 'info' | 'warning' | 'error'

export interface AmortAggByCategory {
  category: string
  source: 'I4-6' | 'I4-7' | 'mixed'
  itemCount: number
  amortMethod: string
  benefitPeriod: string
  lifeMonthsMode: number | null
  /** 测算−账面（工作量）或 账面−测算（直线累计差异取绝对值语义：重大未解释差异） */
  periodDiffAbs: number
  accumDiffAbs: number
}

export interface PolicyParamLike {
  category: string
  benefitPeriod?: string
  amortMethod?: string
  meetsStandards?: string
  matchesBenefitPattern?: string
  reasonableVsPeers?: string
  hasChange?: string
  remark?: string
}

export interface CrossCheckIssue {
  id: string
  severity: CrossSeverity
  category: string
  code: 'method-mismatch' | 'period-mismatch' | 'significant-diff' | 'missing-in-amort' | 'missing-in-policy'
  message: string
  hint?: string
}

export interface CrossCheckResult {
  aggs: AmortAggByCategory[]
  issues: CrossCheckIssue[]
  ok: boolean
  summary: string
}

/** 由勾稽结果生成「待关注」备注片段 */
export function buildAttentionRemarksFromIssues(issues: CrossCheckIssue[]): Map<string, string> {
  const map = new Map<string, string>()
  for (const iss of issues.filter((i) => i.severity === 'error' || i.severity === 'warning')) {
    if (!iss.category) continue
    const prev = map.get(iss.category) || ''
    const line = `[勾稽${iss.severity}] ${iss.message}`
    map.set(iss.category, prev ? `${prev}；${line}` : line)
  }
  return map
}

/** 重大差异类问题 → 补提金额建议（按类别） */
export function significantDiffAmounts(
  result: CrossCheckResult,
): Array<{ category: string; amount: number; source: string }> {
  const out: Array<{ category: string; amount: number; source: string }> = []
  const byCat = new Map(result.aggs.map((a) => [a.category, a]))
  const seen = new Set<string>()
  for (const iss of result.issues) {
    if (iss.code !== 'significant-diff' || !iss.category || seen.has(iss.category)) continue
    const agg = byCat.get(iss.category)
    if (!agg) continue
    const amount = Math.max(agg.periodDiffAbs, agg.accumDiffAbs)
    if (amount < DIFF_WARN) continue
    seen.add(iss.category)
    out.push({
      category: iss.category,
      amount: Math.round(amount * 100) / 100,
      source: agg.source === 'I4-7' ? 'I4-7' : 'I4-6',
    })
  }
  return out
}

const DIFF_WARN = 100 // 金额差异提示阈值（元）
const DIFF_ERROR = 10000

function modeOf(arr: string[]): string {
  if (!arr.length) return ''
  const freq = new Map<string, number>()
  for (const x of arr) freq.set(x, (freq.get(x) ?? 0) + 1)
  return [...freq.entries()].sort((a, b) => b[1] - a[1])[0][0]
}

function modeOfNum(arr: number[]): number | null {
  if (!arr.length) return null
  const freq = new Map<number, number>()
  for (const x of arr) freq.set(x, (freq.get(x) ?? 0) + 1)
  return [...freq.entries()].sort((a, b) => b[1] - a[1])[0][0]
}

/** 解析「3年」「36月」「3-5年」「租赁期」等为可比较月数；无法解析返回 null */
export function parseBenefitPeriodToMonths(text: string): number | null {
  const s = String(text || '').trim()
  if (!s) return null
  if (/租赁|合同|受益/.test(s) && !/\d/.test(s)) return null

  const rangeYear = s.match(/(\d+(?:\.\d+)?)\s*[-~～至到]\s*(\d+(?:\.\d+)?)\s*年/)
  if (rangeYear) {
    const a = Number(rangeYear[1])
    const b = Number(rangeYear[2])
    if (Number.isFinite(a) && Number.isFinite(b)) return Math.round(((a + b) / 2) * 12)
  }

  const yearMonth = s.match(/(\d+(?:\.\d+)?)\s*年\s*[（(]?\s*(\d+)\s*月/)
  if (yearMonth) {
    const m = Number(yearMonth[2])
    if (Number.isFinite(m) && m > 0) return m
  }

  const years = s.match(/(\d+(?:\.\d+)?)\s*年/)
  if (years) {
    const y = Number(years[1])
    if (Number.isFinite(y) && y > 0) return Math.round(y * 12)
  }

  const months = s.match(/(\d+)\s*月/)
  if (months) {
    const m = Number(months[1])
    if (Number.isFinite(m) && m > 0) return m
  }

  const bare = Number(s)
  if (Number.isFinite(bare) && bare > 0) {
    // >100 视为月，否则视为年
    return bare > 100 ? Math.round(bare) : Math.round(bare * 12)
  }
  return null
}

function normalizeMethod(m: string): string {
  const s = String(m || '').trim()
  if (!s) return ''
  if (/工作量|产量|产量法/.test(s)) return '工作量法'
  if (/直线/.test(s)) return '直线法'
  return s
}

function periodsCompatible(a: string, b: string): boolean {
  if (!a || !b) return true
  const ma = parseBenefitPeriodToMonths(a)
  const mb = parseBenefitPeriodToMonths(b)
  if (ma != null && mb != null) {
    // 允许 ±1 月或 5% 误差
    const tol = Math.max(1, Math.round(Math.max(ma, mb) * 0.05))
    return Math.abs(ma - mb) <= tol
  }
  // 都含租赁期等定性描述
  if (/租赁/.test(a) && /租赁/.test(b)) return true
  return a.replace(/\s/g, '') === b.replace(/\s/g, '')
}

function monthsToPeriodLabel(months: number | null): string {
  if (months == null || months <= 0) return ''
  if (months % 12 === 0) return `${months / 12}年`
  const y = Math.round((months / 12) * 10) / 10
  return `${y}年（${months}月）`
}

/** 从 I4-6 直线法行聚合 */
export function aggregateI46ByCategory(rows: any[]): AmortAggByCategory[] {
  const map = new Map<string, {
    methods: string[]
    periods: string[]
    months: number[]
    periodDiffAbs: number
    accumDiffAbs: number
    count: number
  }>()
  for (const r of rows || []) {
    const cat = String(r.category ?? r.expenseType ?? '其他').trim() || '其他'
    const usefulLife = String(r.usefulLife ?? '').trim()
    const lifeMonths = Number(r.lifeMonths ?? r.totalMonths ?? 0)
    const periodLabel = usefulLife || monthsToPeriodLabel(lifeMonths > 0 ? lifeMonths : null)
    const cur = map.get(cat) ?? {
      methods: [], periods: [], months: [], periodDiffAbs: 0, accumDiffAbs: 0, count: 0,
    }
    cur.methods.push(normalizeMethod(r.amortMethod ?? r.amortizationMethod ?? '直线法') || '直线法')
    if (periodLabel) cur.periods.push(periodLabel)
    if (lifeMonths > 0) cur.months.push(lifeMonths)
    else {
      const parsed = parseBenefitPeriodToMonths(usefulLife)
      if (parsed) cur.months.push(parsed)
    }
    cur.periodDiffAbs += Math.abs(Number(r.monthlyDiff ?? r.periodDiff ?? 0) || 0)
    cur.accumDiffAbs += Math.abs(Number(r.accumDiff ?? 0) || 0)
    cur.count++
    map.set(cat, cur)
  }
  return [...map.entries()].map(([category, v]) => ({
    category,
    source: 'I4-6' as const,
    itemCount: v.count,
    amortMethod: modeOf(v.methods) || '直线法',
    benefitPeriod: modeOf(v.periods) || monthsToPeriodLabel(modeOfNum(v.months)),
    lifeMonthsMode: modeOfNum(v.months),
    periodDiffAbs: Math.round(v.periodDiffAbs * 100) / 100,
    accumDiffAbs: Math.round(v.accumDiffAbs * 100) / 100,
  }))
}

/** 从 I4-7 工作量法行聚合 */
export function aggregateI47ByCategory(rows: any[]): AmortAggByCategory[] {
  const map = new Map<string, {
    methods: string[]
    periodDiffAbs: number
    accumDiffAbs: number
    count: number
  }>()
  for (const r of rows || []) {
    const cat = String(r.category ?? r.expenseType ?? '其他').trim() || '其他'
    const cur = map.get(cat) ?? {
      methods: [], periodDiffAbs: 0, accumDiffAbs: 0, count: 0,
    }
    cur.methods.push('工作量法')
    cur.periodDiffAbs += Math.abs(Number(r.periodDiff ?? 0) || 0)
    cur.accumDiffAbs += Math.abs(Number(r.accumDiff ?? 0) || 0)
    cur.count++
    map.set(cat, cur)
  }
  return [...map.entries()].map(([category, v]) => ({
    category,
    source: 'I4-7' as const,
    itemCount: v.count,
    amortMethod: '工作量法',
    benefitPeriod: '按工作量',
    lifeMonthsMode: null,
    periodDiffAbs: Math.round(v.periodDiffAbs * 100) / 100,
    accumDiffAbs: Math.round(v.accumDiffAbs * 100) / 100,
  }))
}

function mergeAggs(a: AmortAggByCategory[], b: AmortAggByCategory[]): AmortAggByCategory[] {
  const map = new Map<string, AmortAggByCategory>()
  for (const x of [...a, ...b]) {
    const prev = map.get(x.category)
    if (!prev) {
      map.set(x.category, { ...x })
      continue
    }
    map.set(x.category, {
      category: x.category,
      source: prev.source === x.source ? prev.source : 'mixed',
      itemCount: prev.itemCount + x.itemCount,
      amortMethod: prev.amortMethod === x.amortMethod
        ? prev.amortMethod
        : `${prev.amortMethod}/${x.amortMethod}`,
      benefitPeriod: prev.benefitPeriod || x.benefitPeriod,
      lifeMonthsMode: prev.lifeMonthsMode ?? x.lifeMonthsMode,
      periodDiffAbs: Math.round((prev.periodDiffAbs + x.periodDiffAbs) * 100) / 100,
      accumDiffAbs: Math.round((prev.accumDiffAbs + x.accumDiffAbs) * 100) / 100,
    })
  }
  return [...map.values()]
}

/**
 * 表A 政策参数 vs I4-6/I4-7 测算聚合勾稽
 */
export function crossCheckPolicyVsAmort(
  policyRows: PolicyParamLike[],
  i46Rows: any[],
  i47Rows: any[],
): CrossCheckResult {
  const aggs = mergeAggs(aggregateI46ByCategory(i46Rows), aggregateI47ByCategory(i47Rows))
  const issues: CrossCheckIssue[] = []
  const policyCats = policyRows.filter((r) => r.category?.trim())
  const aggByCat = new Map(aggs.map((a) => [a.category, a]))

  if (!aggs.length) {
    return {
      aggs,
      issues: [{
        id: 'no-amort',
        severity: 'info',
        category: '',
        code: 'missing-in-amort',
        message: 'I4-6/I4-7 暂无测算数据，无法勾稽表A',
        hint: '请先编制摊销测算表',
      }],
      ok: true,
      summary: '测算未就绪',
    }
  }

  for (const p of policyCats) {
    const agg = aggByCat.get(p.category)
    if (!agg) {
      // 表A有类型但测算无 — 仅当表A已填方法/期限时提示
      if (p.amortMethod || p.benefitPeriod) {
        issues.push({
          id: `missing-amort-${p.category}`,
          severity: 'warning',
          category: p.category,
          code: 'missing-in-amort',
          message: `表A「${p.category}」在 I4-6/7 无对应测算行`,
          hint: '核对费用类型命名是否一致，或从 I4-2 带入后再测算',
        })
      }
      continue
    }

    const policyMethod = normalizeMethod(p.amortMethod || '')
    const aggMethod = normalizeMethod(agg.amortMethod)
    if (policyMethod && aggMethod && policyMethod !== aggMethod && !aggMethod.includes(policyMethod)) {
      issues.push({
        id: `method-${p.category}`,
        severity: 'error',
        category: p.category,
        code: 'method-mismatch',
        message: `「${p.category}」摊销方法不一致：表A=${policyMethod}，测算=${agg.amortMethod}`,
        hint: '统一政策表述或修正测算分支（直线法 I4-6 / 工作量法 I4-7）',
      })
    }

    if (agg.source !== 'I4-7' && p.benefitPeriod && agg.benefitPeriod) {
      if (!periodsCompatible(p.benefitPeriod, agg.benefitPeriod)) {
        issues.push({
          id: `period-${p.category}`,
          severity: 'error',
          category: p.category,
          code: 'period-mismatch',
          message: `「${p.category}」受益期限不一致：表A=${p.benefitPeriod}，测算≈${agg.benefitPeriod}`,
          hint: '核对使用月限/租赁期孰短；若本期变更请标记「存在变更」并填表C',
        })
      }
    }

    const maxDiff = Math.max(agg.periodDiffAbs, agg.accumDiffAbs)
    if (maxDiff >= DIFF_ERROR) {
      const positiveJudgment =
        p.meetsStandards === 'Y' || p.matchesBenefitPattern === 'Y'
      issues.push({
        id: `diff-${p.category}`,
        severity: positiveJudgment ? 'error' : 'warning',
        category: p.category,
        code: 'significant-diff',
        message: `「${p.category}」测算差异较大（本期/月摊合计差 ${agg.periodDiffAbs}，累计差 ${agg.accumDiffAbs}）`,
        hint: positiveJudgment
          ? '表A已判「Y」但测算差异重大，请复核判断或提调整（I4-3）'
          : '请在备注说明差异原因，必要时调整政策判断',
      })
    } else if (maxDiff >= DIFF_WARN) {
      issues.push({
        id: `diff-warn-${p.category}`,
        severity: 'warning',
        category: p.category,
        code: 'significant-diff',
        message: `「${p.category}」测算存在可关注差异（累计/本期差约 ${maxDiff}）`,
        hint: '金额不大时可说明后关闭；持续扩大则追查受益期或起算时点',
      })
    }
  }

  for (const agg of aggs) {
    if (!policyCats.some((p) => p.category === agg.category)) {
      issues.push({
        id: `missing-policy-${agg.category}`,
        severity: 'info',
        category: agg.category,
        code: 'missing-in-policy',
        message: `测算有「${agg.category}」但表A未列示`,
        hint: '可从 I4-2 带入或手工新增类型',
      })
    }
  }

  const errors = issues.filter((i) => i.severity === 'error').length
  const warns = issues.filter((i) => i.severity === 'warning').length
  const ok = errors === 0
  const summary = ok
    ? (warns ? `勾稽通过（${warns}项关注）` : '勾稽通过')
    : `勾稽未通过：${errors}项错误 / ${warns}项关注`

  return { aggs, issues, ok, summary }
}

export default crossCheckPolicyVsAmort
