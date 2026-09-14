/**
 * G11-4 收益率分析 — 持有期间项目 ↔ 资产科目映射
 * 用于从试算表带入平均投资的期初/期末余额。
 * 处置/控制权利得等一次性项目不映射（收益率常为 N/A）。
 */
import { parseNum } from './useG11FormulaEngine'

export interface G11BalanceAccountDef {
  /** 适用的 G11-4 / G11-1 rowKey */
  rowKeys: string[]
  /** 标准科目编码（优先精确，再前缀） */
  codes: string[]
  /** 科目名称关键词（编码冲突时消歧，如 1503） */
  nameHints: string[]
  /** 界面展示 */
  label: string
  /** 关联底稿提示 */
  wpHint?: string
}

/** 仅「持有期间」收益行参与 TB 余额带入 */
export const G11_RETURN_RATE_BALANCE_SOURCES: G11BalanceAccountDef[] = [
  {
    rowKeys: ['equity_method'],
    codes: ['1511'],
    nameHints: ['长期股权'],
    label: '1511 长期股权投资',
    wpHint: 'G7',
  },
  {
    rowKeys: ['trading_hold'],
    codes: ['1101'],
    nameHints: ['交易性金融资产'],
    label: '1101 交易性金融资产',
    wpHint: 'G1',
  },
  {
    rowKeys: ['debt_hold_interest'],
    codes: ['1501'],
    nameHints: ['债权投资', '持有至到期'],
    label: '1501 债权投资',
    wpHint: 'G4',
  },
  {
    rowKeys: ['oth_debt_hold_interest'],
    // 标准科目表 1506；兼容旧 CoA/TB 仍用 1503 记其他债权
    codes: ['1506', '1503'],
    nameHints: ['其他债权'],
    label: '1506 其他债权投资',
    wpHint: 'G6',
  },
  {
    rowKeys: ['onfa_hold'],
    codes: ['1519', '1510', '1504'],
    nameHints: ['其他非流动金融'],
    label: '1519 其他非流动金融资产',
    wpHint: 'G9',
  },
  {
    rowKeys: ['oei_dividend'],
    // 标准科目表 1507；兼容旧 CoA/G8 仍用 1503 记其他权益工具
    codes: ['1507', '1503'],
    nameHints: ['其他权益工具'],
    label: '1507 其他权益工具投资',
    wpHint: 'G8',
  },
]

export interface G11TbRowLike {
  standard_account_code?: string
  account_code?: string
  account_name?: string
  standard_account_name?: string
  opening_balance?: number | string | null
  closing_balance?: number | string | null
  ending_balance?: number | string | null
  audited_amount?: number | string | null
  unadjusted_amount?: number | string | null
  debit_amount?: number | string | null
  credit_amount?: number | string | null
}

export interface G11TbOpenClose {
  opening: number
  closing: number
  matchedCodes: string[]
}

function rowCode(r: G11TbRowLike): string {
  return String(r.standard_account_code ?? r.account_code ?? '').trim()
}

function rowName(r: G11TbRowLike): string {
  return String(r.account_name ?? r.standard_account_name ?? '').trim()
}

/** 期末余额：优先 closing/ending，再审定/未审，再借−贷（资产） */
export function pickTbClosing(row: G11TbRowLike): number {
  const direct = row.closing_balance ?? row.ending_balance ?? row.audited_amount ?? row.unadjusted_amount
  if (direct != null && String(direct).trim() !== '') {
    const n = parseNum(direct)
    if (Number.isFinite(n)) return n
  }
  return parseNum(row.debit_amount) - parseNum(row.credit_amount)
}

export function pickTbOpening(row: G11TbRowLike): number {
  if (row.opening_balance != null && String(row.opening_balance).trim() !== '') {
    return parseNum(row.opening_balance)
  }
  return 0
}

function matchesSource(row: G11TbRowLike, src: G11BalanceAccountDef): boolean {
  const code = rowCode(row)
  const name = rowName(row)
  const codeHit = src.codes.some((c) => code === c || code.startsWith(c))
  if (!codeHit) return false
  // 多源共用同一编码时（如 1503）必须命中名称关键词
  if (src.nameHints.length > 0) {
    const nameHit = src.nameHints.some((h) => name.includes(h))
    // 名称空时：仅当该编码在本表唯一占用时放行
    if (!name) {
      const ambiguous = G11_RETURN_RATE_BALANCE_SOURCES.filter((s) =>
        s.codes.some((c) => src.codes.includes(c)),
      )
      return ambiguous.length <= 1
    }
    return nameHit
  }
  return true
}

/** 按映射聚合 TB 期初/期末（含子科目） */
export function aggregateTbOpenClose(
  rows: G11TbRowLike[],
  src: G11BalanceAccountDef,
): G11TbOpenClose | null {
  if (!Array.isArray(rows) || !rows.length) return null
  let opening = 0
  let closing = 0
  const matchedCodes: string[] = []
  let matched = false
  for (const r of rows) {
    if (!matchesSource(r, src)) continue
    matched = true
    opening += pickTbOpening(r)
    closing += pickTbClosing(r)
    const c = rowCode(r)
    if (c && !matchedCodes.includes(c)) matchedCodes.push(c)
  }
  if (!matched) return null
  return {
    opening: Math.round(opening * 100) / 100,
    closing: Math.round(closing * 100) / 100,
    matchedCodes,
  }
}

export function findBalanceSourceForRowKey(rowKey: string): G11BalanceAccountDef | undefined {
  return G11_RETURN_RATE_BALANCE_SOURCES.find((s) => s.rowKeys.includes(rowKey))
}

/** 由 rowKey → 余额补丁（纯函数，便于单测） */
export function buildBalancePatchFromTb(
  rowKey: string,
  currentYearRows: G11TbRowLike[],
  priorYearRows: G11TbRowLike[] | null,
): {
  currentOpening: number
  currentClosing: number
  priorOpening: number
  priorClosing: number
  sourceLabel: string
  usedPriorContinuity: boolean
} | null {
  const src = findBalanceSourceForRowKey(rowKey)
  if (!src) return null
  const cur = aggregateTbOpenClose(currentYearRows, src)
  if (!cur) return null

  let priorOpening = 0
  let priorClosing = 0
  let usedPriorContinuity = false
  const prior = priorYearRows ? aggregateTbOpenClose(priorYearRows, src) : null
  if (prior) {
    priorOpening = prior.opening
    priorClosing = prior.closing
  } else {
    // 无上期 TB：上期期末 ≈ 本期期初（连续性假设），上期期初留 0
    priorClosing = cur.opening
    usedPriorContinuity = true
  }

  return {
    currentOpening: cur.opening,
    currentClosing: cur.closing,
    priorOpening,
    priorClosing,
    sourceLabel: src.label,
    usedPriorContinuity,
  }
}
