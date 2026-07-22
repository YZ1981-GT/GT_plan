/** G9 试算表科目解析：平台映射码不一致时按别名 + 科目名称回退 */
import {
  G9_ACCOUNT_ALIASES,
  G9_ACCOUNT_CODE,
  G9_ACCOUNT_NAME,
} from './g9Constants'

export interface G9TbRowLike {
  standard_account_code?: string
  account_code?: string
  account_name?: string
  standard_account_name?: string
  debit_amount?: number | string
  credit_amount?: number | string
  period_debit?: number | string
  period_credit?: number | string
  unadjusted_amount?: number | string
  closing_balance?: number | string
  ending_balance?: number | string
}

function rowCode(r: G9TbRowLike): string {
  return String(r.standard_account_code ?? r.account_code ?? '').trim()
}

function rowName(r: G9TbRowLike): string {
  return String(r.account_name ?? r.standard_account_name ?? '').trim()
}

/** 从试算表行列表解析 G9 科目行（优先标准码，再别名，再名称包含） */
export function resolveG9TbRow(rows: G9TbRowLike[]): G9TbRowLike | null {
  if (!Array.isArray(rows) || !rows.length) return null

  for (const code of G9_ACCOUNT_ALIASES) {
    const exact = rows.find((r) => rowCode(r) === code)
    if (exact) return exact
  }
  for (const code of G9_ACCOUNT_ALIASES) {
    const prefix = rows.find((r) => rowCode(r).startsWith(code))
    if (prefix) return prefix
  }
  const byName = rows.find((r) => rowName(r).includes(G9_ACCOUNT_NAME))
  if (byName) return byName
  return null
}

/** 资产方向余额：优先未审/期末余额字段，否则借−贷 */
export function g9TbRowBalance(row: G9TbRowLike | null | undefined): number {
  if (!row) return 0
  const direct = row.unadjusted_amount ?? row.closing_balance ?? row.ending_balance
  if (direct != null && direct !== '') {
    const n = Number(direct)
    if (Number.isFinite(n)) return n
  }
  const debit = Number(row.debit_amount ?? row.period_debit ?? 0) || 0
  const credit = Number(row.credit_amount ?? row.period_credit ?? 0) || 0
  return debit - credit
}

export function g9TbResolvedCode(row: G9TbRowLike | null | undefined): string {
  if (!row) return G9_ACCOUNT_CODE
  return rowCode(row) || G9_ACCOUNT_CODE
}
