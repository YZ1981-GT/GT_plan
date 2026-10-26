/**
 * 审定表「变动率」按权威模板口径（spec oo-writeback-template-parity-closure R2）。
 *
 * D / F 循环审定表的变动率列都是同一族公式，期初为 0 时的处理与各表单原先的写法不一致：
 *
 * | 模板 | 公式 | 期初=0 且 期末=0 |
 * |---|---|---|
 * | D1-1 / D2-1 / D3-1 / D5 / D6-1 / D7-1 | `IF(AND(E=0,I=0),"",IF(AND(E=0,I>0),1,J/E))` | `""` |
 * | F1-1 / F4-1 | `IF(AND(E=0,J=0),0,IF(AND(E=0,J>0),1,J/E))` | `0` |
 *
 * 期初为 0、期末为正 → 1（100%）；期初为 0、期末为负 → 模板 `J/E` 除零显示 `#DIV/0!`，表单记 `'N/A'`。
 * 原先 D1 / D2 期初为 0 一律记 100%（期末为负也是）、D3 / D5 / D6 / D7 / F1 一律 N/A（期末为正也是）、
 * F4 期末为负记 −100%。
 */

/** 变动率：比率（0.25 = 25%）；`''` 不显示；`'N/A'` 无法计算（模板 #DIV/0!） */
export type TemplateChangeRate = number | '' | 'N/A'

/** 期初、期末都为 0 时模板返回什么：`""`（D 循环）或 `0`（F1-1 / F4-1） */
export type TemplateChangeRateBlank = '' | 0

/**
 * 按模板计算变动率：期末与期初的变动额 ÷ 期初。
 *
 * @param prior   期初审定（模板 E 列）
 * @param current 期末审定（模板 I 列）
 * @param blank   期初、期末都为 0 时的返回值
 */
export function calcTemplateChangeRate(
  prior: number,
  current: number,
  blank: TemplateChangeRateBlank = '',
): TemplateChangeRate {
  if (prior === 0 && current === 0) return blank
  if (prior === 0) return current > 0 ? 1 : 'N/A'
  return (current - prior) / prior
}

/** |变动率| 是否超过阈值；不显示 / 无法计算的不算超过 */
export function isTemplateChangeRateExceeding(rate: TemplateChangeRate, threshold: number): boolean {
  if (rate === '' || rate === 'N/A') return false
  return Math.abs(rate) > threshold
}

/** 显示：`''` → `-`，`'N/A'` → `N/A`，比率 → 百分比 */
export function formatTemplateChangeRate(rate: TemplateChangeRate, digits = 2): string {
  if (rate === '') return '-'
  if (rate === 'N/A') return 'N/A'
  return `${(rate * 100).toFixed(digits)}%`
}
