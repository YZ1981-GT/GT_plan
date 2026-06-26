/**
 * 统一千分位格式化函数（向后兼容导出）
 *
 * @deprecated 请改用 `useDisplayPrefsStore().fmt(v)` 或 `useDisplayPrefsStore().fmtAmount(v)`
 * 本函数不消费用户显示偏好（单位/小数位），仅裸格式化。
 * 保留导出名以免批量改动导致编译错误，存量逐步迁移后将移除。
 */
import { fmtAmount } from '@/utils/formatters'

export function formatAmount(value: number | string | null | undefined): string {
  if (value == null || value === '') return ''
  return fmtAmount(value, 2, true) || ''
}
