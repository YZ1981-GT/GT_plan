/**
 * parseIndexRef — 跨底稿索引号解析工具函数
 *
 * 11 命名空间路由解析（wp/sheet/cell/Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm）
 * 4 层级跳转语义（cell→1, sheet→2, wp→3, module→4）
 * 9 种边缘 case 处理（中文索引/空格/大小写/多目标/不存在/被裁剪/跨项目/GT_Custom/空 sheet）
 *
 * Validates: Requirements 3.11.8 + 3.11.9 + 3.11.10
 */

// ─── Types ───────────────────────────────────────────────────────────────────

export type Namespace =
  | 'wp'
  | 'sheet'
  | 'cell'
  | 'Note'
  | 'TB'
  | 'Adj'
  | 'Att'
  | 'EQCR'
  | 'Calc'
  | 'Sample'
  | 'Confirm'

export type Layer = 1 | 2 | 3 | 4

export interface ResolvedIndexRef {
  ns: Namespace
  layer: Layer
  target: string
  exists?: boolean
  crossProject?: boolean
  empty?: boolean
  reason?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/**
 * Namespace → Layer 映射表
 * - Layer 1 (cell): 同 sheet 内单元格定位
 * - Layer 2 (sheet): 同底稿内 sheet 切换
 * - Layer 3 (wp): 跨底稿跳转
 * - Layer 4 (module): 跨模块跳转（Note/TB/Adj/Att/EQCR/Calc/Sample/Confirm）
 */
export const NAMESPACE_LAYER_MAP: Record<Namespace, Layer> = {
  cell: 1,
  sheet: 2,
  wp: 3,
  Note: 4,
  TB: 4,
  Adj: 4,
  Att: 4,
  EQCR: 4,
  Calc: 4,
  Sample: 4,
  Confirm: 4,
}

/** All valid namespace strings (case-sensitive canonical form) */
const VALID_NAMESPACES: Namespace[] = [
  'wp',
  'sheet',
  'cell',
  'Note',
  'TB',
  'Adj',
  'Att',
  'EQCR',
  'Calc',
  'Sample',
  'Confirm',
]

/**
 * Case-insensitive lookup map: lowercase → canonical namespace
 */
const NS_LOOKUP: Record<string, Namespace> = {}
for (const ns of VALID_NAMESPACES) {
  NS_LOOKUP[ns.toLowerCase()] = ns
}

// ─── Regex Patterns ──────────────────────────────────────────────────────────

/**
 * 严格模式：`<ns>:<target>` 格式
 * 匹配 11 个命名空间前缀（大小写不敏感）
 */
const STRICT_RE = /^(wp|sheet|cell|Note|TB|Adj|Att|EQCR|Calc|Sample|Confirm):(.+)$/i

/**
 * 宽松模式：识别文本中的底稿编码
 * 格式：[A-S]\d+(-\d+)*[A-Z]?
 * 例：D2, D2-1, D2-1-1, D2A, E1, F2-3B
 */
const LOOSE_RE = /^[A-S]\d+(?:-\d+)*[A-Z]?$/i

/**
 * GT_Custom 白名单模式 — 这些 sheet 不可跳转
 */
const GT_CUSTOM_RE = /^GT_Custom/i

// ─── Helper Functions ────────────────────────────────────────────────────────

/**
 * 检查给定字符串是否为有效命名空间
 */
export function isValidNamespace(ns: string): boolean {
  return ns.toLowerCase() in NS_LOOKUP
}

/**
 * 将命名空间字符串归一化为标准形式
 */
function normalizeNamespace(ns: string): Namespace | null {
  return NS_LOOKUP[ns.toLowerCase()] ?? null
}

/**
 * 判断目标是否为 cell 引用格式（含 ! 分隔符，如 D2-1!B23）
 */
function isCellRef(target: string): boolean {
  return target.includes('!')
}

/**
 * 判断目标是否为 sheet 引用格式（含 - 后缀数字，如 D2-1）
 * 但不是主底稿编码（如 D2 本身）
 */
function isSheetRef(target: string): boolean {
  // Sheet refs have format like D2-1, D2-1-1, D2A (letter suffix)
  // Main workpaper codes are just like D2, E1, F2 (letter + digits only)
  return /^[A-S]\d+(?:-\d+)+$/i.test(target) || /^[A-S]\d+[A-Z]$/i.test(target)
}

// ─── Main Function ───────────────────────────────────────────────────────────

/**
 * 解析索引引用字符串，返回结构化的 ResolvedIndexRef 或 null
 *
 * 支持两种模式：
 * 1. 严格模式 `<ns>:<target>`：如 `Note:五-1-1`, `TB:1122`, `wp:D2`
 * 2. 宽松模式：识别底稿编码如 `D2`, `D2-1`, `D2A`
 *
 * 纯函数，不做 API 调用。校验（exists/crossProject/empty）由 GtIndexChip 组件负责。
 *
 * @param value - 索引引用字符串
 * @returns ResolvedIndexRef | null
 */
export function parseIndexRef(value: string): ResolvedIndexRef | null {
  // Edge case: null/undefined/empty
  if (!value || typeof value !== 'string') {
    return null
  }

  // Edge case 2: trim spaces (空格处理)
  const trimmed = value.trim()
  if (!trimmed) {
    return null
  }

  // Edge case 7: GT_Custom — return null (whitelist skip)
  if (GT_CUSTOM_RE.test(trimmed)) {
    return null
  }

  // Try strict mode first: `<ns>:<target>`
  const strictMatch = trimmed.match(STRICT_RE)
  if (strictMatch) {
    const rawNs = strictMatch[1]
    const rawTarget = strictMatch[2].trim()

    if (!rawTarget) {
      return null
    }

    const ns = normalizeNamespace(rawNs)
    if (!ns) {
      return null
    }

    const layer = NAMESPACE_LAYER_MAP[ns]

    return {
      ns,
      layer,
      target: rawTarget,
    }
  }

  // Try loose mode: workpaper code pattern [A-S]\d+(-\d+)*[A-Z]?
  // Normalize to uppercase for matching (大小写归一化)
  const normalized = trimmed.toUpperCase()

  if (LOOSE_RE.test(normalized)) {
    // Determine layer based on the code structure
    if (isCellRef(normalized)) {
      // Contains ! separator → cell reference (Layer 1)
      // This shouldn't normally match LOOSE_RE, but handle defensively
      return {
        ns: 'cell',
        layer: 1,
        target: normalized,
      }
    }

    if (isSheetRef(normalized)) {
      // Has sub-number suffix (D2-1) or letter suffix (D2A) → sheet reference (Layer 2)
      return {
        ns: 'sheet',
        layer: 2,
        target: normalized,
      }
    }

    // Main workpaper code (D2, E1, F2) → workpaper reference (Layer 3)
    return {
      ns: 'wp',
      layer: 3,
      target: normalized,
    }
  }

  // Check if it's a cell reference with ! (e.g., "D2-1!B23") that didn't match strict
  if (trimmed.includes('!')) {
    const parts = trimmed.split('!')
    if (parts.length === 2) {
      const sheetPart = parts[0].trim().toUpperCase()
      const cellPart = parts[1].trim().toUpperCase()
      if (sheetPart && cellPart && LOOSE_RE.test(sheetPart)) {
        return {
          ns: 'cell',
          layer: 1,
          target: `${sheetPart}!${cellPart}`,
        }
      }
    }
  }

  // No match
  return null
}
