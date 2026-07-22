/**
 * G 循环 → G13 源科目 FV 变动 EventBus（g-cycle:source-fv）
 */
import { parseNum, calcSubtotal } from './useG13FormulaEngine'
import { G13_FV_SOURCES, type G13FvSource } from './gCycleExternalCross'

export const G_CYCLE_SOURCE_FV_EVENT = 'g-cycle:source-fv'

export function publishGCycleSourceFv(source: G13FvSource, amount: number): void {
  if (!G13_FV_SOURCES.includes(source)) return
  try {
    window.dispatchEvent(
      new CustomEvent(G_CYCLE_SOURCE_FV_EVENT, {
        detail: { source, amount: parseNum(amount) },
      }),
    )
  } catch { /* best effort */ }
}

/** 从明细 JSON 数组汇总计入损益的公允变动（字段因科目而异） */
export function sumSourceDetailFvChange(
  rows: unknown[],
  source: G13FvSource,
): number {
  if (!Array.isArray(rows) || !rows.length) return 0
  return calcSubtotal(
    rows.map((raw) => {
      if (!raw || typeof raw !== 'object') return 0
      const r = raw as Record<string, unknown>
      if (source === 'G10') {
        return parseNum(r.movementFvChange ?? r.fvChangeAmount ?? r.periodFvChange)
      }
      if (source === 'H3') {
        return parseNum(r.fairValueChange ?? r.fvChangeAmount)
      }
      if (source === 'G1') {
        return parseNum(r.fvChangeInPL ?? r.periodFvChange ?? r.fairValueChange)
      }
      // G8 / G9
      return parseNum(r.fvChangeAmount ?? r.periodFvChange ?? r.fairValueChange)
    }),
  )
}

export function parseDetailRowsJson(json: string | null | undefined): unknown[] {
  if (!json) return []
  try {
    const parsed = JSON.parse(json)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/** checklist item 中明细行 → 源 FV 合计 */
export function sumFvFromChecklistRemark(
  json: string | null | undefined,
  source: G13FvSource,
): number {
  return sumSourceDetailFvChange(parseDetailRowsJson(json), source)
}

/** 源科目明细 checklist itemId */
export const G13_SOURCE_DETAIL_ITEM_IDS: Record<G13FvSource, string> = {
  G1: 'G1-2-rows',
  G8: 'G8-detail-rows',
  G9: 'G9-detail-rows',
  G10: 'G10-detail-rows',
  H3: 'H3-2-fair-rows',
}
