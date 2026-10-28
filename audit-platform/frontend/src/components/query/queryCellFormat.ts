/**
 * queryCellFormat.ts — 查询结果单元格的显示格式（advanced-query-linkage-closure 任务 28 / 29）
 *
 * 弹窗与页面版共用一个实现。金额格式化按列类型判定（execute 响应 `meta.column_types`，由后端注册表的列定义给出），
 * 不再按字符串长度：原先超过 12 个字符的值原样输出，十亿以上带两位小数的金额（如 6473114514.96）不加千分位，
 * 与同一列里的 822,999,085.83 混排（B5 浏览器验收）。
 * - 有列类型（注册表 SQL 源）：`number` ⇒ 金额千分位两位小数；其余类型原样输出（文本列里的数字串不当金额）。
 * - 没有列类型（附注表格、合并工作底稿、底稿选区等内存源）：JSON 数字 ⇒ 金额；数字字符串只在不超过 12 位时按金额
 *   （避免把银行账号、信用代码这类长数字编码当金额）。
 * - 编码 / 序号 / 比率类列名一律原样（科目码、行次、凭证号、层级等）。
 */
import { fmtAmount } from '@/utils/formatters'

/** 列键 → 列类型（number / text / date / bool） */
export type ColumnTypes = Readonly<Record<string, string>>

/** 空值的显示 */
export const EMPTY_CELL = '—'

const CODE_LIKE_COL_RE = /(_code$|^code$|_no$|number$|_id$|section|cell_ref|indent|row_count|is_total|ratio|比例|编码|编号|账号|行次|序号)/i
const NUMERIC_TEXT_RE = /^-?\d+(\.\d+)?$/
/** 没有列类型时，数字字符串按金额的最大长度（更长的多半是编码） */
const UNTYPED_NUMERIC_TEXT_MAX = 12

/** 编码 / 标识 / 比率类列：不做金额格式化 */
export function isCodeLikeColumn(column?: string | null): boolean {
  return !!column && CODE_LIKE_COL_RE.test(column)
}

function finiteNumber(value: unknown): boolean {
  if (typeof value === 'number') return Number.isFinite(value)
  return typeof value === 'string' && NUMERIC_TEXT_RE.test(value.trim())
}

/** 该格是否按金额显示（右对齐、千分位、两位小数） */
export function isAmountCell(value: unknown, column?: string | null, columnTypes?: ColumnTypes | null): boolean {
  if (value === null || value === undefined || isCodeLikeColumn(column)) return false
  const dtype = column ? columnTypes?.[column] : undefined
  if (dtype !== undefined) return dtype === 'number' && finiteNumber(value)
  if (typeof value === 'number') return Number.isFinite(value)
  return typeof value === 'string' && value.trim().length <= UNTYPED_NUMERIC_TEXT_MAX && finiteNumber(value)
}

/** 结果格的显示文本 */
export function formatQueryCell(value: unknown, column?: string | null, columnTypes?: ColumnTypes | null): string {
  if (value === null || value === undefined) return EMPTY_CELL
  if (Array.isArray(value)) return value.join(', ')
  if (typeof value === 'boolean') return value ? '是' : '否'
  if (typeof value === 'object') return JSON.stringify(value)
  if (isAmountCell(value, column, columnTypes)) return fmtAmount(Number(value))
  return String(value)
}

/** 响应 `meta.column_types` → 列类型表（形状不对时为空表，回到按值判定） */
export function columnTypesOf(meta: unknown): ColumnTypes {
  const raw = meta && typeof meta === 'object' ? (meta as Record<string, unknown>).column_types : undefined
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return {}
  const out: Record<string, string> = {}
  for (const [key, value] of Object.entries(raw as Record<string, unknown>)) {
    if (typeof value === 'string') out[key] = value
  }
  return out
}
