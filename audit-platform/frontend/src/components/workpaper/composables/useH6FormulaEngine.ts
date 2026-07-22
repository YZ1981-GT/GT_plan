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

/**
 * P5: 净账面价值 = 原值 - 累计折旧 - 减值准备
 * impairment 默认 0，兼容历史两参数调用；与 H1-8 转出净值口径一致。
 */
export function calcNetBookValue(cost: number, accDep: number, impairment = 0): number {
  return cost - accDep - impairment
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

/**
 * 对齐 Excel H6-1 变动率：
 * I=IF(AND(D=0,H=0),0,IF(AND(D=0,H>0),1,H/D))，输出为百分比。
 * 期初审定=0 且变动<0 时返回 -100（Excel 原式仅处理 H>0→100%，数字化补对称）。
 */
export function calcH6ChangeRate(change: number, beginAudited: number): number | null {
  if (beginAudited === 0 && change === 0) return 0
  if (beginAudited === 0) return change > 0 ? 100 : change < 0 ? -100 : 0
  return (change / Math.abs(beginAudited)) * 100
}

/** H6-2 未审期末 = 期初 + 本期增加 − 本期减少（对齐 Excel E=B+C−D） */
export function calcH62EndUnadjusted(begin: number, increase: number, decrease: number): number {
  return begin + increase - decrease
}

/** H6-2 审定期初 = 期初未审 + 期初调整（对齐 Excel I=B+F） */
export function calcH62BeginAudited(beginUnadj: number, beginAdj: number): number {
  return beginUnadj + beginAdj
}

/** H6-2 期末账项调整 = 期初调整 + 账项增加 − 账项减少（对齐 H6-1!F ← F+G−H） */
export function calcH62EndAdjustment(beginAdj: number, ajeInc: number, ajeDec: number): number {
  return beginAdj + ajeInc - ajeDec
}

/** H6-2 审定期末 = 审定期初 + 审定增加 − 审定减少（对齐 Excel L=I+J−K） */
export function calcH62EndAudited(
  beginAudited: number,
  increaseAudited: number,
  decreaseAudited: number,
): number {
  return beginAudited + increaseAudited - decreaseAudited
}

/** 默认报表截止日：指定年（或当年）12-31 */
export function defaultH6PeriodEnd(year?: number): string {
  const y = year ?? new Date().getFullYear()
  return `${y}-12-31`
}

/**
 * 转入清理起始时间是否已超过 1 年（对齐致同 H6-2「超1年进展」关注点）
 * @param startDate 转入清理日期 YYYY-MM-DD
 * @param asOfDate  报表截止日，缺省用今天
 */
export function isClearingOverOneYear(startDate: string, asOfDate?: string): boolean {
  const s = startDate?.trim()
  if (!s) return false
  const start = new Date(s)
  if (Number.isNaN(start.getTime())) return false
  const asOf = asOfDate?.trim() ? new Date(asOfDate) : new Date()
  if (Number.isNaN(asOf.getTime())) return false
  const threshold = new Date(start)
  threshold.setFullYear(threshold.getFullYear() + 1)
  return asOf >= threshold
}
