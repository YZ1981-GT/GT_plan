/**
 * H6 固定资产清理 — 公式引擎（纯函数，无副作用）
 * 科目：1606固定资产清理（借方/资产类，过渡科目）
 * 特殊：过渡科目期末余额应为0（清理完毕结转H10）
 * Spec: .kiro/specs/h6-asset-disposal-clearing/
 */

/** P1: 审定数 = 未审数 + AJE调整 + RJE重分类 */
export function calcAuditedAmount(unadj: number, aje: number, rje: number): number {
  return unadj + aje + rje
}

/** P2: 资产类期末余额（借方科目1606）：期末 = 期初 + 借方发生 - 贷方发生 */
export function calcAssetEndBalance(begin: number, debit: number, credit: number): number {
  return begin + debit - credit
}

/** P5: 净账面价值 = 原值 - 累计折旧 */
export function calcNetBookValue(cost: number, accDep: number): number {
  return cost - accDep
}

/** P3: 清理净损益 = 处置收入 - 净值 - 清理费用 - 税费 */
export function calcDisposalGainLoss(income: number, netValue: number, expenses: number, tax: number): number {
  return income - netValue - expenses - tax
}

/** 合计 = SUM(数组)；空数组返回0 */
export function calcSubtotal(arr: number[]): number {
  return arr.reduce((a, b) => a + b, 0)
}

/** P4: 过渡科目零余额判定：期末余额为0→true（清理完毕）；非0→false（存在未结转） */
export function isTransitBalanceZero(endBalance: number): boolean {
  return endBalance === 0
}
