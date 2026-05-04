/**
 * 全局格式化工具函数
 *
 * 统一金额、日期、百分比等格式化逻辑，替代 35+ 处重复的 toLocaleString 调用。
 * 所有审计平台页面统一使用这些函数，修改格式只需改一处。
 */

// ── 金额格式化 ──────────────────────────────────────────

/**
 * 格式化金额（千分位 + 2位小数）
 * - null/undefined → '-'
 * - 0 → '-'（审计惯例：零值显示横杠）
 * - NaN → '-'
 *
 * @param v 任意值（number/string/null）
 * @param decimals 小数位数，默认 2
 * @param showZero 是否显示零值，默认 false（显示 '-'）
 */
export function fmtAmount(v: any, decimals = 2, showZero = false): string {
  if (v == null) return '-'
  const n = typeof v === 'number' ? v : Number(v)
  if (isNaN(n)) return '-'
  if (n === 0 && !showZero) return '-'
  return n.toLocaleString('zh-CN', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
  })
}

/**
 * 格式化金额（允许零值显示）
 * 用于需要明确显示 0.00 的场景（如差异对比）
 */
export function fmtAmountWithZero(v: any, decimals = 2): string {
  return fmtAmount(v, decimals, true)
}

// ── 百分比格式化 ─────────────────────────────────────────

/**
 * 格式化百分比
 * - null/undefined/0 → '--'
 * - 51.5 → '51.50%'
 */
export function fmtPercent(v: any, decimals = 2): string {
  if (v == null) return '--'
  const n = Number(v)
  if (isNaN(n) || n === 0) return '--'
  return `${n.toFixed(decimals)}%`
}

// ── 日期格式化 ───────────────────────────────────────────

/**
 * 格式化日期（仅日期：2025-01-15）
 */
export function fmtDate(d: string | Date | null | undefined): string {
  if (!d) return '-'
  const date = typeof d === 'string' ? new Date(d) : d
  if (isNaN(date.getTime())) return '-'
  return date.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit',
  })
}

/**
 * 格式化日期时间（2025-01-15 14:30:00）
 */
export function fmtDateTime(d: string | Date | null | undefined): string {
  if (!d) return '-'
  const date = typeof d === 'string' ? new Date(d) : d
  if (isNaN(date.getTime())) return '-'
  return date.toLocaleString('zh-CN')
}

// ── 数值辅助 ─────────────────────────────────────────────

/**
 * 安全转数值（用于计算，非显示）
 * - null/undefined/NaN → 0
 */
export function toNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return isNaN(n) ? 0 : n
}

// ── 金额单位换算 ─────────────────────────────────────────

/** 金额单位类型 */
export type AmountUnit = 'yuan' | 'wan' | 'qian'

/** 单位配置 */
export const AMOUNT_UNITS: Record<AmountUnit, { label: string; suffix: string; divisor: number }> = {
  yuan: { label: '元', suffix: '元', divisor: 1 },
  wan:  { label: '万元', suffix: '万元', divisor: 10000 },
  qian: { label: '千元', suffix: '千元', divisor: 1000 },
}

/**
 * 按单位格式化金额
 * - unit='yuan': 原值显示（默认）
 * - unit='wan':  除以 10000 后显示
 * - unit='qian': 除以 1000 后显示
 *
 * @param v 原始金额（以"元"为单位存储）
 * @param unit 显示单位
 * @param decimals 小数位数（万元默认2位，元默认2位）
 * @param showZero 是否显示零值
 */
export function fmtAmountUnit(
  v: any,
  unit: AmountUnit = 'yuan',
  decimals?: number,
  showZero = false,
): string {
  if (v == null) return '-'
  const n = typeof v === 'number' ? v : Number(v)
  if (isNaN(n)) return '-'
  if (n === 0 && !showZero) return '-'

  const cfg = AMOUNT_UNITS[unit]
  const converted = n / cfg.divisor
  const dec = decimals ?? (unit === 'yuan' ? 2 : 2)

  return converted.toLocaleString('zh-CN', {
    minimumFractionDigits: dec,
    maximumFractionDigits: dec,
  })
}

/**
 * 获取单位标签文本（用于表头显示"单位：万元"）
 */
export function unitLabel(unit: AmountUnit): string {
  return AMOUNT_UNITS[unit]?.suffix || '元'
}

// ── 字体字号预设 ─────────────────────────────────────────

/** 表格字号预设 */
export type FontSize = 'xs' | 'sm' | 'md' | 'lg'

export const FONT_SIZES: Record<FontSize, { label: string; tableFont: string; headerFont: string }> = {
  xs: { label: '紧凑', tableFont: '11px', headerFont: '11px' },
  sm: { label: '标准', tableFont: '12px', headerFont: '12px' },
  md: { label: '舒适', tableFont: '13px', headerFont: '13px' },
  lg: { label: '大字', tableFont: '14px', headerFont: '14px' },
}
