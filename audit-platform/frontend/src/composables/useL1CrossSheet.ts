/**
 * useL1CrossSheet — L1 短期借款跨sheet引擎 + L2/L8联动 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.2
 * Requirements: 2.5, 3.6, 5.4, 10.1-10.4
 *
 * 职责：
 * 1. adjudicationVsDetail — 审定表合计 vs 明细表合计 勾稽校验
 * 2. creditVsDetail — 征信核对表余额 vs 明细表合计 一致性
 * 3. interestToL2L8 — 利息测算结果打包，供 EventBus 发布到 L2/L8
 * 4. publishInterestCalculated — EventBus 发布 'l1:interest-calculated'
 *
 * 联动方向：L1-5利息测算 → L2应付利息（计提核对）/ L8财务费用（利息支出测算）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type {
  AdjudicationState,
  DetailRow,
  InterestCalcRow,
  CreditCheckRow,
} from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = 审定表合计endBalance - 明细表合计endBalance */
  diff: number
  /** 差额绝对值 ≤ 0.01 视为匹配 */
  isMatch: boolean
}

/** 征信核对 vs 明细表 一致性结果 */
export interface CreditVsDetailResult {
  /** 差额 = 征信倒轧余额合计 - 明细表endBalance合计 */
  diff: number
  /** 差额绝对值 ≤ 0.01 视为一致 */
  isConsistent: boolean
}

/** 利息测算 → L2/L8 联动载荷 */
export interface InterestToL2L8Result {
  /** 测算利息合计 */
  totalInterest: number
  /** 计入财务费用(L8)的利息（非资本化部分） */
  financialExpenseInterest: number
  /** 按合同明细 */
  byContract: Array<{ contractNo: string; interest: number }>
}

/** EventBus 'l1:interest-calculated' 载荷 */
export interface L1InterestCalculatedPayload {
  wpCode: string
  totalInterest: number
  financialExpenseInterest: number
  byContract: Array<{ contractNo: string; interest: number }>
  timestamp: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 勾稽匹配阈值（0.01元内视为匹配） */
const MATCH_THRESHOLD = 0.01

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1 跨sheet引擎 + L2/L8联动
 *
 * @param adjudicationData 审定表状态（含分类categories和total）
 * @param detailRows 明细表行数据
 * @param interestCalcRows 利息测算表行数据
 * @param creditCheckRows 征信核对表行数据
 * @param wpCode 底稿编码（如 'L1'）
 */
export function useL1CrossSheet(
  adjudicationData: Ref<AdjudicationState>,
  detailRows: Ref<DetailRow[]>,
  interestCalcRows: Ref<InterestCalcRow[]>,
  creditCheckRows: Ref<CreditCheckRow[]>,
  wpCode: string,
) {
  // ─── 上次发布的利息值（用于变化检测，仅变化时发布） ─────────────────────────
  const _lastPublishedInterest = ref<number | null>(null)

  // ─── 1. adjudicationVsDetail — 审定表合计 vs 明细表合计 勾稽校验 ─────────────

  /**
   * 审定表各分类 endBalance 合计 应= 明细表各行 endBalance 合计
   * 差额 = 审定表total.end - Σ(明细行.endBalance)
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计（取 total.end）
    const adjTotal = adjudicationData.value.total.end

    // 明细表合计（Σ endBalance）
    let detailTotal = 0
    for (const row of detailRows.value) {
      detailTotal += row.endBalance
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) <= MATCH_THRESHOLD,
    }
  })

  // ─── 2. creditVsDetail — 征信核对表余额 vs 明细表合计 一致性 ────────────────

  /**
   * 征信倒轧余额合计 应= 明细表 endBalance 合计
   * 差额 = Σ(征信行.creditBalance) - Σ(明细行.endBalance)
   */
  const creditVsDetail: ComputedRef<CreditVsDetailResult> = computed(() => {
    // 征信核对表：各行 creditBalance 合计
    let creditTotal = 0
    for (const row of creditCheckRows.value) {
      creditTotal += row.creditBalance
    }

    // 明细表合计
    let detailTotal = 0
    for (const row of detailRows.value) {
      detailTotal += row.endBalance
    }

    const diff = parseFloat((creditTotal - detailTotal).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= MATCH_THRESHOLD,
    }
  })

  // ─── 3. interestToL2L8 — 利息测算结果打包 ──────────────────────────────────

  /**
   * 汇总每笔借款的测算利息：
   * - totalInterest: Σ calculatedInterest
   * - financialExpenseInterest: 计入财务费用(L8)的利息（短期借款利息全部计入财务费用，非资本化）
   * - byContract: 按合同号明细
   *
   * 注：短期借款利息通常全部费用化（计入L8财务费用），不存在资本化部分。
   * 如有特殊资本化需求，需在 interestCalcRow 增加标记字段。
   */
  const interestToL2L8: ComputedRef<InterestToL2L8Result> = computed(() => {
    let totalInterest = 0
    const byContract: Array<{ contractNo: string; interest: number }> = []

    for (const row of interestCalcRows.value) {
      totalInterest += row.calculatedInterest
      if (row.contractNo) {
        byContract.push({
          contractNo: row.contractNo,
          interest: row.calculatedInterest,
        })
      }
    }

    // 短期借款利息全部费用化 → financialExpenseInterest = totalInterest
    return {
      totalInterest: parseFloat(totalInterest.toFixed(2)),
      financialExpenseInterest: parseFloat(totalInterest.toFixed(2)),
      byContract,
    }
  })

  // ─── 4. publishInterestCalculated — EventBus 发布 ──────────────────────────

  /**
   * 发布 'l1:interest-calculated' 事件到 EventBus。
   * 仅在值变化时发布（避免重复广播）。
   *
   * 载荷：wpCode / 总利息 / 按合同明细 / 时间戳
   * L2应付利息 订阅用于计提核对；L8财务费用 订阅用于利息支出测算。
   */
  function publishInterestCalculated(): void {
    const result = interestToL2L8.value
    const currentTotal = result.totalInterest

    // 仅在值变化时发布
    if (_lastPublishedInterest.value === currentTotal) return

    _lastPublishedInterest.value = currentTotal

    const payload: L1InterestCalculatedPayload = {
      wpCode,
      totalInterest: result.totalInterest,
      financialExpenseInterest: result.financialExpenseInterest,
      byContract: result.byContract,
      timestamp: Date.now(),
    }

    eventBus.emit('l1:interest-calculated', payload)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    creditVsDetail,
    interestToL2L8,
    publishInterestCalculated,
  }
}

export default useL1CrossSheet
