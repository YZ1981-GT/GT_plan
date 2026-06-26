/**
 * useWpCodeParser — wp_code 正则解析 composable
 *
 * 从文本中提取底稿编码（wp_code）模式，以及按 + 分割 source_label。
 * wp_code 格式：[A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?
 * 示例：A1, B50, D2-1, F3A, A17-2-1 → 注意 A17-2-1 匹配为 A17-2 + 余下文本中的 1 不匹配
 */

// ─── wp_code 正则 ────────────────────────────────────────────────────────────────

/**
 * 匹配 wp_code 的正则表达式
 * - 首字母 A-S
 * - 1~2 位数字
 * - 可选 -数字(1~2位)
 * - 可选尾部大写字母
 */
const WP_CODE_RE = /[A-S]\d{1,2}(?:-\d{1,2})?(?:[A-Z])?/g

/**
 * 从文本中提取所有匹配的 wp_code
 */
export function extractWpCodes(text: string): string[] {
  if (!text) return []
  const matches = text.match(WP_CODE_RE)
  return matches ? [...matches] : []
}

/**
 * 按 + 分隔符分割 source_label 字符串
 * 例如 "A15+A15-1" → ["A15", "A15-1"]
 */
export function parseSourceLabel(label: string): string[] {
  if (!label) return []
  return label.split('+').filter((s) => s.length > 0)
}

/**
 * composable 形式导出
 */
export function useWpCodeParser() {
  return {
    extractWpCodes,
    parseSourceLabel,
  }
}
