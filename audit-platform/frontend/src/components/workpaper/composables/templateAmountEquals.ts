/**
 * 模板「核对」列的金额相等判断（spec oo-writeback-template-parity-closure R2）。
 *
 * 模板核对列是 `=J11=D11` 这类精确比较。金额录入都是两位小数，两侧都是加减出来的数，
 * 差别只会是浮点尾差（0.1 + 0.2 ≠ 0.3），所以按「四舍五入到分后相等」判，与模板同结论。
 *
 * 原先 G13 / G14 用 `|a − b| ≤ 0.01`：差一分时浮点结果落在 0.00999… 就判成「核对一致」，
 * 模板（与 OnlyOffice）判不一致，两侧显示相反。
 */

/** 四舍五入到分，远离 0（与模板 ROUND 同向）；先按 15 位有效数字消掉二进制误差 */
export function roundToCents(x: number): number {
  if (!Number.isFinite(x)) return 0
  const scaled = Number((Math.abs(x) * 100).toPrecision(15))
  return (Math.sign(x) * Math.round(scaled)) / 100
}

/** 两个金额四舍五入到分后是否相等 */
export function amountsEqualToCent(a: number, b: number): boolean {
  return roundToCents(a) === roundToCents(b)
}
