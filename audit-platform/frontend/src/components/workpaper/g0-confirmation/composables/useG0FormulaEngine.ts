/**
 * useG0FormulaEngine — G0 投资循环函证公式引擎（纯函数，可 PBT 验证）
 */

export function calcQuantityDiff(confirmed: number, booked: number): number {
  return confirmed - booked
}

export function calcFairValueDiff(confirmedFV: number, bookedFV: number): number {
  return confirmedFV - bookedFV
}

export function calcMarketValueDiff(confirmedMV: number, bookedMV: number): number {
  return confirmedMV - bookedMV
}

export function calcDisposalGain(proceeds: number, cost: number, fee: number): number {
  const safeFee = fee < 0 ? 0 : fee
  return Math.round((proceeds - cost - safeFee) * 100) / 100
}

export function calcDividendDiff(declared: number, received: number, tax: number): number {
  return Math.round((declared - received - tax) * 100) / 100
}

export function hasDifference(qtyDiff: number, fvDiff: number): boolean {
  return Math.abs(qtyDiff) > 0 || Math.abs(fvDiff) > 0.01
}
