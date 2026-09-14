/**
 * G11 附注披露 — 从 v2 store 生成结构化附注叙述文本（6111 投资收益）
 */
import { parseNum } from './useG11FormulaEngine'
import {
  G11_LISTED_TRADING_DISPOSE_ROWS,
  G11_SOE_REPATRIATION_PLACEHOLDER,
  G11_TRADING_DISPOSE_SUFFIXES,
  isG11DisclosureLeaf,
} from './g11SchemaRows'
import {
  sumG11DisclosureLeafCurrent,
  sumG11DisclosureLeafPrior,
  sumG11TradingDisposeCurrent,
  type G11DiscStoreV2,
} from './g11DisclosureFromAdj'

const AMOUNT_EPS = 0.005

export function formatG11NoteAmount(value: number): string {
  return value.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

function isNonZeroAmount(value: number): boolean {
  return Math.abs(value) >= AMOUNT_EPS
}

export interface BuildG11NoteTextOptions {
  /** 是否列出发生额均为零的分项（默认仅列非零） */
  includeZeroRows?: boolean
  /** G11-1 审定数，用于叙述勾稽 */
  adjudicatedAmount?: number | null
}

/**
 * 由附注披露 store 生成附注模块可用的叙述文本。
 * 上市含「处置交易性」子表；国企含汇回限制说明。
 */
export function buildG11NoteTextFromStore(
  store: G11DiscStoreV2,
  variant: 'listed' | 'soe',
  opts?: BuildG11NoteTextOptions,
): string {
  const lines: string[] = []
  const currentTotal = sumG11DisclosureLeafCurrent(store.rows)
  const priorTotal = sumG11DisclosureLeafPrior(store.rows)

  lines.push(
    `投资收益本期发生额合计 ${formatG11NoteAmount(currentTotal)} 元，`
    + `上期发生额合计 ${formatG11NoteAmount(priorTotal)} 元。`,
  )

  if (opts?.adjudicatedAmount != null && isNonZeroAmount(opts.adjudicatedAmount)) {
    const diff = currentTotal - opts.adjudicatedAmount
    if (Math.abs(diff) <= AMOUNT_EPS) {
      lines.push(`与 G11-1 审定数 ${formatG11NoteAmount(opts.adjudicatedAmount)} 元勾稽一致。`)
    } else {
      lines.push(
        `G11-1 审定数为 ${formatG11NoteAmount(opts.adjudicatedAmount)} 元，`
        + `与附注分项合计差异 ${formatG11NoteAmount(diff)} 元。`,
      )
    }
  }

  const detailLines: string[] = []
  for (const row of store.rows) {
    if (!isG11DisclosureLeaf(row.rowKey)) continue
    const current = parseNum(row.currentAmount)
    const prior = parseNum(row.priorAmount)
    if (!opts?.includeZeroRows && !isNonZeroAmount(current) && !isNonZeroAmount(prior)) continue
    detailLines.push(
      `${row.label}：本期 ${formatG11NoteAmount(current)} 元，上期 ${formatG11NoteAmount(prior)} 元。`,
    )
  }
  if (detailLines.length > 0) {
    lines.push('其中：')
    for (const line of detailLines) {
      lines.push(`  ${line}`)
    }
  }

  if (variant === 'listed' && store.tradingDispose) {
    const map = store.tradingDispose
    const hasTradingSub = G11_TRADING_DISPOSE_SUFFIXES.some((key) => {
      const pair = map[key]
      return pair && (isNonZeroAmount(parseNum(pair.currentAmount)) || isNonZeroAmount(parseNum(pair.priorAmount)))
    })
    const tdTotal = sumG11TradingDisposeCurrent(map)
    if (hasTradingSub || isNonZeroAmount(tdTotal)) {
      lines.push('')
      lines.push('处置交易性金融资产取得的投资收益明细如下：')
      for (const def of G11_LISTED_TRADING_DISPOSE_ROWS) {
        const pair = map[def.rowKey as keyof typeof map]
        const current = parseNum(pair?.currentAmount)
        const prior = parseNum(pair?.priorAmount)
        if (!opts?.includeZeroRows && !isNonZeroAmount(current) && !isNonZeroAmount(prior)) continue
        lines.push(
          `  ${def.label}：本期 ${formatG11NoteAmount(current)} 元，上期 ${formatG11NoteAmount(prior)} 元。`,
        )
      }
      if (isNonZeroAmount(tdTotal)) {
        lines.push(`  合计：本期 ${formatG11NoteAmount(tdTotal)} 元。`)
      }
    }
  }

  if (variant === 'soe') {
    const repatriation = (store.repatriationNote ?? '').trim()
    if (repatriation && repatriation !== G11_SOE_REPATRIATION_PLACEHOLDER) {
      lines.push('')
      lines.push(repatriation)
    }
  }

  for (const row of store.rows) {
    const remark = String(row.remark ?? '').trim()
    if (!remark) continue
    lines.push('')
    lines.push(`${row.label}说明：${remark}`)
  }

  return lines.join('\n').trim()
}
