/**
 * K1-1 跨表勾稽：组合名称 vs K1-6 / K1-8
 */
import {
  comboNamesMatch,
  computeK16K18ComboConsistency,
  extractK18GroupNames,
  type K16K18ComboConsistency,
} from './k1PolicyCrossHelpers'

export function parseK16ComboBases(raw: unknown): string[] {
  if (!raw) return []
  try {
    const parsed = typeof raw === 'string' ? JSON.parse(raw) : raw
    if (!Array.isArray(parsed)) return []
    return parsed.map((c: any) => String(c.basis || '').trim()).filter(Boolean)
  } catch {
    return []
  }
}

/** K1-1 组合行标签 + K1-6 组合 vs K1-8 分组 */
export function computeK11ComboCrossCheck(
  map: Map<string, any>,
  k11PortfolioLabels: string[],
): K16K18ComboConsistency & { k16Names: string[] } {
  const k16FromPolicy = parseK16ComboBases(map.get('K1-6-combos')?.remark)
  const k16Names = k16FromPolicy.length
    ? k16FromPolicy
    : k11PortfolioLabels.filter((l) => l && l !== '单项计提')
  const k18Groups = extractK18GroupNames(map)
  const result = computeK16K18ComboConsistency(k16Names, k18Groups)
  return { ...result, k16Names }
}

export const K1_VARIANCE_THRESHOLD = 0.3

export function draftVarianceReason(label: string, changeRate: number | null): string {
  if (changeRate == null || Math.abs(changeRate) < K1_VARIANCE_THRESHOLD) return ''
  const pct = (Math.abs(changeRate) * 100).toFixed(1)
  const direction = changeRate > 0 ? '增加' : '减少'
  return `${label}审定数较上期${direction}${pct}%，须说明原因。`
}
