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
    const openingAmortized =
      openingSubtotal ||
      Math.round((openingCost + openingInterestAdj + openingAccrued) * 100) / 100

    out.push({
      id: String(row.id || row.crossSheetInvestmentId || `g6-2-${key}`),
      investProject: name,
      faceValue: parseNum(row.faceValue ?? row.face_value),
      couponRate: parseNum(row.couponRate ?? row.coupon_rate),
      effectiveRate: parseNum(row.effectiveRate ?? row.effective_rate),
      openingAmortized,
    })
  }
  return out
}
