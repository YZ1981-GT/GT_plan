/**
 * G12-5 编制完成度判定
 */
import { findG12NetExposureCrossIssues } from './g12NetExposureCross'
import type { ChecklistResponse } from './useF1FormData'

export interface G12NetExposureRowLike {
  rowId?: string
  item?: string
  currency?: string
  position1Desc?: string
  position2Desc?: string
  netPosition?: string
  hedgeRelationId?: string
  checkItem?: string
  sectionTitle?: string
}

const ROWS_KEY = 'G12-net-exposure-rows'
const NOTE_KEY = 'G12-net-exposure-audit-note'
const CONCLUSION_KEY = 'G12-net-exposure-conclusion'

export function isG12NetExposureRowComplete(r: G12NetExposureRowLike): boolean {
  return !!(
    String(r.item ?? '').trim()
    && String(r.currency ?? '').trim()
    && String(r.position1Desc ?? '').trim()
    && String(r.position2Desc ?? '').trim()
    && String(r.netPosition ?? '').trim()
  )
}

export function parseG12NetExposureRows(raw: string | null | undefined): G12NetExposureRowLike[] {
  if (!raw) return []
  try {
    const arr = JSON.parse(raw)
    if (!Array.isArray(arr) || !arr.length) return []
    if ('checkItem' in (arr[0] ?? {}) || 'sectionTitle' in (arr[0] ?? {})) return []
    return arr
  } catch {
    return []
  }
}

/** G12-5 是否达到「已编制」：行完整 + 说明/结论 + 无未解释交叉差异 */
export function isG12NetExposureSheetComplete(m: Map<string, ChecklistResponse>): boolean {
  const rows = parseG12NetExposureRows(m.get(ROWS_KEY)?.remark)
  if (!rows.length) return false
  if (!rows.every(isG12NetExposureRowComplete)) return false

  const note = m.get(NOTE_KEY)?.remark?.trim()
  const conclusion = m.get(CONCLUSION_KEY)?.conclusion?.trim()
  if (!note || !conclusion) return false

  const crossIssues = findG12NetExposureCrossIssues(
    rows as Parameters<typeof findG12NetExposureCrossIssues>[0],
    m,
  )
  if (crossIssues.length > 0) return false

  return true
}
