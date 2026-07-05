/**
 * H10 资产处置损益 — 处置计算引擎（纯函数）
 * Spec: .kiro/specs/h10-asset-disposal-income/
 */
import { parseNum } from './useH10FormulaEngine'

/** 处置净损益 = 处置收入 − 净值 − 处置费用 − 税费 */
export function calcDisposalGainLoss(
  income: number,
  netValue: number,
  expenses: number,
  tax: number,
): number {
  return parseNum(income) - parseNum(netValue) - parseNum(expenses) - parseNum(tax)
}

/** 净账面值 = 原值 − 累计折旧 */
export function calcNetBookValue(cost: number, accDep: number): number {
  return parseNum(cost) - parseNum(accDep)
}

/** 处置损益率 = 损益 / 原值 × 100；原值为 0 或非有限数时 null */
export function calcGainLossRate(gainLoss: number, cost: number): number | null {
  const gl = parseNum(gainLoss)
  const c = parseNum(cost)
  if (c === 0 || !Number.isFinite(gl) || !Number.isFinite(c)) return null
  return (gl / c) * 100
}
