/** G12-5 净头寸辅助计算 — 从头寸金额文本推导净敞口表述 */

import { G12_CURRENCY_UNIT_LABELS } from './g12Constants'

const AMOUNT_RE = /(-?\d[\d,]*(?:\.\d+)?)\s*(万)?\s*(美元|欧元|英镑|日元|人民币|港币|元|USD|EUR|GBP|JPY|HKD|CNY)?/i

const TEXT_TO_CURRENCY: Record<string, string> = {
  美元: 'USD', usd: 'USD',
  欧元: 'EUR', eur: 'EUR',
  英镑: 'GBP', gbp: 'GBP',
  日元: 'JPY', jpy: 'JPY',
  港币: 'HKD', hkd: 'HKD',
  人民币: 'CNY', 元: 'CNY', cny: 'CNY',
}

export interface ParsedPositionAmount {
  /** 数值（若含「万」则为「万」为单位，否则为原值） */
  value: number
  inWan: boolean
  unit: string
}

export function currencyUnitLabel(currency: string): string {
  return G12_CURRENCY_UNIT_LABELS[currency] ?? currency
}

export function inferCurrencyFromAmount(text: string | undefined | null): string {
  const trimmed = String(text ?? '').trim()
  if (!trimmed) return ''
  const m = trimmed.match(AMOUNT_RE)
  if (!m?.[3]) return ''
  const key = m[3].trim()
  return TEXT_TO_CURRENCY[key] ?? TEXT_TO_CURRENCY[key.toLowerCase()] ?? ''
}

export function parsePositionAmount(text: string | undefined | null): ParsedPositionAmount | null {
  const trimmed = String(text ?? '').trim()
  if (!trimmed) return null
  const m = trimmed.match(AMOUNT_RE)
  if (!m) return null
  const value = parseFloat(m[1].replace(/,/g, ''))
  if (Number.isNaN(value)) return null
  return { value, inWan: Boolean(m[2]), unit: (m[3] ?? '').trim() }
}

function resolveUnit(p1: ParsedPositionAmount, p2: ParsedPositionAmount, currency?: string): string {
  const fromText = p1.unit || p2.unit
  if (fromText) return fromText
  if (currency) return currencyUnitLabel(currency)
  return ''
}

/** 头寸1 − 头寸2；负值表示净支付 */
export function suggestNetPosition(
  position1Amount: string,
  position2Amount: string,
  currency?: string,
): string {
  const p1 = parsePositionAmount(position1Amount)
  const p2 = parsePositionAmount(position2Amount)
  if (!p1 || !p2) return ''
  if (p1.inWan !== p2.inWan) return ''

  const diff = p1.value - p2.value
  if (Math.abs(diff) < 1e-9) return '零净头寸'

  const unit = resolveUnit(p1, p2, currency)
  const abs = Math.abs(diff)
  const formatted = Number.isInteger(abs) ? abs.toLocaleString('zh-CN') : abs.toFixed(2)

  if (p1.inWan) {
    const suffix = unit ? unit : ''
    return diff > 0 ? `收${formatted}万${suffix}` : `支付${formatted}万${suffix}`
  }

  const suffix = unit ? unit : ''
  return diff > 0 ? `收${formatted}${suffix}` : `支付${formatted}${suffix}`
}

/** 从已有行推断币种，或返回默认 USD */
export function resolveRowCurrency(row: {
  currency?: string
  position1Amount?: string
  position2Amount?: string
  netPosition?: string
}): string {
  if (row.currency?.trim()) return row.currency.trim()
  return inferCurrencyFromAmount(row.position1Amount ?? '')
    || inferCurrencyFromAmount(row.position2Amount ?? '')
    || inferCurrencyFromAmount(row.netPosition ?? '')
    || 'USD'
}

/** 金额占位：按币种显示「万」单位 */
export function amountPlaceholder(currency: string, example = '1,000'): string {
  const unit = currencyUnitLabel(currency)
  return unit ? `${example}万${unit}` : example
}

/** 将净头寸文本解析为绝对值（原币单位，「万」已换算） */
export function parseNetAbs(netPosition: string | undefined | null): number | null {
  const cleaned = String(netPosition ?? '').replace(/^(支付|收|净)/, '').trim()
  if (cleaned === '零净头寸' || cleaned === '0') return 0
  const p = parsePositionAmount(cleaned)
  if (!p) return null
  return p.inWan ? p.value * 10_000 : p.value
}
