/**
 * G6 跨实例辅助 — Main(G6-1/G6-2) ↔ SPPI(G6-6) 等
 */
import http from '@/utils/http'
import { parseG6AdjStore } from './g6AdjudicationItems'
import { parseNum } from '@/composables/useG6SppiFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'

export function normalizeG6InvestName(name: string): string {
  return String(name || '').trim().replace(/\s+/g, '')
}

/**
 * 利率归一化为小数（0.05 = 5%）。
 * |x|>1 按百分数启发式（与后端 _rate_to_decimal 一致）。
 */
export function normalizeG6Rate(value: unknown): number {
  const num = parseNum(value)
  if (!Number.isFinite(num) || num === 0) return 0
  if (Math.abs(num) > 1) return Math.round((num / 100) * 1e8) / 1e8
  return num
}

export function parseG6RowsJson(raw: string | null | undefined): any[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed
    if (Array.isArray(parsed?.rows)) return parsed.rows
    if (Array.isArray(parsed?.groups)) return parsed.groups
  } catch { /* ignore */ }
  return []
}

export function parseG6ChecklistPayload(
  resp: { conclusion?: string | null; remark?: string | null } | undefined,
): any {
  if (!resp) return null
  for (const raw of [resp.conclusion, resp.remark]) {
    if (!raw) continue
    try {
      return JSON.parse(raw)
    } catch { /* ignore */ }
  }
  return null
}

/** 解析 Main wp_id（G6-1 / G6 / G6-2） */
export async function resolveG6MainWorkpaperId(
  projectId: string,
  fallbackWpId?: string,
): Promise<string | null> {
  if (!projectId) return fallbackWpId || null
  for (const sheetCode of ['G6-1', 'G6-2', 'G6']) {
    try {
      const { data } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: projectId, parent: 'G6', sheet_code: sheetCode },
        _silent: true,
      } as any)
      const resolved = data?.data?.wp_id ?? data?.wp_id
      if (resolved) return String(resolved)
    } catch { /* try next */ }
  }
  return fallbackWpId || null
}

export async function fetchG6ChecklistMap(wpId: string): Promise<Map<string, ChecklistResponse>> {
  const map = new Map<string, ChecklistResponse>()
  if (!wpId) return map
  try {
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`)
    const responses: any[] = Array.isArray(data) ? data : (data?.data ?? [])
    for (const item of responses) {
      if (!item?.item_id) continue
      map.set(String(item.item_id), {
        item_id: String(item.item_id),
        conclusion: item.conclusion ?? null,
        remark: item.remark ?? null,
      })
    }
  } catch { /* ignore */ }
  return map
}

/** 拉取 G6-2 明细行（跨 Main 实例） */
export async function fetchG62DetailRows(
  projectId: string,
  fallbackWpId?: string,
): Promise<any[]> {
  const mainWpId = await resolveG6MainWorkpaperId(projectId, fallbackWpId)
  if (!mainWpId) return []
  const map = await fetchG6ChecklistMap(mainWpId)
  const item = map.get('G6-2-rows')
  const payload = parseG6ChecklistPayload(item)
  if (Array.isArray(payload)) return payload
  if (Array.isArray(payload?.rows)) return payload.rows
  return parseG6RowsJson(item?.conclusion) || parseG6RowsJson(item?.remark)
}

/**
 * G6-1 利息调整本期变动合计
 * = Σ(interest-individual / interest-portfolio) 的 (期末审定 − 期初审定)
 */
export async function fetchG61InterestAdjPeriodChange(
  projectId: string,
  fallbackWpId?: string,
): Promise<number | null> {
  const mainWpId = await resolveG6MainWorkpaperId(projectId, fallbackWpId)
  if (!mainWpId) return null
  const map = await fetchG6ChecklistMap(mainWpId)
  const raw = map.get('G6-1-rows')?.conclusion || map.get('G6-1-rows')?.remark
  const store = parseG6AdjStore(raw)
  if (!Object.keys(store).length) return null

  let total = 0
  for (const key of ['interest-individual', 'interest-portfolio']) {
    const cell = store[key]
    if (!cell) continue
    const opening = parseNum(cell.openingUnadjusted) + parseNum(cell.openingAdjustment)
    const closing = parseNum(cell.closingUnadjusted) + parseNum(cell.closingAdjustment)
    total += closing - opening
  }
  return Math.round(total * 100) / 100
}

export const G6_CLASSIFICATION_SUMMARY_KEY = 'G6-1-classification-summary'
export const G6_SPPI_CLASSIFICATION_SUMMARY_KEY = 'G6-sppi-classification-summary'

export interface G6ClassificationSummary {
  businessModel: string | null
  businessModelLabel: string | null
  sppiOverall: string | null
  expectedClassification: string | null
  level: 'ok' | 'info' | 'warning' | null
  message: string
  accountConflict: boolean
  updatedAt: string
  source: string
}

export interface G62SaleSummary {
  projectCount: number
  openingTotal: number
  /** 出售/减少代理金额：优先 periodDecrease，否则取负的 periodCostChange */
  decreaseProxy: number
  ratio: number | null
  draftText: string
  method: 'periodDecrease' | 'negativeCostChange' | 'none'
}

function rowOpeningBalance(row: any): number {
  const sub = parseNum(row?.openingSubtotal)
  if (sub) return sub
  return Math.round((
    parseNum(row?.openingCost) +
    parseNum(row?.openingInterestAdj) +
    parseNum(row?.openingAccruedInterest)
  ) * 100) / 100
}

function rowDecreaseProxy(row: any): { amount: number; method: 'periodDecrease' | 'negativeCostChange' | 'none' } {
  const explicit = parseNum(row?.periodDecrease ?? row?.period_decrease)
  if (explicit > 0) return { amount: explicit, method: 'periodDecrease' }
  const costChange = parseNum(row?.periodCostChange ?? row?.period_cost_change)
  if (costChange < 0) return { amount: Math.abs(costChange), method: 'negativeCostChange' }
  return { amount: 0, method: 'none' }
}

/** 从 G6-2 行估算出售/减少规模（净减少代理；有 periodDecrease 时更准） */
export function summarizeG62SaleActivity(rows: any[]): G62SaleSummary {
  let openingTotal = 0
  let decreaseProxy = 0
  let method: G62SaleSummary['method'] = 'none'
  let projectCount = 0

  for (const row of rows || []) {
    const name = String(row?.investProject || row?.invest_project || '').trim()
    if (!name && !rowOpeningBalance(row) && !rowDecreaseProxy(row).amount) continue
    projectCount++
    openingTotal += rowOpeningBalance(row)
    const dec = rowDecreaseProxy(row)
    decreaseProxy += dec.amount
    if (dec.method === 'periodDecrease') method = 'periodDecrease'
    else if (dec.method === 'negativeCostChange' && method !== 'periodDecrease') method = 'negativeCostChange'
  }

  openingTotal = Math.round(openingTotal * 100) / 100
  decreaseProxy = Math.round(decreaseProxy * 100) / 100
  const ratio = openingTotal > 0.005 ? Math.round((decreaseProxy / openingTotal) * 10000) / 10000 : null

  const methodNote =
    method === 'periodDecrease'
      ? '依据 G6-2 periodDecrease 汇总'
      : method === 'negativeCostChange'
        ? '依据 G6-2 成本净减少（periodCostChange<0）代理，购入与出售轧差后可能低估/高估出售规模'
        : 'G6-2 未识别到减少额'

  const draftText =
    method === 'none'
      ? ''
      : [
          `【系统根据 G6-2 预填，可修改】本期投资项目 ${projectCount} 个；`,
          `期初账面余额合计约 ${openingTotal.toLocaleString('zh-CN')}；`,
          `本期减少/出售代理金额约 ${decreaseProxy.toLocaleString('zh-CN')}`,
          ratio != null ? `，约占期初 ${((ratio || 0) * 100).toFixed(2)}%。` : '。',
          `（${methodNote}）`,
        ].join('')

  return { projectCount, openingTotal, decreaseProxy, ratio, draftText, method }
}

export async function putG6ChecklistItems(
  wpId: string,
  projectId: string,
  items: Array<{ item_id: string; conclusion?: string | null; remark?: string | null }>,
): Promise<boolean> {
  if (!wpId || !items.length) return false
  try {
    await http.put(`/api/workpapers/${wpId}/checklist-responses`, {
      project_id: projectId,
      items: items.map((item) => ({
        item_id: item.item_id,
        conclusion: item.conclusion ?? null,
        remark: item.remark ?? null,
      })),
    }, { _silent: true } as any)
    return true
  } catch {
    return false
  }
}

/** 将 G6-7×G6-8 分类摘要写回 Main（G6-1）及当前 SPPI 实例 */
export async function writeG6ClassificationSummary(opts: {
  projectId: string
  sppiWpId: string
  summary: G6ClassificationSummary
}): Promise<{ mainOk: boolean; sppiOk: boolean }> {
  const payload = JSON.stringify(opts.summary)
  const items = [
    {
      item_id: G6_CLASSIFICATION_SUMMARY_KEY,
      conclusion: opts.summary.expectedClassification,
      remark: payload,
    },
  ]
  const sppiItems = [
    {
      item_id: G6_SPPI_CLASSIFICATION_SUMMARY_KEY,
      conclusion: opts.summary.expectedClassification,
      remark: payload,
    },
  ]

  const mainWpId = await resolveG6MainWorkpaperId(opts.projectId, opts.sppiWpId)
  const [mainOk, sppiOk] = await Promise.all([
    mainWpId
      ? putG6ChecklistItems(mainWpId, opts.projectId, items)
      : Promise.resolve(false),
    putG6ChecklistItems(opts.sppiWpId, opts.projectId, sppiItems),
  ])
  return { mainOk, sppiOk }
}

export function parseG6ClassificationSummary(
  resp: { conclusion?: string | null; remark?: string | null } | undefined,
): G6ClassificationSummary | null {
  const payload = parseG6ChecklistPayload(resp)
  if (!payload || typeof payload !== 'object') return null
  if (!('expectedClassification' in payload) && !('businessModel' in payload)) return null
  return {
    businessModel: payload.businessModel ?? null,
    businessModelLabel: payload.businessModelLabel ?? null,
    sppiOverall: payload.sppiOverall ?? null,
    expectedClassification: payload.expectedClassification ?? null,
    level: payload.level ?? null,
    message: payload.message || '',
    accountConflict: Boolean(payload.accountConflict),
    updatedAt: payload.updatedAt || '',
    source: payload.source || '',
  }
}

/** 将 G6-2 明细行映射为 G6-6 利息测算分组种子 */
export function mapG62RowsToInterestSeeds(rows: any[]): Array<{
  id: string
  investProject: string
  faceValue: number
  couponRate: number
  effectiveRate: number
  openingAmortized: number
}> {
  const out: Array<{
    id: string
    investProject: string
    faceValue: number
    couponRate: number
    effectiveRate: number
    openingAmortized: number
  }> = []
  const seen = new Set<string>()

  for (const row of rows || []) {
    const name = String(row?.investProject || row?.invest_project || '').trim()
    if (!name) continue
    const key = normalizeG6InvestName(name)
    if (seen.has(key)) continue
    seen.add(key)

    const openingSubtotal = parseNum(row.openingSubtotal)
    const openingCost = parseNum(row.openingCost)
    const openingInterestAdj = parseNum(row.openingInterestAdj)
    const openingAccrued = parseNum(row.openingAccruedInterest)
    // 摊余成本口径：成本 + 利息调整（不含应计利息）
    let openingAmortized = Math.round((openingCost + openingInterestAdj) * 100) / 100
    if (!openingAmortized && openingSubtotal) {
      openingAmortized = Math.round((openingSubtotal - openingAccrued) * 100) / 100
    }

    out.push({
      id: String(row.id || row.crossSheetInvestmentId || `g6-2-${key}`),
      investProject: name,
      faceValue: parseNum(row.faceValue ?? row.face_value),
      couponRate: normalizeG6Rate(row.couponRate ?? row.coupon_rate),
      effectiveRate: normalizeG6Rate(row.effectiveRate ?? row.effective_rate),
      openingAmortized,
    })
  }
  return out
}

export interface G66InterestGroupLike {
  id?: string
  investProject?: string
  periods?: Array<{ effectiveInterest?: number; cashInflow?: number }>
}

export interface G66InterestWritebackResult<T = Record<string, any>> {
  rows: T[]
  matched: string[]
  unmatched: string[]
}

/**
 * G6-6 → G6-2：回写本期利息调整变动 = Σ(实际利息 − 票息)，并重算相关期末公式列。
 */
export function applyG66InterestToDetailRows<T extends Record<string, any>>(
  existing: T[] | unknown,
  groups: G66InterestGroupLike[],
): G66InterestWritebackResult<T> {
  const rows = Array.isArray(existing) ? existing.map((row) => ({ ...row })) as T[] : []
  const byId = new Map(
    rows.map((row) => [String(row.crossSheetInvestmentId || row.id || ''), row] as const),
  )
  const byName = new Map(
    rows.map((row) => [
      normalizeG6InvestName(String(row.investProject ?? row.investmentProject ?? '')),
      row,
    ] as const),
  )
  const matched: string[] = []
  const unmatched: string[] = []

  for (const group of groups || []) {
    const id = String(group.id || '')
    const name = normalizeG6InvestName(group.investProject || '')
    const row = (id && byId.get(id)) || (name && byName.get(name)) || undefined
    const label = String(group.investProject || id || '未命名项目')
    if (!row) {
      unmatched.push(label)
      continue
    }

    const adjustment = (group.periods || []).reduce(
      (sum, period) =>
        sum + (Number(period.effectiveInterest) || 0) - (Number(period.cashInflow) || 0),
      0,
    )
    const adj = Math.round(adjustment * 100) / 100
    row.periodInterestAdjChange = adj
    row.periodChangeSubtotal = Math.round((
      (Number(row.periodCostChange) || 0)
      + adj
      + (Number(row.periodAccruedInterestChange) || 0)
    ) * 100) / 100
    row.closingInterestAdj = Math.round((
      (Number(row.openingInterestAdj) || 0) + adj
    ) * 100) / 100
    row.closingCost = Math.round((
      (Number(row.openingCost) || 0) + (Number(row.periodCostChange) || 0)
    ) * 100) / 100
    row.closingAccruedInterest = Math.round((
      (Number(row.openingAccruedInterest) || 0) + (Number(row.periodAccruedInterestChange) || 0)
    ) * 100) / 100
    row.closingSubtotal = Math.round((
      (Number(row.closingCost) || 0)
      + (Number(row.closingInterestAdj) || 0)
      + (Number(row.closingAccruedInterest) || 0)
    ) * 100) / 100
    row.interestWritebackSource = 'G6-6'
    row.interestWritebackUpdatedAt = new Date().toISOString()
    matched.push(String(row.investProject || label))
  }

  return { rows, matched, unmatched }
}

/** 将明细行写回 Main 实例 G6-2-rows（跨 SPPI→Main） */
export async function saveG62DetailRows(
  projectId: string,
  rows: any[],
  fallbackWpId?: string,
): Promise<string | null> {
  const mainWpId = await resolveG6MainWorkpaperId(projectId, fallbackWpId)
  if (!mainWpId) return null
  const json = JSON.stringify(rows)
  await http.put(`/api/workpapers/${mainWpId}/checklist-responses`, {
    project_id: projectId,
    items: [{
      item_id: 'G6-2-rows',
      conclusion: json,
      remark: json,
    }],
  })
  try {
    window.dispatchEvent(new CustomEvent('g6:interest-writeback', {
      detail: { wpId: mainWpId, rows },
    }))
  } catch { /* ignore */ }
  return mainWpId
}
