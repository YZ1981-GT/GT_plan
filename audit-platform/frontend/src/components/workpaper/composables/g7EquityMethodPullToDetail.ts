/**
 * G7-14 权益法测算 → G7-2 权益法行 跨册带入（Task 4.3 / Decision 2）。
 *
 * 带入目标是 **G7-2 权益法行**（G7EquityRow），写入后由既有 `g7:detail-updated`
 * 传导到 G7-1（G7-1 只做只读对照差异，不写值）。带入的是权益法运动分量
 * （opening/profitLoss/oci/otherEquity/dividend），G7-2 的期末由 `recalcG7EquityRow`
 * 派生 → 与 G7-14 `closingBalance` 对照（复用 `calcClosingReconVariance`，不新造公式）。
 *
 * Cross_Book_Pull：ACNR `resolve-instance` 解析 Method_Group 的 G7-14 wp_id
 * → 读 `checklist-responses` → 纯函数映射（缺源返回空集合，Property 10）。
 */
import http from '@/utils/http'
import {
  flattenG714Rows,
  makeG714ConclusionGetter,
  resolveG714PayloadFromChecklist,
  pickDefinedNum,
  normalizeInvesteeKey,
} from './g7EquityMethodCrossSheet'
import { fetchChecklistResponseMap } from './g4CrossHelpers'
import {
  createG7EquityRow,
  recalcG7EquityRow,
  type G7DetailState,
  type G7EquityRow,
} from './g7DetailModel'

export interface G7EquityClosingRow {
  investeeName: string
  closingAmount: number
  /** 权益法运动分量（供带入 G7-2 权益法行的直接输入；派生期末与 closingAmount 对齐） */
  opening: number
  profitLoss: number
  oci: number
  otherEquity: number
  dividend: number
}

export interface G7EquityPullDiff {
  investeeName: string
  current: number   // G7-2 权益法行当前派生期末
  incoming: number  // G7-14 期末余额
  diff: number
  matched: boolean
}

/** 纯函数：从 G7-14 payload 提取逐户期末余额 + 权益法运动分量 */
export function extractG7_14ClosingRows(payload: unknown): G7EquityClosingRow[] {
  const rows = flattenG714Rows(payload as any)
  const out: G7EquityClosingRow[] = []
  const seen = new Set<string>()
  for (const r of rows) {
    const name = String(r?.investeeName ?? r?.investee_name ?? '').trim()
    if (!name) continue
    const key = normalizeInvesteeKey(name)
    if (seen.has(key)) continue
    const closing = pickDefinedNum(r.closingBalance, r.closing_balance, r.lteiBookBalance, r.closingAmount)
    const opening = pickDefinedNum(r.openingBalance, r.opening_balance)
    const profitLoss = pickDefinedNum(r.equityShare, r.equity_share)
    const oci = pickDefinedNum(r.ociShare, r.oci_share)
    const otherEquity = pickDefinedNum(r.otherEquityShare, r.other_equity_share)
    const dividend = pickDefinedNum(r.dividendDistributed, r.dividend_distributed)
    // 全零且无期末的行不带入（避免臆造空行）
    if (Math.abs(closing) < 1e-9 && Math.abs(opening) < 1e-9
      && Math.abs(profitLoss) < 1e-9 && Math.abs(oci) < 1e-9
      && Math.abs(otherEquity) < 1e-9 && Math.abs(dividend) < 1e-9) {
      continue
    }
    seen.add(key)
    out.push({ investeeName: name, closingAmount: closing, opening, profitLoss, oci, otherEquity, dividend })
  }
  return out
}

/** 纯函数：逐户对照（G7-2 权益法行当前派生期末 vs G7-14 期末余额） */
export function buildEquityPullDiff(
  detail: G7DetailState,
  src: G7EquityClosingRow[],
): G7EquityPullDiff[] {
  const byName = new Map<string, G7EquityRow>()
  for (const row of detail.equityRows) {
    byName.set(normalizeInvesteeKey(row.investeeName), row)
  }
  return src.map((s) => {
    const row = byName.get(normalizeInvesteeKey(s.investeeName))
    const current = row ? Number(row.closingAmount || 0) : 0
    const incoming = Math.round(s.closingAmount * 100) / 100
    return {
      investeeName: s.investeeName,
      current: Math.round(current * 100) / 100,
      incoming,
      diff: Math.round((current - incoming) * 100) / 100,
      matched: !!row,
    }
  })
}

/** 解析 Method_Group 的 G7-14 wp_id 集（ACNR resolve-instance；缺源返回空集合）。 */
async function resolveG714WorkpaperIds(projectId: string): Promise<string[]> {
  const ids = new Set<string>()
  if (!projectId) return []
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

export interface G7EquityPullApplyResult {
  added: number
  filled: number
  skipped: number
}

/** G7-14 运动分量是否非空（用于 Persist_First「只填空」判定：目标字段全为 0 才写入）。 */
function equityRowIsEmpty(row: G7EquityRow): boolean {
  return (
    Math.abs(Number(row.openingAmount || 0)) < 1e-9 &&
    Math.abs(Number(row.profitLossAdjustment || 0)) < 1e-9 &&
    Math.abs(Number(row.otherComprehensiveIncome || 0)) < 1e-9 &&
    Math.abs(Number(row.otherEquityChange || 0)) < 1e-9 &&
    Math.abs(Number(row.dividendReceived || 0)) < 1e-9
  )
}

/**
 * 纯函数：把 G7-14 逐户运动分量按 Persist_First 写入 G7-2 权益法行（Decision 2 / Property 2）。
 *
 * - 按 `normalizeInvesteeKey` 匹配既有 `state.equityRows`；
 * - `overwrite=false`（默认）时只对「运动分量全为 0」的行写入，已填行不动（skipped）；
 * - 未匹配单位新建 `G7EquityRow`（默认 `joint_venture`，控制类型由审计师后续按 G7-4 判断）；
 * - 写入后 `recalcG7EquityRow` 派生期末余额（与 G7-14 `closingBalance` 对照）。
 *
 * 幂等（Property 4）：同一 src 连续应用两次，第二次全部命中已填行 → skipped，行数与字段不变。
 */
export function applyEquityPullToDetail(
  state: G7DetailState,
  src: G7EquityClosingRow[],
  opts: { overwrite: boolean } = { overwrite: false },
): G7EquityPullApplyResult {
  let added = 0
  let filled = 0
  let skipped = 0
  const byKey = new Map<string, G7EquityRow>()
  for (const row of state.equityRows) {
    byKey.set(normalizeInvesteeKey(row.investeeName), row)
  }
  const write = (row: G7EquityRow, s: G7EquityClosingRow): void => {
    row.openingAmount = s.opening
    row.profitLossAdjustment = s.profitLoss
    row.otherComprehensiveIncome = s.oci
    row.otherEquityChange = s.otherEquity
    row.dividendReceived = s.dividend
    recalcG7EquityRow(row)
  }
  for (const s of src) {
    const key = normalizeInvesteeKey(s.investeeName)
    const existing = byKey.get(key)
    if (existing) {
      if (opts.overwrite || equityRowIsEmpty(existing)) {
        write(existing, s)
        filled += 1
      } else {
        skipped += 1
      }
      continue
    }
    const row = createG7EquityRow(state.equityRows.length + 1, s.investeeName, 'joint_venture')
    write(row, s)
    state.equityRows.push(row)
    byKey.set(key, row)
    added += 1
  }
  return { added, filled, skipped }
}

/** Cross_Book_Pull：读 G7-14 逐户期末余额；未实例化/无数据返回空集合（Property 10）。 */
export async function pullG7_14ForDetail(projectId: string): Promise<G7EquityClosingRow[]> {
  const wpIds = await resolveG714WorkpaperIds(projectId)
  const byName = new Map<string, G7EquityClosingRow>()
  for (const wpId of wpIds) {
    try {
      const map = await fetchChecklistResponseMap(wpId)
      const getter = makeG714ConclusionGetter(map)
      const payload = resolveG714PayloadFromChecklist(getter)
      for (const row of extractG7_14ClosingRows(payload)) {
        byName.set(normalizeInvesteeKey(row.investeeName), row)
      }
    } catch { /* 缺源安全 */ }
  }
  return [...byName.values()]
}
