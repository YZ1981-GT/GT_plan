/**
 * useD1CrossSheet — D1 跨 Sheet 只读聚合（provide 给子 Tab）
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import { parseNum } from './useD1FormulaEngine'
import type { ChecklistResponse } from './useD1FormData'
import {
  readD1AdjudicationTotals,
  readD1BadDebtTotal,
  readD1CategoryTotal,
} from './d1AdjudicationModel'

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

  /**
   * 审定表应收票据**净值**期末审定数（源模板 D1-1 三、应收票据净值 小计 I18）。
   *
   * 🔴 改造前读 `D1-adj-notes-receivable-current-audited` —— 该锚点**全平台无写入方**
   * （审定表实际锚点是 `D1-adj-{gross|bd|net}-{slug}-{field}`，且审定数是 computed 列
   * 从不持久化），故 D1-10 监盘 / D1-11 关联方的账面余额一直恒 0、
   * `bookBalanceLoaded` / `adjDataLoaded` 恒 false。现改由共享模型现算。
   */
  const adjNotesReceivableAudited: ComputedRef<number> = computed(
    () => readD1AdjudicationTotals(allResponses.value).netTotal.currentAudited,
  )

  /** 审定表应收票据**原值**期末审定合计（票据面值口径，供实物监盘/关联方核对用）。 */
  const adjGrossAudited: ComputedRef<number> = computed(
    () => readD1AdjudicationTotals(allResponses.value).grossTotal.currentAudited,
  )

  /**
   * D1-4 坏账准备期末审定合计。
   *
   * 🔴 改造前直接读行里的 `currentAudited` —— `useD1BadDebt.serializeRows()` 不持久化
   * 派生列 → 恒 0 → `eclVsBadDebtDiff` 把整个 ECL 应计提额当差异常亮。现由共享模型现算。
   */
  const badDebtTotalAudited: ComputedRef<number> = computed(
    () => readD1BadDebtTotal(allResponses.value).currentAudited,
  )

  /** D1-2 按类别原值期末审定合计（同上：派生列不落库，必须现算）。 */
  const categoryTotalBalance: ComputedRef<number> = computed(
    () => readD1CategoryTotal(allResponses.value).currentAudited,
  )

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
    adjGrossAudited,
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
