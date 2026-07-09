/**
 * useH9CrossSheet — H9 租赁负债跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('H9-{item_id}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射：
 * - H9-1 审定合计 vs H9-2 明细合计（Req 2.6）
 * - H9 初始确认 vs H8 联动校验（CAS21核心：H9初始≈H8初始-直接费用+激励，±1元容差）（Req 2.7, 8.1-8.4）
 * - H9-4 摊销表利息合计 vs H9-1 审定表本期利息（Req 4.8）
 *
 * 科目：2205租赁负债（贷方/负债类）+ 未确认融资费用（借方/负债备抵类）
 * CAS21：H8使用权资产 = H9租赁负债初始确认 + 初始直接费用 - 租赁激励
 *        即 H9初始确认 = H8初始计量 - 直接费用 + 激励
 *
 * Spec: .kiro/specs/h9-lease-liabilities/
 * Task: 3.2
 * Requirements: 2.6, 2.7, 4.8, 8.1-8.4
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 跨sheet校验结果（通用，±1元容差） */
export interface CrossSheetCheck {
  /** 差额（来源A - 来源B） */
  diff: number
  /** 是否匹配（|diff| <= 1） */
  isMatch: boolean
}

/** H9-H8联动校验结果 */
export interface H9H8LinkageCheck {
  /** 差额：H9初始确认 - expected（expected = H8初始 - 直接费用 + 激励） */
  diff: number
  /** 是否一致（CAS21允许±1元尾差容差） */
  isConsistent: boolean
  /** 校验说明消息 */
  message: string
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

/**
 * 从 allResponses 获取指定 item_id 的数值（存储在 remark 字段）
 */
function _getResponseNum(allResponses: Map<string, any>, itemId: string): number {
  const resp = allResponses.get(itemId)
  if (!resp) return 0
  const raw = resp.remark ?? resp.conclusion
  return _getNum(raw)
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useH9CrossSheet(allResponses: Ref<Map<string, any>>) {
  // ═══════════════════════════════════════════════════════════════════════════
  // 1. adjudicationVsDetail — H9-1审定合计 vs H9-2明细合计（Req 2.6）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H9-1 审定表租赁负债合计（审定数） 与 H9-2 明细表合计的交叉验证。
   * 两者应一致（±1元容差），不一致时显示警告。
   *
   * 公式：diff = H9-1审定合计 - H9-2明细审定合计
   * isMatch: |diff| <= 1
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheck> = computed(() => {
    const map = allResponses.value
    const adjudicationTotal = _getResponseNum(map, 'H9-1-liability-total-audited')
    const detailTotal = _getResponseNum(map, 'H9-2-detail-total-audited')
    const diff = adjudicationTotal - detailTotal
    return {
      diff,
      isMatch: Math.abs(diff) <= 1,
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 2. h9VsH8Linkage — H9初始确认 vs H8联动（CAS21核心，Req 2.7, 8.1-8.4）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * CAS21核心联动验证（从H9视角）：
   * H9初始确认金额 ≈ H8初始计量 - 初始直接费用 + 租赁激励
   *
   * 验证公式：
   * expected = h8Initial - directCost + incentive
   * diff = h9Initial - expected
   * isConsistent: |diff| ≤ 1（允许±1元尾差容差，四舍五入差异）
   *
   * 数据源：
   * - H9-initial-recognition: H9租赁负债初始确认金额
   * - H9-h8-initial-measurement: H8初始计量（从H8-1或H8-2汇总跨底稿传入）
   * - H9-h8-direct-cost: H8初始直接费用
   * - H9-h8-incentive: H8租赁激励
   */
  const h9VsH8Linkage: ComputedRef<H9H8LinkageCheck> = computed(() => {
    const map = allResponses.value
    const h9Initial = _getResponseNum(map, 'H9-initial-recognition')
    const h8Initial = _getResponseNum(map, 'H9-h8-initial-measurement')
    const directCost = _getResponseNum(map, 'H9-h8-direct-cost')
    const incentive = _getResponseNum(map, 'H9-h8-incentive')

    // CAS21: H9初始确认 = H8初始 - 直接费用 + 激励
    const expected = h8Initial - directCost + incentive
    const diff = h9Initial - expected

    // CAS21允许尾差±1元（实务中四舍五入差异）
    const isConsistent = Math.abs(diff) <= 1

    // 生成校验消息
    let message: string
    if (h9Initial === 0 && h8Initial === 0) {
      message = 'H8/H9数据未加载，暂无法校验'
    } else if (isConsistent) {
      message = 'H9与H8联动一致（CAS21：H9初始≈H8初始-直接费用+激励）'
    } else {
      message = `H9与H8不一致，差额：${diff.toFixed(2)}元（H9初始=${h9Initial.toFixed(2)}，H8初始=${h8Initial.toFixed(2)}，直接费用=${directCost.toFixed(2)}，激励=${incentive.toFixed(2)}）`
    }

    return { diff, isConsistent, message }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 3. amortizationVsAdjudication — H9-4摊销表利息合计 vs H9-1本期利息（Req 4.8）
  // ═══════════════════════════════════════════════════════════════════════════

  /**
   * H9-4 摊销表全部期数利息费用合计 与 H9-1 审定表本期利息费用的交叉验证。
   * 摊销表当期确认的利息费用应等于审定表中的利息支出审定数。
   *
   * 公式：diff = H9-4摊销表本期利息合计 - H9-1审定表本期利息
   * isMatch: |diff| <= 1
   */
  const amortizationVsAdjudication: ComputedRef<CrossSheetCheck> = computed(() => {
    const map = allResponses.value
    const amortTotalInterest = _getResponseNum(map, 'H9-amort-total-interest')
    const adjInterestExpense = _getResponseNum(map, 'H9-1-interest-expense-audited')
    const diff = amortTotalInterest - adjInterestExpense
    return {
      diff,
      isMatch: Math.abs(diff) <= 1,
    }
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // 辅助 computed（供子组件直接使用）
  // ═══════════════════════════════════════════════════════════════════════════

  /** H9-1 审定表租赁负债审定合计 */
  const adjudicationTotal = computed<number>(() => {
    return _getResponseNum(allResponses.value, 'H9-1-liability-total-audited')
  })

  /** H9-2 明细表审定合计 */
  const detailTotal = computed<number>(() => {
    return _getResponseNum(allResponses.value, 'H9-2-detail-total-audited')
  })

  /** H9-4 摊销表本期利息合计 */
  const amortInterestTotal = computed<number>(() => {
    return _getResponseNum(allResponses.value, 'H9-amort-total-interest')
  })

  /** H9-1 审定表本期利息费用审定数 */
  const adjInterestExpense = computed<number>(() => {
    return _getResponseNum(allResponses.value, 'H9-1-interest-expense-audited')
  })

  /** H9 初始确认金额 */
  const h9InitialRecognition = computed<number>(() => {
    return _getResponseNum(allResponses.value, 'H9-initial-recognition')
  })

  // ═══════════════════════════════════════════════════════════════════════════
  // Return
  // ═══════════════════════════════════════════════════════════════════════════

  return {
    // H9-1审定合计 vs H9-2明细合计（Req 2.6）
    adjudicationVsDetail,
    // H9初始确认 vs H8联动（CAS21核心，Req 2.7, 8.1-8.4）
    h9VsH8Linkage,
    // H9-4摊销表利息合计 vs H9-1本期利息（Req 4.8）
    amortizationVsAdjudication,
    // 辅助 computed（供子组件直接使用）
    adjudicationTotal,
    detailTotal,
    amortInterestTotal,
    adjInterestExpense,
    h9InitialRecognition,
  }
}

export default useH9CrossSheet
