/**
 * G11 跨底稿取数（G7-14 权益法 → G11-2 明细）+ 序时账预填 + 勾稽校验
 */
import http from '@/utils/http'
import { parseNum, calcAdjustedAmount, calcSubtotal } from './useG11FormulaEngine'
import {
  flattenG714Rows,
  G7_14_SECTION_KEY,
  G7_14_ROWS_KEY,
  makeG714ConclusionGetter,
  resolveG714PayloadFromChecklist,
} from './g7EquityMethodCrossSheet'
import { fetchChecklistResponseMap } from './g4CrossHelpers'
import { inferG11AdjudicationRowKey } from './g11AccountMatch'
import { G11_ACCOUNT_CODE, G11_ADJUDICATION_ITEMS } from './g11Constants'
import { parseG11AdjStore } from './g11AdjStorage'
import {
  g11TbRowPlAmount,
  resolveG11TbChildRows,
  resolveG11TbRow,
  type G11TbRowLike,
} from './g11TbResolve'
import type { G11DetailRow } from './useG11DetailAnalysis'

export interface G11EquityIncomeSeed {
  investeeName: string
  currentUnadjusted: number
  equityShare: number
  incomeDifference: number
  reasonIndex: string
}

export async function resolveG714WorkpaperIds(
  projectId: string,
  htmlData?: Record<string, unknown> | null,
): Promise<string[]> {
  const ids = new Set<string>()
  const cycle = htmlData?.cycle_workpapers
  if (Array.isArray(cycle)) {
    for (const entry of cycle) {
      const code = String((entry as any)?.wp_code ?? (entry as any)?.sheet_code ?? '')
      const name = String((entry as any)?.sheet_name ?? (entry as any)?.name ?? '')
      if (/G7-14|权益法/.test(`${code}${name}`)) {
        const id = String((entry as any)?.wp_id ?? '')
        if (id) ids.add(id)
      }
    }
  }
  if (!projectId) return [...ids]
  for (const sheetCode of ['G7-14', 'G7']) {
    try {
      const { data } = await http.get('/api/acnr/resolve-instance', {
        params: { project_id: projectId, parent: 'G7', sheet_code: sheetCode },
        _silent: true,
      } as any)
      const resolved = data?.data?.wp_id ?? data?.wp_id
      if (resolved) ids.add(String(resolved))
    } catch { /* try next */ }
  }
  return [...ids]
}

/** 从 G7-14 payload 提取权益法投资收益明细种子 */
export function extractEquityIncomeSeedsFromG714(
  payload: Record<string, any> | null | undefined,
): G11EquityIncomeSeed[] {
  if (!payload) return []
  return flattenG714Rows(payload)
    .map((row) => {
      const investeeName = String(row.investeeName ?? row.investee_name ?? '').trim()
      if (!investeeName) return null
      const confirmed = parseNum(row.confirmedIncome ?? row.confirmed_income)
      const equityShare = parseNum(row.equityShare ?? row.equity_share)
      const incomeDifference = parseNum(row.incomeDifference ?? row.income_difference)
      if (Math.abs(confirmed) < 0.005 && Math.abs(equityShare) < 0.005) return null
      return {
        investeeName,
        currentUnadjusted: confirmed,
        equityShare,
        incomeDifference,
        reasonIndex: 'wp:G7-14',
      } as G11EquityIncomeSeed
    })
    .filter((s): s is G11EquityIncomeSeed => !!s)
}

function parseJsonPayload(raw: unknown): Record<string, any> | null {
  if (!raw) return null
  if (typeof raw === 'object') return raw as Record<string, any>
  if (typeof raw === 'string') {
    try {
      return JSON.parse(raw) as Record<string, any>
    } catch {
      return null
    }
  }
  return null
}

export async function loadG714EquityIncomeSeeds(opts: {
  projectId: string
  htmlData?: Record<string, unknown> | null
}): Promise<{ seeds: G11EquityIncomeSeed[]; sourceWpIds: string[] }> {
  const wpIds = await resolveG714WorkpaperIds(opts.projectId, opts.htmlData)
  const seeds: G11EquityIncomeSeed[] = []
  const hitIds: string[] = []

  for (const wpId of wpIds) {
    const map = await fetchChecklistResponseMap(wpId)
    const getter = makeG714ConclusionGetter(map)
    const payload = resolveG714PayloadFromChecklist(getter)
    let batch = extractEquityIncomeSeedsFromG714(payload)
    if (!batch.length) {
      batch = extractEquityIncomeSeedsFromG714(parseJsonPayload(map.get(G7_14_ROWS_KEY)?.conclusion))
      if (!batch.length) {
        batch = extractEquityIncomeSeedsFromG714(parseJsonPayload(map.get(G7_14_SECTION_KEY)?.conclusion))
      }
    }
    if (batch.length) {
      seeds.push(...batch)
      hitIds.push(wpId)
    }
  }

  const byName = new Map<string, G11EquityIncomeSeed>()
  for (const s of seeds) byName.set(s.investeeName, s)
  return { seeds: [...byName.values()], sourceWpIds: [...new Set(hitIds)] }
}

/** 将 G7-14 权益法种子并入 G11-2 明细行 */
export function mergeG714SeedsIntoDetailRows(
  existing: Partial<G11DetailRow>[],
  seeds: G11EquityIncomeSeed[],
  mode: 'empty_only' | 'overwrite' = 'empty_only',
): Partial<G11DetailRow>[] {
  if (!seeds.length) return existing
  let result = [...existing]

  for (const seed of seeds) {
    const idx = result.findIndex(
      (r) =>
        r.rowKey === 'equity_method'
        && String(r.investeeName ?? '').trim() === seed.investeeName,
    )
    const patch: Partial<G11DetailRow> = {
      rowKey: 'equity_method',
      itemName: '权益法核算的长期股权投资收益',
      group: '长期股权投资',
      investeeName: seed.investeeName,
      reasonIndex: seed.reasonIndex,
      isSkeleton: false,
    }
    if (mode === 'overwrite' || idx < 0 || !parseNum(result[idx]?.currentUnadjusted)) {
      patch.currentUnadjusted = seed.currentUnadjusted
    }
    if (Math.abs(seed.incomeDifference) >= 0.005) {
      patch.reasonIndex = `${seed.reasonIndex}；差异${seed.incomeDifference.toFixed(2)}`
    }
    if (idx >= 0) {
      result[idx] = { ...result[idx], ...patch }
    } else {
      result.push(patch)
    }
  }

  if (seeds.some((s) => s.investeeName)) {
    result = result.filter(
      (r) => !(r.rowKey === 'equity_method' && r.isSkeleton && !String(r.investeeName ?? '').trim()),
    )
  }
  return result
}

export interface G11LedgerIncomeSeed {
  rowKey: string
  itemName: string
  investeeName: string
  currentUnadjusted: number
  priorUnadjusted: number
  reasonIndex: string
}

export interface G11DetailCrossCheck {
  isBalanced: boolean
  hasDetailData: boolean
  adjTotal: number
  detailTotal: number
  diff: number
  message: string | null
}

export function computeG11DetailCrossCheck(
  adjRemark?: string | null,
  detailRemark?: string | null,
): G11DetailCrossCheck {
  const store = parseG11AdjStore(adjRemark ?? undefined)
  const adjTotal = calcSubtotal(
    G11_ADJUDICATION_ITEMS.map((def) => {
      const r = store[def.rowKey] ?? {}
      return calcAdjustedAmount(parseNum(r.currentUnadjusted), parseNum(r.currentAdjustment))
    }),
  )

  let detailRows: Array<Record<string, unknown>> = []
  if (detailRemark) {
    try {
      const parsed = JSON.parse(detailRemark)
      if (Array.isArray(parsed)) detailRows = parsed
    } catch { /* ignore */ }
  }
  const hasDetailData = detailRows.length > 0
  const detailTotal = calcSubtotal(
    detailRows.map((r) =>
      calcAdjustedAmount(parseNum(r.currentUnadjusted), parseNum(r.currentAdjustment)),
    ),
  )
  const diff = Math.round((adjTotal - detailTotal) * 100) / 100
  const isBalanced = !hasDetailData || Math.abs(diff) <= 0.01
  const message = isBalanced
    ? null
    : `G11-1 审定合计 ${adjTotal.toFixed(2)} 与 G11-2 明细合计 ${detailTotal.toFixed(2)} 不一致（差额 ${diff.toFixed(2)}）`
  return { isBalanced, hasDetailData, adjTotal, detailTotal, diff, message }
}

function ledgerEntryPlAmount(r: Record<string, unknown>): number {
  const credit = parseNum(r.credit_amount ?? r.creditAmount ?? r.credit)
  const debit = parseNum(r.debit_amount ?? r.debitAmount ?? r.debit)
  return credit - debit
}

function mapTbRowToSeed(r: G11TbRowLike, year: number): G11LedgerIncomeSeed | null {
  const code = String(r.standard_account_code ?? r.account_code ?? '').trim()
  const name = String(r.account_name ?? r.standard_account_name ?? r.aux_name ?? '').trim()
  const amount = g11TbRowPlAmount(r)
  if (Math.abs(amount) < 0.005) return null
  const rowKey = inferG11AdjudicationRowKey({
    description: name,
    itemName: name,
    accountName: name,
  })
  const def = G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === rowKey)
  const investeeName = rowKey === 'equity_method' ? name : ''
  return {
    rowKey,
    itemName: def?.label ?? name,
    investeeName,
    currentUnadjusted: amount,
    priorUnadjusted: 0,
    reasonIndex: `TB:${code || G11_ACCOUNT_CODE}/${year}`,
  }
}

/** 从试算表子科目 / 序时账汇总 6111 分项发生额 */
export async function fetchG11LedgerIncomeSeeds(opts: {
  projectId: string
  year?: number
}): Promise<{ seeds: G11LedgerIncomeSeed[]; source: string; error?: string }> {
  if (!opts.projectId) return { seeds: [], source: '', error: '缺少项目 ID' }
  const y = opts.year ?? new Date().getFullYear() - 1

  // 1) 试算表子科目
  try {
    const { data } = await http.get(`/api/projects/${opts.projectId}/trial-balance`, {
      params: { year: y, account_prefix: G11_ACCOUNT_CODE },
      _silent: true,
    } as any)
    const rows: G11TbRowLike[] = Array.isArray(data)
      ? data
      : (data?.data ?? data?.items ?? data?.rows ?? [])
    const childRows = resolveG11TbChildRows(rows)
    if (childRows.length) {
      const seeds = childRows
        .map((r) => mapTbRowToSeed(r, y))
        .filter((s): s is G11LedgerIncomeSeed => !!s)
      if (seeds.length) return { seeds, source: `TB 子科目 ${y}` }
    }
    const main = resolveG11TbRow(rows)
    const mainAmt = g11TbRowPlAmount(main)
    if (Math.abs(mainAmt) >= 0.005) {
      return {
        seeds: [{
          rowKey: 'other',
          itemName: '其他',
          investeeName: '',
          currentUnadjusted: mainAmt,
          priorUnadjusted: 0,
          reasonIndex: `TB:${G11_ACCOUNT_CODE}/${y}`,
        }],
        source: `TB 合计 ${y}`,
      }
    }
  } catch { /* fallback */ }

  // 2) 序时账按摘要聚合
  try {
    const aggregated = new Map<string, G11LedgerIncomeSeed>()
    let page = 1
    let hasMore = true
    while (hasMore && page <= 20) {
      const { data } = await http.get(
        `/api/projects/${opts.projectId}/ledger/entries/${G11_ACCOUNT_CODE}`,
        { params: { year: y, page, page_size: 1000 }, _silent: true } as any,
      )
      const items: any[] = data?.items ?? data?.data?.items ?? data?.rows ?? (Array.isArray(data) ? data : [])
      for (const r of items) {
        const summary = String(r.summary ?? r.description ?? '').trim() || '未分类'
        const amt = ledgerEntryPlAmount(r)
        if (Math.abs(amt) < 0.005) continue
        const rowKey = inferG11AdjudicationRowKey({ description: summary, itemName: summary })
        const def = G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === rowKey)
        const key = rowKey === 'equity_method' ? `${rowKey}:${summary.slice(0, 32)}` : rowKey
        const prev = aggregated.get(key)
        if (prev) {
          prev.currentUnadjusted = Math.round((prev.currentUnadjusted + amt) * 100) / 100
        } else {
          aggregated.set(key, {
            rowKey,
            itemName: def?.label ?? summary.slice(0, 40),
            investeeName: rowKey === 'equity_method' ? summary.slice(0, 40) : '',
            currentUnadjusted: amt,
            priorUnadjusted: 0,
            reasonIndex: `序时账/${y}`,
          })
        }
      }
      hasMore = items.length >= 1000
      page++
    }
    const seeds = [...aggregated.values()].filter((s) => Math.abs(s.currentUnadjusted) >= 0.005)
    if (seeds.length) return { seeds, source: `序时账 ${y}` }
    return { seeds: [], source: '', error: `6111 无 ${y} 年度序时账发生额` }
  } catch (e: any) {
    return { seeds: [], source: '', error: e?.message || '序时账取数失败' }
  }
}

/** 将序时账/TB 种子并入 G11-2 明细行 */
export function mergeLedgerSeedsIntoDetailRows(
  existing: Partial<G11DetailRow>[],
  seeds: G11LedgerIncomeSeed[],
  mode: 'empty_only' | 'overwrite' = 'empty_only',
): Partial<G11DetailRow>[] {
  if (!seeds.length) return existing
  let result = [...existing]

  for (const seed of seeds) {
    const idx = result.findIndex((r) => {
      if (seed.rowKey === 'equity_method' && seed.investeeName) {
        return r.rowKey === 'equity_method' && String(r.investeeName ?? '').trim() === seed.investeeName
      }
      return r.rowKey === seed.rowKey && !String(r.investeeName ?? '').trim()
    })
    const def = G11_ADJUDICATION_ITEMS.find((d) => d.rowKey === seed.rowKey)
    const patch: Partial<G11DetailRow> = {
      rowKey: seed.rowKey,
      itemName: def?.label ?? seed.itemName,
      group: def?.group ?? '其他',
      investeeName: seed.investeeName,
      reasonIndex: seed.reasonIndex,
      isSkeleton: false,
    }
    if (mode === 'overwrite' || idx < 0 || !parseNum(result[idx]?.currentUnadjusted)) {
      patch.currentUnadjusted = seed.currentUnadjusted
    }
    if (mode === 'overwrite' || idx < 0 || !parseNum(result[idx]?.priorUnadjusted)) {
      if (Math.abs(seed.priorUnadjusted) >= 0.005) patch.priorUnadjusted = seed.priorUnadjusted
    }
    if (idx >= 0) {
      result[idx] = { ...result[idx], ...patch }
    } else {
      result.push(patch)
    }
  }

  if (seeds.some((s) => s.rowKey === 'equity_method' && s.investeeName)) {
    result = result.filter(
      (r) => !(r.rowKey === 'equity_method' && r.isSkeleton && !String(r.investeeName ?? '').trim()),
    )
  }
  return result
}
