/**
 * 逐 kind 显示规则的唯一实现（design §17 G4）。
 *
 * | kind | 除数 | 小数位 | 千分位 | 零值 | 负数红 | 高亮 |
 * |---|---|---|---|---|---|---|
 * | amount | effective 金额单位 | 账号 decimals | 是 | 生效 | 生效 | 生效 |
 * | ratio | 1；fraction 先 ×100 | 固定 2 位 + `%` | 是 | 生效 | 生效 | 否 |
 * | count | 1 | 0 位；原值带小数时按 quantity 规则并记一次开发告警 | 是 | 生效 | 生效 | 否 |
 * | quantity / exchange_rate / unit_price | 1 | 原值有效小数位，最多 6 位 | 是 | 生效 | 生效 | 否 |
 * | text | — | 原样输出 | — | — | — | — |
 * | 未登记（null / unknown） | 1 | 账号 decimals | 是 | 生效 | 生效 | 否 |
 *
 * 只有 `amount` 消费金额单位除数；其余 kind 的 divisor 恒为 1。
 */
import Decimal from 'decimal.js'
import { toDecimal } from '@/utils/decimal'
import { AMOUNT_UNITS, type AmountUnit } from '@/utils/formatters'
import { normalizeDecimals } from '@/utils/displayPreferencesNormalizer'
import type { DisplayMeasureKind, RatioScale } from '@/types/displayMeasure'

/** 非金额 kind 的小数位上限（design §17 G4）。 */
export const MAX_SIGNIFICANT_DECIMALS = 6

/** 比例固定 2 位（与 formatters.fmtPercent 默认值一致）。 */
export const RATIO_DECIMALS = 2

export interface MeasureDisplayOptions {
  /** effective 金额单位，只对 amount 生效 */
  amountUnit: AmountUnit
  /** 账号小数位，对 amount 与未登记分支生效 */
  decimals: number
  /** 零值是否显示 0（false 时显示 '-'） */
  showZero: boolean
  /** 列语义；null / undefined 走未登记分支 */
  kind?: DisplayMeasureKind | null
  /** kind=ratio 时必填 */
  ratioScale?: RatioScale | null
}

/** 空值占位，与 GtAmountCell 既有口径一致。 */
const BLANK = '-'

function groupFixed(value: string): string {
  const negative = value.startsWith('-')
  const unsigned = negative ? value.slice(1) : value
  const [integer, fraction] = unsigned.split('.')
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}${fraction === undefined ? '' : `.${fraction}`}`
}

function safeDecimal(value: unknown): Decimal | null {
  if (value === null || value === undefined) return null
  if (typeof value === 'string' && value.trim() === '') return null
  if (typeof value === 'boolean') return null
  try {
    return toDecimal(value as string | number, false, '数值')
  } catch {
    return null
  }
}

/**
 * 原值的有效小数位：以原值字符串构造 Decimal、去掉尾零后的小数位数，最多 6 位。
 * 超过 6 位的按 ROUND_HALF_UP 保留 6 位（由调用方量化）。
 */
export function significantDecimals(d: Decimal): number {
  const fixed = d.toFixed()
  const dot = fixed.indexOf('.')
  if (dot < 0) return 0
  const fraction = fixed.slice(dot + 1).replace(/0+$/, '')
  return Math.min(fraction.length, MAX_SIGNIFICANT_DECIMALS)
}

let countWithDecimalsWarned = false

/** 仅测试用：重置「count 带小数」的一次性开发告警。 */
export function __resetMeasureWarnings(): void {
  countWithDecimalsWarned = false
}

/**
 * 按 kind 格式化展示值。原值永不被改写；text 原样输出。
 */
export function formatMeasure(value: unknown, options: MeasureDisplayOptions): string {
  const kind = options.kind ?? null

  if (kind === 'text') {
    if (value === null || value === undefined) return ''
    return String(value)
  }

  const d = safeDecimal(value)
  if (d === null) return BLANK
  if (d.isZero() && !options.showZero) return BLANK

  if (kind === 'amount') {
    const divisor = AMOUNT_UNITS[options.amountUnit]?.divisor ?? 1
    const decimals = normalizeDecimals(options.decimals)
    return groupFixed(d.dividedBy(divisor).toDecimalPlaces(decimals, Decimal.ROUND_HALF_UP).toFixed(decimals))
  }

  if (kind === 'ratio') {
    // fraction 原值 0.2 与 percent_points 原值 20 都显示 20.00%
    const scaled = options.ratioScale === 'fraction' ? d.times(100) : d
    const rounded = scaled.toDecimalPlaces(RATIO_DECIMALS, Decimal.ROUND_HALF_UP)
    return `${groupFixed(rounded.toFixed(RATIO_DECIMALS))}%`
  }

  if (kind === 'count') {
    const sig = significantDecimals(d)
    if (sig > 0) {
      // 笔数带小数是上游数据问题，不静默取整（否则 1.5 笔显示成 2 笔）
      if (!countWithDecimalsWarned && import.meta.env?.DEV) {
        countWithDecimalsWarned = true
        // eslint-disable-next-line no-console
        console.warn('[displayMeasure] kind=count 的原值带小数，已按 quantity 规则显示', d.toFixed())
      }
      return groupFixed(d.toDecimalPlaces(sig, Decimal.ROUND_HALF_UP).toFixed(sig))
    }
    return groupFixed(d.toDecimalPlaces(0, Decimal.ROUND_HALF_UP).toFixed(0))
  }

  if (kind === 'quantity' || kind === 'exchange_rate' || kind === 'unit_price') {
    const sig = significantDecimals(d)
    return groupFixed(d.toDecimalPlaces(sig, Decimal.ROUND_HALF_UP).toFixed(sig))
  }

  // 未登记（kind 为 null / 未知）：divisor 恒为 1、不加 %、不高亮，小数位用账号设置
  const decimals = normalizeDecimals(options.decimals)
  return groupFixed(d.toDecimalPlaces(decimals, Decimal.ROUND_HALF_UP).toFixed(decimals))
}

/** 只有 amount 参与变动高亮（design §17 G4）。 */
export function measureSupportsHighlight(kind: DisplayMeasureKind | null | undefined): boolean {
  return kind === 'amount'
}

/** 原始值（不随显示单位换算），供复制 / 求和读取。 */
export function measureRawValue(value: unknown): string {
  const d = safeDecimal(value)
  return d === null ? '' : d.toString()
}
