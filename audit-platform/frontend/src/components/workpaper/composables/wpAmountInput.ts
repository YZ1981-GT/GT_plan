/**
 * wpAmountInput.ts — 底稿金额输入框统一格式化（千分符 + 两位小数）
 *
 * 用于 el-input-number 的 :formatter / :parser，让可编辑金额单元格与只读
 * displayPrefs.fmtAmount() 展示口径一致（千分符 + 固定两位小数）。
 *
 * 用法：
 *   <el-input-number :precision="2" :formatter="amountFormatter" :parser="amountParser" ... />
 *
 * 注意：仅用于「金额」字段。利率 / 汇率 / 比例 / 数量等非金额字段应保留各自
 * precision（如 :precision="4|6"），不要套用本 formatter。
 */

/** el-input-number formatter：数字 → 千分符 + 两位小数字符串 */
export function amountFormatter(value: number | string): string {
  if (value === '' || value === null || value === undefined) return ''
  const num = Number(value)
  if (Number.isNaN(num)) return String(value)
  return num.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** el-input-number parser：去掉千分符逗号还原为可解析数字字符串 */
export function amountParser(value: string): string {
  return (value ?? '').replace(/,/g, '')
}

/**
 * 判断通用列渲染器里的某数值列是否为「金额」列（应套千分符+两位小数）。
 * 用于 COLUMN_CONFIG 驱动的动态表格（如 E1-23/E1-26~32）：金额列格式化，
 * 月份/年度/笔数/数量/率/比例/天数等非金额数值列不格式化。
 */
export function isAmountColumn(col: { key?: string; label?: string }): boolean {
  const label = String(col?.label ?? '')
  const key = String(col?.key ?? '')
  if (/月份|月度|年度|年份|笔数|数量|次数|个数|天数|比例|率$|占比/.test(label)) return false
  if (/^(month|year|count|qty|quantity|days|rate|ratio|pct|percent|times)$/i.test(key)) return false
  return true
}
