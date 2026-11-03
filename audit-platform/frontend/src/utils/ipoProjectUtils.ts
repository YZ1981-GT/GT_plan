/**
 * ipoProjectUtils — 统一 IPO/上市/新三板/重组/再融资 项目判定
 *
 * 核心单一来源：D4 通过 allowedCats 扩展 fraud_risk；F2 保留自身的三级兼容瀑布。
 * 这些场景都复用本函数，不在业务 composable 内复制 IPO 关键词判定。
 *
 * spec: s-cycle-linkage-trimming-and-component-wiring §1.4
 * R4（trim-generation-plan-followup-optimizations）：优先读后端 project_classification 的适用性标签
 * （专项场景 + 语义等价细分类 + 上市公司报表模板），按标签精确匹配；只有分类列字符串时保留旧的子串语义
 * （迁移期兼容；V219 后分类列只剩质控分类码，子串不会再命中）。
 */

/** 默认 IPO 业务关键词（小写） */
export const IPO_BIZ_KEYWORDS = ['ipo', 'listed', 'neeq', 'restructuring', 'refinancing'] as const

/** 后端 ProjectClassification 的最小形状：只用适用性标签。 */
export interface ProjectClassificationTags {
  tags?: readonly string[] | null
}

export type IpoProjectSource = string | ProjectClassificationTags | null | undefined

/**
 * 判断项目是否属于 IPO/上市类。
 *
 * @param source - 项目分类（推荐：后端 project_classification）或 business_category 字段值（兼容）
 * @param allowedCats - 可选：自定义关键词列表（覆盖默认 IPO_BIZ_KEYWORDS）
 * @returns true 表示项目属于 IPO/上市类
 */
export function isIpoProject(source: IpoProjectSource, allowedCats?: readonly string[]): boolean {
  if (!source) return false
  const matches = typeof source === 'object'
    ? (cat: string) => (source.tags ?? []).some((tag) => tag.toLowerCase() === cat.toLowerCase())
    : (cat: string) => source.toLowerCase().includes(cat.toLowerCase())
  if (allowedCats?.length) {
    return allowedCats.some(matches)
  }
  return IPO_BIZ_KEYWORDS.some(matches)
}
