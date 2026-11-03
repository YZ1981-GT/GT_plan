/** G9 试算表科目解析：平台映射码不一致时按别名 + 科目名称回退 */
import {
  G9_ACCOUNT_ALIASES,
  G9_ACCOUNT_CODE,
  G9_ACCOUNT_NAME,
} from './g9Constants'

export interface G9TbRowLike {
  standard_account_code?: string
  account_code?: string
  account_name?: string | null
  standard_account_name?: string
  unadjusted_amount?: number | string | null
  audited_amount?: number | string | null
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

/** 资产类期末未审数（试算表正数口径）。端点没有期末余额 / 借贷字段，不再按「借 − 贷」兜底 */
export function g9TbRowBalance(row: G9TbRowLike | null | undefined): number {
  if (!row || row.unadjusted_amount == null || row.unadjusted_amount === '') return 0
  const n = Number(row.unadjusted_amount)
  return Number.isFinite(n) ? n : 0
}

export function g9TbResolvedCode(row: G9TbRowLike | null | undefined): string {
  if (!row) return G9_ACCOUNT_CODE
  return rowCode(row) || G9_ACCOUNT_CODE
}
