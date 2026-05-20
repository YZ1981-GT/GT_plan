/**
 * resolveMainVersionSheet — H 循环同 wp_code 多 sheet 路由分支保护
 *
 * spec workpaper-h-fixed-assets-cycle H-F1b（Task 1.2）
 *
 * 当 cross_wp_references 跳转到某 wp_code（如 H1-12）时，可能匹配多个 sheet。
 * 本函数按"主版本识别优先级"选择默认显示的 sheet。
 *
 * 主版本识别优先级（按 sheet 名关键词匹配）：
 *   1. 含"（不含减值）" → 优先（最常用的基础版本）
 *   2. 含"-直线法"     → 次优先（折旧默认方法）
 *   3. 含"（成本模式）" → 第三（计量模式默认）
 *   4. 含"（按月）"     → 第四（计算频率默认）
 *   5. fallback: 首个匹配
 */

/**
 * 主版本关键词优先级列表（按优先级降序排列）
 */
export const MAIN_VERSION_KEYWORDS = [
  '（不含减值）',
  '-直线法',
  '（成本模式）',
  '（按月）',
] as const

/**
 * 从 sheet 列表中解析指定 wp_code 的主版本 sheet 名
 *
 * @param wpCode - 底稿编码（如 "H1-12"）
 * @param allSheets - 全部 sheet 名列表
 * @returns 主版本 sheet 名；无匹配时返回空字符串
 */
export function resolveMainVersionSheet(wpCode: string, allSheets: string[]): string {
  // 筛选出包含该 wp_code 的 sheet（wp_code 通常在 sheet 名末尾）
  const matches = allSheets.filter((s) => s.includes(wpCode))

  if (matches.length === 0) return ''
  if (matches.length === 1) return matches[0]

  // 多匹配时按关键词优先级选主版本
  for (const kw of MAIN_VERSION_KEYWORDS) {
    const hit = matches.find((s) => s.includes(kw))
    if (hit) return hit
  }

  // fallback: 首个匹配
  return matches[0]
}
