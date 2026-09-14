/**
 * 截止测试跨期判定纯函数
 * ~60行，无 Vue 依赖
 */

export type CutoffDirection = 'post_cutoff' | 'pre_cutoff' | 'window'
export type CutoffStatus = '可能跨期' | '待检查' | '正常'

/**
 * 解析日期字符串为 Date，避免时区偏移
 */
function parseDate(dateStr: string): Date | null {
  const d = new Date(dateStr + 'T00:00:00')
  return isNaN(d.getTime()) ? null : d
}

/**
 * 格式化 Date 为 YYYY-MM-DD
 */
function formatDate(d: Date): string {
  const y = d.getFullYear()
  const m = String(d.getMonth() + 1).padStart(2, '0')
  const day = String(d.getDate()).padStart(2, '0')
  return `${y}-${m}-${day}`
}

/**
 * 计算日期窗口范围
 */
export function computeDateRange(
  cutoffDate: string,
  daysBefore: number,
  daysAfter: number,
): { start: string; end: string } {
  const base = parseDate(cutoffDate)
  if (!base) return { start: cutoffDate, end: cutoffDate }

  const start = new Date(base)
  start.setDate(start.getDate() - daysBefore)

  const end = new Date(base)
  end.setDate(end.getDate() + daysAfter)

  return { start: formatDate(start), end: formatDate(end) }
}

/**
 * 截止测试跨期判定纯函数
 *
 * @param voucherDate - 凭证日期 (YYYY-MM-DD)
 * @param cutoffDate - 截止基准日 (YYYY-MM-DD)
 * @param direction - 判定模式
 * @param amount - 金额（借方为正、贷方为负）
 * @param daysBefore - 前窗口天数 (default 5)
 * @param daysAfter - 后窗口天数 (default 10)
 */
export function determineCutoffStatus(
  voucherDate: string,
  cutoffDate: string,
  direction: CutoffDirection,
  amount: number,
  daysBefore: number = 5,
  daysAfter: number = 10,
): CutoffStatus {
  const vd = parseDate(voucherDate)
  const cd = parseDate(cutoffDate)
  if (!vd || !cd) return '正常'

  const vTime = vd.getTime()
  const cTime = cd.getTime()

  if (direction === 'post_cutoff') {
    return vTime > cTime && amount > 0 ? '可能跨期' : '正常'
  }

  if (direction === 'pre_cutoff') {
    return vTime < cTime && amount < 0 ? '可能跨期' : '正常'
  }

  // direction === 'window'
  const { start, end } = computeDateRange(cutoffDate, daysBefore, daysAfter)
  const startTime = parseDate(start)!.getTime()
  const endTime = parseDate(end)!.getTime()

  return vTime >= startTime && vTime <= endTime ? '待检查' : '正常'
}
