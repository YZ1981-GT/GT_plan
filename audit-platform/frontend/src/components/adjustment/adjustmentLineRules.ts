/**
 * 调整分录明细行规则（spec adjustment-hall-entry-review-closure 需求 1.2）。
 *
 * 与后端 `services/adjustment_entry_rules.entry_rule_errors` 同口径、同文案，录入弹窗据此即时提示；
 * 保存时后端再校验一次（以后端为准）。金额一律换成「分」（整数）计算，避免浮点尾差。
 */
/* eslint-disable gt-audit/no-amount-arithmetic -- 下面的加减都是「分」整数运算（toCents 之后），没有浮点误差 */

export interface EditableLine {
  standard_account_code: string
  account_name?: string
  debit_amount?: number | null
  credit_amount?: number | null
  /** 编辑既有分录时原样带回（导入的二级科目码 / 底稿给的报表行）；改了科目就清掉 */
  detail_account_code?: string | null
  report_line_code?: string | null
  /** 快捷模板提示的方向（只用于占位提示，不提交） */
  side?: 'debit' | 'credit'
}

/** 录入弹窗保存后回传给大厅的结果 */
export interface EntrySavedPayload {
  entryGroupId: string
  adjustmentNo: string
  mode: 'create' | 'edit'
  /** 用户点的是「保存并提交复核」 */
  submit: boolean
}

export interface AccountLike {
  code: string
  name: string
}

const AMOUNT_TEXT = /^([-+]?)(\d*)(?:\.(\d*))?$/
const IGNORED_CHARS = /[,，¥￥$\s]/g

/** 金额 → 分（整数，按分四舍五入，与后端 ROUND_HALF_UP 一致）；空为 0，无法识别为 NaN。 */
export function toCents(value: unknown): number {
  if (value === null || value === undefined) return 0
  if (typeof value === 'number' && !Number.isFinite(value)) return NaN
  const text = String(value).replace(IGNORED_CHARS, '')
  if (!text) return 0
  const m = AMOUNT_TEXT.exec(text)
  if (!m || (!m[2] && !m[3])) return NaN
  const frac = (m[3] || '').padEnd(3, '0')
  let cents = Number(m[2] || '0') * 100 + Number(frac.slice(0, 2))
  if (Number(frac[2]) >= 5) cents += 1
  return m[1] === '-' ? -cents : cents
}

/** 分 → 「1234.50」（与后端 Decimal 文案一致，不带千分位） */
export function centsText(cents: number): string {
  const sign = cents < 0 ? '-' : ''
  const abs = Math.abs(cents)
  return `${sign}${Math.floor(abs / 100)}.${String(abs % 100).padStart(2, '0')}`
}

/** 没选科目且借贷都没填的行（录入时多加的空行，保存时丢弃，不报错） */
export function isBlankLine(line: EditableLine): boolean {
  return !String(line.standard_account_code || '').trim() && toCents(line.debit_amount) === 0
    && toCents(line.credit_amount) === 0
}

export function lineTotals(lines: EditableLine[]): { debit: number; credit: number; diff: number } {
  let debit = 0
  let credit = 0
  for (const li of lines) {
    const d = toCents(li.debit_amount)
    const c = toCents(li.credit_amount)
    if (Number.isFinite(d)) debit += d
    if (Number.isFinite(c)) credit += c
  }
  return { debit, credit, diff: debit - credit }
}

/**
 * 一笔分录违反的全部规则（行号按界面行序，空行跳过）；为空表示通过。
 * 规则：每行有科目；金额非负；同一行借贷不能同时有数；借贷不能都为 0；整组借贷相等且大于 0。
 */
export function lineRuleErrors(lines: EditableLine[]): string[] {
  const errors: string[] = []
  let debit = 0
  let credit = 0
  let counted = 0
  lines.forEach((li, idx) => {
    if (isBlankLine(li)) return
    counted += 1
    const label = `第 ${idx + 1} 行`
    const d = toCents(li.debit_amount)
    const c = toCents(li.credit_amount)
    if (!Number.isFinite(d) || !Number.isFinite(c)) {
      errors.push(`${label}金额无法识别：${!Number.isFinite(d) ? li.debit_amount : li.credit_amount}`)
      return
    }
    if (!String(li.standard_account_code || '').trim()) {
      errors.push(li.account_name ? `${label}科目「${li.account_name}」不在本项目科目中，请重新选择` : `${label}未选择科目`)
    }
    if (d < 0 || c < 0) errors.push(`${label}金额不能为负数（冲减请录入到相反方向）`)
    if (d !== 0 && c !== 0) errors.push(`${label}借方和贷方不能同时填写`)
    if (d === 0 && c === 0) errors.push(`${label}借贷金额均为 0`)
    debit += d
    credit += c
  })
  if (!counted) return ['至少需要一行明细']
  if (debit !== credit) {
    errors.push(`借贷不平衡：借方合计 ${centsText(debit)}，贷方合计 ${centsText(credit)}，差额 ${centsText(debit - credit)}`)
  } else if (debit === 0) {
    errors.push('借贷合计为 0，没有需要调整的金额')
  }
  return errors
}

/** 提交用的明细：丢掉空行，金额按分换回元（数字）。 */
export function linesForSubmit(lines: EditableLine[]) {
  return lines.filter((li) => !isBlankLine(li)).map((li) => ({
    standard_account_code: String(li.standard_account_code || '').trim(),
    account_name: li.account_name || undefined,
    debit_amount: toCents(li.debit_amount) / 100,
    credit_amount: toCents(li.credit_amount) / 100,
    ...(li.detail_account_code ? { detail_account_code: li.detail_account_code } : {}),
    ...(li.report_line_code ? { report_line_code: li.report_line_code } : {}),
  }))
}

/**
 * 差额补平：把「借 − 贷」的差额填进最后一个还没填金额的行（借贷都空，可已选科目）；没有这样的行就新加一行（科目待选）。
 * 不改已填的金额。返回新的明细数组（不改入参）。
 */
export function fillDifference(lines: EditableLine[]): EditableLine[] {
  const { diff } = lineTotals(lines)
  if (diff === 0) return lines
  const next = lines.map((li) => ({ ...li }))
  const side: 'debit_amount' | 'credit_amount' = diff > 0 ? 'credit_amount' : 'debit_amount'
  const amount = Math.abs(diff) / 100
  for (let i = next.length - 1; i >= 0; i -= 1) {
    if (toCents(next[i].debit_amount) === 0 && toCents(next[i].credit_amount) === 0) {
      next[i] = { ...next[i], debit_amount: undefined, credit_amount: undefined, [side]: amount }
      return next
    }
  }
  next.push({ standard_account_code: '', account_name: '', debit_amount: undefined, credit_amount: undefined, [side]: amount })
  return next
}

/** 按编码精确匹配，否则按名称精确匹配，再退到名称包含该名称的科目中名称最短的一个。 */
export function matchAccount(code: string, name: string, options: AccountLike[]): AccountLike | null {
  const c = code.trim()
  if (c) {
    const byCode = options.find((o) => o.code === c)
    if (byCode) return byCode
  }
  const n = name.trim()
  if (!n) return null
  const exact = options.find((o) => o.name === n)
  if (exact) return exact
  const partial = options.filter((o) => o.name.includes(n)).sort((a, b) => a.name.length - b.name.length)
  return partial[0] || null
}

/**
 * 解析从 Excel 复制的多行（制表符分隔）：列序为「科目编码、科目名称、借方、贷方[、摘要]」。
 * 返回明细行、第一个非空摘要与问题提示；科目按编码 / 名称匹配本项目科目，匹配不到的保留名称、科目留空待选；
 * 金额去千分位与货币符号，识别不了的留空并在 problems 里说明。
 */
export function parsePastedLines(text: string, options: AccountLike[]): {
  lines: EditableLine[]; summary: string; problems: string[]
} {
  const lines: EditableLine[] = []
  const problems: string[] = []
  let summary = ''
  const amount = (raw: string, label: string): number | undefined => {
    if (raw === '') return undefined
    const cents = toCents(raw)
    if (Number.isFinite(cents)) return cents / 100
    problems.push(`${label}「${raw}」无法识别，已留空`)
    return undefined
  }
  for (const row of text.split(/\r?\n/)) {
    const [code = '', name = '', debit = '', credit = '', memo = ''] = row.split('\t').map((c) => c.trim())
    if (!code && !name && !debit && !credit) continue
    const no = lines.length + 1
    const hit = matchAccount(code, name, options)
    if (!hit) problems.push(`第 ${no} 行科目「${name || code}」不在本项目科目中，请选择`)
    lines.push({
      standard_account_code: hit?.code || '',
      account_name: hit?.name || name || code,
      debit_amount: amount(debit, `第 ${no} 行借方`),
      credit_amount: amount(credit, `第 ${no} 行贷方`),
    })
    if (!summary && memo) summary = memo
  }
  return { lines, summary, problems }
}
