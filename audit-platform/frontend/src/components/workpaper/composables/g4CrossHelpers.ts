/**
 * G4 跨表辅助 — G4-2 ↔ G4-9 ↔ G4-10
 */
import http from '@/utils/http'
import {
  fetchTrialBalanceByPrefix,
  pickTbAmount,
} from './workpaperAuditYear'
import { parseG4AdjStore } from './g4AdjudicationItems'
import {
  G4_STORAGE_SCHEMA_VERSION,
  buildCanonicalPayload,
} from './g4StorageContract'
import type { ChecklistResponse } from './useF1FormData'

/** 名称归一：去空白 */
export function normalizeInvestName(name: string): string {
  return String(name || '').trim().replace(/\s+/g, '')
}

/** 解析 checklist 中的 JSON 数组（兼容 conclusion / remark） */
export function parseRowsJson(raw: string | null | undefined): any[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (Array.isArray(parsed)) return parsed
    if (Array.isArray(parsed?.rows)) return parsed.rows
  } catch { /* ignore */ }
  return []
}

/** 从单条 checklist response 取 JSON 数组（prefer conclusion，兼容 remark） */
export function parseChecklistRows(resp: { conclusion?: string | null; remark?: string | null } | undefined): any[] {
  if (!resp) return []
  const fromConclusion = parseRowsJson(resp.conclusion)
  if (fromConclusion.length) return fromConclusion
  return parseRowsJson(resp.remark)
}

/**
 * 直接拉取 G4-2 明细行（ECL formData 默认不加载 G4-2- 前缀）
 */
export async function fetchG42DetailRows(wpId: string): Promise<any[]> {
  if (!wpId) return []
  try {
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`)
    const responses: any[] = Array.isArray(data) ? data : (data?.data ?? [])
    const item = responses.find((r: any) => r.item_id === 'G4-2-rows')
    return parseChecklistRows(item)
  } catch {
    return []
  }
}

/** 计算相对基准日已逾期天数（未逾期返回 0） */
export function calcOverdueDays(maturityDate: string | undefined | null, asOfDate?: string | null): number {
  if (!maturityDate) return 0
  const mat = new Date(maturityDate)
  const asOf = asOfDate ? new Date(asOfDate) : new Date()
  if (Number.isNaN(mat.getTime()) || Number.isNaN(asOf.getTime())) return 0
  const days = Math.round((asOf.getTime() - mat.getTime()) / 86400000)
  return days > 0 ? days : 0
}

export const G4_9_ROWS_KEY = 'G4-9-rows'
export const G4_10_ROWS_KEY = 'G4-10-rows'
export const G4_11_MEASUREMENT_KEY = 'G4-11-ecl-measurement'
export const G4_STAGE_UPDATED_EVENT = 'g4:stage-updated'
export const G4_ECL_RATE_UPDATED_EVENT = 'g4:ecl-rate-updated'
export const G4_1_ROWS_KEY = 'G4-1-rows'
export const G4_CLASSIFICATION_WRITEBACK_EVENT = 'g4:classification-writeback'

export type G4MeasurementClassification = 'AC' | 'FVOCI' | 'FVTPL' | 'INCOMPLETE'

export interface G4ClassificationUpdate {
  investmentId?: string
  investProject?: string
  businessModelResult?: string
  sppiResult?: string
  measurementClassification?: G4MeasurementClassification
  sourcePortfolioId?: string
  crossSheetInvestmentId?: string
  classificationSource?: string
}

export interface G4CrossApplyResult<T = any> {
  rows: T[]
  matched: string[]
  unmatched: string[]
}

function crossId(value: unknown): string {
  return String(value ?? '').trim()
}

export function deriveG4MeasurementClassification(
  businessModelResult?: string | null,
  sppiResult?: string | null,
): G4MeasurementClassification {
  const bm = String(businessModelResult || '').toUpperCase()
  const sppi = String(sppiResult || '').toUpperCase()
  if (sppi === 'FAIL' || bm === 'FVTPL') return 'FVTPL'
  if (sppi !== 'PASS') return 'INCOMPLETE'
  if (bm === 'AC') return 'AC'
  if (bm === 'FVOCI') return 'FVOCI'
  return 'INCOMPLETE'
}

/** G4-5/G4-6 → G4-2，优先稳定 id，其次名称归一匹配。 */
export function applyG4ClassificationUpdates<T extends Record<string, any>>(
  existing: T[] | unknown,
  updates: G4ClassificationUpdate[],
): G4CrossApplyResult<T> {
  const rows = Array.isArray(existing) ? existing.map(row => ({ ...row })) as T[] : []
  const byId = new Map<string, T>()
  const byName = new Map<string, T>()
  for (const row of rows) {
    for (const id of [row.id, row.crossSheetInvestmentId, row.sourcePortfolioId]) {
      if (crossId(id)) byId.set(crossId(id), row)
    }
    const name = normalizeInvestName(row.investProject ?? row.investmentProject ?? row.name)
    if (name) byName.set(name, row)
  }
  const matched: string[] = []
  const unmatched: string[] = []
  const now = new Date().toISOString()
  for (const update of updates) {
    const stableIds = [
      update.investmentId,
      update.crossSheetInvestmentId,
      update.sourcePortfolioId,
    ].map(crossId).filter(Boolean)
    const name = normalizeInvestName(update.investProject || '')
    const row = stableIds.map(id => byId.get(id)).find(Boolean) ?? (name ? byName.get(name) : undefined)
    const label = update.investProject || stableIds[0] || '未命名项目'
    if (!row) {
      unmatched.push(label)
      continue
    }
    const businessModelResult = update.businessModelResult ?? row.businessModelResult ?? ''
    const sppiResult = update.sppiResult ?? row.sppiResult ?? ''
    Object.assign(row, {
      businessModelResult,
      sppiResult,
      measurementClassification: update.measurementClassification
        ?? deriveG4MeasurementClassification(businessModelResult, sppiResult),
      classificationSource: update.classificationSource || 'G4-5/G4-6',
      classificationUpdatedAt: now,
      sourcePortfolioId: update.sourcePortfolioId ?? row.sourcePortfolioId ?? '',
      crossSheetInvestmentId: update.crossSheetInvestmentId
        ?? update.investmentId
        ?? row.crossSheetInvestmentId
        ?? row.id
        ?? '',
    })
    matched.push(String(row.investProject || label))
  }
  return { rows, matched, unmatched }
}

export interface G44InterestGroupLike {
  id?: string
  projectName?: string
  periods?: Array<{ effectiveInterest?: number; cashInflow?: number }>
}

/** G4-4 → G4-2：只回写期间利息调整（实际利息－票息），不生成 G4-3 总利息调整。 */
export function applyG44InterestToDetailRows<T extends Record<string, any>>(
  existing: T[] | unknown,
  groups: G44InterestGroupLike[],
): G4CrossApplyResult<T> {
  const rows = Array.isArray(existing) ? existing.map(row => ({ ...row })) as T[] : []
  const byId = new Map(rows.map(row => [crossId(row.crossSheetInvestmentId || row.id), row]))
  const byName = new Map(rows.map(row => [
    normalizeInvestName(row.investProject ?? row.investmentProject ?? row.name),
    row,
  ]))
  const matched: string[] = []
  const unmatched: string[] = []
  for (const group of groups || []) {
    const id = crossId(group.id)
    const name = normalizeInvestName(group.projectName || '')
    const row = (id ? byId.get(id) : undefined) ?? (name ? byName.get(name) : undefined)
    const label = String(group.projectName || id || '未命名项目')
    if (!row) {
      unmatched.push(label)
      continue
    }
    const adjustment = (group.periods || []).reduce(
      (sum, period) => sum + (Number(period.effectiveInterest) || 0) - (Number(period.cashInflow) || 0),
      0,
    )
    if ('periodInterestAdjChange' in row) {
      row.periodInterestAdjChange = Math.round(adjustment * 100) / 100
      if ('periodChangeSubtotal' in row) {
        row.periodChangeSubtotal = Math.round((
          (Number(row.periodCostChange) || 0)
          + row.periodInterestAdjChange
          + (Number(row.periodAccruedInterestChange) || 0)
        ) * 100) / 100
      }
      if ('closingInterestAdj' in row) {
        row.closingInterestAdj = Math.round((
          (Number(row.openingInterestAdj) || 0) + row.periodInterestAdjChange
        ) * 100) / 100
      }
      if ('closingSubtotal' in row) {
        row.closingSubtotal = Math.round((
          (Number(row.closingCost) || 0)
          + (Number(row.closingInterestAdj) || 0)
          + (Number(row.closingAccruedInterest) || 0)
        ) * 100) / 100
      }
      if ('closingAudited' in row) {
        row.closingAudited = Math.round((
          (Number(row.closingSubtotal) || 0) + (Number(row.closingAdjustment) || 0)
        ) * 100) / 100
      }
      if ('amortizedCost' in row) {
        row.amortizedCost = Math.round((
          (Number(row.closingAudited) || 0)
          - (Number(row.closingImpairment ?? row.impairmentAdjusted) || 0)
        ) * 100) / 100
      }
      if ('bookValue' in row) {
        row.bookValue = Math.round((
          (Number(row.amortizedCost) || 0) - (Number(row.oneYearSubtotal) || 0)
        ) * 100) / 100
      }
    }
    row.interestWritebackSource = 'G4-4'
    row.interestWritebackUpdatedAt = new Date().toISOString()
    matched.push(String(row.investProject || label))
  }
  return { rows, matched, unmatched }
}

export async function resolveG4MainWorkpaperId(
  projectId: string,
  fallbackWpId?: string,
): Promise<string | null> {
  if (!projectId) return fallbackWpId || null
  for (const sheetCode of ['G4-2', 'G4']) {
    try {
      const { data } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: projectId, parent: 'G4', sheet_code: sheetCode },
        _silent: true,
      } as any)
      const resolved = data?.data?.wp_id ?? data?.wp_id
      if (resolved) return String(resolved)
    } catch { /* try fallback */ }
  }
  return fallbackWpId || null
}

/** 解析 G4 Main / SPPI / ECL 三组工作底稿 wp_id（用于套件状态聚合） */
export async function resolveG4SuiteWorkpaperIds(
  projectId: string,
  fallbackMainWpId?: string,
): Promise<{ main: string | null; sppi: string | null; ecl: string | null }> {
  const resolveOne = async (sheetCode: string): Promise<string | null> => {
    if (!projectId) return null
    try {
      const { data } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: projectId, parent: 'G4', sheet_code: sheetCode },
        _silent: true,
      } as any)
      const resolved = data?.data?.wp_id ?? data?.wp_id
      return resolved ? String(resolved) : null
    } catch {
      return null
    }
  }
  const [main, sppi, ecl] = await Promise.all([
    resolveG4MainWorkpaperId(projectId, fallbackMainWpId),
    resolveOne('G4-5'),
    resolveOne('G4-9'),
  ])
  return { main, sppi, ecl }
}

export async function fetchChecklistResponseMap(
  wpId: string,
): Promise<Map<string, ChecklistResponse>> {
  const map = new Map<string, ChecklistResponse>()
  if (!wpId) return map
  try {
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`)
    const responses: any[] = Array.isArray(data) ? data : (data?.data ?? [])
    for (const item of responses) {
      if (item?.item_id) {
        map.set(String(item.item_id), {
          item_id: String(item.item_id),
          conclusion: item.conclusion ?? null,
          remark: item.remark ?? null,
        })
      }
    }
  } catch { /* ignore */ }
  return map
}

/** 合并 Main/SPPI/ECL 三组 responses，供套件状态栏使用 */
export async function fetchG4SuiteResponseMap(
  projectId: string,
  fallbackMainWpId?: string,
): Promise<Map<string, ChecklistResponse>> {
  const ids = await resolveG4SuiteWorkpaperIds(projectId, fallbackMainWpId)
  const maps = await Promise.all(
    [ids.main, ids.sppi, ids.ecl]
      .filter((id): id is string => Boolean(id))
      .map((id) => fetchChecklistResponseMap(id)),
  )
  const merged = new Map<string, ChecklistResponse>()
  for (const map of maps) {
    for (const [key, value] of map) merged.set(key, value)
  }
  return merged
}

export async function fetchCanonicalRowsFromWorkpaper(
  wpId: string,
  itemId: string,
): Promise<any[]> {
  if (!wpId) return []
  const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`)
  const responses: any[] = Array.isArray(data) ? data : (data?.data ?? [])
  return parseChecklistRows(responses.find(r => r.item_id === itemId))
}

export async function saveCanonicalRowsToWorkpaper(
  wpId: string,
  projectId: string,
  itemId: string,
  rows: unknown[],
): Promise<void> {
  const payload = buildCanonicalPayload(itemId, rows)
  await http.put(`/api/workpapers/${wpId}/checklist-responses`, {
    project_id: projectId,
    items: [payload],
  })
}

export function buildG411MeasurementPayload(value: Record<string, any>): Record<string, any> {
  return { ...value, schemaVersion: G4_STORAGE_SCHEMA_VERSION }
}

/** G4 调整分录口径：债权投资减值准备 */
export const G4_IMPAIRMENT_ACCOUNT_CODE = '1502'
export const G4_IMPAIRMENT_ACCOUNT_NAME = '债权投资减值准备'

/** G4-1 减值准备叶子行（单项 + 组合） */
export const G4_1_IMPAIRMENT_LEAF_KEYS = [
  'impairment-individual',
  'impairment-portfolio',
] as const

/**
 * 从 G4-1 审定表 store 汇总减值准备期末审定数（小计，不含一年内到期扣减）。
 * closingAudited = closingUnadjusted + closingAdjustment
 */
export function extractG41ImpairmentClosingAudited(store: Record<string, any> | null | undefined): number {
  if (!store || typeof store !== 'object') return 0
  let total = 0
  for (const key of G4_1_IMPAIRMENT_LEAF_KEYS) {
    const cell = store[key]
    if (!cell || typeof cell !== 'object') continue
    const unadj = Number(cell.closingUnadjusted ?? 0) || 0
    const adj = Number(cell.closingAdjustment ?? 0) || 0
    // 兼容未迁移的 AJE/RJE
    const closingAJE = Number(cell.closingAJE ?? 0) || 0
    const closingRJE = Number(cell.closingRJE ?? 0) || 0
    const adjustment = cell.closingAdjustment != null ? adj : closingAJE + closingRJE
    total += unadj + adjustment
  }
  return Math.round(total * 100) / 100
}

/** 拉取 G4-1 减值准备小计（期末审定） */
export async function fetchG41ImpairmentSubtotal(wpId: string): Promise<number | null> {
  if (!wpId) return null
  try {
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`)
    const responses: any[] = Array.isArray(data) ? data : (data?.data ?? [])
    const item = responses.find((r: any) => r.item_id === G4_1_ROWS_KEY)
    if (!item) {
      const imp = responses.find((r: any) => r.item_id === 'G4-1-adj-groups-impairment')
      if (!imp?.remark) return null
      return extractG41ImpairmentClosingAudited(parseG4AdjStore(imp.remark))
    }
    const store = parseG4AdjStore(item.remark || item.conclusion)
    if (!Object.keys(store).length) return null
    return extractG41ImpairmentClosingAudited(store)
  } catch {
    return null
  }
}

/** 解析 G4-11 持久化的测算 payload */
export function parseG411MeasurementPayload(raw: string | null | undefined): Record<string, any> | null {
  if (!raw) return null
  try {
    const parsed = JSON.parse(raw)
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) return null
    return parsed
  } catch {
    return null
  }
}

/** 拉取 G4-11 测算明细（供 G4-10 回写损失率） */
export async function fetchG411MeasurementRows(wpId: string): Promise<{
  pdLgdRows: any[]
  lossRateRows: any[]
} | null> {
  if (!wpId) return null
  try {
    const { data } = await http.get(`/api/workpapers/${wpId}/checklist-responses`)
    const responses: any[] = Array.isArray(data) ? data : (data?.data ?? [])
    const item = responses.find((r: any) => r.item_id === G4_11_MEASUREMENT_KEY)
    const parsed = parseG411MeasurementPayload(item?.conclusion || item?.remark)
    if (!parsed) return null
    return {
      pdLgdRows: Array.isArray(parsed.pdLgdRows) ? parsed.pdLgdRows : [],
      lossRateRows: Array.isArray(parsed.lossRateRows) ? parsed.lossRateRows : [],
    }
  } catch {
    return null
  }
}

export interface G4ImpairmentTbHit {
  amount: number
  code: string
  name: string
}

/**
 * 从试算行中解析「债权投资减值准备」：
 * 1) 科目名精确匹配
 * 2) 科目代码 1502（及以 1502 开头的明细）
 * 3) 科目代码 1505 且名称含「债权投资」与「减值」
 */
export function pickG4ImpairmentTbRow(list: any[]): G4ImpairmentTbHit | null {
  if (!Array.isArray(list) || !list.length) return null

  const codeOf = (r: any) => String(r.standard_account_code ?? r.account_code ?? '').trim()
  const nameOf = (r: any) => String(r.standard_account_name ?? r.account_name ?? r.name ?? '').trim()

  const byName = list.find(r => nameOf(r) === G4_IMPAIRMENT_ACCOUNT_NAME)
  if (byName) {
    return {
      amount: pickTbAmount(byName),
      code: codeOf(byName) || G4_IMPAIRMENT_ACCOUNT_CODE,
      name: nameOf(byName),
    }
  }

  const by1502 = list.find(r => {
    const c = codeOf(r)
    return c === G4_IMPAIRMENT_ACCOUNT_CODE || c.startsWith(`${G4_IMPAIRMENT_ACCOUNT_CODE}.`) || c.startsWith('1502')
  })
  if (by1502) {
    return {
      amount: pickTbAmount(by1502),
      code: codeOf(by1502),
      name: nameOf(by1502) || G4_IMPAIRMENT_ACCOUNT_NAME,
    }
  }

  const by1505 = list.find(r => {
    const c = codeOf(r)
    const n = nameOf(r)
    return c.startsWith('1505') && n.includes('债权投资') && n.includes('减值')
  })
  if (by1505) {
    return {
      amount: pickTbAmount(by1505),
      code: codeOf(by1505),
      name: nameOf(by1505),
    }
  }

  return null
}

/** 拉取项目试算中的债权投资减值准备金额 */
export async function fetchG4ImpairmentTbAmount(
  projectId: string,
  year: number | null,
): Promise<G4ImpairmentTbHit | null> {
  if (!projectId || year == null) return null
  try {
    const list = await fetchTrialBalanceByPrefix(projectId, year, '150')
    return pickG4ImpairmentTbRow(list)
  } catch {
    return null
  }
}
