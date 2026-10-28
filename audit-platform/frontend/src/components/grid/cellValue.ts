/**
 * 单元格值的显示格式与文本解析（spec excel-style-table-editing design §4）。
 *
 * 纯函数，不依赖 Vue / DOM：显示态文本、复制文本、粘贴 / 清空时把文本解析成目标格的值，
 * 全部走这里，保证「看到的」「复制出去的」「粘贴回来的」是同一套口径。
 */
import dayjs from 'dayjs'

export type CellEditorKind = 'text' | 'number' | 'select' | 'date' | 'toggle'

export type ParseResult<T = unknown> = { ok: true; value: T } | { ok: false; reason: string }

const ok = <T>(value: T): ParseResult<T> => ({ ok: true, value })
const fail = (reason: string): ParseResult<never> => ({ ok: false, reason })

function isBlank(v: unknown): boolean {
  return v === null || v === undefined || (typeof v === 'string' && v.trim() === '')
}

/** 全角数字 / 符号转半角，去掉不换行空格（从网页、Word 粘贴常见）。 */
export function normalizeWidth(text: string): string {
  return text
    .replace(/[\uFF01-\uFF5E]/g, (ch) => String.fromCharCode(ch.charCodeAt(0) - 0xFEE0))
    .replace(/\u3000|\u00A0/g, ' ')
    .replace(/\u2212/g, '-')
}

// ── 数字 ─────────────────────────────────────────────────────────────────────

/** 值本身的小数位（最多 10 位，去掉浮点尾差）。 */
function ownDecimals(n: number): number {
  if (!Number.isFinite(n) || Number.isInteger(n)) return 0
  // eslint-disable-next-line gt-audit/no-amount-toFixed -- 只数小数位（定显示位数用），不产出显示文本
  const s = n.toFixed(10).replace(/0+$/, '')
  const dot = s.indexOf('.')
  return dot < 0 ? 0 : s.length - dot - 1
}

/**
 * 数字显示：有 precision 按位数；没有按值本身的小数位。
 * 有小数或绝对值 ≥ 10000 时加千分位 —— 年度（2025）、笔数、序号这类 4 位整数不加，金额照加。
 */
export function formatNumberDisplay(value: unknown, precision?: number | null): string {
  if (isBlank(value)) return ''
  const n = typeof value === 'number' ? value : Number(value)
  if (!Number.isFinite(n)) return String(value)
  const decimals = precision != null && precision >= 0 ? Math.min(precision, 20) : ownDecimals(n)
  const grouping = decimals > 0 || Math.abs(n) >= 10000
  return n.toLocaleString('en-US', {
    minimumFractionDigits: decimals,
    maximumFractionDigits: decimals,
    useGrouping: grouping,
  })
}

/** 与 el-input-number 的 precision 舍入同口径（toFixed 有二进制误差，先放大再四舍五入）。 */
export function roundTo(n: number, precision: number): number {
  const factor = 10 ** precision
  return Math.round((n + Number.EPSILON * Math.sign(n)) * factor) / factor
}

export interface NumberParseOptions {
  precision?: number | null
  min?: number | null
  max?: number | null
}

/**
 * 文本 → 数字：去千分位、全角、空格；括号负数；末尾 % 去掉不换算（平台的百分比列存的是百分点）；
 * 「—」「-」视为空。空 → null。按 precision 舍入，min / max 夹紧。
 */
export function parseNumberText(text: string, opts: NumberParseOptions = {}): ParseResult<number | null> {
  let s = normalizeWidth(String(text ?? '')).trim()
  if (s === '' || s === '-' || s === '\u2014' || s === '\u2013' || s === '\u2014\u2014') return ok(null)
  let negative = false
  const paren = /^\((.*)\)$/.exec(s)
  if (paren) { negative = true; s = paren[1].trim() }
  s = s.replace(/[,\s]/g, '').replace(/^[¥￥$]/, '').replace(/[元%]$/, '')
  if (s.startsWith('-')) { negative = !negative; s = s.slice(1) }
  else if (s.startsWith('+')) s = s.slice(1)
  if (!/^(\d+\.?\d*|\.\d+)(e[+-]?\d+)?$/i.test(s)) return fail('不是数字')
  let n = Number(s)
  if (!Number.isFinite(n)) return fail('不是数字')
  if (negative) n = -n
  if (opts.precision != null && opts.precision >= 0) n = roundTo(n, opts.precision)
  if (opts.min != null && n < opts.min) n = opts.min
  if (opts.max != null && n > opts.max) n = opts.max
  return ok(n)
}

/** 从显示文本里取数（选区统计用）：千分位 / 括号负数 / 百分号；取不到返回 null。 */
export function parseLooseNumber(text: string): number | null {
  const cleaned = stripDecorations(String(text ?? ''))
  const m = /\(?-?[¥￥$]?\d[\d,]*(\.\d+)?\)?%?|\(?-?\.\d+\)?%?/.exec(normalizeWidth(cleaned))
  if (!m) return null
  const r = parseNumberText(m[0])
  return r.ok && typeof r.value === 'number' ? r.value : null
}

// ── 文本 ─────────────────────────────────────────────────────────────────────

export function formatTextDisplay(value: unknown, inputType?: string): string {
  if (isBlank(value)) return ''
  const s = String(value)
  return inputType === 'password' ? '•'.repeat(Math.min(s.length, 12)) : s
}

// ── 下拉 ─────────────────────────────────────────────────────────────────────

export interface SelectOptionLite {
  label: string
  value: unknown
}

function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (a == null || b == null) return false
  return typeof a !== 'object' && typeof b !== 'object' && String(a) === String(b)
}

export function formatSelectDisplay(value: unknown, options: SelectOptionLite[], multiple = false): string {
  const one = (v: unknown): string => {
    if (isBlank(v)) return ''
    const hit = options.find((o) => sameValue(o.value, v))
    return hit ? hit.label : String(v)
  }
  if (multiple || Array.isArray(value)) {
    const arr = Array.isArray(value) ? value : isBlank(value) ? [] : [value]
    return arr.map(one).filter((s) => s !== '').join('、')
  }
  return one(value)
}

export interface SelectParseOptions {
  multiple?: boolean
  allowCreate?: boolean
}

export function parseSelectText(text: string, options: SelectOptionLite[], opts: SelectParseOptions = {}): ParseResult {
  const matchOne = (raw: string): ParseResult => {
    const t = normalizeWidth(raw).trim()
    if (t === '') return ok(null)
    const byLabel = options.find((o) => o.label === t) ?? options.find((o) => o.label.trim() === t)
    if (byLabel) return ok(byLabel.value)
    const byValue = options.find((o) => o.value != null && String(o.value) === t)
    if (byValue) return ok(byValue.value)
    if (opts.allowCreate) return ok(t)
    return fail(`没有「${t}」这个选项`)
  }
  if (opts.multiple) {
    const parts = String(text ?? '').split(/[、,;，；\n]/).map((s) => s.trim()).filter(Boolean)
    const values: unknown[] = []
    for (const p of parts) {
      const r = matchOne(p)
      if (!r.ok) return r
      if (r.value != null) values.push(r.value)
    }
    return ok(values)
  }
  return matchOne(String(text ?? ''))
}

// ── 日期 ─────────────────────────────────────────────────────────────────────

export interface DateFormatOptions {
  type?: string
  format?: string
  valueFormat?: string
  rangeSeparator?: string
}

const DEFAULT_DISPLAY_FORMAT: Record<string, string> = {
  year: 'YYYY',
  month: 'YYYY-MM',
  date: 'YYYY-MM-DD',
  week: 'YYYY-MM-DD',
  datetime: 'YYYY-MM-DD HH:mm:ss',
  daterange: 'YYYY-MM-DD',
  monthrange: 'YYYY-MM',
  datetimerange: 'YYYY-MM-DD HH:mm:ss',
}

function toDate(v: unknown): Date | null {
  if (v instanceof Date) return Number.isNaN(v.getTime()) ? null : v
  if (typeof v === 'number') return Number.isFinite(v) ? new Date(v) : null
  if (typeof v === 'string' && v.trim() !== '') {
    const parsed = parseDateLoose(v)
    return parsed
  }
  return null
}

export function formatDateDisplay(value: unknown, opts: DateFormatOptions = {}): string {
  if (isBlank(value) || (Array.isArray(value) && value.length === 0)) return ''
  const type = opts.type || 'date'
  const fmt = opts.format || DEFAULT_DISPLAY_FORMAT[type] || 'YYYY-MM-DD'
  const one = (v: unknown): string => {
    if (isBlank(v)) return ''
    // 已经是按 value-format 存的字符串、且没有指定显示格式：原样显示，不经过解析（避免时区 / 格式漂移）
    if (typeof v === 'string' && !opts.format) return v
    const d = toDate(v)
    return d ? dayjs(d).format(fmt) : String(v)
  }
  if (Array.isArray(value)) {
    return value.map(one).join(` ${opts.rangeSeparator || '至'} `)
  }
  return one(value)
}

const EXCEL_EPOCH_MS = Date.UTC(1899, 11, 30)

/** 宽松解析：YYYY-M-D / YYYY/M/D / YYYY.M.D / YYYYMMDD / YYYY年M月D日 / YYYY-M / YYYY年M月 / Excel 序列号。 */
export function parseDateLoose(text: string): Date | null {
  const t = normalizeWidth(String(text ?? '')).trim()
  if (t === '') return null
  let m = /^(\d{4})[-/.年](\d{1,2})[-/.月](\d{1,2})日?(?:[ T](\d{1,2}):(\d{2})(?::(\d{2}))?)?$/.exec(t)
  if (m) return buildDate(+m[1], +m[2], +m[3], m[4] ? +m[4] : 0, m[5] ? +m[5] : 0, m[6] ? +m[6] : 0)
  m = /^(\d{4})(\d{2})(\d{2})$/.exec(t)
  if (m) return buildDate(+m[1], +m[2], +m[3])
  m = /^(\d{4})[-/.年](\d{1,2})月?$/.exec(t)
  if (m) return buildDate(+m[1], +m[2], 1)
  m = /^(\d{4})年?$/.exec(t)
  if (m) return buildDate(+m[1], 1, 1)
  if (/^\d{1,5}(\.\d+)?$/.test(t)) {
    const serial = Number(t)
    if (serial >= 1 && serial < 100000) {
      const d = new Date(EXCEL_EPOCH_MS + Math.floor(serial) * 86400000)
      return buildDate(d.getUTCFullYear(), d.getUTCMonth() + 1, d.getUTCDate())
    }
  }
  return null
}

function buildDate(y: number, mo: number, d: number, h = 0, mi = 0, s = 0): Date | null {
  if (mo < 1 || mo > 12 || d < 1 || d > 31 || h > 23 || mi > 59 || s > 59) return null
  const date = new Date(y, mo - 1, d, h, mi, s)
  if (date.getFullYear() !== y || date.getMonth() !== mo - 1 || date.getDate() !== d) return null
  return date
}

export function parseDateText(text: string, opts: DateFormatOptions = {}): ParseResult {
  const t = String(text ?? '').trim()
  const isRange = (opts.type || '').endsWith('range')
  if (t === '') return ok(isRange ? [] : null)
  const toModel = (d: Date): unknown => (opts.valueFormat ? dayjs(d).format(opts.valueFormat) : d)
  if (isRange) {
    const parts = t.split(/\s*(?:至|~|～|—|--|\s-\s)\s*/).filter(Boolean)
    if (parts.length !== 2) return fail('日期区间需写成「开始 至 结束」')
    const a = parseDateLoose(parts[0])
    const b = parseDateLoose(parts[1])
    if (!a || !b) return fail('不是日期')
    return ok([toModel(a), toModel(b)])
  }
  const d = parseDateLoose(t)
  return d ? ok(toModel(d)) : fail('不是日期')
}

// ── 勾选 / 开关 ───────────────────────────────────────────────────────────────

const TRUTHY = new Set(['1', 'true', 'yes', 'y', 'on', '是', '√', '✓', '✔', '勾选', '已勾选', '有', '适用'])
const FALSY = new Set(['0', 'false', 'no', 'n', 'off', '否', '×', '✗', '✘', '未勾选', '无', '不适用', ''])

export interface ToggleOptions {
  activeValue?: unknown
  inactiveValue?: unknown
}

export function parseToggleText(text: string, opts: ToggleOptions = {}): ParseResult {
  const t = normalizeWidth(String(text ?? '')).trim().toLowerCase()
  const on = opts.activeValue === undefined ? true : opts.activeValue
  const off = opts.inactiveValue === undefined ? false : opts.inactiveValue
  if (TRUTHY.has(t)) return ok(on)
  if (FALSY.has(t)) return ok(off)
  if (opts.activeValue !== undefined && t === String(opts.activeValue).toLowerCase()) return ok(on)
  if (opts.inactiveValue !== undefined && t === String(opts.inactiveValue).toLowerCase()) return ok(off)
  return fail('只能填 是 / 否')
}

export function formatToggleCopy(value: unknown, opts: ToggleOptions = {}): string {
  const on = opts.activeValue === undefined ? true : opts.activeValue
  return sameValue(value, on) ? '是' : '否'
}

// ── 剪贴板 ───────────────────────────────────────────────────────────────────

/** 去掉图标类字符（📊 ✏️ 🔒 等）与多余空白：复制只读格、取统计数时用。 */
export function stripDecorations(text: string): string {
  return String(text ?? '')
    .replace(/[\p{Extended_Pictographic}\uFE0F\u200D]/gu, '')
    .replace(/[ \t]+\n/g, '\n')
    .replace(/[ \t]{2,}/g, ' ')
    .trim()
}

/**
 * 解析制表符文本（Excel 复制出来的 text/plain）：行以换行分隔，列以 Tab 分隔；
 * 带换行 / Tab / 引号的格被双引号包住、内部引号写成两个。只丢最后一个空行，中间空行保留（对齐不错位）。
 */
export function parseTsv(text: string): string[][] {
  const src = String(text ?? '').replace(/\r\n?/g, '\n')
  if (src === '') return []
  const rows: string[][] = []
  let row: string[] = []
  let cell = ''
  let i = 0
  let atCellStart = true
  while (i < src.length) {
    const ch = src[i]
    if (atCellStart && ch === '"') {
      // 引号格：读到配对的结束引号
      let j = i + 1
      let buf = ''
      let closed = false
      while (j < src.length) {
        if (src[j] === '"') {
          if (src[j + 1] === '"') { buf += '"'; j += 2; continue }
          closed = true
          j++
          break
        }
        buf += src[j]
        j++
      }
      if (closed && (j >= src.length || src[j] === '\t' || src[j] === '\n')) {
        cell = buf
        i = j
        atCellStart = false
        continue
      }
      // 不是合法引号格：按普通字符处理
    }
    if (ch === '\t') { row.push(cell); cell = ''; atCellStart = true; i++; continue }
    if (ch === '\n') { row.push(cell); rows.push(row); row = []; cell = ''; atCellStart = true; i++; continue }
    cell += ch
    atCellStart = false
    i++
  }
  if (cell !== '' || row.length > 0 || !src.endsWith('\n')) {
    row.push(cell)
    rows.push(row)
  }
  return rows
}

/** 网页 / Excel 的 text/html 里第一张表 → 矩阵；按 rowspan / colspan 展开成规则矩阵（被覆盖的格为空）。 */
export function parseHtmlMatrix(html: string): string[][] | null {
  if (!html || !/<table[\s>]/i.test(html) || typeof DOMParser === 'undefined') return null
  const doc = new DOMParser().parseFromString(html, 'text/html')
  const table = doc.querySelector('table')
  if (!table) return null
  const out: string[][] = []
  const occupied: boolean[][] = []
  Array.from(table.querySelectorAll('tr')).forEach((tr, r) => {
    out[r] = out[r] || []
    occupied[r] = occupied[r] || []
    let c = 0
    for (const cell of Array.from(tr.querySelectorAll('td, th'))) {
      while (occupied[r][c]) c++
      const text = (cell as HTMLElement).innerText ?? cell.textContent ?? ''
      const rs = Math.max(1, Number(cell.getAttribute('rowspan')) || 1)
      const cs = Math.max(1, Number(cell.getAttribute('colspan')) || 1)
      for (let dr = 0; dr < rs; dr++) {
        out[r + dr] = out[r + dr] || []
        occupied[r + dr] = occupied[r + dr] || []
        for (let dc = 0; dc < cs; dc++) {
          occupied[r + dr][c + dc] = true
          out[r + dr][c + dc] = dr === 0 && dc === 0 ? String(text).replace(/\r\n?/g, '\n').trim() : ''
        }
      }
      c += cs
    }
  })
  const width = Math.max(0, ...out.map((row) => row.length))
  const matrix = out.map((row) => Array.from({ length: width }, (_, i) => row[i] ?? ''))
  return matrix.length ? matrix : null
}

/** 剪贴板 → 矩阵：优先 text/plain（Excel 的口径最准）；没有文本或文本不像表格而 HTML 是表格时用 HTML。 */
export function parseClipboardMatrix(text: string, html: string): string[][] {
  const plain = String(text ?? '')
  if (plain !== '' && (plain.includes('\t') || plain.includes('\n') || !/<table[\s>]/i.test(html || ''))) {
    return parseTsv(plain)
  }
  return parseHtmlMatrix(html) ?? parseTsv(plain)
}

function escapeHtml(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;')
}

function tsvCell(s: string): string {
  return /[\t\n"]/.test(s) ? `"${s.replace(/"/g, '""')}"` : s
}

/** 矩阵 → 剪贴板两种格式（与 Excel 互通）。 */
export function buildClipboardPayload(matrix: string[][]): { text: string; html: string } {
  const text = matrix.map((row) => row.map(tsvCell).join('\t')).join('\r\n')
  const body = matrix
    .map((row) => '<tr>' + row.map((c) => `<td>${escapeHtml(c).replace(/\n/g, '<br>')}</td>`).join('') + '</tr>')
    .join('')
  const html = `<table border="1" style="border-collapse:collapse">${body}</table>`
  return { text, html }
}
