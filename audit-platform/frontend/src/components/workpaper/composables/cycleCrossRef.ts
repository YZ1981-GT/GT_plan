export type CycleCode = 'S34' | 'S35'

/** 归一化 chip 传入的底稿编码，兼容 wp:D4-24 形式。 */
export function normalizeCycleRef(value: string): string {
  return value.trim().replace(/^wp:/i, '')
}

/** 判断引用是否指向当前 S 循环 bundle 内部 Tab/子表。 */
export function isCycleInternalRef(value: string, cycleCode: CycleCode): boolean {
  const ref = normalizeCycleRef(value)
  return new RegExp(`^${cycleCode}-\\d+(?:-\\d+)?$`).test(ref)
}

/** 外部引用才显示循环审定额 hover；空值和内部 Tab 不显示。 */
export function isCycleExternalRef(value: string, cycleCode?: CycleCode): boolean {
  if (!cycleCode) return false
  const ref = normalizeCycleRef(value)
  return Boolean(ref) && !isCycleInternalRef(ref, cycleCode)
}
