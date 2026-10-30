/**
 * noteTotalTerms — 附注表格合计构成（spec note-pull-header-formula-closure R5）
 *
 * 与后端 `backend/app/services/note_total_terms.py` 逐条同一判定（按模板逐表的 golden
 * `backend/data/note_total_terms_golden.json` 交叉锁死，任一侧改判定另一侧必红）：合计 / 小计由哪些行加减而来，
 * 只在判得准时给出；判不准的回原因，调用方不算、不猜。
 *
 * 原先前端三处都是整表求和：单体附注改单元格时把第一个合计行写成「全部非合计行之和」（「其中：境外款项」、
 * 「减：坏账准备」、别的分段都加进去，明细全空时写 0）；结构编辑后每个合计行都等于全表之和；合并附注编辑时合计
 * 只加到上一个合计 / 小计为止（「小计 / 减：坏账准备 / 合计」的合计 = 坏账准备）。
 *
 * 只加金额列（表头叶子判为比例 / 说明的不加，规则 = 标题行库 `ratio_pattern` / `text_pattern`）；手工 / 锁定格不动；
 * 构成里的格全空不写（不写 0，免得盖掉公式推送按审定数写入的合计）。
 */
import Decimal from 'decimal.js'
import { noteColumnPaths } from './noteColumnTree'

export type NoteRowKind = 'skip' | 'total' | 'subtotal' | 'marker' | 'sub' | 'minus' | 'plus' | 'data'
/** [行号, 符号] */
export type TotalTerm = [number, number]
export interface TotalTermsResult {
  plans: Map<number, TotalTerm[]>
  reasons: Map<number, string>
}

const SKIP_ROW_TYPES = new Set(['header_label', 'dynamic_anchor', 'dynamic_marker_end', 'expandable', 'header'])
const PLACEHOLDER_RE = /^[.…·]+$/
const MARKER_RE = /^其中[:：]?$/
const HEADING_RE = /^(?:[一二三四五六七八九十]+、|[（(][一二三四五六七八九十]+[）)])/
const PLAIN_SUBTOTAL_RE = /^小计[:：]?$/
const NO_DETAIL = '没有可合计的明细行'
const SUB_DETAIL = '表里有「其中：…」明细行，分不出明细到哪一行为止'
const MINUS_PLUS = '减项 / 加项不在小计之后'
const SEGMENT_HEADING = '合计的范围跨了几个分段标题（「一、」「（二）」），合计范围无法自动判定'

/** 标题行库 `ratio_pattern` / `text_pattern`（`backend/data/note_table_header_vocabulary.json`，golden 逐字对照） */
export const RATIO_PATTERN = '比例|比率|率\\(|率$|%'
export const TEXT_PATTERN =
  '性质|原因|方式|程序|^是否|款项是否|依据|理由|日期|期限|备注|说明|到期日|区间|条件|标准|方法|进度|来源|时间|安排|类型|情况$|地$|分类$|^代码$'
const RATIO_RE = new RegExp(RATIO_PATTERN)
const TEXT_RE = new RegExp(TEXT_PATTERN)

function isRecord(value: unknown): value is Record<string, any> {
  return !!value && typeof value === 'object' && !Array.isArray(value)
}

function label(row: unknown): string {
  return isRecord(row) ? String(row.label || '').replace(/\s+/g, '') : ''
}

function range(from: number, to: number): number[] {
  return Array.from({ length: Math.max(0, to - from) }, (_v, k) => from + k)
}

/** 只有行名时的行类型：以「小计」结尾 = subtotal（先判），「合计」「总计」= total（与后端 `label_row_type` 同口径）。 */
export function labelRowType(text: unknown): 'total' | 'subtotal' | 'data' {
  const key = String(text || '').replace(/\s+/g, '').replace(/[:：]+$/, '')
  if (key.endsWith('小计')) return 'subtotal'
  if (key === '合计' || key === '总计') return 'total'
  return 'data'
}

export function rowKind(row: unknown): NoteRowKind {
  if (!isRecord(row)) return 'skip'
  const l = label(row)
  if (SKIP_ROW_TYPES.has(row.row_type) || (l && PLACEHOLDER_RE.test(l))) return 'skip'
  if (row.is_total === true || row.row_type === 'total' || row.row_type === 'subtotal') {
    return row.row_type === 'subtotal' || l.includes('小计') ? 'subtotal' : 'total'
  }
  if (MARKER_RE.test(l)) return 'marker'
  if (l.startsWith('其中')) return 'sub'
  if (l.startsWith('减:') || l.startsWith('减：')) return 'minus'
  if (l.startsWith('加:') || l.startsWith('加：')) return 'plus'
  return 'data'
}

/** 合计 / 小计行（删行、加行、只读渲染用）。 */
export function isTotalRow(row: unknown): boolean {
  const kind = rowKind(row)
  return kind === 'total' || kind === 'subtotal'
}

function topRows(kinds: NoteRowKind[], idxs: number[]): [number[] | null, string | null] {
  if (idxs.some((i) => kinds[i] === 'sub')) return [null, SUB_DETAIL]
  if (idxs.some((i) => kinds[i] === 'minus' || kinds[i] === 'plus')) return [null, MINUS_PLUS]
  const seq = idxs.filter((i) => kinds[i] !== 'skip')
  const markers = seq.filter((i) => kinds[i] === 'marker')
  if (!markers.length) {
    const data = seq.filter((i) => kinds[i] === 'data')
    return data.length ? [data, null] : [null, NO_DETAIL]
  }
  const top = seq.filter((i) => i < markers[0] && kinds[i] === 'data')
  for (const m of markers) {
    const pos = seq.indexOf(m)
    const prev = pos ? seq[pos - 1] : null
    if (prev === null || kinds[prev] !== 'data') return [null, '「其中：」上一行不是明细行']
    if (!top.includes(prev)) top.push(prev)
  }
  return top.length ? [[...top].sort((a, b) => a - b), null] : [null, NO_DETAIL]
}

function headingIssue(rows: readonly unknown[], kinds: NoteRowKind[], idxs: number[]): string | null {
  const seq = idxs.filter((i) => kinds[i] !== 'skip')
  const heads = seq.filter((i) => HEADING_RE.test(label(rows[i])))
  if (!heads.length || (heads.length === 1 && heads[0] === seq[0])) return null
  return '小计的范围跨了几个分段标题（「一、」「（二）」），合计范围无法自动判定'
}

/** 标题式 = 第一行就是小计、下面有明细、没有减项 / 加项（有一组删空了也还是标题式）；「小计 / 减：X / 合计」不是。 */
function subtotalGroups(kinds: NoteRowKind[], subs: number[], end: number): [Array<[number, number[]]>, boolean] {
  const first = kinds.findIndex((k) => k !== 'skip')
  const bounds = [...subs.slice(1), end]
  const below: Array<[number, number[]]> = subs.map((s, k) => [s, range(s + 1, bounds[k])])
  const under = below.flatMap(([, g]) => g.map((i) => kinds[i]))
  const hasDetail = under.some((k) => k === 'data' || k === 'marker' || k === 'sub')
  if (first === subs[0] && hasDetail && !under.some((k) => k === 'minus' || k === 'plus')) {
    return [below, true]
  }
  let prev = -1
  const above: Array<[number, number[]]> = subs.map((s) => {
    const g = range(prev + 1, s)
    prev = s
    return [s, g]
  })
  return [above, false]
}

/**
 * 段首合计（spec note-pull-followup-closure R7，与后端 `_segment_head_terms` 同一判定）：每个合计都是分段标题式
 * （「一、账面原值合计」）、表的第一行就是合计 ⇒ 合计 = 它下面到下一个合计之前的本段明细；段内「其中：X」只许是本段
 * 第一行（列举本段构成），其余位置的「其中」/ 标记行 / 减项 / 加项 / 段内分段标题 ⇒ 该合计判不准。不是这种形态 ⇒ null。
 */
function segmentHeadTerms(rows: readonly unknown[], kinds: NoteRowKind[], totals: number[]): TotalTermsResult | null {
  const first = kinds.findIndex((k) => k !== 'skip')
  if (first !== totals[0] || totals.some((t) => kinds[t] !== 'total' || !HEADING_RE.test(label(rows[t])))) return null
  const plans = new Map<number, TotalTerm[]>()
  const reasons = new Map<number, string>()
  const ends = [...totals.slice(1), rows.length]
  totals.forEach((t, k) => {
    const seq = range(t + 1, ends[k]).filter((i) => kinds[i] !== 'skip')
    if (seq.some((i) => kinds[i] === 'marker') || seq.slice(1).some((i) => kinds[i] === 'sub')) {
      reasons.set(t, SUB_DETAIL)
    } else if (seq.some((i) => kinds[i] === 'minus' || kinds[i] === 'plus')) {
      reasons.set(t, MINUS_PLUS)
    } else if (seq.some((i) => HEADING_RE.test(label(rows[i])))) {
      reasons.set(t, SEGMENT_HEADING)
    } else if (!seq.length) {
      reasons.set(t, NO_DETAIL)
    } else {
      plans.set(t, seq.map((i): TotalTerm => [i, 1]))
    }
  })
  return { plans, reasons }
}

/** 合计 / 小计行 → 参与合计的 [行号, 符号]；判不准的合计行 → 原因（不算、不回填）。 */
export function totalTerms(rows: readonly unknown[]): TotalTermsResult {
  const kinds = rows.map(rowKind)
  const totals = kinds.flatMap((k, i) => (k === 'total' || k === 'subtotal' ? [i] : []))
  const plans = new Map<number, TotalTerm[]>()
  const reasons = new Map<number, string>()
  if (!totals.length) return { plans, reasons }
  const head = segmentHeadTerms(rows, kinds, totals)
  if (head) return head
  if (totals.length === 1) {
    const t = totals[0]
    const idxs = range(0, t)
    let [top, why] = topRows(kinds, idxs)
    if (top && kinds[t] === 'subtotal') {
      why = headingIssue(rows, kinds, idxs)
      if (why) top = null
    }
    if (top) plans.set(t, top.map((i): TotalTerm => [i, 1]))
    else reasons.set(t, why || NO_DETAIL)
    return { plans, reasons }
  }
  const subs = totals.filter((i) => kinds[i] === 'subtotal')
  const tots = totals.filter((i) => kinds[i] === 'total')
  let whole: string | null = null
  if (tots.length > 1 || (tots.length && tots[0] !== totals[totals.length - 1])) {
    whole = '表里有多个合计行（或合计行之后还有小计），合计范围无法自动判定'
  } else {
    const plain = subs.map((s) => PLAIN_SUBTOTAL_RE.test(label(rows[s])))
    if (plain.some(Boolean) && !plain.every(Boolean)) whole = '分项小计与小计并存（嵌套小计），合计范围无法自动判定'
  }
  let groups: Array<[number, number[]]> = []
  let heading = false
  if (whole === null) {
    ;[groups, heading] = subtotalGroups(kinds, subs, tots.length ? tots[0] : rows.length)
    if (!heading) {
      for (const [, g] of groups) {
        whole = headingIssue(rows, kinds, g)
        if (whole) break
      }
    }
  }
  if (whole !== null) {
    for (const t of totals) reasons.set(t, whole)
    return { plans: new Map(), reasons }
  }
  for (const [s, g] of groups) {
    const [top, why] = topRows(kinds, g)
    if (top) plans.set(s, top.map((i): TotalTerm => [i, 1]))
    else reasons.set(s, why || NO_DETAIL)
  }
  if (tots.length) {
    const t = tots[0]
    const between = heading ? [] : range(subs[subs.length - 1] + 1, t).filter((i) => kinds[i] !== 'skip')
    if (between.some((i) => !['data', 'minus', 'plus'].includes(kinds[i]))) {
      reasons.set(t, '最后一个小计与合计之间有「其中」行，合计范围无法自动判定')
    } else {
      plans.set(t, [
        ...subs.map((s): TotalTerm => [s, 1]),
        ...between.map((i): TotalTerm => [i, kinds[i] === 'minus' ? -1 : 1]),
      ])
    }
  }
  return { plans, reasons }
}

/** 回填顺序：先小计、再合计（合计的构成里有小计）。 */
export function totalOrder(rows: readonly unknown[], plans: Map<number, TotalTerm[]>): number[] {
  const rank = (r: number) => (rowKind(rows[r]) === 'subtotal' ? 0 : 1)
  return [...plans.keys()].sort((a, b) => rank(a) - rank(b) || a - b)
}

const BLANK_CELLS = new Set(['', '-', '—', '－'])

/** 单元格 → 数（与后端 `to_decimal` 同口径）：空 / 占位符 / 非数值 → null。 */
export function cellDecimal(value: unknown): Decimal | null {
  if (value === null || value === undefined || typeof value === 'boolean') return null
  if (typeof value === 'number') return Number.isFinite(value) ? new Decimal(String(value)) : null
  if (isRecord(value)) return cellDecimal('value' in value ? value.value : value.manual_value)
  const s = String(value).trim().replace(/[,，]/g, '')
  if (BLANK_CELLS.has(s)) return null
  try {
    const d = new Decimal(s)
    return d.isFinite() ? d : null
  } catch {
    return null
  }
}

/** 按合计构成求和：构成里的格全空 ⇒ null（不写 0）。 */
export function sumTerms(terms: readonly TotalTerm[], read: (row: number) => Decimal | null): Decimal | null {
  let total = new Decimal(0)
  let seen = false
  for (const [r, sign] of terms) {
    const v = read(r)
    if (v === null) continue
    total = sign > 0 ? total.plus(v) : total.minus(v)
    seen = true
  }
  return seen ? total : null
}

function normHeader(text: string): string {
  return text
    .replace(/<br\s*\/?>/gi, '')
    .replace(/\s+/g, '')
    .replace(/（/g, '(').replace(/）/g, ')').replace(/％/g, '%')
    .replace(/：/g, ':').replace(/，/g, ',').replace(/；/g, ';')
    .replace(/[.。．]+$/, '')
}

/** 金额列（`values` 下标）：表头叶子判为比例 / 说明的列不加总（同后端 `amount_columns`）。 */
export function amountColumns(table: any): number[] {
  const out: number[] = []
  noteColumnPaths(table).forEach((path, c) => {
    if (c === 0) return
    const parts = path.map((p) => normHeader(String(p ?? ''))).filter(Boolean)
    const leaf = parts[parts.length - 1] ?? ''
    if (leaf && (RATIO_RE.test(leaf) || TEXT_RE.test(leaf))) return
    out.push(c - 1)
  })
  return out
}

/** 单体附注单元格是不是自动格（手工 / 锁定格不被合计回填覆盖）。 */
export function isAutoCell(row: any, col: number): boolean {
  const cell = Array.isArray(row?.values) ? row.values[col] : undefined
  if (isRecord(cell)) return (cell.mode || 'auto') === 'auto'
  const modes = isRecord(row?._cell_modes) ? row._cell_modes : {}
  const mode = modes[String(col)]
  return !mode || mode === 'auto'
}

function valuesWidth(rows: readonly any[]): number {
  return Math.max(0, ...rows.map((r) => (Array.isArray(r?.values) ? r.values.length : 0)))
}

/** 单体附注表的金额列（没有表头的旧表按 `values` 全部列）。 */
function noteAmountColumns(table: any, rows: readonly any[]): number[] {
  return Array.isArray(table?.headers) && table.headers.length ? amountColumns(table) : range(0, valuesWidth(rows))
}

export interface TotalUpdate {
  row: number
  value: number
}

/**
 * 单体附注一列（`values` 下标）合计 / 小计该写的新值（先小计后合计，合计用新小计）；不是金额列、判不准、手工格、
 * 构成全空、值没变的都不在结果里。调用方逐格写回（编辑器经投影写回源表）。
 */
export function columnTotalUpdates(table: any, col: number): TotalUpdate[] {
  const rows: any[] = Array.isArray(table?.rows) ? table.rows : []
  if (!rows.length || !noteAmountColumns(table, rows).includes(col)) return []
  const { plans } = totalTerms(rows)
  const local = new Map<number, Decimal>()
  const read = (i: number) => (local.has(i) ? (local.get(i) as Decimal) : cellDecimal(rows[i]?.values?.[col]))
  const out: TotalUpdate[] = []
  for (const r of totalOrder(rows, plans)) {
    if (!isAutoCell(rows[r], col)) continue
    const total = sumTerms(plans.get(r) as TotalTerm[], read)
    if (total === null) continue
    local.set(r, total)
    const old = cellDecimal(rows[r]?.values?.[col])
    if (old !== null && old.minus(total).abs().lessThan('0.005')) continue
    out.push({ row: r, value: total.toNumber() })
  }
  return out
}

/** 单体附注一张表按合计构成回填全部合计 / 小计行（结构编辑后调用）→ 改了几格。 */
export function recalcNoteTableTotals(table: any): number {
  const rows: any[] = Array.isArray(table?.rows) ? table.rows : []
  let changed = 0
  for (const col of noteAmountColumns(table, rows)) {
    for (const { row, value } of columnTotalUpdates(table, col)) {
      rows[row].values[col] = value
      changed++
    }
  }
  return changed
}

/** 合计格与合计构成算出的数不一致（判不准 / 构成全空 / 不是金额列 ⇒ 不标）。 */
export function totalMismatch(table: any, rowIndex: number, col: number): boolean {
  const rows: any[] = Array.isArray(table?.rows) ? table.rows : []
  if (rowIndex < 0 || rowIndex >= rows.length || !noteAmountColumns(table, rows).includes(col)) return false
  const plan = totalTerms(rows).plans.get(rowIndex)
  if (!plan) return false
  const expected = sumTerms(plan, (i) => cellDecimal(rows[i]?.values?.[col]))
  if (expected === null) return false
  const actual = cellDecimal(rows[rowIndex]?.values?.[col]) ?? new Decimal(0)
  return expected.minus(actual).abs().greaterThan('0.01')
}

/** 合并附注编辑行：列号 → 文本（`ConsolNoteTab` 的 NoteEditRow）。 */
export type ConsolEditRow = { [col: number]: string }

/**
 * 合并附注编辑行按合计构成回填合计 / 小计行 → 改了几格。`rowTypes` = 后端 `_row_types`（缺省按行名判）；`table` =
 * 表头（`headers` / `multi_header` / `_column_groups`，判金额列）；`isProtected(行, 列)` 为真的格（手工格）不动。
 * 两位小数（与后端拉数 / 汇总写法一致）。
 */
export function recalcConsolTotalRows(
  rows: ConsolEditRow[],
  rowTypes: readonly string[] | null | undefined,
  table: { headers?: unknown[]; multi_header?: unknown; _column_groups?: unknown } | null | undefined,
  isProtected: (row: number, col: number) => boolean = () => false,
): number {
  const shaped = rows.map((r, i) => ({
    label: String(r?.[0] ?? ''),
    row_type: rowTypes && i < rowTypes.length ? rowTypes[i] : labelRowType(r?.[0]),
  }))
  const { plans } = totalTerms(shaped)
  const width = Array.isArray(table?.headers) ? table.headers.length : 0
  if (!plans.size || width < 2) return 0
  let changed = 0
  for (const c of amountColumns(table).map((k) => k + 1)) {
    for (const r of totalOrder(shaped, plans)) {
      if (isProtected(r, c)) continue
      const total = sumTerms(plans.get(r) as TotalTerm[], (i) => cellDecimal(rows[i]?.[c]))
      if (total === null) continue
      const text = total.toFixed(2, Decimal.ROUND_HALF_UP)
      if (rows[r][c] === text) continue
      rows[r][c] = text
      changed++
    }
  }
  return changed
}
