/**
 * ipoProjectUtils — 统一 IPO/上市/新三板/重组/再融资 项目判定
 *
 * 核心单一来源：其他 composable（useD4FormulaEngine / useF2SpecialFormData）
 * 通过 wrapper 调用本函数，保持各自的额外逻辑（如 D4 的 fraud_risk、F2 的三级瀑布）。
 *
 * spec: s-cycle-linkage-trimming-and-component-wiring §1.4
 */

/** 默认 IPO 业务关键词（小写） */
export const IPO_BIZ_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'refinancing'] as const

/**
 * 判断项目是否属于 IPO/上市类。
 *
 * @param businessCategory - 项目的 business_category 字段值
 * @param allowedCats - 可选：自定义关键词列表（覆盖默认 IPO_BIZ_KEYWORDS）
 * @returns true 表示项目属于 IPO/上市类
 */
export function isIpoProject(businessCategory: string, allowedCats?: string[]): boolean {
  if (!businessCategory) return false
  const lower = businessCategory.toLowerCase()
  if (allowedCats?.length) {
    return allowedCats.some(cat => lower.includes(cat.toLowerCase()))
  }
  return IPO_BIZ_KEYWORDS.some(kw => lower.includes(kw))
}
