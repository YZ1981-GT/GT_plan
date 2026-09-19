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
 * 判断通用列渲染器里的某数值列是否为「金额」列（金额列在运行时渲染 WpAmountInput，
 * 非金额数值列保留 el-input-number）。用于 COLUMN_CONFIG 驱动的动态表格
 * （E1-23/E1-26~32 等，label 是运行时值、静态探针判不了 → 运行时兜底）。
 *
 * 🔴 非金额黑名单**与迁移探针真源 `amountColumnSemantics.NON_AMOUNT_LABEL_PATTERNS`
 * 对齐**（利率/汇率/比例/年限/期限/月份/笔数/数量/股数/份数… 一致），两套判定由
 * `amountColumnRuntimeParity.spec.ts` 跨真源守卫锁住不漂移。此前 `率$` 锚定词尾漏掉
 * 「日利率(/360)」这类带后缀的利率列（被误当金额、precision=2 截断利率精度），已修。
 */
export function isAmountColumn(col: { key?: string; label?: string }): boolean {
  const label = String(col?.label ?? '')
  const key = String(col?.key ?? '')
  if (
    /月份|月度|年度|年份|笔数|数量|次数|个数|天数|比例|占比|利率|汇率|折现率|增长率|毛利率|税率|比率|率$|年限|期限|月数|股数|份数|张数|面值|面额/.test(
      label,
    )
  )
    return false
  if (/^(month|year|count|qty|quantity|days|rate|ratio|pct|percent|times)$/i.test(key)) return false
  return true
}
