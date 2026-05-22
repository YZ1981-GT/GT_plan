/**
 * 生成 el-table sort-method 函数，基于原始数值比较。
 * null/undefined/NaN 统一排到末尾。
 */
export function numericSortMethod(prop: string) {
  return (a: Record<string, any>, b: Record<string, any>): number => {
    const va = toSortableNumber(a[prop])
    const vb = toSortableNumber(b[prop])
    if (va === null && vb === null) return 0
    if (va === null) return 1
    if (vb === null) return -1
    return va - vb
  }
}

function toSortableNumber(v: any): number | null {
  if (v == null) return null
  const n = typeof v === 'number' ? v : Number(v)
  return isNaN(n) ? null : n
}
