import type { AmountUnit } from '@/utils/formatters'
import { AMOUNT_UNITS } from '@/utils/formatters'
import { toDecimal } from '@/utils/decimal'
import { normalizeDecimals } from '@/utils/displayPreferencesNormalizer'

export interface DisplayAmountOptions {
  amountUnit: AmountUnit
  decimals: number
  showZero: boolean
  rawUnit?: boolean
}

function groupFixedDecimal(value: string): string {
  const negative = value.startsWith('-')
  const unsigned = negative ? value.slice(1) : value
  const [integer, fraction] = unsigned.split('.')
  const grouped = integer.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${negative ? '-' : ''}${grouped}${fraction === undefined ? '' : `.${fraction}`}`
}

/**
 * 显示层金额唯一 formatter。
 * 以 decimal.js 处理除数和舍入，防止 Number 精度尾差；原始数值不被改写。
 */
export function formatDisplayAmount(value: unknown, options: DisplayAmountOptions): string {
  if (value === null || value === undefined) return '—'

  let decimal
  try {
    decimal = toDecimal(value as string | number, false, '金额')
  } catch {
    return '—'
  }
  if (!decimal) return '—'
  if (decimal.isZero() && !options.showZero) return '-'

  const decimals = normalizeDecimals(options.decimals)
  const divisor = options.rawUnit ? 1 : AMOUNT_UNITS[options.amountUnit].divisor
  return groupFixedDecimal(decimal.div(divisor).toFixed(decimals))
}

export function isFiniteDisplayAmount(value: unknown): boolean {
  try {
    return !!toDecimal(value as string | number, false, '金额')
  } catch {
    return false
  }
}
