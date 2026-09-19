/**
 * i4PolicyLeaseShorter — 装修费/租赁改良「受益期 ≤ 租赁期孰短」规则
 * 数据来源：I4-2 明细 startDate/endDate（或 totalMonths）与表A受益期限
 */
import { parseBenefitPeriodToMonths } from './i4PolicyAmortCrossCheck'

const LEASE_SENSITIVE = new Set(['装修费', '租赁改良'])

export interface LeaseShorterItemIssue {
  category: string
  projectName: string
  declaredMonths: number | null
  leaseMonths: number | null
  ok: boolean
  message: string
}

export interface LeaseShorterCategoryIssue {
  category: string
  severity: 'error' | 'warning' | 'info'
  violatedCount: number
  sampleCount: number
  message: string
  hint?: string
}

export interface LeaseShorterResult {
  items: LeaseShorterItemIssue[]
  byCategory: LeaseShorterCategoryIssue[]
  ok: boolean
  summary: string
}

/** 两日期间隔月数（按日历月近似，至少 1） */
export function monthsBetween(start: string, end: string): number | null {
  const s = String(start || '').slice(0, 10)
  const e = String(end || '').slice(0, 10)
  if (!/^\d{4}-\d{2}-\d{2}$/.test(s) || !/^\d{4}-\d{2}-\d{2}$/.test(e)) return null
  const ds = new Date(s)
  const de = new Date(e)
  if (Number.isNaN(ds.getTime()) || Number.isNaN(de.getTime()) || de < ds) return null
  const months =
    (de.getFullYear() - ds.getFullYear()) * 12
    + (de.getMonth() - ds.getMonth())
    + (de.getDate() >= ds.getDate() ? 0 : -1)
  return Math.max(1, months || 1)
}

function resolveDeclaredMonths(row: any, policyPeriod?: string): number | null {
  const tm = Number(row.totalMonths ?? 0)
  if (tm > 0) return Math.round(tm)
  const fromPolicy = parseBenefitPeriodToMonths(policyPeriod || '')
  if (fromPolicy != null) return fromPolicy
  return parseBenefitPeriodToMonths(String(row.benefitPeriod || row.usefulLife || ''))
}

function resolveLeaseMonths(row: any): number | null {
  const fromDates = monthsBetween(row.startDate || row.occurDate, row.endDate)
  if (fromDates != null) return fromDates
  // 若无结束日但有合同租赁月数字段
  const leaseM = Number(row.leaseMonths ?? row.contractMonths ?? 0)
  return leaseM > 0 ? Math.round(leaseM) : null
}

/**
 * 逐项检查装修/租赁改良是否超过租赁期
 * policyPeriods: 表A类别 → 受益期限（可选，优先于明细）
 */
export function checkLeaseShorterRule(
  detailRows: any[],
  policyPeriods?: Record<string, string>,
): LeaseShorterResult {
  const items: LeaseShorterItemIssue[] = []
  for (const row of detailRows || []) {
    const cat = String(row.expenseType || row.category || '').trim()
    if (!LEASE_SENSITIVE.has(cat)) continue
    const name = String(row.projectName || row.name || cat).trim() || cat
    const leaseMonths = resolveLeaseMonths(row)
    const declaredMonths = resolveDeclaredMonths(row, policyPeriods?.[cat])
    if (leaseMonths == null && declaredMonths == null) {
      items.push({
        category: cat,
        projectName: name,
        declaredMonths: null,
        leaseMonths: null,
        ok: true,
        message: `${name}：缺起止日与期限，无法校验孰短`,
      })
      continue
    }
    if (leaseMonths == null) {
      items.push({
        category: cat,
        projectName: name,
        declaredMonths,
        leaseMonths: null,
        ok: true,
        message: `${name}：无租赁/受益结束日，跳过孰短校验`,
      })
      continue
    }
    if (declaredMonths == null) {
      items.push({
        category: cat,
        projectName: name,
        declaredMonths: null,
        leaseMonths,
        ok: false,
        message: `${name}：租赁约 ${leaseMonths} 月，但未填受益期限`,
      })
      continue
    }
    // 允许 1 月容差
    const ok = declaredMonths <= leaseMonths + 1
    items.push({
      category: cat,
      projectName: name,
      declaredMonths,
      leaseMonths,
      ok,
      message: ok
        ? `${name}：受益 ${declaredMonths} 月 ≤ 租赁 ${leaseMonths} 月`
        : `${name}：受益 ${declaredMonths} 月 > 租赁 ${leaseMonths} 月（违反孰短）`,
    })
  }

  const byCat = new Map<string, LeaseShorterItemIssue[]>()
  for (const it of items) {
    const list = byCat.get(it.category) || []
    list.push(it)
    byCat.set(it.category, list)
  }

  const byCategory: LeaseShorterCategoryIssue[] = [...byCat.entries()].map(([category, list]) => {
    const violated = list.filter((x) => !x.ok)
    const sampleCount = list.filter((x) => x.leaseMonths != null).length
    if (!violated.length) {
      return {
        category,
        severity: 'info' as const,
        violatedCount: 0,
        sampleCount,
        message: `「${category}」孰短校验通过（${sampleCount}项有租赁期）`,
      }
    }
    return {
      category,
      severity: 'error' as const,
      violatedCount: violated.length,
      sampleCount,
      message: `「${category}」${violated.length} 项受益期超过租赁期`,
      hint: violated.slice(0, 3).map((v) => v.message).join('；'),
    }
  })

  const errors = byCategory.filter((c) => c.severity === 'error')
  const ok = errors.length === 0
  const summary = !items.length
    ? '无装修/租赁改良明细'
    : ok
      ? '租赁期孰短校验通过'
      : `孰短未通过：${errors.map((e) => e.category).join('、')}`

  return { items, byCategory, ok, summary }
}

/** 表A 类别级：政策期限 vs 明细租赁期众数/最短 */
export function checkPolicyVsLeaseByCategory(
  policyRows: Array<{ category: string; benefitPeriod?: string }>,
  detailRows: any[],
): LeaseShorterCategoryIssue[] {
  const leaseByCat = new Map<string, number[]>()
  for (const row of detailRows || []) {
    const cat = String(row.expenseType || row.category || '').trim()
    if (!LEASE_SENSITIVE.has(cat)) continue
    const lm = resolveLeaseMonths(row)
    if (lm == null) continue
    const list = leaseByCat.get(cat) || []
    list.push(lm)
    leaseByCat.set(cat, list)
  }

  const out: LeaseShorterCategoryIssue[] = []
  for (const p of policyRows) {
    if (!LEASE_SENSITIVE.has(p.category)) continue
    const leases = leaseByCat.get(p.category)
    if (!leases?.length) continue
    const minLease = Math.min(...leases)
    const declared = parseBenefitPeriodToMonths(p.benefitPeriod || '')
    if (declared == null) continue
    if (declared > minLease + 1) {
      out.push({
        category: p.category,
        severity: 'error',
        violatedCount: 1,
        sampleCount: leases.length,
        message: `表A「${p.category}」受益期「${p.benefitPeriod}」(${declared}月) > 明细最短租赁期 ${minLease} 月`,
        hint: '应按租赁期与预计使用年限孰短确定摊销期',
      })
    }
  }
  return out
}

export default checkLeaseShorterRule
