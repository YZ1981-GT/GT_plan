/**
 * useD1CrossSheet — D1 跨 Sheet 只读聚合（provide 给子 Tab）
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import { parseNum } from './useD1FormulaEngine'
import type { ChecklistResponse } from './useD1FormData'

export interface UseD1CrossSheetOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
}

export function useD1CrossSheet(options: UseD1CrossSheetOptions) {
  const { allResponses } = options

  function getRemark(itemId: string): string | null {
    return allResponses.value.get(itemId)?.remark ?? null
  }

  function parseRows<T>(itemId: string): T[] {
    const raw = getRemark(itemId)
    if (!raw) return []
    try {
      const p = JSON.parse(raw)
      return Array.isArray(p) ? p : []
    } catch {
      return []
    }
  }

  /** 审定表应收票据期末审定数 */
  const adjNotesReceivableAudited: ComputedRef<number> = computed(() =>
    parseNum(getRemark('D1-adj-notes-receivable-current-audited')),
  )

  /** D1-4 坏账准备小计（individual + portfolio currentAudited 之和） */
  const badDebtTotalAudited: ComputedRef<number> = computed(() => {
    const ind = parseRows<{ currentAudited?: number }>('D1-bd-individual-rows')
    const port = parseRows<{ currentAudited?: number }>('D1-bd-portfolio-rows')
    const sum = (rows: typeof ind) => rows.reduce((s, r) => s + parseNum(r.currentAudited), 0)
    return sum(ind) + sum(port)
  })

  /** D1-2 按类别原值合计 */
  const categoryTotalBalance: ComputedRef<number> = computed(() => {
    const rows = parseRows<{ currentUnadjusted?: number; currentAje?: number; currentRje?: number }>('D1-cat-rows')
    return rows.reduce((s, r) => s + parseNum(r.currentUnadjusted) + parseNum(r.currentAje) + parseNum(r.currentRje), 0)
  })

  return {
    adjNotesReceivableAudited,
    badDebtTotalAudited,
    categoryTotalBalance,
    parseRows,
    getRemark,
  }
}

export default useD1CrossSheet
