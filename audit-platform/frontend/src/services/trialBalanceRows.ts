/**
 * 试算表行 —— 前端唯一取数入口（spec post-push-residual-defect-closure R1）
 *
 * 端点 `GET /api/projects/{id}/trial-balance`（`backend/app/routers/trial_balance.py::get_trial_balance`）。
 * 原先 84 处各自直连：37 处不带 year（端点必填 ⇒ 422 被吞成「待取数」），另有 20 多种读法读的是端点
 * 从不返回的字段（debit_amount / credit_amount / ending_balance / prior_* …）⇒ 带上年度也静默得 0。
 * 现在只许经本模块取数（守卫 `__tests__/trialBalanceRowsSingleEntry.spec.ts`），
 * `TrialBalanceRow` 与后端行键逐键一致（`backend/tests/test_trial_balance_row_contract.py`）。
 *
 * 口径（与后端一致）：
 * - 金额均为字符串、正数口径，借贷方向见 `direction`；
 * - 损益类（5xxx / 6xxx）`unadjusted_amount` 是**单边发生额**（收入取贷方、费用取借方）。含年末结转时
 *   余额表借贷两侧恒相等，「贷 − 借」是结构性 0，不能当本期净发生额 —— 用 `tbOccurrence`；
 * - 同一科目族的金额 = 前缀下各行之和（`tbSumUnder`，与报表 `TB('1002')` 同口径；
 *   未审数重算把每个余额表叶子只归到一个标准科目，父子行不重复）。
 */
import { api } from '@/services/apiProxy'

export interface TrialBalanceRow {
  standard_account_code: string
  account_name: string | null
  account_category: string | null
  /** 权威借贷方向（后端 direction_resolver） */
  direction: 'debit' | 'credit'
  unadjusted_amount: string | null
  rje_adjustment: string
  aje_adjustment: string
  audited_amount: string | null
  opening_balance: string | null
  exceeds_materiality: boolean
  below_trivial: boolean
  updated_at: string | null
  /** 底稿审定数发布门写入的调整 / 发布时未审数基线 / 发布时间 */
  wp_adjustment: string | null
  wp_publish_base: string | null
  wp_published_at: string | null
  /** `includeMovement`：本期借方发生额（余额表叶子汇总；损益类含结转分录，勿作净额） */
  period_debit?: string
  /** `includeMovement`：本期贷方发生额 */
  period_credit?: string
  /** `includePrior`：上年同科目审定数（来源同报表上期）；取不到为 null（不代入 0） */
  prior_audited_amount?: string | null
}

export interface TrialBalanceQuery {
  /** 审计年度；省略 ⇒ 后端按项目审计年度取（项目没填 ⇒ 422「未设置审计年度…」） */
  year?: number | null
  /** 标准科目码前缀（后端按前缀筛；多个用数组） */
  accountPrefix?: string | readonly string[]
  /** 附本期借 / 贷方发生额 */
  includeMovement?: boolean
  /** 附上年审定数 */
  includePrior?: boolean
  companyCode?: string
  /** 默认 true：错误不弹全局提示，由调用方显示「待取数」/ 原因 */
  silent?: boolean
}

export interface TrialBalanceResult {
  rows: TrialBalanceRow[]
  /** v1 符号约定残留时后端给的提醒（数据仍可用） */
  warning: string | null
}

function prefixList(prefix: TrialBalanceQuery['accountPrefix']): string[] {
  if (prefix == null) return []
  const list = typeof prefix === 'string' ? prefix.split(',') : [...prefix]
  return [...new Set(list.map((p) => String(p).trim()).filter(Boolean))]
}

function buildParams(query: TrialBalanceQuery): Record<string, unknown> {
  const params: Record<string, unknown> = {}
  if (query.year != null) params.year = query.year
  const prefixes = prefixList(query.accountPrefix)
  if (prefixes.length) params.account_prefix = prefixes.join(',')
  if (query.includeMovement) params.include_movement = true
  if (query.includePrior) params.include_prior = true
  if (query.companyCode) params.company_code = query.companyCode
  return params
}

function unpack(body: unknown): TrialBalanceResult {
  if (Array.isArray(body)) return { rows: body as TrialBalanceRow[], warning: null }
  const obj = (body ?? {}) as { data?: unknown; warning?: unknown }
  if (Array.isArray(obj.data)) {
    return { rows: obj.data as TrialBalanceRow[], warning: typeof obj.warning === 'string' ? obj.warning : null }
  }
  throw new Error('试算表响应格式不符')
}

/** 同参数并发请求合并为一次（页面上多个页签同时取同一份试算表；http 层 GET 去重会取消先发的那一次） */
const inflight = new Map<string, Promise<TrialBalanceResult>>()

/** 取试算表行。失败抛错（调用方据此显示「待取数」/ 原因），不返回空数组冒充 0。 */
export async function fetchTrialBalanceRows(
  projectId: string,
  query: TrialBalanceQuery = {},
): Promise<TrialBalanceResult> {
  if (!projectId) throw new Error('缺少项目')
  const params = buildParams(query)
  const key = `${projectId}|${JSON.stringify(params)}|${query.silent === false ? 'loud' : 'silent'}`
  let pending = inflight.get(key)
  if (!pending) {
    pending = api
      .get(`/api/projects/${projectId}/trial-balance`, {
        params,
        _silent: query.silent !== false,
        _dedupe: false,
      } as any)
      .then(unpack)
      .finally(() => inflight.delete(key))
    inflight.set(key, pending)
  }
  const result = await pending
  // 每个调用方拿自己的数组与行副本：调用方改行不影响别人
  return { rows: result.rows.map((r) => ({ ...r })), warning: result.warning }
}

/** 取数失败的中文原因（后端 422「未设置审计年度…」等原样给用户；取不到用兜底文案） */
export function tbErrorText(error: unknown): string {
  const body = (error as { response?: { data?: any } } | null)?.response?.data
  const detail = body?.detail ?? body?.message
  if (typeof detail === 'string' && detail.trim()) return detail
  if (detail && typeof detail === 'object' && typeof detail.message === 'string') return detail.message
  return '试算表取数失败，请稍后重试'
}

/** 金额字符串 → 数字；空 / 非数字 → null（不当 0） */
export function tbNumber(value: unknown): number | null {
  if (value == null || value === '') return null
  const n = Number(value)
  return Number.isFinite(n) ? n : null
}

/** 标准科目码落在任一前缀下的行（每行只出现一次） */
export function tbRowsUnder(rows: readonly TrialBalanceRow[], prefixes: string | readonly string[]): TrialBalanceRow[] {
  const list = prefixList(prefixes)
  if (!list.length) return []
  return rows.filter((r) => list.some((p) => String(r.standard_account_code ?? '').startsWith(p)))
}

type AmountField = 'unadjusted_amount' | 'audited_amount' | 'opening_balance' | 'rje_adjustment'
  | 'aje_adjustment' | 'wp_adjustment' | 'period_debit' | 'period_credit' | 'prior_audited_amount'

/** 前缀下各行某金额之和；一行都没有 / 全部为空 ⇒ null（「待取数」，不是 0） */
export function tbSumUnder(
  rows: readonly TrialBalanceRow[],
  prefixes: string | readonly string[],
  field: AmountField,
): number | null {
  let total: number | null = null
  for (const r of tbRowsUnder(rows, prefixes)) {
    const n = tbNumber(r[field])
    if (n != null) total = (total ?? 0) + n
  }
  return total
}

/** 是否损益类（标准科目码 5xxx / 6xxx） */
export function tbIsProfitLoss(row: Pick<TrialBalanceRow, 'standard_account_code'>): boolean {
  const first = String(row.standard_account_code ?? '').charAt(0)
  return first === '5' || first === '6'
}

/**
 * 本期借 / 贷方发生额。
 * - 损益类：按试算表单边口径拆（与后端 `four_table/pl_occurrence` 同）—— 收入类贷方 = 金额、费用类借方 = 金额；
 *   不用余额表借贷（含结转分录时两侧相等）。`basis` 选未审 / 审定。
 * - 资产负债类：要 `includeMovement` 取回的 `period_debit/credit`；没取 ⇒ null。
 */
export function tbOccurrence(
  row: TrialBalanceRow,
  basis: 'unadjusted' | 'audited' = 'unadjusted',
): { debit: number; credit: number } | null {
  if (tbIsProfitLoss(row)) {
    const amount = tbNumber(basis === 'audited' ? row.audited_amount : row.unadjusted_amount)
    if (amount == null) return null
    return row.direction === 'credit' ? { debit: 0, credit: amount } : { debit: amount, credit: 0 }
  }
  const debit = tbNumber(row.period_debit)
  const credit = tbNumber(row.period_credit)
  if (debit == null || credit == null) return null
  return { debit, credit }
}

export interface TbProfitLossFamily {
  /** 前缀下有试算表行（没有 ⇒ 调用方提示「未在试算表中找到」） */
  found: boolean
  /** 本期借方发生额之和（单边口径，见 `tbOccurrence`） */
  debit: number
  /** 本期贷方发生额之和 */
  credit: number
  /** 审定数之和；全部为空 ⇒ null */
  audited: number | null
}

/**
 * 损益类科目族（如 6601 及其明细）的本期借 / 贷方发生额与审定数。
 * 原先各底稿读 `borrowing_amount / period_debit / debit_amount`（端点不返回）⇒ 发生额恒 0。
 */
export function tbProfitLossUnder(
  rows: readonly TrialBalanceRow[],
  prefixes: string | readonly string[],
  basis: 'unadjusted' | 'audited' = 'unadjusted',
): TbProfitLossFamily {
  const family = tbRowsUnder(rows, prefixes)
  let debit = 0
  let credit = 0
  for (const r of family) {
    const occ = tbOccurrence(r, basis)
    if (!occ) continue
    debit += occ.debit
    credit += occ.credit
  }
  return { found: family.length > 0, debit, credit, audited: tbSumUnder(family, prefixes, 'audited_amount') }
}
