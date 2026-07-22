/** G11 试算表科目解析：6111 投资收益（损益类取贷−借发生额） */
import { G11_ACCOUNT_CODE } from './g11Constants'

export const G11_ACCOUNT_ALIASES = [G11_ACCOUNT_CODE, '611101', '611102'] as const
export const G11_ACCOUNT_NAME = '投资收益'

export interface G11TbRowLike {
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

function rowCode(r: G11TbRowLike): string {
  return String(r.standard_account_code ?? r.account_code ?? '').trim()
}

function rowName(r: G11TbRowLike): string {
  return String(r.account_name ?? r.standard_account_name ?? '').trim()
}

/** 从试算表行列表解析 G11 科目行 */
export function resolveG11TbRow(rows: G11TbRowLike[]): G11TbRowLike | null {
  if (!Array.isArray(rows) || !rows.length) return null
  for (const code of G11_ACCOUNT_ALIASES) {
    const exact = rows.find((r) => rowCode(r) === code)
    if (exact) return exact
  }
  for (const code of G11_ACCOUNT_ALIASES) {
    const prefix = rows.find((r) => rowCode(r).startsWith(code))
    if (prefix) return prefix
  }
  const byName = rows.find((r) => rowName(r).includes(G11_ACCOUNT_NAME))
  return byName ?? null
}

/** 6111 损益类发生额：贷−借 */
export function g11TbRowPlAmount(row: G11TbRowLike | null | undefined): number {
  if (!row) return 0
  const credit = Number(row.credit_amount ?? row.period_credit ?? 0) || 0
  const debit = Number(row.debit_amount ?? row.period_debit ?? 0) || 0
  return credit - debit
}

/** 6111 子科目行（用于分项预填） */
export function resolveG11TbChildRows(rows: G11TbRowLike[]): G11TbRowLike[] {
  if (!Array.isArray(rows) || !rows.length) return []
  return rows.filter((r) => {
    const code = rowCode(r)
    return code.startsWith(G11_ACCOUNT_CODE) && code !== G11_ACCOUNT_CODE
  })
}
