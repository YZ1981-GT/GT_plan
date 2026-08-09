/**
 * customWpBatchParse.ts — 批量创建自定义底稿的清单解析与校验（纯函数层）
 *
 * spec: custom-workpaper-dual-mode-formula-and-batch Wave 6 Task 20
 *
 * 🔴 零 Vue 依赖，便于 PBT。UI 只负责取输入、展示结果。
 * 🔴 前端只判「格式」与「清单内重号」；**库内重号（duplicate_db）只有后端能判**
 *    —— 见 `POST .../create-custom-batch/preview`。前端不得自行猜测已有编号。
 */

/** 解析出的一行清单项 */
export interface ParsedItem {
  wp_code: string
  wp_name: string
  audit_cycle?: string
  /** 原始行号（1-based），用于把错误定位回用户输入 */
  line: number
}

export interface ItemError {
  line: number
  wp_code: string
  reason: string
}

export interface ValidateResult {
  valid: ParsedItem[]
  errors: ItemError[]
  /**
   * 清单条数超过 `MAX_BATCH_ITEMS`（**未截断**，调用方须提示分批）。
   *
   * 🔴 置标志而不静默截断 —— 截断会让用户以为整份清单都提交了
   * （与 `buildCellPatch` 的 `overflow` 同款铁律）。
   */
  overflow: boolean
}

/**
 * 单次批量上限，**与后端 `wp_template.MAX_BATCH_ITEMS` 交叉锁死**。
 *
 * 🔴 两侧不等的后果：前端放行 300 条、后端 422 整批拒绝 → 用户白填一屏。
 * 守卫读后端源码比对该常量值。
 */
export const MAX_BATCH_ITEMS = 200

/**
 * 编号字符集：字母/数字开头，其后可含字母数字中划线下划线点，总长 ≤32。
 *
 * 🔴 与后端 preview 端点的正则**必须一致**，否则出现「前端放行、后端判 invalid」
 * 的不一致体验。守卫读后端源码交叉锁死。
 */
export const WP_CODE_RE = /^[A-Za-z0-9][A-Za-z0-9\-_.]{0,31}$/

/**
 * 编号归一：去首尾空白 + 大写。**仅用于清单内重号检出**。
 *
 * 🔴 有意与后端不同口径，不要「统一」：后端 `_custom_code_exists` 是**精确匹配**
 * （不归一），那是既有单条 `create-custom` 端点的行为，改成大小写不敏感会让
 * 历史上能创建的 `d1`/`D1` 组合突然 409 = 对既有调用方的回归。
 *
 * 故这里前端**故意更严**：把 `d1` 与 `D1` 判成清单内重复并要求用户自己消歧
 * —— 一份清单里同时出现这两个几乎一定是笔误，让用户改比让他拿到两份
 * 名字只差大小写的底稿更好。库内重号仍由后端 preview 按精确匹配判定。
 */
export function normalizeWpCode(code: unknown): string {
  return String(code ?? '').trim().toUpperCase()
}

/** 一行按 Tab / 多空格 / 逗号 / 全角逗号 切列 */
function splitCells(line: string): string[] {
  return line
    .split(/\t+|,|，|\s{2,}/)
    .map((s) => s.trim())
    .filter((s) => s.length > 0)
}

/**
 * 粘贴文本 → 清单项。
 *
 * 每行 `编号  名称  [循环]`；空行与纯分隔符行跳过。
 * 🔴 只切出前 3 列：多余列忽略而非报错（用户从 Excel 粘贴常带额外列）。
 */
export function parseTextList(text: string): ParsedItem[] {
  if (!text || typeof text !== 'string') return []
  const out: ParsedItem[] = []
  const lines = text.split(/\r?\n/)
  for (let i = 0; i < lines.length; i++) {
    const raw = lines[i]
    if (!raw || !raw.trim()) continue
    const cells = splitCells(raw)
    if (cells.length === 0) continue
    // 跳过表头行（含「编号」「名称」字样且不含数字编号特征）
    if (i === 0 && looksLikeHeader(cells)) continue
    out.push({
      wp_code: cells[0] ?? '',
      wp_name: cells[1] ?? '',
      audit_cycle: cells[2] || undefined,
      line: i + 1,
    })
  }
  return out
}

/** 是否表头行 */
function looksLikeHeader(cells: string[]): boolean {
  const joined = cells.join('')
  return (
    (joined.includes('编号') || joined.includes('索引')) &&
    (joined.includes('名称') || joined.includes('名'))
  )
}

const CODE_KEYS = ['编号', '索引', '索引号', 'code', 'wp_code']
const NAME_KEYS = ['名称', '底稿名称', 'name', 'wp_name']
const CYCLE_KEYS = ['循环', '审计循环', 'cycle', 'audit_cycle']

function matchIdx(header: string[], keys: string[]): number {
  for (let i = 0; i < header.length; i++) {
    const h = String(header[i] ?? '').trim().toLowerCase()
    if (!h) continue
    for (const k of keys) {
      if (h.includes(k.toLowerCase())) return i
    }
  }
  return -1
}

/**
 * Excel 行数组 → 清单项。
 *
 * 识别表头行（含「编号」「名称」字样）并**按列名映射**；无表头时按位置（0/1/2）。
 * 🔴 按列名映射是必需的：用户的 Excel 列序不可控，按位置读会把名称当编号。
 */
export function parseExcelRows(rows: unknown[][]): ParsedItem[] {
  if (!Array.isArray(rows) || rows.length === 0) return []

  const first = (rows[0] ?? []).map((c) => (c == null ? '' : String(c)))
  const ci = matchIdx(first, CODE_KEYS)
  const ni = matchIdx(first, NAME_KEYS)
  const yi = matchIdx(first, CYCLE_KEYS)
  const hasHeader = ci >= 0 && ni >= 0

  const codeIdx = hasHeader ? ci : 0
  const nameIdx = hasHeader ? ni : 1
  const cycleIdx = hasHeader ? yi : 2
  const start = hasHeader ? 1 : 0

  const out: ParsedItem[] = []
  for (let r = start; r < rows.length; r++) {
    const row = rows[r] ?? []
    const code = String(row[codeIdx] ?? '').trim()
    const name = String(row[nameIdx] ?? '').trim()
    const cycle = cycleIdx >= 0 ? String(row[cycleIdx] ?? '').trim() : ''
    if (!code && !name) continue // 整行空 → 跳过
    out.push({
      wp_code: code,
      wp_name: name,
      audit_cycle: cycle || undefined,
      line: r + 1,
    })
  }
  return out
}

/**
 * 校验清单项。
 *
 * @param items 解析出的清单
 * @param existingCodes 该项目下**已存在**的编号（来自后端 preview；
 *   🔴 前端拿不到时传空集合 —— 此时库内重号由后端 preview/创建时判定，
 *   前端不得凭空猜测，否则会把合法编号误判成冲突）
 *
 * 🔴 幂等：同一入参重复调用结果一致（不修改 items）。
 */
export function validateItems(
  items: ParsedItem[],
  existingCodes: Iterable<string> = [],
): ValidateResult {
  // 🔴 库内已存在编号按**后端口径（精确匹配）**比对，不套 normalizeWpCode ——
  //    归一后比会把 `d1` 判成与库里 `D1` 冲突，而后端实际允许创建（精确不等）
  //    ⇒ 前端拦下了后端会放行的编号 = 假阻断。
  const existing = new Set(
    Array.from(existingCodes, (c) => String(c).trim()).filter(Boolean),
  )
  /** 清单内重号用归一后的键（见 normalizeWpCode 的口径说明） */
  const seen = new Set<string>()
  const valid: ParsedItem[] = []
  const errors: ItemError[] = []
  const list = items ?? []

  for (const it of list) {
    const code = (it.wp_code ?? '').trim()
    const name = (it.wp_name ?? '').trim()
    const line = it.line ?? 0

    if (!code) {
      errors.push({ line, wp_code: code, reason: '编号不能为空' })
      continue
    }
    if (!name) {
      errors.push({ line, wp_code: code, reason: '名称不能为空' })
      continue
    }
    if (!WP_CODE_RE.test(code)) {
      errors.push({
        line,
        wp_code: code,
        reason: '编号只能含字母/数字/中划线/下划线/点，且以字母或数字开头（≤32 字符）',
      })
      continue
    }
    const key = normalizeWpCode(code)
    if (seen.has(key)) {
      errors.push({ line, wp_code: code, reason: '清单内编号重复' })
      continue
    }
    if (existing.has(code)) {
      errors.push({ line, wp_code: code, reason: '该项目下编号已存在' })
      continue
    }
    seen.add(key)
    valid.push({
      wp_code: code,
      wp_name: name,
      audit_cycle: (it.audit_cycle ?? '').trim() || undefined,
      line,
    })
  }
  // 🔴 超限如实上报、**不截断** valid（截断 = 用户以为整批都提交了）
  return { valid, errors, overflow: list.length > MAX_BATCH_ITEMS }
}

/** 预览行状态（与后端 preview 端点的 status 取值域一致） */
export type PreviewStatus = 'ok' | 'duplicate_input' | 'duplicate_db' | 'invalid'

export interface PreviewRow {
  wp_code: string
  wp_name: string
  audit_cycle?: string | null
  status: PreviewStatus
  reason?: string | null
}

/**
 * 预览行 → 是否允许提交创建。
 *
 * 🔴 有 `invalid` 时**禁止创建**（门控前置为 disabled，不能点了才提示 —— 平台铁律）。
 * `duplicate_db` / `duplicate_input` 不阻断：它们在创建时被跳过，属正常幂等语义。
 */
export function canSubmitPreview(rows: PreviewRow[]): boolean {
  if (!Array.isArray(rows) || rows.length === 0) return false
  if (rows.some((r) => r.status === 'invalid')) return false
  return rows.some((r) => r.status === 'ok')
}

/** 不可提交的原因（供 tooltip 展示，禁只 disable 不说明） */
export function submitBlockedReason(rows: PreviewRow[]): string {
  if (!Array.isArray(rows) || rows.length === 0) return '请先粘贴或上传清单并预览'
  const bad = rows.filter((r) => r.status === 'invalid').length
  if (bad > 0) return `有 ${bad} 行存在错误，请先修正后再创建`
  if (!rows.some((r) => r.status === 'ok')) return '清单中没有可创建的新编号（全部已存在或重复）'
  return ''
}
