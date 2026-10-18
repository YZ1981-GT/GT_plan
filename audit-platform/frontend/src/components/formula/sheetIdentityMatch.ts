/**
 * sheetIdentityMatch.ts — 右栏「当前页公式」sheet 归属匹配的单一真源（Task 1.2 / ADR-FMC-01）
 *
 * 背景（修复的缺陷 FM-P0-01）：
 *   旧 `matchSheetCode(actual, expected)` 用 `a === b || a.includes(b) || b.includes(a)`
 *   做子串匹配 —— `E1-1` 命中 `E1-10/14/15`、`D2-1` 命中 `D2-10/12`，当前页右栏「串页」
 *   混入其它 sheet 的公式（§1 #1 实测）。
 *
 * 本模块把 sheet 归属匹配收敛为**结构化精确等值 + fail-closed**（ADR-FMC-01 裁定 B）：
 *   - 结构身份优先级：`stable_sheet_key`（展示重命名不改键，与库里 V163 列同口径）→
 *     结构化 `sheet_codes`（如 `['E1-1']`）→ 从 `sheet_name` 提取的结构化 sheet 编码。
 *   - 比较一律**精确等值**（归一后 `a === b`），**禁** `includes` 子串匹配。
 *   - 缺可解析结构身份的行 **fail-closed 排除**（返回 false），**禁退回 `includes`**，
 *     否则精确化形同虚设（ADR-FMC-01「fail-closed」硬约束）。
 *
 * 稳定键单一真源（ADR-FMC-01 / NIT-1）：sheet 展示名归一 `normalizeSheetKey` 与后端
 * `backend/app/services/formula_management/stable_key.py : normalize_sheet_key` 同口径
 * （剥前导排序/编号前缀 + 折叠空白 + 大小写敏感），由 Task 1.3 单测钉死一致性；
 * **禁在本仓另写一套 sheet 名规范化**。
 */

// A1 地址：列字母 + 行号（命名单元/自定义 token 不匹配此式）。
const A1_RE = /^[A-Za-z]+\d+$/

// sheet 展示名的排序/编号前缀（如「五、1 」「1. 」「（一）」「3、」），规范化时剥离。
// 与 stable_key.py `_ORDER_PREFIX_RE` 同口径：
//   - 中文序号后**必须**跟 `、.．`；其后子序号 `\d+` 仅在紧跟空白或 `、.．` 时并入前缀，
//     否则属正文须保留（如「一、0」里的「0」是正文）。
//   - 阿拉伯数字序号 `\d+[、.．]`。
//   - 括号序号 `（一）`/`(1)`。
const ORDER_PREFIX_RE = new RegExp(
  '^\\s*(?:' +
    '[一二三四五六七八九十]+[、.．](?:\\s*\\d+(?=[\\s、.．])[、.．]?)?' +
    '|\\d+[、.．]' +
    '|[（(][一二三四五六七八九十\\d]+[)）]' +
    ')\\s*',
)

/**
 * sheet 展示名 → 稳定 sheet 键（与后端 `normalize_sheet_key` 同口径，单一真源对齐）。
 *   1. 剥前导排序/编号前缀（「五、1 」「1.」「（一）」）。
 *   2. 折叠内部连续空白（含全角空格 \u3000）为单个半角空格，首尾 trim。
 *   3. 大小写不变（sheet 名可能含大小写敏感的 wp_code 如 `D2-1`）。
 * 空/未定义 → 空串（调用方据此判 fail-closed）。
 */
export function normalizeSheetKey(sheetName: string | null | undefined): string {
  if (!sheetName) return ''
  let s = String(sheetName)
  s = s.replace(ORDER_PREFIX_RE, '')
  s = s.replace(/[\s\u3000]+/g, ' ').trim()
  return s
}

/**
 * 结构化 sheet 编码归一（如 `E1-1`/`D2-10`）：trim + 小写 + 破折号/下划线统一为 `-`。
 * 空/未定义 → 空串。与右栏 wp_code 归一口径一致（破折号变体统一），仅用于编码类 token。
 */
export function normalizeSheetCode(value: string | null | undefined): string {
  return (value || '')
    .trim()
    .toLowerCase()
    .replace(/—/g, '-')
    .replace(/_/g, '-')
    .replace(/^wp-|^sheet-/, '')
}

/** 该字符串是否形如结构化 sheet 编码（字母+数字，可带 `-数字`/`-数字字母` 段）。 */
function isStructuredSheetCode(value: string): boolean {
  return /^[a-z]+\d+(?:-\d+[a-z]?)*$/.test(value)
}

/**
 * 从 sheet 展示名中提取结构化 sheet 编码（如从「货币资金审定表E1-1」提取 `e1-1`）。
 * 仅当展示名**整体**就是一个结构化编码，或其**末尾 token** 是结构化编码时才返回；
 * 否则返回空串（fail-closed：宁可不匹配也不用子串启发式串页）。
 */
export function extractSheetCodeFromName(sheetName: string | null | undefined): string {
  const normalized = normalizeSheetCode(sheetName)
  if (!normalized) return ''
  if (isStructuredSheetCode(normalized)) return normalized
  // 末尾结构化编码 token（如「审定表e1-1」→ 末段 e1-1）：用边界锚定，避免 includes 串页。
  const m = normalized.match(/([a-z]+\d+(?:-\d+[a-z]?)*)$/)
  if (m && isStructuredSheetCode(m[1])) {
    // 要求该 token 前是非字母数字边界（或行首），防止把 `e1-10` 的末段误当 `e1-1`。
    const idx = normalized.lastIndexOf(m[1])
    const prevChar = idx > 0 ? normalized[idx - 1] : ''
    if (idx === 0 || !/[a-z0-9]/.test(prevChar)) return m[1]
  }
  return ''
}

/**
 * 判断某行（带 `stable_sheet_key` / `sheet_codes` / `sheet_name`）是否精确归属选中 sheet。
 *
 * @param row          公式行投影（含可选 stable_sheet_key / sheet_codes / sheet_name）
 * @param selectedSheetCode  选中的结构化 sheet 编码（ACNR `sheet_code`，如 `E1-1`）
 * @param selectedSheetKey   选中 sheet 的稳定键（可选；有则参与 stable_sheet_key 维度等值）
 * @returns 结构化精确等值命中返回 true；缺结构身份 fail-closed 返回 false（禁退 includes）。
 */
export function matchRowToSelectedSheet(
  row: {
    stable_sheet_key?: string | null
    sheet_codes?: unknown
    sheet_name?: string | null
  },
  selectedSheetCode: string | null | undefined,
  selectedSheetKey?: string | null | undefined,
): boolean {
  const wantCode = normalizeSheetCode(selectedSheetCode)
  const wantKey = normalizeSheetKey(selectedSheetKey)
  // 选中 sheet 本身无结构身份 → fail-closed（无从精确归属）。
  if (!wantCode && !wantKey) return false

  // 维度 1：stable_sheet_key 精确等值（展示重命名不改键，库里 V163 列同口径）。
  const rowKey = normalizeSheetKey(row.stable_sheet_key)
  if (rowKey && wantKey) {
    return rowKey === wantKey
  }

  // 维度 2：结构化 sheet_codes 数组 —— 任一编码与选中编码精确等值。
  const scs = row.sheet_codes
  if (Array.isArray(scs) && scs.length) {
    if (!wantCode) return false
    return scs.some((c) => {
      const code = normalizeSheetCode(String(c))
      return !!code && code === wantCode
    })
  }

  // 维度 3：从 sheet_name 提取结构化编码 —— 精确等值。
  const nameCode = extractSheetCodeFromName(row.sheet_name)
  if (nameCode && wantCode) {
    return nameCode === wantCode
  }

  // 无任何可解析结构身份 → fail-closed 排除（禁退回 includes）。
  return false
}

/**
 * 两个 sheet 编码的结构化精确等值（归一后 `a === b`，禁子串）。
 * 用于 surfaced 的 `sheet_codes` 逐项与选中编码比对、extraction anchor 前缀归属等
 * 「编码 ↔ 编码」场景；任一侧归一后为空 → false（fail-closed）。
 */
export function sheetCodeEquals(
  actual: string | null | undefined,
  expected: string | null | undefined,
): boolean {
  const a = normalizeSheetCode(actual)
  const b = normalizeSheetCode(expected)
  if (!a || !b) return false
  return a === b
}
