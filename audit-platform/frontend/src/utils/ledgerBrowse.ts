/** 序时账 / 辅助明细账默认展示全部凭证（科目通配 *），科目、日期、关键字都是可选筛选。 */
export const ALL_ACCOUNTS = '*'

/** 浏览模式（未限定科目 / 辅助类型）没有会计意义的期初和月累计余额，只保留凭证行。 */
export const onlyBusinessRows = (rows: any[], scoped: boolean) =>
  scoped ? rows : rows.filter((r: any) => r._type === 'normal' || !r._type)
