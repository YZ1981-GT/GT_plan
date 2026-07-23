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

  /** D1-15 ECL 模型应计提减值合计（标量 remark） */
  const eclShouldProvision: ComputedRef<number> = computed(() =>
    parseNum(getRemark('D1-ecl-total-should-provision')),
  )

  /** D1-15 ECL 模型实际计提减值合计（标量 remark） */
  const eclActualProvision: ComputedRef<number> = computed(() =>
    parseNum(getRemark('D1-ecl-total-actual-provision')),
  )

  /**
   * ECL 模型应计提 vs D1-4 坏账准备明细审定合计 的差异。
   * 二者理论上应一致（坏账准备即按 ECL 模型计提）；差异>阈值提示复核。
   * 仅当 ECL 已计算（eclShouldProvision>0）时才有意义。
   */
  const eclVsBadDebtDiff: ComputedRef<number> = computed(() =>
    eclShouldProvision.value - badDebtTotalAudited.value,
  )

  /**
   * D1-8 已贴现尚未到期票据中「未终止确认」部分汇票金额合计。
   * 未终止确认 → 仍列示为应收票据且需表外披露（或与 D5 应收款项融资勾稽）。
   */
  const discountNotDerecognizedTotal: ComputedRef<number> = computed(() => {
    const rows = parseRows<{ billAmount?: number; isDerecognized?: string; rowType?: string }>('D1-endorse-discount-rows')
    return rows
      .filter(r => r.rowType !== 'summary' && r.isDerecognized !== '是')
      .reduce((s, r) => s + parseNum(r.billAmount), 0)
  })

  /** D1-8 已背书转让尚未到期票据汇票金额合计（表外披露口径） */
  const endorsedTransferTotal: ComputedRef<number> = computed(() => {
    const rows = parseRows<{ billAmount?: number; rowType?: string }>('D1-endorse-transfer-rows')
    return rows
      .filter(r => r.rowType !== 'summary')
      .reduce((s, r) => s + parseNum(r.billAmount), 0)
  })

  return {
    adjNotesReceivableAudited,
    badDebtTotalAudited,
    categoryTotalBalance,
    eclShouldProvision,
    eclActualProvision,
    eclVsBadDebtDiff,
    discountNotDerecognizedTotal,
    endorsedTransferTotal,
    parseRows,
    getRemark,
  }
}

export default useD1CrossSheet
