/** H0-5 替代程序公式引擎（纯函数，可 PBT） */

export function parseNum(v: unknown): number {
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

export function calcBlockTotal(amounts: number[]): number {
  if (!amounts.length) return 0
  return amounts.reduce((sum, v) => sum + parseNum(v), 0)
}

export function calcCheckRatio(checked: number, balance: number): number {
  const b = parseNum(balance)
  if (b <= 0) return 0
  return parseNum(checked) / b
}

export function calcRowVariance(book: number, evidence: number): number {
  return parseNum(book) - parseNum(evidence)
}

export function isAbnormal(variance: number): boolean {
  return Math.abs(parseNum(variance)) > 0
}
