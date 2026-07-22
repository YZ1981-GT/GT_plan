/**
 * G10 跨表联动：G10-2 → G10-1 回写、附注与审定表同步
 */
import { G10_ADJUDICATION_ITEMS } from './g10AdjudicationItems'
import {
  G10_ACCOUNT_ALIASES,
  G10_ACCOUNT_CODE,
} from './g10Constants'
import {
  G10_ADJ_ROWS_KEY,
  G10_ADJ_WRITEBACK_OVERLAY_ID,
  aggregateG10AdjustmentAjeRjeByRow,
  applyG10AdjustmentWritebacks,
  parseG10AdjStore,
  patchG10AdjRow,
  g10RowClosingAdjusted,
  type G10AdjRowStore,
  type G10AdjustmentWritebackMap,
} from './g10AdjStorage'
import { dispatchG10OfferDisclosurePull } from './g10DisclosureSync'
import {
  g10AccountLabel,
  inferG10LiabilityCategory,
  inferG10LiabilityTypeFromName,
  matchG10LiabilityKey,
  resolveG10LiabilitySuffix,
} from './g10AccountMatch'
import { calcAdjustedAmount, calcSubtotal, parseNum } from './useG10FormulaEngine'
import { enrichG10DetailRow, type G10DetailRow } from './useG10Detail'
import type { ChecklistResponse } from './useF1FormData'

export { G10_ADJ_ROWS_KEY }

export const G10_DETAIL_ROWS_KEY = 'G10-detail-rows'
export const G10_ADJUDICATED_KEY = 'G10-1-adjudicated-amount'

export interface G10DetailBucket {
  suffix: string
  openingInit: number
  closingInit: number
  openingFv: number
  closingFv: number
  openingBook: number
  closingBook: number
}

function emptyBucket(): G10DetailBucket {
  return {
    suffix: '',
    openingInit: 0,
    closingInit: 0,
    openingFv: 0,
    closingFv: 0,
    openingBook: 0,
    closingBook: 0,
  }
}

/** 按负债类型汇总 G10-2 → (一)(二)(三) 分项未审数 */
export function aggregateG10DetailBuckets(rows: G10DetailRow[]): Map<string, G10DetailBucket> {
  const map = new Map<string, G10DetailBucket>()
  for (const row of rows) {
    const suffix = resolveG10LiabilitySuffix(row)
    if (suffix === 'trading_liability' || suffix === 'designated_fvtpl') continue
    const openInit = parseNum(row.openingInitialAmount ?? row.initialAmount)
    const closeInit = parseNum(row.closingInitialAmount ?? row.initialAmount)
    const openBook = parseNum(row.openingFairValue ?? row.openingBalance)
    const closeBook = parseNum(row.closingFairValue ?? row.closingBalance)
    const prev = map.get(suffix) ?? { ...emptyBucket(), suffix }
    prev.openingInit += openInit
    prev.closingInit += closeInit
    prev.openingFv += parseNum(row.openingFvAccum ?? (openBook - openInit))
    prev.closingFv += parseNum(row.closingFvAccum ?? (closeBook - closeInit))
    prev.openingBook += openBook
    prev.closingBook += closeBook
    map.set(suffix, prev)
  }
  return map
}

/** G10-2 明细按分项回写 G10-1（保留已有账项调整） */
export function pushG10DetailToAdjudication(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  detailRows: G10DetailRow[],
): number {
  const buckets = aggregateG10DetailBuckets(detailRows)
  if (!buckets.size) return 0

  let store = parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark)
  let n = 0

  for (const [, bucket] of buckets) {
    const hasData =
      Math.abs(bucket.openingBook) > 0.005
      || Math.abs(bucket.closingBook) > 0.005
      || Math.abs(bucket.closingInit) > 0.005
    if (!hasData) continue

    const suffix = bucket.suffix
    store = patchG10AdjRow(store, `init_${suffix}`, {
      openingUnadjusted: bucket.openingInit,
      closingUnadjusted: bucket.closingInit,
      indexRef: 'G10-2',
    })
    store = patchG10AdjRow(store, `fv_${suffix}`, {
      openingUnadjusted: bucket.openingFv,
      closingUnadjusted: bucket.closingFv,
      indexRef: 'G10-2',
    })
    store = patchG10AdjRow(store, `book_${suffix}`, {
      openingUnadjusted: bucket.openingBook,
      closingUnadjusted: bucket.closingBook,
      indexRef: 'G10-2',
    })
    n += 1
  }

  if (!n) return 0

  const closingAdjusted = calcBookSectionTotal(store)
  debouncedSave(G10_ADJ_ROWS_KEY, { remark: JSON.stringify(store) })
  debouncedSave(G10_ADJUDICATED_KEY, { conclusion: String(closingAdjusted) })
  try {
    window.dispatchEvent(new CustomEvent('g10:detail-to-adjudication', {
      detail: { closingAdjusted, buckets: n, timestamp: Date.now() },
    }))
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { accountCode: '2101', adjudicatedAmount: closingAdjusted },
    }))
  } catch { /* silent */ }
  return n
}

export interface G10CommitWritebackOpts {
  source?: string
  /** 回写后提示是否同步附注披露 */
  offerDisclosurePull?: boolean
}

/**
 * G10-3 调整净额回写 G10-1，并同步审定合计 / EventBus。
 * 供 G10-3 persist、G10-4/5/7/8 跨表推送共用。
 */
export function commitG10AdjustmentWriteback(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  writeback: G10AdjustmentWritebackMap,
  opts?: G10CommitWritebackOpts,
): G10AdjRowStore {
  const store = applyG10AdjustmentWritebacks(
    parseG10AdjStore(responses.get(G10_ADJ_ROWS_KEY)?.remark),
    writeback,
  )
  debouncedSave(G10_ADJ_WRITEBACK_OVERLAY_ID, { remark: JSON.stringify(writeback) })
  debouncedSave(G10_ADJ_ROWS_KEY, { remark: JSON.stringify(store) })
  const closingAdjusted = calcBookSectionTotal(store)
  debouncedSave(G10_ADJUDICATED_KEY, { conclusion: String(closingAdjusted) })
  responses.set(G10_ADJ_ROWS_KEY, {
    item_id: G10_ADJ_ROWS_KEY,
    conclusion: responses.get(G10_ADJ_ROWS_KEY)?.conclusion ?? null,
    remark: JSON.stringify(store),
  })
  responses.set(G10_ADJUDICATED_KEY, {
    item_id: G10_ADJUDICATED_KEY,
    conclusion: String(closingAdjusted),
    remark: responses.get(G10_ADJUDICATED_KEY)?.remark ?? null,
  })
  try {
    window.dispatchEvent(new CustomEvent('g10:adjustment-writeback', { detail: writeback }))
    window.dispatchEvent(new CustomEvent('substantive:adjudicated', {
      detail: { accountCode: G10_ACCOUNT_CODE, adjudicatedAmount: closingAdjusted },
    }))
    if (opts?.source) {
      window.dispatchEvent(new CustomEvent('g10:adjustment-updated', { detail: { source: opts.source } }))
    }
    if (opts?.offerDisclosurePull) {
      dispatchG10OfferDisclosurePull(opts.source)
    }
  } catch { /* silent */ }
  return store
}

/** 从 G10-3 分录列表计算并提交回写 */
export function commitG10AdjustmentWritebackFromRows(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  rows: Parameters<typeof aggregateG10AdjustmentAjeRjeByRow>[0],
  opts?: G10CommitWritebackOpts,
): G10AdjRowStore {
  const wb = aggregateG10AdjustmentAjeRjeByRow(rows)
  return commitG10AdjustmentWriteback(responses, debouncedSave, wb, opts)
}

/** (三) 账面余额各分项期末审定合计 */
export function calcBookSectionTotal(store: G10AdjRowStore): number {
  const bookKeys = G10_ADJUDICATION_ITEMS.filter((d) => d.group === 'book_fv').map((d) => d.rowKey)
  return calcSubtotal(bookKeys.map((key) => {
    const row = store[key] ?? {}
    return g10RowClosingAdjusted(row)
  }))
}

// ─── G10-2 明细 ↔ 辅助核算 / G10-5 公允测试 ─────────────────────────────────

export const G10_FV_DIFF_THRESHOLD = 0.01

export interface G10AuxLiabilitySeed {
  liabilityName: string
  openingBalance: number
  closingBalance: number
  auxType: string
  auxCode: string
}

export interface G10FvPushDetailSource {
  liabilityName: string
  fairValueLevel?: string
  valuationMethod?: string
  closingAuditedFV?: number
}

/** 拉取 2101 辅助核算余额，按名称汇总为负债种子 */
export async function fetchG10AuxLiabilitySeeds(
  projectId: string,
  year?: number,
): Promise<{ seeds: G10AuxLiabilitySeed[]; dimType: string; error?: string; accountCode?: string }> {
  if (!projectId) return { seeds: [], dimType: '', error: '缺少项目 ID' }
  try {
    const http = (await import('@/utils/http')).default
    const { resolveAuditYearNumber } = await import('./workpaperAuditYear')
    const y = year
      ?? resolveAuditYearNumber(undefined, new Date().getFullYear() - 1)
      ?? (new Date().getFullYear() - 1)

    let rows: any[] = []
    let usedCode = G10_ACCOUNT_CODE
    for (const code of G10_ACCOUNT_ALIASES) {
      const { data } = await http.get(`/api/projects/${projectId}/ledger/aux-balance/${code}`, {
        params: { year: y },
        _silent: true,
      } as any)
      const list: any[] = Array.isArray(data)
        ? data
        : (data?.data ?? data?.items ?? data?.rows ?? [])
      if (list.length) {
        rows = list
        usedCode = code
        break
      }
    }

    if (!rows.length) {
      return {
        seeds: [],
        dimType: '',
        error: `${g10AccountLabel()} 无辅助核算余额（年度 ${y}）`,
      }
    }

    const byType = new Map<string, any[]>()
    for (const r of rows) {
      const t = String(r.aux_type ?? r.auxType ?? r.dim_type ?? '未分类').trim() || '未分类'
      if (!byType.has(t)) byType.set(t, [])
      byType.get(t)!.push(r)
    }
    let bestType = ''
    let bestRows: any[] = []
    for (const [t, list] of byType) {
      if (list.length > bestRows.length) {
        bestType = t
        bestRows = list
      }
    }

    const merged = new Map<string, G10AuxLiabilitySeed>()
    for (const r of bestRows) {
      const name = String(r.aux_name ?? r.auxName ?? r.name ?? '').trim()
      if (!name) continue
      const key = matchG10LiabilityKey(name)
      const opening = parseNum(r.opening_balance ?? r.openingBalance)
      const closing = parseNum(r.closing_balance ?? r.closingBalance ?? r.ending_balance)
      const prev = merged.get(key)
      if (prev) {
        prev.openingBalance = Math.round((prev.openingBalance + opening) * 100) / 100
        prev.closingBalance = Math.round((prev.closingBalance + closing) * 100) / 100
      } else {
        merged.set(key, {
          liabilityName: name,
          openingBalance: opening,
          closingBalance: closing,
          auxType: bestType,
          auxCode: String(r.aux_code ?? r.auxCode ?? ''),
        })
      }
    }

    const seeds = [...merged.values()].filter(
      (s) => Math.abs(s.openingBalance) > 0.01 || Math.abs(s.closingBalance) > 0.01,
    )
    if (!seeds.length) {
      return { seeds: [], dimType: bestType, error: `维度「${bestType}」无有效余额行` }
    }
    return { seeds, dimType: bestType, accountCode: usedCode }
  } catch (e: any) {
    return { seeds: [], dimType: '', error: e?.message || '辅助核算取数失败' }
  }
}

/** 辅助核算种子 → G10-2 明细行（期末−期初轧差暂入 FV 变动） */
export function seedG10DetailRowFromAux(
  seed: G10AuxLiabilitySeed,
  seq: number,
  existing?: G10DetailRow,
): G10DetailRow {
  const plug = Math.round((seed.closingBalance - seed.openingBalance) * 100) / 100
  const hasMovement = existing && (
    existing.movementInitialAmount
    || existing.movementFvChange
    || existing.interestExpense
    || existing.currentDecrease
  )
  const name = seed.liabilityName
  return enrichG10DetailRow(
    {
      rowId: existing?.rowId ?? `g10d-${Date.now().toString(36)}${Math.random().toString(36).slice(2, 5)}`,
      liabilityName: name,
      liabilityCategory: existing?.liabilityCategory ?? inferG10LiabilityCategory(name),
      liabilityType: existing?.liabilityType ?? inferG10LiabilityTypeFromName(name),
      openingInitialAmount: seed.openingBalance,
      openingFvAccum: existing?.openingFvAccum ?? 0,
      movementInitialAmount: existing?.movementInitialAmount ?? 0,
      movementFvChange: hasMovement ? existing!.movementFvChange : plug,
      interestExpense: existing?.interestExpense ?? 0,
      currentDecrease: existing?.currentDecrease ?? 0,
      closingAdjustment: existing?.closingAdjustment ?? 0,
      fairValueLevel: existing?.fairValueLevel,
      valuationMethod: existing?.valuationMethod ?? '',
      remark: existing?.remark
        || `辅助核算(${seed.auxType})取数；增减轧差暂入本期 FV 变动，请按凭证拆分`,
    },
    seq,
  )
}

/** 回写 G10-2：层次 / 估值方法 */
export function pushG10FvToDetail(
  responses: Map<string, ChecklistResponse>,
  debouncedSave: (itemId: string, data: Partial<ChecklistResponse>) => void,
  fvRows: G10FvPushDetailSource[],
): number {
  const raw = responses.get(G10_DETAIL_ROWS_KEY)?.remark
  if (!raw) return 0
  let details: Record<string, unknown>[]
  try {
    details = JSON.parse(raw)
    if (!Array.isArray(details)) return 0
  } catch {
    return 0
  }

  const byKey = new Map(
    fvRows
      .filter((r) => r.liabilityName?.trim())
      .map((r) => [matchG10LiabilityKey(r.liabilityName), r]),
  )
  let n = 0
  const next = details.map((d) => {
    const hit = byKey.get(matchG10LiabilityKey(String(d.liabilityName ?? '')))
    if (!hit) return d
    n += 1
    return {
      ...d,
      fairValueLevel: hit.fairValueLevel || d.fairValueLevel,
      valuationMethod: hit.valuationMethod || d.valuationMethod,
    }
  })
  if (n) {
    debouncedSave(G10_DETAIL_ROWS_KEY, { remark: JSON.stringify(next) })
    try {
      window.dispatchEvent(new CustomEvent('g10:detail-updated', {
        detail: { source: 'G10-5→G10-2', timestamp: Date.now() },
      }))
    } catch { /* silent */ }
  }
  return n
}

export function parseG10DetailRows(json: string | null | undefined): G10DetailRow[] {
  if (!json) return []
  try {
    const arr = JSON.parse(json)
    if (!Array.isArray(arr)) return []
    return arr.map((r: any, i: number) =>
      enrichG10DetailRow({ ...r, rowId: r.rowId || r.id || `g10d-${i}` }, i + 1),
    )
  } catch {
    return []
  }
}
