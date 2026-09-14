/**
 * G3-1 审定表行存储辅助 — 对齐 g2AdjudicationItems 的调整回写模式
 */
import { parseNum, calcOverdueDays } from './useG3DivRecFormulaEngine'
import { G3_ACCOUNT_CODE, G3_OVERDUE_STORAGE_KEY } from './g3Constants'

export { G3_OVERDUE_STORAGE_KEY }

const G3_ACCOUNT_PREFIX = G3_ACCOUNT_CODE


/** |变动率| 超过该阈值时原因分析必填（对齐 Excel「超过30%」） */
export const G3_CHANGE_RATE_THRESHOLD = 0.3

/** 账龄一年以上判定天数（对齐 Excel「账龄一年以上的应收股利」） */
export const G3_AGING_YEAR_DAYS = 365

/** G3-3 确认调整默认回写到的被投资方行 */
export const G3_ADJ_WRITEBACK_ID = 'g3-adj-writeback'
export const G3_ADJ_WRITEBACK_INVESTEE = '账项调整汇总'

export interface StoredG3AdjRow {
  id: string
  investeeName: string
  shareholdingRatio: number
  openingUnadjusted: number
  openingAJE: number
  openingRJE: number
  currentDeclared: number
  currentReceived: number
  closingAJE: number
  closingRJE: number
  remark: string
  indexRef: string
  /** |变动率|>30% 时填写的原因分析 */
  reasonAnalysis?: string
}

/** G3-1 账龄汇总（期末审定拆分，参照 G3-5） */
export interface G3AgingSummary {
  closingAuditedTotal: number
  /** 逾期天数 ≥365 的应收金额合计（来自 G3-5） */
  over1YearAmount: number
  /** 期末审定合计 − 一年以上（下限 0） */
  within1YearAmount: number
  over1YearCount: number
  /** 一年以上金额是否超过审定合计（勾稽异常） */
  overAgeExceedsTotal: boolean
  source: 'g3-5' | 'empty'
}

export interface G3AdjustmentLineLike {
  entryType?: string
  /** D4/Excel 类别：账项调整 | 报表调整 | 其他（优先于 entryType） */
  category?: string
  accountCode?: string
  accountName?: string
  debitAmount?: number | string
  creditAmount?: number | string
}

function isG3DividendAccount(line: G3AdjustmentLineLike): boolean {
  const code = String(line.accountCode ?? '').trim()
  if (code.startsWith(G3_ACCOUNT_PREFIX)) return true
  return String(line.accountName ?? '').includes('应收股利')
}

function resolveG3EntryKind(line: G3AdjustmentLineLike): 'AJE' | 'RJE' {
  const cat = String(line.category ?? '')
  if (cat === '报表调整' || cat.includes('报表') || cat.includes('重分类')) return 'RJE'
  const type = String(line.entryType ?? 'AJE').toUpperCase()
  if (type === 'RJE' || type.includes('RJE')) return 'RJE'
  return 'AJE'
}

/** 解析科目 1131 上 AJE/RJE 净额（借 − 贷；资产增加为正）。支持 category 或 entryType。 */
export function computeG3NetAdjustments(lines: G3AdjustmentLineLike[]): {
  netAJE: number
  netRJE: number
} {
  let netAJE = 0
  let netRJE = 0
  for (const line of lines) {
    if (!isG3DividendAccount(line)) continue
    const net = parseNum(line.debitAmount) - parseNum(line.creditAmount)
    if (resolveG3EntryKind(line) === 'RJE') netRJE += net
    else netAJE += net
  }
  return { netAJE, netRJE }
}

/**
 * 将 G3-3 净调整写入 G3-1 行存储（期末 AJE/RJE）。
 * 固定落到「账项调整汇总」行，重复确认覆盖（幂等）。
 */
export function applyG3AdjustmentWriteback(
  store: StoredG3AdjRow[],
  netAJE: number,
  netRJE: number,
): StoredG3AdjRow[] {
  const aje = Number.isFinite(Number(netAJE)) ? Number(netAJE) : 0
  const rje = Number.isFinite(Number(netRJE)) ? Number(netRJE) : 0
  const note = '来自 G3-3 调整分录确认回写'
  const rows = Array.isArray(store) ? [...store] : []
  const idx = rows.findIndex(
    (r) => r.id === G3_ADJ_WRITEBACK_ID || r.investeeName === G3_ADJ_WRITEBACK_INVESTEE,
  )
  if (idx >= 0) {
    const prev = rows[idx]
    const prevRemark = String(prev.remark || '')
    rows[idx] = {
      ...prev,
      closingAJE: aje,
      closingRJE: rje,
      remark: prevRemark.includes('G3-3') ? prevRemark : [prevRemark, note].filter(Boolean).join('；'),
    }
    return rows
  }
  rows.push({
    id: G3_ADJ_WRITEBACK_ID,
    investeeName: G3_ADJ_WRITEBACK_INVESTEE,
    shareholdingRatio: 0,
    openingUnadjusted: 0,
    openingAJE: 0,
    openingRJE: 0,
    currentDeclared: 0,
    currentReceived: 0,
    closingAJE: aje,
    closingRJE: rje,
    remark: note,
    indexRef: '',
    reasonAnalysis: '',
  })
  return rows
}

export function parseG3AdjStore(raw: string | null | undefined): StoredG3AdjRow[] {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: Partial<StoredG3AdjRow>) => ({
      id: String(r.id ?? ''),
      investeeName: String(r.investeeName ?? ''),
      shareholdingRatio: parseNum(r.shareholdingRatio),
      openingUnadjusted: parseNum(r.openingUnadjusted),
      openingAJE: parseNum(r.openingAJE),
      openingRJE: parseNum(r.openingRJE),
      currentDeclared: parseNum(r.currentDeclared),
      currentReceived: parseNum(r.currentReceived),
      closingAJE: parseNum(r.closingAJE),
      closingRJE: parseNum(r.closingRJE),
      remark: String(r.remark ?? ''),
      indexRef: String(r.indexRef ?? ''),
      reasonAnalysis: String(r.reasonAnalysis ?? ''),
    })).filter((r) => r.id)
  } catch {
    return []
  }
}

/** 解析 G3-5 逾期行（存储于 conclusion；逾期天数按约定付款日重算） */
export function parseG3OverdueStore(
  raw: string | null | undefined,
  asOf: Date = new Date(),
): Array<{
  receivableAmount: number
  overdueDays: number
  investeeName: string
}> {
  if (!raw) return []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    return parsed.map((r: Record<string, unknown>) => {
      const agreed = String(r.agreedPaymentDate ?? '')
      const agreedDate = agreed ? new Date(agreed) : null
      const overdueDays =
        agreedDate && !Number.isNaN(agreedDate.getTime())
          ? calcOverdueDays(asOf, agreedDate)
          : parseNum(r.overdueDays)
      // 金额优先序：显式 receivableAmount → 期末公式 → 审定余额
      const closingFromRoll =
        parseNum(r.openingBalance) + parseNum(r.periodDebit) - parseNum(r.periodCredit)
      const hasRollForward =
        'openingBalance' in r || 'periodDebit' in r || 'periodCredit' in r
      const receivableAmount = parseNum(
        r.receivableAmount ??
          (hasRollForward ? closingFromRoll : undefined) ??
          r.closingBalance ??
          r.auditedBalance,
      )
      return {
        receivableAmount,
        overdueDays,
        investeeName: String(r.investeeName ?? ''),
      }
    })
  } catch {
    return []
  }
}

/**
 * 账龄一年内/一年以上汇总：一年以上取自 G3-5（逾期≥365天），
 * 一年以内 = 期末审定合计 − 一年以上（对齐 Excel G3-1 账龄行口径）。
 */
export function computeG3AgingSummary(
  closingAuditedTotal: number,
  overdueRaw: string | null | undefined,
  asOf: Date = new Date(),
): G3AgingSummary {
  const rows = parseG3OverdueStore(overdueRaw, asOf).filter(
    (r) => r.investeeName.trim() || r.receivableAmount !== 0,
  )
  const aged = rows.filter((r) => r.overdueDays >= G3_AGING_YEAR_DAYS)
  const over1YearAmount = aged.reduce((s, r) => s + r.receivableAmount, 0)
  const overAgeExceedsTotal = over1YearAmount - closingAuditedTotal > 0.005
  const within1YearAmount = Math.max(0, closingAuditedTotal - over1YearAmount)
  return {
    closingAuditedTotal,
    over1YearAmount,
    within1YearAmount,
    over1YearCount: aged.length,
    overAgeExceedsTotal,
    source: rows.length > 0 ? 'g3-5' : 'empty',
  }
}

/** 附注上市行：从 G3-1 审定行带入 */
export interface G3ListedDisclosureSeedRow {
  id: string
  investeeName: string
  openingBalance: number
  currentIncrease: number
  currentDecrease: number
  remark: string
}

/** 附注国企行：从 G3-1 审定行带入 */
export interface G3SoeDisclosureSeedRow {
  id: string
  investeeName: string
  openingBalance: number
  currentChange: number
  remark: string
}

function isInvesteeDataRow(r: StoredG3AdjRow): boolean {
  if (!r.investeeName?.trim()) return false
  if (r.id === G3_ADJ_WRITEBACK_ID) return false
  if (r.investeeName === G3_ADJ_WRITEBACK_INVESTEE) return false
  return true
}

function openingAudited(r: StoredG3AdjRow): number {
  return parseNum(r.openingUnadjusted) + parseNum(r.openingAJE) + parseNum(r.openingRJE)
}

/** G3-1 → 附注上市：期初审定 / 本期宣告 / 本期收回 */
export function buildListedDisclosureFromAdj(store: StoredG3AdjRow[]): G3ListedDisclosureSeedRow[] {
  return store.filter(isInvesteeDataRow).map((r) => ({
    id: `dl-${r.id}`,
    investeeName: r.investeeName.trim(),
    openingBalance: openingAudited(r),
    currentIncrease: parseNum(r.currentDeclared),
    currentDecrease: parseNum(r.currentReceived),
    remark: r.remark || '',
  }))
}

/** G3-1 → 附注国企：期初审定 / 本期净变动(宣告−收回) */
export function buildSoeDisclosureFromAdj(store: StoredG3AdjRow[]): G3SoeDisclosureSeedRow[] {
  return store.filter(isInvesteeDataRow).map((r) => ({
    id: `ds-${r.id}`,
    investeeName: r.investeeName.trim(),
    openingBalance: openingAudited(r),
    currentChange: parseNum(r.currentDeclared) - parseNum(r.currentReceived),
    remark: r.remark || '',
  }))
}

/** 现有附注表是否仅为空占位（可安全被审定带入覆盖） */
export function isG3DisclosurePlaceholder(
  rows: Array<{ investeeName?: string; openingBalance?: number; currentIncrease?: number; currentDecrease?: number; currentChange?: number }>,
): boolean {
  if (!rows.length) return true
  return rows.every((r) => {
    const name = String(r.investeeName ?? '').trim()
    const nums =
      parseNum(r.openingBalance)
      + parseNum(r.currentIncrease)
      + parseNum(r.currentDecrease)
      + parseNum(r.currentChange)
    return !name && Math.abs(nums) < 0.005
  })
}

/** G3-2 明细按被投资方汇总后的未审要素（供 G3-1 同步） */
export interface G3DetailInvesteeAgg {
  investeeName: string
  shareholdingRatio: number
  currentDeclared: number
  currentReceived: number
}

/**
 * 解析 G3-2 明细 conclusion，按被投资方合并本期宣告/收回。
 * 宣告优先 dividendReceivable，缺省用 totalDividend；持股比例取加权（按宣告额）否则取最大非零。
 */
export function aggregateG3DetailByInvestee(raw: string | null | undefined): G3DetailInvesteeAgg[] {
  if (!raw) return []
  let list: Array<Record<string, unknown>> = []
  try {
    const parsed = JSON.parse(raw)
    if (!Array.isArray(parsed)) return []
    list = parsed
  } catch {
    return []
  }

  type Acc = {
    name: string
    declared: number
    received: number
    ratioWeighted: number
    weight: number
    ratioMax: number
  }
  const byName = new Map<string, Acc>()

  for (const d of list) {
    const name = String(d.investeeName ?? '').trim()
    if (!name) continue
    const declared = parseNum(
      d.dividendReceivable ?? d.totalDividend ?? 0,
    )
    const received = parseNum(d.receivedAmount)
    const ratio = parseNum(d.shareholdingRatio)
    const acc = byName.get(name) ?? {
      name,
      declared: 0,
      received: 0,
      ratioWeighted: 0,
      weight: 0,
      ratioMax: 0,
    }
    acc.declared += declared
    acc.received += received
    if (ratio > 0) {
      acc.ratioMax = Math.max(acc.ratioMax, ratio)
      const w = Math.abs(declared) > 0.005 ? Math.abs(declared) : 1
      acc.ratioWeighted += ratio * w
      acc.weight += w
    }
    byName.set(name, acc)
  }

  return [...byName.values()].map((a) => ({
    investeeName: a.name,
    shareholdingRatio:
      a.weight > 0 ? Math.round((a.ratioWeighted / a.weight) * 10000) / 10000 : a.ratioMax,
    currentDeclared: a.declared,
    currentReceived: a.received,
  }))
}

/**
 * 将 G3-2 汇总写入 G3-1 存储：覆盖本期宣告/收回/持股比例，保留期初与期末 AJE/RJE。
 * 不碰「账项调整汇总」行；可新建被投资方行。
 */
export function applyG3DetailSyncToAdjStore(
  store: StoredG3AdjRow[],
  aggs: G3DetailInvesteeAgg[],
): { next: StoredG3AdjRow[]; added: number; updated: number } {
  const next = Array.isArray(store) ? [...store] : []
  let added = 0
  let updated = 0
  const byName = new Map(
    next
      .filter(isInvesteeDataRow)
      .map((r) => [r.investeeName.trim(), r] as const),
  )

  for (const agg of aggs) {
    const existing = byName.get(agg.investeeName)
    if (existing) {
      const idx = next.findIndex((r) => r.id === existing.id)
      if (idx < 0) continue
      next[idx] = {
        ...next[idx],
        shareholdingRatio: agg.shareholdingRatio || next[idx].shareholdingRatio,
        currentDeclared: agg.currentDeclared,
        currentReceived: agg.currentReceived,
      }
      updated++
    } else {
      const id = `g3-d2-${Date.now()}-${added}`
      const row: StoredG3AdjRow = {
        id,
        investeeName: agg.investeeName,
        shareholdingRatio: agg.shareholdingRatio,
        openingUnadjusted: 0,
        openingAJE: 0,
        openingRJE: 0,
        currentDeclared: agg.currentDeclared,
        currentReceived: agg.currentReceived,
        closingAJE: 0,
        closingRJE: 0,
        remark: '来自 G3-2 明细同步',
        indexRef: '',
        reasonAnalysis: '',
      }
      next.push(row)
      byName.set(agg.investeeName, row)
      added++
    }
  }
  return { next, added, updated }
}
