/**
 * 统一千分位格式化函数
 * 用于所有金额列的数值显示，确保一致的格式化行为
 */
export function formatAmount(value: number | string | null | undefined): string {
  if (value == null || value === '') return ''
  const num = typeof value === 'string' ? parseFloat(value) : value
  if (isNaN(num)) return String(value)
  return num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}
