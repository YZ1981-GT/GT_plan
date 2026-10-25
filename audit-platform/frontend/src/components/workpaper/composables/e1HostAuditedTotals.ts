/**
 * 宿主（GtE1MonetaryFund）在审定表未挂载时派生三科目审定合计 —— 与审定表 composable 同式（纯函数）。
 *
 * spec: chain-closure-phase2-formula-push-engine · design §四 前端配套 · 需求 4.5
 *
 * 口径逐式对齐 `useE1Adjudication.aggregateAuditedByCode`（后端 `e1_calc.adjudicated_total` 复刻同一式）：
 *   1001 = 现金未审 + 调整；1002 = 银行存款本金未审 + 调整；1012 = (其他货币资金未审 + 调整) + (数字货币未审 + 调整)
 *   调整 = `e1AdjustmentFor`（E1-5 本地 + 大厅已确认，后者只进期末三行）
 *
 * 🔴 改造前宿主内联一份：用 `parseFloat`（`"1e3"` / `"0x10"` 与 `Number` 不同）、漏大厅已确认调整、
 *    1012 把数字货币调整并进其他货币资金括号 —— 三处与 composable 不同，两个写入方来回覆盖。
 */
import { e1AdjustmentFor, type E1AdjustmentGetter } from './e1AdjustmentFor'
import { parseNum } from './useE1FormulaEngine'

export type E1Period = 'opening' | 'ending'

const UNAUDITED_KEYS: Record<string, Record<E1Period, string>> = {
  cash: { opening: 'E1-cash-detail-opening-unaudited', ending: 'E1-cash-detail-total-unaudited' },
  bank_principal: {
    opening: 'E1-bank-detail-principal-opening-unaudited',
    ending: 'E1-bank-detail-principal-total-unaudited',
  },
  other_mf: {
    opening: 'E1-bank-detail-other-opening-unaudited',
    ending: 'E1-bank-detail-other-total-unaudited',
  },
  digital: { opening: 'E1-digital-opening-unaudited', ending: 'E1-digital-total-unaudited' },
}

function audited(get: E1AdjustmentGetter, itemKey: string, period: E1Period): number {
  return parseNum(get(UNAUDITED_KEYS[itemKey][period])) + e1AdjustmentFor(get, itemKey, period)
}

/** 三科目审定合计 `{1001, 1002, 1012}`。 */
export function e1HostAuditedTotals(get: E1AdjustmentGetter, period: E1Period): Record<string, number> {
  return {
    '1001': audited(get, 'cash', period),
    '1002': audited(get, 'bank_principal', period),
    '1012': audited(get, 'other_mf', period) + audited(get, 'digital', period),
  }
}

/** 审定合计键名（期末 `E1-adj-total-{code}`，期初加 `-opening`）。 */
export function e1AdjTotalKey(code: string, period: E1Period): string {
  return period === 'opening' ? `E1-adj-total-${code}-opening` : `E1-adj-total-${code}`
}

/**
 * 宿主审定合计种子：**总是派生**（不再「键已存在就跳过」）。
 * 返回要写入内存的 `[键, 值字符串]`；值为 0 且该键原本不存在时不写（保持空白，与 buildCrossSheetSeeds 同策略）。
 */
export function e1HostAdjTotalSeeds(
  get: E1AdjustmentGetter,
  has: (key: string) => boolean,
): Array<[string, string]> {
  const out: Array<[string, string]> = []
  for (const period of ['ending', 'opening'] as const) {
    for (const [code, value] of Object.entries(e1HostAuditedTotals(get, period))) {
      const key = e1AdjTotalKey(code, period)
      if (Math.abs(value) < 0.005 && !has(key)) continue
      out.push([key, String(value)])
    }
  }
  return out
}
