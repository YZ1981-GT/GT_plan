/**
 * useH7CrossSheet — H7 生产性生物资产跨Sheet交叉验证 computed 引擎
 *
 * Spec: .kiro/specs/h7-biological-assets/ Task 3.2
 * Requirements: 2.6, 7.6
 *
 * 跨Sheet映射（数据流图）：
 * - H7-1 审定表总计 vs H7-2 明细表总计（adjudicationVsDetail）
 * - H7-11 折旧计提合计 vs H7-1 累计折旧本期贷方（depreciationVsAdjudication）
 * - H7-14 互转差额校验（transferDiffCheck）
 *
 * 科目方向：
 * - 1621 生产性生物资产（借方/资产类）：期末=期初+借方-贷方
 * - 累计折旧（贷方/备抵类）：期末=期初+贷方-借方
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：左侧 - 右侧 */
  diff: number
  /** 是否匹配（|diff| < 0.01） */
  isMatch: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

function getNumFromMap(map: Map<string, any>, key: string): number {
  const item = map.get(key)
  if (!item) return 0
  const raw = item.remark ?? item.conclusion
  if (raw == null) return 0
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH7CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  depreciationVsAdjudication: ComputedRef<CrossSheetCheckResult>
  transferDiffCheck: ComputedRef<CrossSheetCheckResult>
} {
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // H7-1 审定表原值合计 vs H7-2 明细表期末合计
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('H7-1-cost-total')
    const detailSubtotal = getNum('H7-2-cost-total')
    const diff = adjTotal - detailSubtotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // H7-11 折旧测算本期计提 vs H7-1 累计折旧本期贷方发生
  const depreciationVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const depCalcTotal = getNum('H7-11-dep-total')
    const adjDepCredit = getNum('H7-1-dep-credit')
    const diff = depCalcTotal - adjDepCredit
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // H7-14 互转差额校验（转出金额合计 - 转入金额合计 应为0）
  const transferDiffCheck: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const transferOut = getNum('H7-14-transfer-out-total')
    const transferIn = getNum('H7-14-transfer-in-total')
    const diff = transferOut - transferIn
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  return {
    adjudicationVsDetail,
    depreciationVsAdjudication,
    transferDiffCheck,
  }
}

export default useH7CrossSheet
