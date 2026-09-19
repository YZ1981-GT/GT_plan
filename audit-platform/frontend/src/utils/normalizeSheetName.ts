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

/**
 * 深链 `?sheet=` → 实际 sheet_name 解析（纯函数，供 `GtWpRenderer` 与守卫共用）。
 *
 * 三级匹配，逐级放宽：
 * 1. 原样精确相等
 * 2. `normalizeSheetName` 归一后相等（吸收全/半角括号与空白差异）
 * 3. **归一后**的后缀 / 包含匹配 —— 覆盖两类调用方：
 *    - 来源底稿跳转只知底稿编码（`K9-3` / `D4-4`），不知中文 sheet 全名
 *    - 🔴 附注「打开同步底稿」传的是**源 xlsx tab 名**（`附注披露信息(上市公司）`），
 *      而 render-config 下发的 `sheet_name` 带科目前缀
 *      （`合同资产附注披露信息（上市公司）`）→ 两者既差前缀又差括号宽度。
 *      此前第 3 级用**未归一**的原串做 `endsWith/includes`，全角左括号 vs 半角左括号
 *      直接落空 → 深链回退到「底稿目录」（D6/D7 实测中招）。
 *
 * @returns 命中的 `sheet_name`（原样），未命中返回 `null`
 */
export function resolveSheetNameByDeepLink(
  sheetNames: readonly string[],
  target: string | null | undefined,
): string | null {
  const want = String(target ?? '')
  if (!want) return null
  const exact = sheetNames.find((n) => n === want)
  if (exact !== undefined) return exact
  const normWant = normalizeSheetName(want)
  const normHit = sheetNames.find((n) => normalizeSheetName(n) === normWant)
  if (normHit !== undefined) return normHit
  const suffix = sheetNames.find((n) => normalizeSheetName(n).endsWith(normWant))
  if (suffix !== undefined) return suffix
  const contains = sheetNames.find((n) => normalizeSheetName(n).includes(normWant))
  return contains ?? null
}
