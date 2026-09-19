/**
 * 源科目 → G14 信用减值损失 ECL EventBus（g-cycle:source-ecl）
 * 金额口径：本期计入损益净额 = 计提 − 转回（与 G14-2 profitLoss 一致）
 */
import { parseNum } from './useG14FormulaEngine'
import { G14_ECL_CROSS_REF } from './g14Constants'

export const G_CYCLE_SOURCE_ECL_EVENT = 'g-cycle:source-ecl'

/** 源科目编码 → G14-2 rowKey */
export const G14_SOURCE_TO_ROW_KEY: Record<string, string> = {
  D1: 'notes',
  D2: 'ar',
  D5: 'rfin',
  F1: 'othar',
  G4: 'debt',
  G6: 'othdebt',
  G5: 'ltar',
  D6: 'ca',
}

/** G14 rowKey → 默认索引（与 G14_ECL_CROSS_REF 一致） */
export const G14_ROW_KEY_TO_SOURCE_WP: Record<string, string> = Object.fromEntries(
  Object.entries(G14_ECL_CROSS_REF)
    .filter(([, v]) => !!v)
    .map(([k, v]) => [k, String(v).replace(/^wp:/, '').split('-')[0] ?? '']),
)

export function resolveG14EclRowKey(sourceOrRowKey: string): string | null {
  const key = String(sourceOrRowKey ?? '').trim()
  if (!key) return null
  if (G14_SOURCE_TO_ROW_KEY[key]) return G14_SOURCE_TO_ROW_KEY[key]
  if (key in G14_ECL_CROSS_REF) return key
  // 兼容 wp:D2-1 / D2-1
  const code = key.replace(/^wp:/i, '').split('-')[0]?.toUpperCase()
  if (code && G14_SOURCE_TO_ROW_KEY[code]) return G14_SOURCE_TO_ROW_KEY[code]
  return null
}

export function publishGCycleSourceEcl(sourceOrRowKey: string, amount: number): void {
  const rowKey = resolveG14EclRowKey(sourceOrRowKey)
  if (!rowKey) return
  try {
    window.dispatchEvent(
      new CustomEvent(G_CYCLE_SOURCE_ECL_EVENT, {
        detail: { rowKey, source: sourceOrRowKey, amount: parseNum(amount) },
      }),
    )
  } catch {
    /* best effort */
  }
}

/** 计提 − |转回| → 净信用减值损失（计入损益） */
export function calcSourceEclProfitLoss(provision: number, reversal: number): number {
  return parseNum(provision) - Math.abs(parseNum(reversal))
}
