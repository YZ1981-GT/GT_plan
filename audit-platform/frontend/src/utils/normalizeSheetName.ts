/**
 * 折叠 sheet 名称中的半角↔全角标点宽度差异，用于匹配层。
 * 只归一**标点宽度+空白**，不碰内容字/数字/字母。
 *
 * 🔴 绝不用于章节号匹配（五、1 vs 五、10 那条链保持严格 ===，本函数只作用于 sheet_name）。
 */
export function normalizeSheetName(name: string): string {
  if (!name) return ''
  return name
    // 全角圆括号→半角
    .replace(/\uff08/g, '(')
    .replace(/\uff09/g, ')')
    // 全角逗号、冒号、分号→半角
    .replace(/\uff0c/g, ',')
    .replace(/\uff1a/g, ':')
    .replace(/\uff1b/g, ';')
    // 全角空格→半角空格
    .replace(/\u3000/g, ' ')
    // 多个连续空白合成一个空格
    .replace(/\s+/g, ' ')
    // trim 首尾空白
    .trim()
}
