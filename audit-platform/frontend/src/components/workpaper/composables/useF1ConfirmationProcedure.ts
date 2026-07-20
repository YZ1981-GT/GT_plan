/**
 * useF1ConfirmationProcedure — F1-CONF 函证程序（F1-2 拟发函清单 + 覆盖率）
 */
import { parseNum } from './useF1FormulaEngine'

export const F1_DETAIL_ROWS_ITEM_ID = 'F1-det-rows'

export interface F1ConfirmationCandidate {
  rowId: string
  customerName: string
  endAudited: number
  relationType: string
  isConfirmed: string
}

export interface F1ConfirmationCoverage {
  totalAccounts: number
  totalBalance: number
  confirmedAccounts: number
  confirmedBalance: number
  coverageRatio: number | null
}

function isDataRowId(rowId: unknown): boolean {
  const id = String(rowId || '')
  return !!id && !id.startsWith('__')
}

export function parseConfirmationCandidates(jsonStr: string | null | undefined): F1ConfirmationCandidate[] {
  if (!jsonStr) return []
  try {
    const raw = JSON.parse(jsonStr)
    if (!Array.isArray(raw)) return []
    return raw
      .filter(r => isDataRowId(r.rowId) && String(r.customerName || '').trim())
      .map(r => ({
        rowId: String(r.rowId),
        customerName: String(r.customerName || '').trim(),
        endAudited: parseNum(r.endAudited),
        relationType: String(r.relationType || ''),
        isConfirmed: String(r.isConfirmed || '').trim().toUpperCase(),
      }))
      .filter(r => r.endAudited > 0)
      .sort((a, b) => b.endAudited - a.endAudited)
  } catch {
    return []
  }
}

export function isConfirmedMarked(flag: string): boolean {
  const v = String(flag || '').trim().toUpperCase()
  return v === 'Y' || v === '是'
}

export function computeConfirmationCoverage(rows: F1ConfirmationCandidate[]): F1ConfirmationCoverage {
  const totalBalance = rows.reduce((sum, r) => sum + r.endAudited, 0)
  const confirmedRows = rows.filter(r => isConfirmedMarked(r.isConfirmed))
  const confirmedBalance = confirmedRows.reduce((sum, r) => sum + r.endAudited, 0)
  return {
    totalAccounts: rows.length,
    totalBalance,
    confirmedAccounts: confirmedRows.length,
    confirmedBalance,
    coverageRatio: totalBalance > 0 ? (confirmedBalance / totalBalance) * 100 : null,
  }
}

/** 将选中行标记为已发函(Y)，返回更新后的 JSON 与变更行数 */
export function markRowsConfirmedInJson(
  jsonStr: string | null | undefined,
  rowIds: readonly string[],
): { json: string; changed: number } {
  const idSet = new Set(rowIds)
  if (!idSet.size) return { json: jsonStr || '[]', changed: 0 }
  let rows: any[]
  try {
    const parsed = jsonStr ? JSON.parse(jsonStr) : []
    rows = Array.isArray(parsed) ? parsed : []
  } catch {
    return { json: jsonStr || '[]', changed: 0 }
  }
  let changed = 0
  const next = rows.map(r => {
    if (!idSet.has(String(r.rowId))) return r
    if (isConfirmedMarked(r.isConfirmed)) return r
    changed += 1
    return { ...r, isConfirmed: 'Y' }
  })
  return { json: JSON.stringify(next), changed }
}
