/**
 * useH5CrossSheet — H5 油气资产跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H5-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - H5-1 审定表总计 vs H5-2 明细表总计（adjudicationVsDetail）
 * - H5-12 折耗计提合计 vs H5-1 累计折耗本期贷方（depletionVsAdjudication）
 * - H5-7 增加合计 vs H5-1 原值本期借方（additionVsAdjudication）
 * - H5-8 减少合计 vs H5-1 原值本期贷方（disposalVsAdjudication）
 *
 * 科目方向：
 * - 1631 油气资产（借方/资产类）：期末=期初+借方-贷方
 * - 1632 累计折耗（贷方/备抵类）：期末=期初+贷方-借方
 *
 * Spec: .kiro/specs/h5-oil-gas-assets/
 * Task: 3.2
 * Requirements: 2.8, 3.2
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：左侧(审定表/主表) - 右侧(明细/专项检查表) */
  diff: number
  /** 是否匹配（|diff| < 0.01） */
  isMatch: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 从 allResponses Map 中获取指定 item_id 的数值（尝试 remark → conclusion）。
 * NaN/null/undefined → 0
 */
function getNumFromMap(map: Map<string, any>, key: string): number {
  const item = map.get(key)
  if (!item) return 0
  const raw = item.remark ?? item.conclusion
  if (raw == null) return 0
  const n = Number(raw)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * H5 跨Sheet computed links：
 * - H5-1 审定表原值合计 ↔ H5-2 明细表期末原值合计
 * - H5-12 折耗测算本期计提 ↔ H5-1 累计折耗本期贷方发生
 * - H5-7 增加检查合计 ↔ H5-1 原值本期借方发生
 * - H5-8 减少检查合计 ↔ H5-1 原值本期贷方发生
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map（来自 useH5FormData）
 */
export function useH5CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  depletionVsAdjudication: ComputedRef<CrossSheetCheckResult>
  additionVsAdjudication: ComputedRef<CrossSheetCheckResult>
  disposalVsAdjudication: ComputedRef<CrossSheetCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: H5-1 审定合计 vs H5-2 明细期末合计（Req 2.8）═══

  /**
   * H5-1 审定表油气资产原值审定合计 与 H5-2 明细表原值期末合计交叉验证。
   * diff = H5-1 原值审定 total - H5-2 明细原值期末 subtotal
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 资产类：存在性是主要风险，审定表>明细需特别关注（多计资产）。
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('H5-1-cost-total')
    const detailSubtotal = getNum('H5-2-cost-total')
    const diff = adjTotal - detailSubtotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ depletionVsAdjudication: H5-12 折耗计提 vs H5-1 累计折耗本期贷方（Req 2.8）═══

  /**
   * H5-12 折耗测算表本期折耗计提合计 与 H5-1 审定表累计折耗区块本期贷方发生交叉验证。
   * diff = H5-1 累计折耗本期贷方 - H5-12 折耗计提合计
   * isMatch = |diff| < 0.01
   *
   * 差异>0 表示审定表贷方大于折耗测算（可能有其他折耗来源）；
   * 差异<0 表示审定表贷方小于折耗测算（折耗少计提，需查原因）。
   */
  const depletionVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjDepletionCredit = getNum('H5-1-depletion-credit')
    const depletionCalcTotal = getNum('H5-12-depletion-total')
    const diff = adjDepletionCredit - depletionCalcTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ additionVsAdjudication: H5-7 增加合计 vs H5-1 原值本期借方（Req 3.2）═══

  /**
   * H5-7 增加检查表本期增加合计 与 H5-1 审定表原值区块本期借方发生交叉验证。
   * diff = H5-1 原值本期借方 - H5-7 增加合计
   * isMatch = |diff| < 0.01
   *
   * 差异>0 表示审定表借方大于增加检查表合计（可能漏检增加项）；
   * 差异<0 表示增加检查表多于审定表借方（H5-7包含非本期项）。
   */
  const additionVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjCostDebit = getNum('H5-1-cost-debit')
    const additionTotal = getNum('H5-7-addition-total')
    const diff = adjCostDebit - additionTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ disposalVsAdjudication: H5-8 减少合计 vs H5-1 原值本期贷方（Req 3.2）═══

  /**
   * H5-8 减少检查表本期减少合计 与 H5-1 审定表原值区块本期贷方发生交叉验证。
   * diff = H5-1 原值本期贷方 - H5-8 减少合计
   * isMatch = |diff| < 0.01
   *
   * 差异>0 表示审定表贷方大于减少检查表合计（可能漏检处置项）；
   * 差异<0 表示减少检查表多于审定表贷方（H5-8包含转入/其他贷方）。
   */
  const disposalVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjCostCredit = getNum('H5-1-cost-credit')
    const disposalTotal = getNum('H5-8-disposal-total')
    const diff = adjCostCredit - disposalTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    depletionVsAdjudication,
    additionVsAdjudication,
    disposalVsAdjudication,
  }
}

export default useH5CrossSheet
