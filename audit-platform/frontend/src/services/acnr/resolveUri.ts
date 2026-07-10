/**
 * resolveUri.ts — ACNR URI 规范化辅助
 *
 * 提供 URI 格式校验与规范化：
 * - standard profile: wp://{parent}/{sheet_name}#{cell}
 * - custom_flat profile: wp://{wp_code}/{cell}
 * - 索引 ns 语法: cell:D2-2!E100 / TB:1001 / wp:D2-2
 *
 * Requirements: R9
 */

// ─── URI Profiles ─────────────────────────────────────────────────────────────

export type UriProfile = 'standard' | 'custom_flat' | 'tb' | 'report' | 'note' | 'aux'

export interface ParsedUri {
  profile: UriProfile
  domain: string
  parent?: string
  sheetName?: string
  cell?: string
  wpCode?: string
  code?: string
}

/** standard profile 正则: wp://{parent}/{sheet_name}#{cell} */
const RE_STANDARD = /^wp:\/\/([A-Za-z0-9-]+)\/([^#]+)(?:#(.+))?$/

/** custom_flat profile 正则: wp://{wp_code}/{cell} (无 # 分隔, cell 为 A1 格式) */
const RE_CUSTOM_FLAT = /^wp:\/\/([A-Za-z0-9-]+)\/([A-Z]\d+)$/

/** 标准底稿码判定（grammar_v1: STANDARD_WP_CODE_RE = ^[A-S]\d） */
const RE_STANDARD_WP_CODE = /^[A-S]\d/

/** 非 wp 域 URI */
const RE_TB = /^tb:\/\/([^#]+)(?:#(.+))?$/
const RE_REPORT = /^report:\/\/([^#]+)(?:#(.+))?$/
const RE_NOTE = /^note:\/\/(.+)$/
const RE_AUX = /^aux:\/\/([^#]+)(?:#(.+))?$/

/**
 * 解析 URI 为结构化对象
 *
 * 判定逻辑（wp:// 域）：
 * - 有 `#` 分隔符 → standard profile
 * - 无 `#`、第二段为纯 A1 坐标（[A-Z]\d+）、且第一段非标准码（^[A-S]\d） → custom_flat
 * - 其余 → standard（sheet 级，无 cell）
 *
 * @returns ParsedUri | null (不合法时返回 null)
 */
export function parseUri(uri: string): ParsedUri | null {
  if (!uri) return null

  // wp:// 域处理
  if (uri.startsWith('wp://')) {
    // 有 # 分隔符 → 一定是 standard profile
    if (uri.includes('#')) {
      const m = uri.match(RE_STANDARD)
      if (m) {
        return {
          profile: 'standard',
          domain: 'wp',
          parent: m[1],
          sheetName: m[2],
          cell: m[3] || undefined,
        }
      }
    }

    // 无 # 分隔符：尝试 custom_flat（第二段为纯 A1 坐标 + 第一段非标准码）
    const mFlat = uri.match(RE_CUSTOM_FLAT)
    if (mFlat && !RE_STANDARD_WP_CODE.test(mFlat[1])) {
      return {
        profile: 'custom_flat',
        domain: 'wp',
        wpCode: mFlat[1],
        cell: mFlat[2],
      }
    }

    // 否则按 standard（sheet 级，无 cell）
    const mStd = uri.match(RE_STANDARD)
    if (mStd) {
      return {
        profile: 'standard',
        domain: 'wp',
        parent: mStd[1],
        sheetName: mStd[2],
        cell: mStd[3] || undefined,
      }
    }

    return null
  }

  // 非 wp 域
  let m = uri.match(RE_TB)
  if (m) {
    return { profile: 'tb', domain: 'tb', code: m[1], cell: m[2] || undefined }
  }

  m = uri.match(RE_REPORT)
  if (m) {
    return { profile: 'report', domain: 'report', code: m[1], cell: m[2] || undefined }
  }

  m = uri.match(RE_NOTE)
  if (m) {
    return { profile: 'note', domain: 'note', code: m[1] }
  }

  m = uri.match(RE_AUX)
  if (m) {
    return { profile: 'aux', domain: 'aux', code: m[1], cell: m[2] || undefined }
  }

  return null
}

/**
 * 校验 URI 是否为合法的 ACNR URI
 */
export function isValidUri(uri: string): boolean {
  return parseUri(uri) !== null
}

/**
 * 从 URI 提取 domain
 */
export function extractDomain(uri: string): string | null {
  const parsed = parseUri(uri)
  return parsed?.domain ?? null
}

/**
 * 规范化 URI（去除多余空格/尾 slash，统一大小写格式）
 */
export function normalizeUri(uri: string): string {
  if (!uri) return ''
  return uri.trim().replace(/\/+$/, '')
}

// ─── 索引 ns 语法解析 ──────────────────────────────────────────────────────────

export interface ParsedIndexRef {
  namespace: string
  target: string
}

/** 索引命名空间引用正则: ns:target */
const RE_INDEX_REF = /^(wp|sheet|cell|TB|Note|Adj|Att|EQCR|Calc|Sample|Confirm):(.+)$/

/**
 * 解析索引命名空间语法 (如 cell:D2-2!E100, TB:1001)
 */
export function parseIndexRef(indexRef: string): ParsedIndexRef | null {
  if (!indexRef) return null
  const m = indexRef.match(RE_INDEX_REF)
  if (!m) return null
  return { namespace: m[1], target: m[2] }
}

/**
 * 校验索引命名空间引用是否合法
 */
export function isValidIndexRef(indexRef: string): boolean {
  return parseIndexRef(indexRef) !== null
}
