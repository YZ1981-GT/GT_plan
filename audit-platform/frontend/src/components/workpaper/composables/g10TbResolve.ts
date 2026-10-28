/** G10 试算表科目解析：平台映射码不一致时按别名 + 科目名称回退 */
import {
  G10_ACCOUNT_ALIASES,
  G10_ACCOUNT_CODE,
  G10_ACCOUNT_NAME,
} from './g10Constants'

export interface G10TbRowLike {
  standard_account_code?: string
  account_code?: string
  account_name?: string | null
  standard_account_name?: string
  unadjusted_amount?: number | string | null
  audited_amount?: number | string | null
}

function rowCode(r: G10TbRowLike): string {
  return String(r.standard_account_code ?? r.account_code ?? '').trim()
}

function rowName(r: G10TbRowLike): string {
  return String(r.account_name ?? r.standard_account_name ?? '').trim()
}

/** 从试算表行列表解析 G10 科目行（优先标准码，再别名，再名称包含） */
export function resolveG10TbRow(rows: G10TbRowLike[]): G10TbRowLike | null {
  if (!Array.isArray(rows) || !rows.length) return null

  for (const code of G10_ACCOUNT_ALIASES) {
    const exact = rows.find((r) => rowCode(r) === code)
    if (exact) return exact
  }
  for (const code of G10_ACCOUNT_ALIASES) {
    const prefix = rows.find((r) => rowCode(r).startsWith(code))
    if (prefix) return prefix
  }
  const byName = rows.find((r) => rowName(r).includes(G10_ACCOUNT_NAME))
  if (byName) return byName
  return null
}

/** 负债类期末未审数（试算表正数口径）。端点没有期末余额 / 借贷字段，不再按「贷 − 借」兜底 */
export function g10TbRowBalance(row: G10TbRowLike | null | undefined): number {
  if (!row || row.unadjusted_amount == null || row.unadjusted_amount === '') return 0
  const n = Number(row.unadjusted_amount)
  return Number.isFinite(n) ? n : 0
}

export function g10TbResolvedCode(row: G10TbRowLike | null | undefined): string {
  if (!row) return G10_ACCOUNT_CODE
  return rowCode(row) || G10_ACCOUNT_CODE
}

export function g10AccountLabel(code?: string | null): string {
  const c = code || G10_ACCOUNT_CODE
  return `${G10_ACCOUNT_NAME}（${c}）`
}

/** 从试算表行列表解析 G10 科目余额；未找到返回 null */
export function resolveG10TbBalanceFromList(rows: G10TbRowLike[]): number | null {
  const hit = resolveG10TbRow(rows)
  return hit != null ? g10TbRowBalance(hit) : null
}
