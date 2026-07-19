/**
 * G6 跨实例辅助 — Main(G6-1/G6-2) ↔ SPPI(G6-6) 等
 */
import http from '@/utils/http'
import { parseG6AdjStore } from './g6AdjudicationItems'
import { parseNum } from '@/composables/useG6SppiFormulaEngine'
import type { ChecklistResponse } from './useF1FormData'
import type { G6AdjustmentEntry } from './useG6MainAdjustment'
import {
  createEmptyG6Entry,
  normalizeG6AdjustmentEntry,
  parseG6AdjustmentEntries,
  G6_4_STORAGE_KEY,
} from './useG6MainAdjustment'
import { G6_ITEM_IDS } from './g6StorageContract'

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

/** 拉取项目实际执行重要性（B15 performance materiality） */
export async function fetchPerformanceMateriality(projectId: string): Promise<number | null> {
  if (!projectId) return null
  try {
    const { data } = await http.get(`/api/projects/${projectId}/materiality`, {
      _silent: true,
    } as any)
    const payload = (data as any)?.data ?? data
    const pm =
      payload?.performance_materiality ??
      payload?.performanceMateriality ??
      null
    const n = Number(pm)
    return Number.isFinite(n) && n > 0 ? Math.round(n * 100) / 100 : null
  } catch {
    return null
  }
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

export type G6ResolveOptions = {
  /**
   * 解析失败时是否回退 fallbackWpId。
   * 读操作默认可回退；跨组写操作必须传 false，避免写入错误实例。
   */
  allowFallback?: boolean
}

export type G6ResolveResult = {
  wpId: string | null
  source: 'resolved' | 'fallback' | 'none'
  error?: string
}

async function resolveG6Instance(
  projectId: string,
  sheetCodes: string[],
  fallbackWpId?: string,
  opts?: G6ResolveOptions,
): Promise<G6ResolveResult> {
  const allowFallback = opts?.allowFallback !== false
  if (!projectId) {
    if (allowFallback && fallbackWpId) {
      return { wpId: fallbackWpId, source: 'fallback', error: '缺少 projectId' }
    }
    return { wpId: null, source: 'none', error: '缺少 projectId' }
  }
  for (const sheetCode of sheetCodes) {
    try {
      const { data } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: projectId, parent: 'G6', sheet_code: sheetCode },
        _silent: true,
      } as any)
      const resolved = data?.data?.wp_id ?? data?.wp_id
      if (resolved) return { wpId: String(resolved), source: 'resolved' }
    } catch { /* try next */ }
  }
  if (allowFallback && fallbackWpId) {
    return {
      wpId: fallbackWpId,
      source: 'fallback',
      error: `未解析到实例（已尝试 ${sheetCodes.join('/')}），已回退当前底稿`,
    }
  }
  return {
    wpId: null,
    source: 'none',
    error: `未解析到实例（已尝试 ${sheetCodes.join('/')}）`,
  }
}

/** 解析 Main wp_id（G6-1 / G6 / G6-2） */
export async function resolveG6MainWorkpaperId(
  projectId: string,
  fallbackWpId?: string,
  opts?: G6ResolveOptions,
): Promise<string | null> {
  const result = await resolveG6MainWorkpaperDetailed(projectId, fallbackWpId, opts)
  return result.wpId
}

export async function resolveG6MainWorkpaperDetailed(
  projectId: string,
  fallbackWpId?: string,
  opts?: G6ResolveOptions,
): Promise<G6ResolveResult> {
  return resolveG6Instance(projectId, ['G6-1', 'G6-2', 'G6'], fallbackWpId, opts)
}

/** 解析 ECL 组 wp_id（G6-12 / G6-11 / G6-ECL；不含 Main 的 G6） */
export async function resolveG6EclWorkpaperId(
  projectId: string,
  fallbackWpId?: string,
  opts?: G6ResolveOptions,
): Promise<string | null> {
  const result = await resolveG6EclWorkpaperDetailed(projectId, fallbackWpId, opts)
  return result.wpId
}

export async function resolveG6EclWorkpaperDetailed(
  projectId: string,
  fallbackWpId?: string,
  opts?: G6ResolveOptions,
): Promise<G6ResolveResult> {
  return resolveG6Instance(projectId, ['G6-12', 'G6-11', 'G6-ECL'], fallbackWpId, opts)
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

export const G6_11_ROWS_KEY = G6_ITEM_IDS.G6_11_ROWS
export const G6_12_DATA_KEY = G6_ITEM_IDS.G6_12_DATA
export const G6_12_ROWS_KEY = G6_ITEM_IDS.G6_12_ROWS
export const G6_14_DATA_KEY = G6_ITEM_IDS.G6_14_DATA
export const G6_14_ROWS_KEY = G6_ITEM_IDS.G6_14_ROWS
export const G6_STAGE_UPDATED_EVENT = 'g6-stage-updated'
export const G6_ECL_RATE_UPDATED_EVENT = 'g6:ecl-rate-updated'

/** 解析 checklist 中存的 JSON 行数组（remark/conclusion 双写兼容） */
export function parseG6ChecklistRows(
  resp: { conclusion?: string | null; remark?: string | null } | undefined,
): any[] {
  if (!resp) return []
  for (const raw of [resp.conclusion, resp.remark]) {
    if (!raw) continue
    const rows = parseG6RowsJson(raw)
    if (rows.length) return rows
  }
  return []
}

export const G6_CLASSIFICATION_SUMMARY_KEY = G6_ITEM_IDS.G6_1_CLASSIFICATION_SUMMARY
export const G6_SPPI_CLASSIFICATION_SUMMARY_KEY = G6_ITEM_IDS.G6_SPPI_CLASSIFICATION_SUMMARY

export interface G6ClassificationInstrument {
  instrumentId: string
  instrumentName: string
  businessModel: string | null
  businessModelLabel: string | null
  sppiOverall: string | null
  expectedClassification: string | null
  level: 'ok' | 'info' | 'warning' | null
  message: string
  accountConflict: boolean
}

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
  /** 项目级矩阵（可选；顶层字段仍为组合聚合） */
  instruments?: G6ClassificationInstrument[]
}

export interface G6SaveItemsDetail {
  wpId: string
  items: Array<{ item_id: string; conclusion?: string | null; remark?: string | null }>
}

/** 带 wpId 作用域的保存事件，避免多 G6 根同时挂载时串写 */
export function dispatchG6SaveItems(
  wpId: string,
  items: G6SaveItemsDetail['items'],
): void {
  if (!wpId || !items?.length) return
  try {
    window.dispatchEvent(
      new CustomEvent('g6:save-items', {
        detail: { wpId, items } satisfies G6SaveItemsDetail,
      }),
    )
  } catch { /* silent */ }
}

/** 解析 save-items 事件；wpId 不匹配或缺失时返回 null */
export function matchG6SaveItemsEvent(
  e: Event,
  expectedWpId: string,
): G6SaveItemsDetail['items'] | null {
  const detail = (e as CustomEvent<Partial<G6SaveItemsDetail>>).detail
  if (!detail || detail.wpId !== expectedWpId) return null
  if (!Array.isArray(detail.items) || !detail.items.length) return null
  return detail.items
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
}): Promise<{ mainOk: boolean; sppiOk: boolean; mainWpId: string | null; resolveError?: string }> {
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

  // 跨组写 Main：禁止把 SPPI wp 当 fallback
  const resolved = await resolveG6MainWorkpaperDetailed(
    opts.projectId,
    undefined,
    { allowFallback: false },
  )
  const [mainOk, sppiOk] = await Promise.all([
    resolved.wpId
      ? putG6ChecklistItems(resolved.wpId, opts.projectId, items)
      : Promise.resolve(false),
    putG6ChecklistItems(opts.sppiWpId, opts.projectId, sppiItems),
  ])
  return {
    mainOk,
    sppiOk,
    mainWpId: resolved.wpId,
    resolveError: resolved.wpId ? undefined : resolved.error,
  }
}

export function parseG6ClassificationSummary(
  resp: { conclusion?: string | null; remark?: string | null } | undefined,
): G6ClassificationSummary | null {
  const payload = parseG6ChecklistPayload(resp)
  if (!payload || typeof payload !== 'object') return null
  if (!('expectedClassification' in payload) && !('businessModel' in payload)) return null
  const instruments = Array.isArray(payload.instruments)
    ? payload.instruments
      .filter((row: any) => row && (row.instrumentId || row.instrumentName))
      .map((row: any): G6ClassificationInstrument => ({
        instrumentId: String(row.instrumentId || ''),
        instrumentName: String(row.instrumentName || ''),
        businessModel: row.businessModel ?? null,
        businessModelLabel: row.businessModelLabel ?? null,
        sppiOverall: row.sppiOverall ?? null,
        expectedClassification: row.expectedClassification ?? null,
        level: row.level ?? null,
        message: row.message || '',
        accountConflict: Boolean(row.accountConflict),
      }))
    : undefined
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
    ...(instruments?.length ? { instruments } : {}),
  }
}

export function mapG62RowsToSppiSeeds(rows: any[]): Array<{
  id: string
  name: string
  projectName: string
}> {
  const out: Array<{ id: string; name: string; projectName: string }> = []
  const seenIds = new Set<string>()
  const seenLegacyNames = new Set<string>()
  for (const row of rows || []) {
    const name = String(row?.investProject || row?.invest_project || row?.investmentProject || '').trim()
    if (!name) continue
    const stableId = String(
      row.crossSheetInvestmentId || row.cross_sheet_investment_id || '',
    ).trim()
    const rowId = String(row.id || '').trim()
    const id = stableId || rowId || `g6-2-${normalizeG6InvestName(name)}`
    if (seenIds.has(id)) continue
    const nameKey = normalizeG6InvestName(name)
    // 无稳定 ID 时按项目名去重（兼容旧数据）；有 crossSheet/row id 则允许同名异券
    if (!stableId && !rowId && seenLegacyNames.has(nameKey)) continue
    seenIds.add(id)
    seenLegacyNames.add(nameKey)
    out.push({
      id,
      name,
      projectName: name,
    })
  }
  return out
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
      id: String(row.crossSheetInvestmentId || row.id || `g6-2-${key}`),
      investProject: name,
      faceValue: parseNum(row.faceValue ?? row.face_value),
      couponRate: normalizeG6Rate(row.couponRate ?? row.coupon_rate),
      effectiveRate: normalizeG6Rate(row.effectiveRate ?? row.effective_rate),
      openingAmortized,
    })
  }
  return out
}

/**
 * G6-2 期末摊余成本口径：成本 + 利息调整（不含应计利息）
 */
export function closingAmortizedFromG62Row(row: Record<string, any> | null | undefined): number {
  if (!row) return 0
  const closingCost = parseNum(row.closingCost)
  const closingInterestAdj = parseNum(row.closingInterestAdj)
  let closing = Math.round((closingCost + closingInterestAdj) * 100) / 100
  if (!closing) {
    const sub = parseNum(row.closingSubtotal)
    const accrued = parseNum(row.closingAccruedInterest)
    if (sub) closing = Math.round((sub - accrued) * 100) / 100
  }
  return closing
}

export interface G66EndingCompareInput {
  id?: string
  crossSheetInvestmentId?: string
  investProject?: string
  periods?: Array<{ endingAmortized?: number }>
}

export interface G66EndingCompareRow {
  groupId: string
  investProject: string
  g66Ending: number
  g62Ending: number | null
  diff: number | null
  matched: boolean
}

/**
 * 第三层勾稽：G6-6 各项目末期期末摊余 ↔ G6-2 明细摊余（成本+利息调整）
 */
export function compareG66EndingToG62(
  groups: G66EndingCompareInput[],
  detailRows: any[] | unknown,
  threshold = 0.01,
): G66EndingCompareRow[] {
  const rows = Array.isArray(detailRows) ? detailRows : []
  const byId = new Map(
    rows.map((row) => [String(row.crossSheetInvestmentId || row.id || ''), row] as const),
  )
  const byName = new Map(
    rows.map((row) => [
      normalizeG6InvestName(String(row.investProject ?? row.investmentProject ?? '')),
      row,
    ] as const),
  )

  return (groups || []).map((group) => {
    const id = String(group.crossSheetInvestmentId || group.id || '')
    const name = String(group.investProject || '')
    const nameKey = normalizeG6InvestName(name)
    const detail = (id && byId.get(id)) || (nameKey && byName.get(nameKey)) || undefined
    const periods = group.periods || []
    const last = periods.length ? periods[periods.length - 1] : undefined
    const g66Ending = Math.round((Number(last?.endingAmortized) || 0) * 100) / 100
    if (!detail) {
      return {
        groupId: id || nameKey || name,
        investProject: name || id || '未命名项目',
        g66Ending,
        g62Ending: null,
        diff: null,
        matched: false,
      }
    }
    const g62Ending = closingAmortizedFromG62Row(detail)
    const diff = Math.round((g66Ending - g62Ending) * 100) / 100
    return {
      groupId: id || nameKey || name,
      investProject: name || String(detail.investProject || id),
      g66Ending,
      g62Ending,
      diff,
      matched: Math.abs(diff) < threshold,
    }
  })
}

/** 将 G6-2 明细行映射为 G6-9 盘点种子（名称/代码/面值/账面数量） */
export function mapG62RowsToInventorySeeds(rows: any[]): Array<{
  id: string
  securitiesName: string
  securitiesCode: string
  faceValue: number
  bookQuantity: number
  indexRef: string
}> {
  const out: Array<{
    id: string
    securitiesName: string
    securitiesCode: string
    faceValue: number
    bookQuantity: number
    indexRef: string
  }> = []
  const seen = new Set<string>()
  const seenNames = new Set<string>()

  for (const row of rows || []) {
    const name = String(
      row?.investProject || row?.invest_project || row?.investmentProject || row?.securitiesName || '',
    ).trim()
    if (!name) continue
    const code = String(
      row?.securitiesCode || row?.bondCode || row?.code || row?.securityCode || '',
    ).trim()
    const nameKey = normalizeG6InvestName(name)
    const key = code
      ? `code:${code.replace(/\s+/g, '').toUpperCase()}`
      : `name:${nameKey}`
    if (seen.has(key) || seenNames.has(nameKey)) continue
    seen.add(key)
    seenNames.add(nameKey)

    const bookQuantity = parseNum(
      row.bookQuantity
      ?? row.quantity
      ?? row.holdingQuantity
      ?? row.closingQuantity
      ?? row.auditedQty
      ?? row.unadjustedQty,
    )

    out.push({
      id: String(row.crossSheetInvestmentId || row.id || `g6-2-${normalizeG6InvestName(name)}`),
      securitiesName: name,
      securitiesCode: code,
      faceValue: parseNum(row.faceValue ?? row.face_value),
      bookQuantity,
      indexRef: 'G6-2',
    })
  }
  return out
}

/** 读取 G6-2 资产负债表日 */
export async function fetchG62BalanceSheetDate(
  projectId: string,
  fallbackWpId?: string,
): Promise<string | null> {
  const mainWpId = await resolveG6MainWorkpaperId(projectId, fallbackWpId)
  if (!mainWpId) return null
  const map = await fetchG6ChecklistMap(mainWpId)
  const item = map.get('G6-2-balance-sheet-date')
  const raw = (item?.conclusion || item?.remark || '').trim()
  return raw || null
}

export type G6EclStageSeed = {
  id: string
  investProject: string
  stage: 'Stage1' | 'Stage2' | 'Stage3'
  /** 审定减值准备（优先 adjImpairment，否则 impairmentProvision） */
  openingImpairment: number
}

function normalizeG6Stage(raw: unknown): 'Stage1' | 'Stage2' | 'Stage3' {
  const s = String(raw || '')
  if (s === 'Stage2' || s === 'Stage3') return s
  return 'Stage1'
}

/** 将 G6-12 减值测算行映射为 G6-6 阶段/减值种子 */
export function mapG612RowsToInterestStageSeeds(rows: any[]): G6EclStageSeed[] {
  const out: G6EclStageSeed[] = []
  const seen = new Set<string>()
  for (const row of rows || []) {
    const name = String(row?.investProject || row?.projectName || '').trim()
    if (!name) continue
    const key = normalizeG6InvestName(name)
    if (seen.has(key)) continue
    seen.add(key)
    const stage = normalizeG6Stage(row.stage || row.stageGroup || row.auditStage)
    const impairment = parseNum(
      row.adjImpairment ?? row.impairmentProvision ?? row.openingImpairment,
    )
    out.push({
      id: String(row.id || row.crossSheetInvestmentId || `g6-12-${key}`),
      investProject: name,
      stage,
      openingImpairment: Math.round(impairment * 100) / 100,
    })
  }
  return out
}

/** 拉取 G6-12 减值测算行（跨 ECL 实例；DATA 优先，ROWS 兼容） */
export async function fetchG612ImpairmentRows(
  projectId: string,
  fallbackWpId?: string,
): Promise<any[]> {
  const eclWpId = await resolveG6EclWorkpaperId(projectId, fallbackWpId)
  if (!eclWpId) return []
  const map = await fetchG6ChecklistMap(eclWpId)
  for (const key of [G6_12_DATA_KEY, G6_12_ROWS_KEY]) {
    const item = map.get(key)
    const payload = parseG6ChecklistPayload(item)
    if (Array.isArray(payload) && payload.length) return payload
    if (Array.isArray(payload?.rows) && payload.rows.length) return payload.rows
    const rows = parseG6ChecklistRows(item)
    if (rows.length) return rows
  }
  return []
}

/** 拉取 G6-14 转回核销数据（跨 ECL 实例；DATA 优先，ROWS 兼容） */
export async function fetchG614ReversalWriteOffData(
  projectId: string,
  fallbackWpId?: string,
): Promise<{
  reversals: any[]
  writeOffs: any[]
  rows?: any[]
  conclusion?: string
} | null> {
  const eclWpId = await resolveG6EclWorkpaperId(projectId, fallbackWpId)
  if (!eclWpId) return null
  const map = await fetchG6ChecklistMap(eclWpId)
  for (const key of [G6_14_DATA_KEY, G6_14_ROWS_KEY]) {
    const payload = parseG6ChecklistPayload(map.get(key))
    if (!payload || typeof payload !== 'object') continue
    if (
      Array.isArray(payload.reversals)
      || Array.isArray(payload.writeOffs)
      || Array.isArray(payload.rows)
    ) {
      return {
        reversals: Array.isArray(payload.reversals) ? payload.reversals : [],
        writeOffs: Array.isArray(payload.writeOffs) ? payload.writeOffs : [],
        rows: Array.isArray(payload.rows) ? payload.rows : undefined,
        conclusion: String(payload.conclusion || ''),
      }
    }
  }
  return null
}

export interface G66InterestGroupLike {
  id?: string
  crossSheetInvestmentId?: string
  investProject?: string
  periods?: Array<{ effectiveInterest?: number; cashInflow?: number }>
}

export interface G66InterestWritebackResult<T = Record<string, any>> {
  rows: T[]
  matched: string[]
  unmatched: string[]
  /** 仅匹配行的 Σ(实际利息−票息)，用于预览合计 */
  matchedAdjustmentTotal: number
}

/**
 * G6-6 → G6-2：回写本期利息调整变动 = Σ(实际利息 − 票息)，并重算依赖利息调整的期末列。
 * 不改写 closingCost / closingAccruedInterest（避免覆盖手工期末成本/应计）。
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
  let matchedAdjustmentTotal = 0

  for (const group of groups || []) {
    const id = String(group.crossSheetInvestmentId || group.id || '')
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
    matchedAdjustmentTotal = Math.round((matchedAdjustmentTotal + adj) * 100) / 100
    row.periodInterestAdjChange = adj
    row.periodChangeSubtotal = Math.round((
      (Number(row.periodCostChange) || 0)
      + adj
      + (Number(row.periodAccruedInterestChange) || 0)
    ) * 100) / 100
    row.closingInterestAdj = Math.round((
      (Number(row.openingInterestAdj) || 0) + adj
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

  return { rows, matched, unmatched, matchedAdjustmentTotal }
}

/** 将明细行写回 Main 实例 G6-2-rows（跨 SPPI→Main；禁止 fallback） */
export async function saveG62DetailRows(
  projectId: string,
  rows: any[],
  _fallbackWpId?: string,
): Promise<string | null> {
  const resolved = await resolveG6MainWorkpaperDetailed(
    projectId,
    undefined,
    { allowFallback: false },
  )
  if (!resolved.wpId) return null
  const mainWpId = resolved.wpId
  const json = JSON.stringify(rows)
  await http.put(`/api/workpapers/${mainWpId}/checklist-responses`, {
    project_id: projectId,
    items: [{
      item_id: G6_ITEM_IDS.G6_2_ROWS,
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

// ─── G6-9 → G6-4 调整草稿 ───────────────────────────────────────────────────

export type G69VarianceAmountEstimate = {
  amount: number
  basis: string
}

/** 由数量差异估算调整金额（草稿，需人工确认） */
export function estimateG69VarianceAmount(item: {
  variance?: number
  faceValue?: number
  bookQuantity?: number
  countQuantity?: number
}): G69VarianceAmountEstimate {
  const qtyVar = Math.abs(parseNum(item.variance))
  if (qtyVar === 0) return { amount: 0, basis: '无差异' }
  const face = parseNum(item.faceValue)
  const bookQty = parseNum(item.bookQuantity)
  if (face > 0 && bookQty > 0) {
    const unit = face / bookQty
    return {
      amount: Math.round(qtyVar * unit * 100) / 100,
      basis: `数量差异 ${qtyVar} × 单位面值 ${unit.toFixed(4)}（面值/账面数量）`,
    }
  }
  if (face > 0) {
    return {
      amount: Math.round(qtyVar * face * 100) / 100,
      basis: `数量差异 ${qtyVar} × 面值 ${face}（按单位面值假设）`,
    }
  }
  return { amount: 0, basis: '缺少面值，无法估算金额' }
}

export type G69AdjDraftPair = {
  sourceId: string
  securitiesName: string
  variance: number
  amount: number
  amountBasis: string
  direction: 'surplus' | 'shortage'
  entries: G6AdjustmentEntry[]
}

function g69DraftEntryId(sourceId: string, side: 'dr' | 'cr'): string {
  return `g69-${sourceId}-${side}`
}

/**
 * 将 G6-9 账实数量差异转为 G6-4 借贷成对草稿。
 * - 盘盈(variance>0)：借 成本 / 贷 投资收益
 * - 盘亏(variance<0)：借 投资收益 / 贷 成本
 * 金额为估算值，写入前须人工确认。
 */
export function buildG69VarianceAdjustmentDrafts(
  items: Array<{
    id: string
    securitiesName: string
    securitiesCode?: string
    variance: number
    faceValue?: number
    bookQuantity?: number
    countQuantity?: number
    varianceReason?: string
    varianceConclusion?: string
    indexRef?: string
  }>,
  opts?: { onlyProposedAdjust?: boolean },
): { pairs: G69AdjDraftPair[]; skipped: Array<{ name: string; reason: string }> } {
  const pairs: G69AdjDraftPair[] = []
  const skipped: Array<{ name: string; reason: string }> = []
  const onlyProposed = opts?.onlyProposedAdjust !== false

  for (const item of items || []) {
    const variance = parseNum(item.variance)
    if (variance === 0) continue
    const name = (item.securitiesName || '').trim() || '未命名证券'
    const conclusion = String(item.varianceConclusion || '')
    const isProposed = /拟调整|需调整|建议调整|调整入账/.test(conclusion)
    if (onlyProposed && !isProposed) {
      skipped.push({ name, reason: '差异结论未标注拟调整（可改为包含“拟调整”后重试，或关闭筛选）' })
      continue
    }
    const est = estimateG69VarianceAmount(item)
    if (est.amount <= 0) {
      skipped.push({ name, reason: est.basis })
      continue
    }

    const direction: 'surplus' | 'shortage' = variance > 0 ? 'surplus' : 'shortage'
    const reason = String(item.varianceReason || '').trim() || '账实数量不符'
    const descBase = `G6-9盘点差异-${name}${item.securitiesCode ? `(${item.securitiesCode})` : ''}：数量差${variance}，${reason}`
    const remark = `source=G6-9;sourceId=${item.id};variance=${variance};basis=${est.basis}`

    const cost = createEmptyG6Entry(1, descBase)
    cost.id = g69DraftEntryId(item.id, direction === 'surplus' ? 'dr' : 'cr')
    cost.rowId = cost.id
    cost.accountCode = '150301'
    cost.accountName = '其他债权投资——成本'
    cost.category = '账项调整'
    cost.entryType = 'AJE'
    cost.indexRef = item.indexRef || 'G6-9'
    cost.remark = remark
    cost.summary = descBase

    const contra = createEmptyG6Entry(1, descBase)
    contra.id = g69DraftEntryId(item.id, direction === 'surplus' ? 'cr' : 'dr')
    contra.rowId = contra.id
    contra.accountCode = '6111'
    contra.accountName = '投资收益'
    contra.category = '账项调整'
    contra.entryType = 'AJE'
    contra.indexRef = item.indexRef || 'G6-9'
    contra.remark = remark
    contra.summary = descBase

    if (direction === 'surplus') {
      cost.debitAmount = est.amount
      cost.creditAmount = 0
      contra.debitAmount = 0
      contra.creditAmount = est.amount
    } else {
      cost.debitAmount = 0
      cost.creditAmount = est.amount
      contra.debitAmount = est.amount
      contra.creditAmount = 0
    }

    pairs.push({
      sourceId: item.id,
      securitiesName: name,
      variance,
      amount: est.amount,
      amountBasis: est.basis,
      direction,
      entries: [normalizeG6AdjustmentEntry(cost, 0), normalizeG6AdjustmentEntry(contra, 1)],
    })
  }

  return { pairs, skipped }
}

/** 合并草稿：同 sourceId 的旧 g69-* 分录先移除再追加 */
export function mergeG64EntriesWithG69Drafts(
  existing: G6AdjustmentEntry[],
  draftPairs: G69AdjDraftPair[],
): G6AdjustmentEntry[] {
  const sourceIds = new Set(draftPairs.map((p) => p.sourceId))
  const kept = (existing || []).filter((e) => {
    const id = String(e.id || '')
    const remark = String(e.remark || '')
    for (const sid of sourceIds) {
      if (id.startsWith(`g69-${sid}-`)) return false
      if (remark.includes(`sourceId=${sid}`)) return false
    }
    return true
  })
  const appended = draftPairs.flatMap((p) => p.entries)
  const merged = [...kept, ...appended]
  return merged.map((e, i) => normalizeG6AdjustmentEntry({ ...e, seq: i + 1 }, i))
}

export async function fetchG64AdjustmentEntries(
  projectId: string,
  fallbackWpId?: string,
): Promise<{ mainWpId: string | null; entries: G6AdjustmentEntry[] }> {
  const mainWpId = await resolveG6MainWorkpaperId(projectId, fallbackWpId)
  if (!mainWpId) return { mainWpId: null, entries: [] }
  const map = await fetchG6ChecklistMap(mainWpId)
  const entries = parseG6AdjustmentEntries(map.get(G6_4_STORAGE_KEY))
  return { mainWpId, entries }
}

export async function saveG64AdjustmentEntries(
  projectId: string,
  entries: G6AdjustmentEntry[],
  _fallbackWpId?: string,
): Promise<string | null> {
  const resolved = await resolveG6MainWorkpaperDetailed(
    projectId,
    undefined,
    { allowFallback: false },
  )
  if (!resolved.wpId) return null
  const mainWpId = resolved.wpId
  const json = JSON.stringify(entries)
  const ok = await putG6ChecklistItems(mainWpId, projectId, [
    { item_id: G6_4_STORAGE_KEY, conclusion: json, remark: json },
  ])
  return ok ? mainWpId : null
}

// ─── G6-6 → G6-4 利息勾稽差异调整草稿 ───────────────────────────────────────

export type G66AdjDraftLayer = 'amortization' | 'income'

export type G66AdjDraftPair = {
  layer: G66AdjDraftLayer
  layerLabel: string
  diff: number
  amount: number
  entries: G6AdjustmentEntry[]
}

function g66DraftEntryId(layer: G66AdjDraftLayer, side: 'dr' | 'cr'): string {
  return `g66-${layer}-${side}`
}

/**
 * 将 G6-6 超 B15 的勾稽差异转为 G6-4 借贷草稿（须人工确认后写入）。
 * - 摊销层（实际利息−票息 − G6-1利息调整变动）：借/贷 150302 利息调整 ↔ 6111 投资收益
 * - 损益层（实际利息 − 账面利息，仅已填账面时）：同上科目对，金额按 incomeDiff
 * diff>0 表示测算大于账面（漏记收入/利息调整）→ 借 150302 / 贷 6111
 */
export function buildG66InterestVarianceAdjustmentDrafts(input: {
  amortizationDiff: number
  incomeDiff: number
  incomeLayerActive?: boolean
  performanceMateriality?: number
  varianceReason?: string
  /** 默认仅生成 |diff| > B15（或 B15 未取到时 >0.01）的层 */
  onlyMaterial?: boolean
}): { pairs: G66AdjDraftPair[]; skipped: Array<{ layer: string; reason: string }> } {
  const pairs: G66AdjDraftPair[] = []
  const skipped: Array<{ layer: string; reason: string }> = []
  const pm = parseNum(input.performanceMateriality)
  const threshold = pm > 0 ? pm : 0.01
  const onlyMaterial = input.onlyMaterial !== false
  const reason = String(input.varianceReason || '').trim() || 'G6-6勾稽差异待调整'

  const layers: Array<{
    layer: G66AdjDraftLayer
    label: string
    diff: number
    active: boolean
  }> = [
    {
      layer: 'amortization',
      label: '摊销层（实际利息−票息 vs G6-1利息调整变动）',
      diff: parseNum(input.amortizationDiff),
      active: true,
    },
    {
      layer: 'income',
      label: '损益层（实际利息 vs 账面利息收入）',
      diff: parseNum(input.incomeDiff),
      active: Boolean(input.incomeLayerActive),
    },
  ]

  for (const item of layers) {
    if (!item.active) {
      skipped.push({ layer: item.label, reason: '该层未启用（账面利息未填）' })
      continue
    }
    const abs = Math.abs(item.diff)
    if (abs < 0.01) {
      skipped.push({ layer: item.label, reason: '差异可忽略（<0.01）' })
      continue
    }
    if (onlyMaterial && abs <= threshold) {
      skipped.push({
        layer: item.label,
        reason: `差异 ${abs.toFixed(2)} 未超过阈值 ${threshold.toFixed(2)}`,
      })
      continue
    }

    const amount = Math.round(abs * 100) / 100
    const understated = item.diff > 0 // 测算 > 账面 → 漏记
    const descBase = `G6-6利息勾稽-${item.label}：差异${item.diff.toFixed(2)}，${reason}`
    const remark = `source=G6-6;layer=${item.layer};diff=${item.diff};threshold=${threshold}`

    const adj = createEmptyG6Entry(1, descBase)
    adj.id = g66DraftEntryId(item.layer, understated ? 'dr' : 'cr')
    adj.rowId = adj.id
    adj.accountCode = '150302'
    adj.accountName = '其他债权投资——利息调整'
    adj.category = '账项调整'
    adj.entryType = 'AJE'
    adj.indexRef = 'G6-6'
    adj.remark = remark
    adj.summary = descBase
    adj.reportItem = '其他债权投资'

    const income = createEmptyG6Entry(1, descBase)
    income.id = g66DraftEntryId(item.layer, understated ? 'cr' : 'dr')
    income.rowId = income.id
    income.accountCode = '6111'
    income.accountName = '投资收益'
    income.category = '账项调整'
    income.entryType = 'AJE'
    income.indexRef = 'G6-6'
    income.remark = remark
    income.summary = descBase
    income.reportItem = '投资收益'

    if (understated) {
      adj.debitAmount = amount
      adj.creditAmount = 0
      income.debitAmount = 0
      income.creditAmount = amount
    } else {
      adj.debitAmount = 0
      adj.creditAmount = amount
      income.debitAmount = amount
      income.creditAmount = 0
    }

    pairs.push({
      layer: item.layer,
      layerLabel: item.label,
      diff: item.diff,
      amount,
      entries: [normalizeG6AdjustmentEntry(adj, 0), normalizeG6AdjustmentEntry(income, 1)],
    })
  }

  return { pairs, skipped }
}

/** 合并草稿：同 layer 的旧 g66-* 分录先移除再追加 */
export function mergeG64EntriesWithG66Drafts(
  existing: G6AdjustmentEntry[],
  draftPairs: G66AdjDraftPair[],
): G6AdjustmentEntry[] {
  const layers = new Set(draftPairs.map((p) => p.layer))
  const kept = (existing || []).filter((e) => {
    const id = String(e.id || '')
    const remark = String(e.remark || '')
    for (const layer of layers) {
      if (id.startsWith(`g66-${layer}-`)) return false
      if (remark.includes(`source=G6-6`) && remark.includes(`layer=${layer}`)) return false
    }
    return true
  })
  const appended = draftPairs.flatMap((p) => p.entries)
  const merged = [...kept, ...appended]
  return merged.map((e, i) => normalizeG6AdjustmentEntry({ ...e, seq: i + 1 }, i))
}
