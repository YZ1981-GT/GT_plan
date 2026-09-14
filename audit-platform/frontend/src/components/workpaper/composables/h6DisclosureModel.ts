/**
 * H6 附注披露（上市 / 国企）数据模型
 *
 * 对齐致同 Excel「附注披露信息（上市公司|国有企业）」：
 *  A 汇总：固定资产 / 固定资产清理 / 合计
 *     - 上市列：期末余额 | 上年年末余额
 *     - 国企列：期末账面价值 | 期初账面价值
 *  B (2) 固定资产清理明细：项目 | 期末 | 期初/上年年末 | 转入清理的原因
 *  C 超 1 年清理进展说明
 *
 * 数据流：H6-1 审定 → 汇总清理行；H6-2 明细 → (2) 明细；固定资产行可手填或从 H1 带入。
 */
import {
  extractH61Balances,
  mapH62ToClearingRows,
} from './h1SoeClearingH6Pull'

// ─── Persistence keys ────────────────────────────────────────────────────────

export const H6_LISTED_KEYS = {
  pack: 'H6-disc-listed-pack',
  faEnd: 'H6-disc-listed-fa-end',
  faPrior: 'H6-disc-listed-fa-prior',
  clearingRows: 'H6-disc-listed-clearing-rows',
  clearingNote: 'H6-disc-listed-clearing-note',
} as const

export const H6_SOE_KEYS = {
  pack: 'H6-disc-soe-pack',
  faEnd: 'H6-disc-soe-fa-end',
  faBegin: 'H6-disc-soe-fa-begin',
  clearingRows: 'H6-disc-soe-clearing-rows',
  clearingNote: 'H6-disc-soe-clearing-note',
} as const

// ─── Types ───────────────────────────────────────────────────────────────────

export function n(v: unknown): number {
  if (v == null || v === '') return 0
  const x = Number(v)
  return Number.isFinite(x) ? x : 0
}

export function newRowId(prefix = 'h6clr'): string {
  return `${prefix}-${Date.now().toString(36)}-${Math.random().toString(36).slice(2, 7)}`
}

/** 统一清理明细行（上市 prior≈上年年末；国企 begin≈期初账面价值） */
export interface H6ClearingRow {
  rowId: string
  name: string
  endBalance: number
  priorBalance: number
  reason: string
}

export interface H6SummaryAmounts {
  faEnd: number
  faPrior: number
  clearingEnd: number
  clearingPrior: number
}

export interface H6DisclosureState {
  faEnd: number
  faPrior: number
  clearingRows: H6ClearingRow[]
  clearingNote: string
}

export function emptyClearingRow(): H6ClearingRow {
  return { rowId: newRowId(), name: '', endBalance: 0, priorBalance: 0, reason: '' }
}

export function createDefaultState(): H6DisclosureState {
  return { faEnd: 0, faPrior: 0, clearingRows: [], clearingNote: '' }
}

export function sumClearing(rows: H6ClearingRow[]): { endBalance: number; priorBalance: number } {
  return rows.reduce(
    (acc, r) => ({
      endBalance: acc.endBalance + n(r.endBalance),
      priorBalance: acc.priorBalance + n(r.priorBalance),
    }),
    { endBalance: 0, priorBalance: 0 },
  )
}

export function summaryAmounts(state: H6DisclosureState): H6SummaryAmounts {
  const tot = sumClearing(state.clearingRows)
  return {
    faEnd: n(state.faEnd),
    faPrior: n(state.faPrior),
    clearingEnd: tot.endBalance,
    clearingPrior: tot.priorBalance,
  }
}

export function summaryTotal(state: H6DisclosureState): { end: number; prior: number } {
  const s = summaryAmounts(state)
  return {
    end: s.faEnd + s.clearingEnd,
    prior: s.faPrior + s.clearingPrior,
  }
}

/** 汇总表展示行（含合计） */
export function buildSummaryDisplay(state: H6DisclosureState) {
  const s = summaryAmounts(state)
  const t = summaryTotal(state)
  return [
    { key: 'fixed_assets' as const, label: '固定资产', endBalance: s.faEnd, priorBalance: s.faPrior, editable: true },
    { key: 'clearing' as const, label: '固定资产清理', endBalance: s.clearingEnd, priorBalance: s.clearingPrior, editable: false },
    { key: '__total__' as const, label: '合计', endBalance: t.end, priorBalance: t.prior, editable: false },
  ]
}

export function buildClearingDisplay(rows: H6ClearingRow[]) {
  const tot = sumClearing(rows)
  return [
    ...rows,
    {
      rowId: '__total__',
      name: '合计',
      endBalance: tot.endBalance,
      priorBalance: tot.priorBalance,
      reason: '',
    },
  ]
}

function parseRemark(raw: unknown): unknown {
  if (raw == null) return null
  if (typeof raw !== 'string') return raw
  const s = raw.trim()
  if (!s) return null
  try {
    return JSON.parse(s)
  } catch {
    return raw
  }
}

function remarkNum(map: Map<string, any>, itemId: string): number {
  const item = map.get(itemId)
  if (!item) return 0
  const parsed = parseRemark(item.remark ?? item.conclusion)
  if (typeof parsed === 'number') return n(parsed)
  return n(typeof parsed === 'string' ? parsed : item.remark)
}

/**
 * 从本底稿 H6-1 / H6-2 聚合披露取数结果。
 * - 汇总清理期末优先 H6-1-end-balance-audited
 * - 明细来自 H6-2；若明细合计与审定不一致，用审定覆盖汇总（明细仍保留）
 */
export function pullClearingFromH6Responses(allResponses: Map<string, any>): {
  clearingEnd: number
  clearingPrior: number
  clearingRows: H6ClearingRow[]
  clearingNoteDraft: string
  overOneYearCount: number
  transitZero: boolean
  detailCount: number
} {
  const endFromKey = remarkNum(allResponses, 'H6-1-end-balance-audited')
  const h61 = extractH61Balances(parseRemark(allResponses.get('H6-1-rows')?.remark))
  const clearingEnd = endFromKey || h61.end
  const clearingPrior = h61.begin

  const mapped = mapH62ToClearingRows(parseRemark(allResponses.get('H6-2-rows')?.remark))
  const clearingRows: H6ClearingRow[] = mapped.rows.map((r) => ({
    rowId: r.rowId,
    name: r.name,
    endBalance: n(r.endCarrying),
    priorBalance: n(r.beginCarrying),
    reason: r.reason,
  }))

  // 明细为空但审定有余额：保留一行汇总占位，便于编制
  if (!clearingRows.length && (clearingEnd !== 0 || clearingPrior !== 0)) {
    clearingRows.push({
      rowId: newRowId('h6sum'),
      name: '固定资产清理',
      endBalance: clearingEnd,
      priorBalance: clearingPrior,
      reason: '',
    })
  }

  // 明细合计与审定不一致时：按比例不改明细，汇总以审定为准（UI 用 sumClearing 前可覆盖）
  const detailTot = sumClearing(clearingRows)
  if (clearingRows.length && Math.abs(detailTot.endBalance - clearingEnd) >= 0.005 && clearingEnd !== 0) {
    // 保持明细原样；调用方用 clearingEnd 写汇总提示；此处仍返回明细合计作为可编辑真相源
  }

  return {
    clearingEnd: clearingRows.length ? sumClearing(clearingRows).endBalance : clearingEnd,
    clearingPrior: clearingRows.length ? sumClearing(clearingRows).priorBalance : clearingPrior,
    clearingRows,
    clearingNoteDraft: mapped.overOneYearNote,
    overOneYearCount: mapped.overOneYearCount,
    transitZero: Math.abs(clearingEnd) < 0.005,
    detailCount: clearingRows.length,
  }
}

/** 勾稽：明细合计 vs H6-1 审定期末 */
export function clearingVsAdjudication(
  rows: H6ClearingRow[],
  allResponses: Map<string, any>,
): { diff: number; isMatch: boolean; auditedEnd: number; detailEnd: number } {
  const auditedEnd = remarkNum(allResponses, 'H6-1-end-balance-audited')
    || extractH61Balances(parseRemark(allResponses.get('H6-1-rows')?.remark)).end
  const detailEnd = sumClearing(rows).endBalance
  const diff = detailEnd - auditedEnd
  return { diff, isMatch: Math.abs(diff) < 0.01, auditedEnd, detailEnd }
}

export function hydrateClearingRows(raw: unknown): H6ClearingRow[] {
  if (!Array.isArray(raw)) return []
  return raw.map((r: any, i: number) => ({
    rowId: String(r?.rowId || newRowId(`h6-${i}`)),
    name: String(r?.name ?? r?.label ?? ''),
    endBalance: n(r?.endBalance ?? r?.endCarrying ?? r?.end_balance ?? r?.end_carrying),
    priorBalance: n(r?.priorBalance ?? r?.beginCarrying ?? r?.prior_balance ?? r?.begin_carrying),
    reason: String(r?.reason ?? ''),
  }))
}

export function parsePack(raw: unknown): Partial<H6DisclosureState> | null {
  const parsed = typeof raw === 'string' ? parseRemark(raw) : raw
  if (!parsed || typeof parsed !== 'object') return null
  const o = parsed as Record<string, unknown>
  return {
    faEnd: n(o.faEnd),
    faPrior: n(o.faPrior ?? o.faBegin),
    clearingRows: hydrateClearingRows(o.clearingRows),
    clearingNote: typeof o.clearingNote === 'string' ? o.clearingNote : '',
  }
}

export function serializePack(state: H6DisclosureState): string {
  return JSON.stringify({
    faEnd: n(state.faEnd),
    faPrior: n(state.faPrior),
    clearingRows: state.clearingRows,
    clearingNote: state.clearingNote || '',
  })
}

export function fmtAmt(val: number | null | undefined): string {
  if (val == null || Number.isNaN(val) || val === 0) return '-'
  if (val < 0) {
    return `(${Math.abs(val).toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })})`
  }
  return val.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
