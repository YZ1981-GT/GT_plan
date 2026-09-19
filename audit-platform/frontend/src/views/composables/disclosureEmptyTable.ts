/**
 * disclosureEmptyTable — 附注空表判定（纯函数）
 *
 * 🔴 与后端 `backend/app/services/note_empty_table_detector.py` **同口径**：
 * 两侧用同一组用例互相镜像（`disclosureEmptyTable.spec.ts` ↔
 * `test_note_empty_table_detector.py`），任一侧改判定规则必须同步另一侧。
 *
 * 输入契约 = 投影后的表（`note_sub_table_projector.project_sub_tables` 输出）：
 *   rows    = [{ label, values: [...], is_total }]
 *   columns = ColumnDef[]（含标签列；values[j] 对应去掉标签列后的第 j 个）
 *
 * 判定规则见后端 docstring；要点：
 * - 行标签**不参与**判断（模板骨架恒有标签，否则永不为空）
 * - 合计行 / 段标题行 / 假表头行不参与判断
 * - 数值列（format ∈ amount|percent|number）：null / '' / 0 视为空
 * - 其余按文本：trim 后为空视为空
 *
 * Spec: .kiro/specs/disclosure-note-follow-actual-content/ R4.1 / Task 1.2
 */

/** 视为「数值列」的 format 值 */
export const AMOUNT_FORMATS: ReadonlySet<string> = new Set(['amount', 'percent', 'number'])

/**
 * 不参与空表判定的行类型（派生行 / 结构行 / 可扩位行）
 *
 * 🔴 必须与后端 `note_empty_table_detector.SKIP_ROW_TYPES` 逐项一致
 * （守卫 `test_note_expandable_rows.py` 读本文件源码交叉锁死）。
 * `expandable` = 源模板留的可扩位（`……` / `可无限量添加行`），零可见内容。
 * spec: note-template-columns-and-legacy-snapshot-closure Property 33
 */
export const SKIP_ROW_TYPES: ReadonlySet<string> = new Set([
  'total',
  'subtotal',
  'section',
  'header_label',
  'expandable',
])

/** 数值零容差：附注金额保留 2 位小数，绝对值小于半分即视为零 */
const ZERO_EPS = 0.005

export interface EmptyTableColumnDef {
  key?: string
  label?: string
  is_label?: boolean
  format?: string
  [k: string]: unknown
}

export interface EmptyTableRow {
  label?: unknown
  values?: unknown
  is_total?: unknown
  row_type?: unknown
  [k: string]: unknown
}

function isLabelDef(d: EmptyTableColumnDef): boolean {
  return Boolean(d && d.is_label)
}

/** 与投影器同规则取「非标签列」：优先 is_label，否则剔除第一列 */
function valueDefs(columns?: EmptyTableColumnDef[] | null): EmptyTableColumnDef[] {
  const defs = (columns ?? []).filter((d): d is EmptyTableColumnDef => !!d && typeof d === 'object')
  if (defs.length === 0) return []
  if (defs.some(isLabelDef)) return defs.filter((d) => !isLabelDef(d))
  return defs.slice(1)
}

function isAmountCol(d: EmptyTableColumnDef): boolean {
  return AMOUNT_FORMATS.has(String(d.format ?? ''))
}

function skipRow(row: EmptyTableRow): boolean {
  if (row.is_total) return true
  return SKIP_ROW_TYPES.has(String(row.row_type ?? ''))
}

function amountIsBlank(v: unknown): boolean {
  if (v === null || v === undefined) return true
  if (typeof v === 'boolean') return !v
  if (typeof v === 'number') return !Number.isFinite(v) ? false : Math.abs(v) < ZERO_EPS
  const s = String(v).trim()
  if (!s) return true
  // 允许千分符 / 全角逗号 / 括号负数
  let cleaned = s.replace(/[,，\s]/g, '')
  if (cleaned.startsWith('(') && cleaned.endsWith(')')) {
    cleaned = `-${cleaned.slice(1, -1)}`
  }
  const n = Number(cleaned)
  // 数值列里出现非数值文本（如「不适用」）→ 视为有内容
  if (!Number.isFinite(n)) return false
  return Math.abs(n) < ZERO_EPS
}

function textIsBlank(v: unknown): boolean {
  if (v === null || v === undefined) return true
  if (typeof v === 'boolean') return !v
  // 文本列里出现数值：0 也算填了内容
  if (typeof v === 'number') return false
  return !String(v).trim()
}

/**
 * 该表本期是否无业务内容。
 *
 * @param rows 投影后的行列表
 * @param columns 列定义（含标签列）；缺省时全部按文本列判定
 */
export function isEmptyTable(
  rows: unknown,
  columns?: EmptyTableColumnDef[] | null,
): boolean {
  if (!Array.isArray(rows) || rows.length === 0) return true

  const vdefs = valueDefs(columns)

  for (const raw of rows) {
    if (!raw || typeof raw !== 'object') continue
    const row = raw as EmptyTableRow
    if (skipRow(row)) continue
    const values = row.values
    if (!Array.isArray(values)) continue
    for (let j = 0; j < values.length; j++) {
      const col = j < vdefs.length ? vdefs[j] : null
      const blank =
        col && isAmountCol(col) ? amountIsBlank(values[j]) : textIsBlank(values[j])
      if (!blank) return false
    }
  }
  return true
}

export interface EmptyTableLike {
  name?: unknown
  rows?: unknown
  columns?: EmptyTableColumnDef[] | null
}

/** 批量：从投影后的 `_tables[]` 挑出空表名（保持原顺序） */
export function emptyTableNames(tables: unknown): string[] {
  if (!Array.isArray(tables)) return []
  const out: string[] = []
  for (const t of tables) {
    if (!t || typeof t !== 'object') continue
    const tbl = t as EmptyTableLike
    if (isEmptyTable(tbl.rows, tbl.columns ?? null)) out.push(String(tbl.name ?? ''))
  }
  return out
}


/**
 * 互斥披露组判定（Requirement 4.5 / Property 9）：
 * 同一 `exclusive_group` 的表构成「或」关系（源模版用「或：」表达），
 * 只要组内有一张非空，其余空表不触发「未完成」提示。
 *
 * @param tables 投影后的表列表（含 `exclusive_group` 字段）
 * @param emptyNames 空表名集合（`emptyTableNames` 输出）
 * @returns 被互斥组豁免的空表名集合（这些表不应报「未完成」）
 */
export function exclusiveGroupExemptions(
  tables: readonly { name?: unknown; exclusive_group?: unknown }[],
  emptyNames: ReadonlySet<string> | readonly string[],
): Set<string> {
  const emptySet = emptyNames instanceof Set ? emptyNames : new Set(emptyNames)
  const exempted = new Set<string>()

  // 按 exclusive_group 分组
  const groups = new Map<string, string[]>()
  for (const t of tables) {
    const group = String(t.exclusive_group ?? '').trim()
    if (!group) continue
    const name = String(t.name ?? '').trim()
    if (!name) continue
    const arr = groups.get(group) ?? []
    arr.push(name)
    groups.set(group, arr)
  }

  // 组内有非空表 → 其余空表被豁免
  for (const [, members] of groups) {
    const hasNonEmpty = members.some(n => !emptySet.has(n))
    if (hasNonEmpty) {
      for (const n of members) {
        if (emptySet.has(n)) exempted.add(n)
      }
    }
  }

  return exempted
}
