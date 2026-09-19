/**
 * G14-2 减值准备期末 — 试算取数与对账（纯函数 + API）
 */
import {
  G14_LINE_ITEMS,
  type G14LineDef,
} from './g14Constants'
import { parseNum } from './useG14FormulaEngine'
import {
  fetchTrialBalanceByPrefix,
  pickTbAmount,
} from './workpaperAuditYear'

const TOLERANCE = 0.01

export interface G14TbRowLike {
  standard_account_code?: string
  account_code?: string
  account_name?: string
  name?: string
  audited_amount?: unknown
  unadjusted_amount?: unknown
  ending_balance?: unknown
  closing_balance?: unknown
  debit_amount?: unknown
  credit_amount?: unknown
}

/** 准备类科目多为贷方余额：取绝对值便于与明细「期末余额」勾稽 */
export function pickProvisionTbClosing(hit: G14TbRowLike | null | undefined): number {
  if (!hit) return 0
  const raw = pickTbAmount(hit)
  // closing_balance 若存在且 pick 未覆盖，补一层
  if (raw === 0 && hit.closing_balance != null) {
    return Math.abs(parseNum(hit.closing_balance))
  }
  return Math.abs(raw)
}

function accountCodeOf(row: G14TbRowLike): string {
  return String(row.standard_account_code ?? row.account_code ?? '').trim()
}

function accountNameOf(row: G14TbRowLike): string {
  return String(row.account_name ?? row.name ?? '')
}

/**
 * 在已拉取的试算行中，按前缀 + 名称关键字匹配最合适的准备科目行。
 * - 有 nameHints：优先名称命中；同前缀多行时避免串户（如 1231）
 * - 无名称命中：若该前缀仅 1 行则采用；多行则放弃（避免误配）
 */
export function matchProvisionTbRow(
  rows: G14TbRowLike[],
  def: G14LineDef,
): G14TbRowLike | null {
  if (!def.tbPrefixes.length) return null

  for (const prefix of def.tbPrefixes) {
    const candidates = rows.filter((r) => accountCodeOf(r).startsWith(prefix))
    if (!candidates.length) continue

    if (def.tbNameHints.length) {
      const named = candidates.filter((r) => {
        const name = accountNameOf(r)
        return def.tbNameHints.some((h) => name.includes(h))
      })
      if (named.length === 1) return named[0]
      if (named.length > 1) {
        // 多条命中时取科目码最长（更明细）者
        return [...named].sort((a, b) => accountCodeOf(b).length - accountCodeOf(a).length)[0]
      }
    }

    if (candidates.length === 1) return candidates[0]
  }
  return null
}

export function isClosingReconciledWithTb(
  closingProvision: number,
  tbClosing: number | null | undefined,
  tolerance = TOLERANCE,
): boolean {
  if (tbClosing == null || Number.isNaN(tbClosing)) return true
  return Math.abs(closingProvision - tbClosing) <= tolerance
}

export type G14ProvisionTbResult = Record<string, number | null>

/** 按各行映射批量取试算准备期末（并行按唯一前缀拉取） */
export async function fetchG14ProvisionClosingsFromTb(
  projectId: string,
  year: number,
): Promise<G14ProvisionTbResult> {
  const prefixes = new Set<string>()
  for (const def of G14_LINE_ITEMS) {
    for (const p of def.tbPrefixes) prefixes.add(p)
  }

  const byPrefix = new Map<string, G14TbRowLike[]>()
  await Promise.all(
    [...prefixes].map(async (prefix) => {
      try {
        const list = await fetchTrialBalanceByPrefix(projectId, year, prefix)
        byPrefix.set(prefix, list)
      } catch {
        byPrefix.set(prefix, [])
      }
    }),
  )

  const allRows: G14TbRowLike[] = []
  const seen = new Set<string>()
  for (const list of byPrefix.values()) {
    for (const r of list) {
      const key = `${accountCodeOf(r)}|${accountNameOf(r)}`
      if (seen.has(key)) continue
      seen.add(key)
      allRows.push(r)
    }
  }

  const out: G14ProvisionTbResult = {}
  for (const def of G14_LINE_ITEMS) {
    if (!def.tbPrefixes.length) {
      out[def.rowKey] = null
      continue
    }
    const hit = matchProvisionTbRow(allRows, def)
    out[def.rowKey] = hit ? pickProvisionTbClosing(hit) : null
  }
  return out
}
