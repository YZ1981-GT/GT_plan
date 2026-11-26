/**
 * 日历日计算：与时区、一天中的时刻无关。
 *
 * 🔴 为什么需要它（2026-11-26 CI 实测）：`new Date('2025-07-01')` 按 **UTC 零点**解析，而
 * `new Date()` 是本地当前时刻；两者直接相减再 `/ 86400000` 向下取整，北京时间 0~8 点（UTC 仍是前一天）
 * 会少算一天。F3-5 逾期天数在 CI（UTC）上得 106、本地（UTC+8）得 105，正确值是 106。
 * 同理 `new Date().toISOString().slice(0, 10)` 取到的是 **UTC 的今天**，北京时间早上 8 点前是昨天。
 */

const DAY_MS = 86_400_000
const ISO_DATE = /^(\d{4})-(\d{1,2})-(\d{1,2})(?=$|[T\s])/

/** 本地日历上的今天（或给定时刻所在的本地日期），`YYYY-MM-DD`。 */
export function localDateIso(at: Date = new Date()): string {
  const y = at.getFullYear()
  const m = String(at.getMonth() + 1).padStart(2, '0')
  const d = String(at.getDate()).padStart(2, '0')
  return `${y}-${m}-${d}`
}

/**
 * 把日期折算成「日历日序号」（自 1970-01-01 起的天数）；无效输入返回 null。
 *
 * - `YYYY-MM-DD…` 字符串：直接取年月日（不经 Date 解析，不受时区影响）；
 * - `Date`：恰好是 UTC 零点的（来自 `new Date('YYYY-MM-DD')`）取其 UTC 日期，其余（如 `new Date()`
 *   当前时刻）取本地日期 —— 两种来源在任何时区都落到用户看到的那一天；
 * - 其他字符串：交给 `Date` 解析后按上一条处理。
 */
export function calendarDayIndex(value: string | Date | null | undefined): number | null {
  if (value == null || value === '') return null
  let date: Date
  if (typeof value === 'string') {
    const m = ISO_DATE.exec(value.trim())
    if (m) return Date.UTC(Number(m[1]), Number(m[2]) - 1, Number(m[3])) / DAY_MS
    date = new Date(value)
  } else {
    date = value
  }
  const t = date.getTime()
  if (Number.isNaN(t)) return null
  if (t % DAY_MS === 0) return t / DAY_MS
  return Date.UTC(date.getFullYear(), date.getMonth(), date.getDate()) / DAY_MS
}

/** `to - from` 的日历日数；任一端无效返回 null。 */
export function calendarDaysBetween(
  from: string | Date | null | undefined,
  to: string | Date | null | undefined,
): number | null {
  const a = calendarDayIndex(from)
  const b = calendarDayIndex(to)
  return a === null || b === null ? null : b - a
}
