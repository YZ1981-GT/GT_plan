/**
 * useN1CrossSheet — N1 递延所得税资产跨sheet校验 + N3/N5跨底稿联动
 *
 * Spec: .kiro/specs/n1-deferred-tax-assets/
 * Task: 3.2
 * Requirements: 2.5, 2.6, 4.4, 4.6, 5.5, 7.1-7.5
 *
 * 职责：
 * 1. adjudicationVsDetail — N1-1审定表合计 vs N1-2明细表合计 交叉验证
 * 2. adjudicationVsCalcTable — N1-1审定确认额 vs N1-4测算结果 交叉验证
 * 3. lossCheckToCalcTable — N1-5可确认合计 → N1-4可弥补亏损行 回填校验
 * 4. n1ToN3Correspondence — N1-4测算表资产部分(N1) vs 负债部分(N3) 分列
 * 5. deferredTaxChange — 递延税资产期末-期初变动额，供N5核对递延所得税费用
 *
 * 联动方向：
 *   N1-1审定表合计 ↔ N1-2明细表合计（双向勾稽）
 *   N1-1审定确认额 ↔ N1-4测算结果（应相等）
 *   N1-5可确认合计 → N1-4可弥补亏损行
 *   N1-4资产部分 → N1-1（本底稿）; N1-4负债部分 → N3递延所得税负债
 *   N1-1本期变动额(期末-期初) → N5-8递延所得税费用核对
 *
 * 科目：1811 递延所得税资产（**借方/资产类**！取期末余额）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { parseNum } from './useN1FormulaEngine'
import type { ChecklistResponse } from './useN1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = N1-1审定表合计 - N1-2明细表合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** 审定表 vs 测算表 交叉验证结果 */
export interface AdjudicationVsCalcTableResult {
  /** 差额 = N1-1审定确认额 - N1-4测算结果(资产部分) */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** N1-5亏损可确认合计 → N1-4对应行 */
export interface LossCheckToCalcTableResult {
  /** N1-5可确认递延税资产合计 */
  total: number
}

/** N1-4测算表资产/负债分列（N1 vs N3对应） */
export interface N1ToN3CorrespondenceResult {
  /** 递延所得税资产部分（可抵扣暂时性差异×税率，归N1） */
  assetPart: number
  /** 递延所得税负债部分（应纳税暂时性差异×税率，归N3） */
  liabilityPart: number
}

/** 递延税资产本期变动额（供N5核对） */
export interface DeferredTaxChangeResult {
  /** 变动额 = 期末递延税资产 - 期初递延税资产 */
  change: number
}

/** 跨底稿引用定义 */
export interface CrossWpReference {
  /** 目标底稿编码 */
  targetWpCode: string
  /** 引用说明 */
  label: string
  /** 引用方向：from=从目标引入, to=输出到目标 */
  direction: 'from' | 'to'
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 浮点比较容差：|diff| < 0.01 视为匹配 */
const FLOAT_TOLERANCE = 0.01

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * N1 跨sheet校验引擎 + N3/N5跨底稿联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useN1FormData）
 */
export function useN1CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 1. adjudicationVsDetail — N1-1审定表合计 vs N1-2明细表合计 ─────────

  /**
   * N1-1 审定表递延所得税资产合计 应= N1-2 明细表期末递延税资产合计
   *
   * 数据来源：
   * - N1-1 审定表合计: item_id "N1-1-total-audited"（remark=审定期末余额合计）
   * - N1-2 明细表合计: item_id "N1-2-total-deferred-tax-asset"（remark=期末递延税资产合计）
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    const adjResp = allResponses.value.get('N1-1-total-audited')
    const adjTotal = parseNum(adjResp?.remark)

    const detailResp = allResponses.value.get('N1-2-total-deferred-tax-asset')
    const detailTotal = parseNum(detailResp?.remark)

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < FLOAT_TOLERANCE,
    }
  })

  // ─── 2. adjudicationVsCalcTable — N1-1审定确认额 vs N1-4测算结果 ───────

  /**
   * N1-1 审定表递延所得税资产确认额 应= N1-4 测算表递延税资产合计（资产部分）
   *
   * 数据来源：
   * - N1-1 审定确认额: item_id "N1-1-total-audited"（同上）
   * - N1-4 测算结果资产部分: item_id "N1-4-total-deferred-tax-asset"（remark=递延税资产合计）
   */
  const adjudicationVsCalcTable: ComputedRef<AdjudicationVsCalcTableResult> = computed(() => {
    const adjResp = allResponses.value.get('N1-1-total-audited')
    const adjTotal = parseNum(adjResp?.remark)

    const calcResp = allResponses.value.get('N1-4-total-deferred-tax-asset')
    const calcTotal = parseNum(calcResp?.remark)

    const diff = parseFloat((adjTotal - calcTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < FLOAT_TOLERANCE,
    }
  })

  // ─── 3. lossCheckToCalcTable — N1-5可确认合计 → N1-4可弥补亏损行 ───────

  /**
   * N1-5 可用以后年度税前利润弥补的亏损检查表 可确认递延税资产合计
   * 此值应回填到 N1-4 测算表的可弥补亏损行
   *
   * 数据来源：
   * - N1-5 可确认合计: item_id "N1-5-total-recognizable"（remark=可确认递延税资产合计）
   */
  const lossCheckToCalcTable: ComputedRef<LossCheckToCalcTableResult> = computed(() => {
    const lossResp = allResponses.value.get('N1-5-total-recognizable')
    const total = parseNum(lossResp?.remark)
    return { total }
  })

  // ─── 4. n1ToN3Correspondence — 测算表资产/负债分列 ─────────────────────

  /**
   * N1-4 测算表同源产出递延税资产/负债两部分：
   * - 可抵扣暂时性差异×税率 → 递延所得税资产（归N1）
   * - 应纳税暂时性差异×税率 → 递延所得税负债（归N3）
   *
   * 不能抵销的分列：
   * - 同一纳税主体的递延税资产与负债可抵销后净额列示
   * - 不同纳税主体不能抵销，需分别在 N1/N3 列示
   *
   * 数据来源：
   * - 资产部分: item_id "N1-4-total-deferred-tax-asset"（remark=可抵扣暂时性差异对应递延税资产）
   * - 负债部分: item_id "N1-4-total-deferred-tax-liability"（remark=应纳税暂时性差异对应递延税负债）
   */
  const n1ToN3Correspondence: ComputedRef<N1ToN3CorrespondenceResult> = computed(() => {
    const assetResp = allResponses.value.get('N1-4-total-deferred-tax-asset')
    const assetPart = parseNum(assetResp?.remark)

    const liabilityResp = allResponses.value.get('N1-4-total-deferred-tax-liability')
    const liabilityPart = parseNum(liabilityResp?.remark)

    return { assetPart, liabilityPart }
  })

  // ─── 5. deferredTaxChange — 期末-期初变动额供N5核对 ─────────────────────

  /**
   * 递延所得税资产本期变动额 = 期末递延税资产 - 期初递延税资产
   *
   * 供 N5-8 递延所得税费用核对表接收。
   * 递延所得税费用 = -(递延税资产期末-期初) + (递延税负债期末-期初)
   *
   * 数据来源：
   * - 期末: item_id "N1-1-total-audited"（remark=审定期末余额）
   * - 期初: item_id "N1-1-total-begin"（remark=期初余额合计）
   */
  const deferredTaxChange: ComputedRef<DeferredTaxChangeResult> = computed(() => {
    const endResp = allResponses.value.get('N1-1-total-audited')
    const endBalance = parseNum(endResp?.remark)

    const beginResp = allResponses.value.get('N1-1-total-begin')
    const beginBalance = parseNum(beginResp?.remark)

    const change = parseFloat((endBalance - beginBalance).toFixed(2))
    return { change }
  })

  // ─── 跨底稿引用定义 ────────────────────────────────────────────────────────

  /** N1 递延所得税资产 cross_wp_references */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'N3',
      label: 'N1-4测算表负债部分→N3递延所得税负债',
      direction: 'to',
    },
    {
      targetWpCode: 'N5',
      label: 'N1本期变动额→N5-8递延所得税费用核对',
      direction: 'to',
    },
    {
      targetWpCode: 'N3',
      label: 'N3递延所得税负债→N1-4同源暂时性差异',
      direction: 'from',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 跨sheet勾稽
    adjudicationVsDetail,
    adjudicationVsCalcTable,
    lossCheckToCalcTable,
    // 跨底稿联动
    n1ToN3Correspondence,
    deferredTaxChange,
    // 跨底稿引用
    crossWpReferences,
  }
}

export default useN1CrossSheet
