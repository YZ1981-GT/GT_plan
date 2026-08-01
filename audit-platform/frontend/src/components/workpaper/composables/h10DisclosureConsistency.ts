/**
 * H10 资产处置损益披露内部勾稽校验（纯函数）
 *
 * 源模板逐行公式（`useH10Disclosure.H10DisclosureRow`）：本期变动金额 = 本期发生额
 * − 上期发生额；变动率 = 变动金额 ÷ |上期发生额| × 100%（上期为 0 时不判定）。
 * 试运行明细表（`H10TrialDetailRow`）净额 = 收入 − 成本，两期独立。
 *
 * spec: .kiro/specs/h-cycle-legacy-cleanup-and-platform-hygiene/ R5
 */
import { eqCheck, type WpCheckResult } from './shared/disclosureConsistency'
import type { H10DisclosureRow, H10TrialDetailRow } from './useH10Disclosure'

export function buildH10RowChecks(rows: readonly H10DisclosureRow[]): WpCheckResult[] {
  const checks: WpCheckResult[] = []
  for (const row of rows) {
    if (row.rowKey.startsWith('__')) continue
    const derived = Math.round((row.currentAmount - row.priorAmount) * 100) / 100
    checks.push(
      eqCheck(
        `「${row.label}」本期变动金额`,
        '本期变动金额 = 本期发生额 − 上期发生额（源模板逐行公式列）',
        row.changeAmount,
        derived,
        [],
      ),
    )
  }
  return checks
}

/**
 * 试运行销售损益明细表的净额合计（收入合计 − 成本合计），供与主表「营业外收入/成本」
 * 分项比对（比对留给调用方，此处只做可判定的合计推导，不猜跨表勾稽关系）。
 */
export function trialDetailNetTotal(rows: readonly H10TrialDetailRow[]): number {
  const income = rows.reduce((s, r) => s + (Number(r.currentIncome) || 0), 0)
  const cost = rows.reduce((s, r) => s + (Number(r.currentCost) || 0), 0)
  return Math.round((income - cost) * 100) / 100
}
