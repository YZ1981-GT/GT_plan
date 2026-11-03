/**
 * 凭证身份（前端侧）—— 与后端 `backend/app/services/voucher_identity.py` 同一口径
 * （spec voucher-identity-writeback-and-audit-phase 需求 1，ADR-VK-01~04）。
 *
 * - 凭证键 = (年度, 主体编码, 凭证日期, 凭证字, 凭证号)；规范串是紧凑 JSON 数组，年度写成字符串，凭证字为空按空串。
 * - 借贷栏按栏位判定：只有借方栏非零为 D，只有贷方栏非零为 C，其余为 X（借贷双填或都为零）。
 *   不按正负号：红字借方仍记在借方栏，仍是 D。
 * - 分录指纹 = 凭证键五元素 + 科目 + 借贷栏 + 金额（两位小数、四舍五入远离零、带符号，零写 0.00）+ 同组序号。
 *
 * 前端只做格式化与比较：同组序号由后端分组编号后随数据下发，这里不编号。
 * 两边读同一份样例 `backend/tests/fixtures/voucher_identity_vectors.json`，输出逐字相同。
 */
import Decimal from 'decimal.js'

export type VoucherSide = 'D' | 'C' | 'X'
export type VoucherKeyParts = [
  year: string,
  companyCode: string,
  voucherDate: string,
  voucherType: string,
  voucherNo: string,
]

/**
 * 与 Python `str.strip()` 去掉的字符相同（`str.isspace()` 为真的字符）。
 * 不能用 `String.prototype.trim()`：它不去 \x1c-\x1f、\x85，却会去掉 BOM（\ufeff），两边会得出不同的键。
 */
const PY_SPACE = '\\t\\n\\v\\f\\r\\x1c-\\x1f \\x85\\xa0\\u1680\\u2000-\\u200a\\u2028\\u2029\\u202f\\u205f\\u3000'
const STRIP_RE = new RegExp(`^[${PY_SPACE}]+|[${PY_SPACE}]+$`, 'g')

export function normText(value: unknown): string {
  return value === null || value === undefined ? '' : String(value).replace(STRIP_RE, '')
}

export function normDate(value: unknown): string {
  if (value === null || value === undefined || value === '') return ''
  if (value instanceof Date) {
    const pad = (n: number) => String(n).padStart(2, '0')
    return `${value.getFullYear()}-${pad(value.getMonth() + 1)}-${pad(value.getDate())}`
  }
  return normText(value).slice(0, 10)
}

function toAmount(value: unknown): Decimal {
  if (value === null || value === undefined) return new Decimal(0)
  if (Decimal.isDecimal(value)) return value as Decimal
  const text = normText(value)
  if (text === '') return new Decimal(0)
  try {
    return new Decimal(text)
  } catch {
    throw new Error(`金额无法解析：${String(value)}`)
  }
}

/** 两位小数、四舍五入远离零、带符号；零一律写 0.00。舍入方式显式传入，不受全局 Decimal.set 影响。 */
export function amountString(value: unknown): string {
  const text = toAmount(value).toFixed(2, Decimal.ROUND_HALF_UP)
  return text === '-0.00' ? '0.00' : text
}

export function sideOf(debit: unknown, credit: unknown): VoucherSide {
  const d = toAmount(debit)
  const c = toAmount(credit)
  if (!d.isZero() && c.isZero()) return 'D'
  if (!c.isZero() && d.isZero()) return 'C'
  return 'X'
}

/** 分录在其借贷栏上的带符号金额；不明（X）时取非零那栏，都非零取借方。 */
export function signedAmount(debit: unknown, credit: unknown, side: VoucherSide = sideOf(debit, credit)): Decimal {
  const d = toAmount(debit)
  const c = toAmount(credit)
  if (side === 'D') return d
  if (side === 'C') return c
  return d.isZero() ? c : d
}

type Row = Record<string, unknown>

/** 行上取字段：后端返回下划线命名，前端行结构多为驼峰，两种都认。 */
function pick(row: Row, snake: string, camel: string): unknown {
  const v = row[snake]
  return v === null || v === undefined ? row[camel] : v
}

/** 行上没有年度时用参数补（与后端 `VoucherKey.from_row(row, year=...)` 相同）。 */
export function voucherKeyParts(row: Row, year?: unknown): VoucherKeyParts {
  const rowYear = row.year
  return [
    normText(rowYear === null || rowYear === undefined || rowYear === '' ? year : rowYear),
    normText(pick(row, 'company_code', 'companyCode')),
    normDate(pick(row, 'voucher_date', 'voucherDate')),
    normText(pick(row, 'voucher_type', 'voucherType')),
    normText(pick(row, 'voucher_no', 'voucherNo')),
  ]
}

export function voucherKeyString(row: Row, year?: unknown): string {
  return JSON.stringify(voucherKeyParts(row, year))
}

/** 分录行 → 凭证键、科目、借贷栏、金额串（即分录指纹去掉同组序号的部分）。 */
export function describeLine(row: Row, year?: unknown) {
  const debit = pick(row, 'debit_amount', 'debitAmount')
  const credit = pick(row, 'credit_amount', 'creditAmount')
  const side = sideOf(debit, credit)
  return {
    vk: voucherKeyParts(row, year),
    accountCode: normText(pick(row, 'account_code', 'accountCode')),
    side,
    amount: amountString(signedAmount(debit, credit, side)),
  }
}

export function lineFingerprint(
  vk: VoucherKeyParts | string,
  accountCode: unknown,
  side: VoucherSide,
  amount: unknown,
  occ: number,
): string {
  const parts = typeof vk === 'string' ? (JSON.parse(vk) as VoucherKeyParts) : vk
  return JSON.stringify([...parts, normText(accountCode), side, amountString(amount), Math.trunc(occ)])
}

/** 凭证穿透 409 VOUCHER_KEY_AMBIGUOUS 的候选（后端 `voucher_identity.single_voucher_lines`）。 */
export interface VoucherKeyCandidate {
  voucher_key: string
  company_code: string
  voucher_date: string
  voucher_type: string
  voucher_no: string
  line_count: number
  debit_total: string
  summary: string
}

export interface VoucherKeyAmbiguity {
  message: string
  candidates: VoucherKeyCandidate[]
  /** 候选超过后端上限（50 张）时为 true，只列了前 50 张 */
  truncated: boolean
}

/**
 * 从请求错误里取凭证键歧义：只给凭证号（或日期 + 号）却命中多张凭证时，后端回 409 + 候选，不合并分录。
 * 业务 HTTPException 的详情在信封的 `message` 里，http 拦截器会补成 `detail`，两处都认；不是这类错误返回 null。
 */
export function voucherKeyAmbiguityOf(err: unknown): VoucherKeyAmbiguity | null {
  const res = (err as { response?: { status?: number; data?: Record<string, unknown> } } | null)?.response
  if (res?.status !== 409) return null
  const body = (res.data?.detail ?? res.data?.message) as Record<string, unknown> | undefined
  if (!body || typeof body !== 'object' || body.error_code !== 'VOUCHER_KEY_AMBIGUOUS') return null
  return {
    message: String(body.message ?? ''),
    candidates: Array.isArray(body.candidates) ? (body.candidates as VoucherKeyCandidate[]) : [],
    truncated: body.truncated === true,
  }
}

/** 界面上的凭证称呼：有凭证字写「FY-0003」，凭证字为空或未知写号本身。 */
export function voucherLabel(voucherType: unknown, voucherNo: unknown): string {
  const t = normText(voucherType)
  const n = normText(voucherNo)
  return t ? `${t}-${n}` : n
}

/**
 * 抽凭 / 截止测试结果里「已抽排除」的两种需要告诉用户的情形（后端 stats，见 voucher_sampling_exclusion）：
 * - `legacy_exclusion`：有只记了凭证号的旧回填记录，它按凭证号整张排除，会连带同号的其他凭证；
 * - `unresolved_excluded_lines`：已抽分录在当前账套里找不到（账套重导后分录改了或删了），没能排除。
 */
export function exclusionCaveats(stats: Record<string, unknown> | null | undefined): string[] {
  const out: string[] = []
  if (stats?.legacy_exclusion === true) {
    out.push('本底稿有旧版抽凭记录只记了凭证号，排除已抽凭证时按凭证号整张排除，可能连带排除同号的其他凭证')
  }
  const unresolved = Number(stats?.unresolved_excluded_lines ?? 0)
  if (unresolved > 0) {
    out.push(`有 ${unresolved} 笔已抽分录在当前账套里找不到（账套重导后分录已改或已删），本次没有排除`)
  }
  return out
}
