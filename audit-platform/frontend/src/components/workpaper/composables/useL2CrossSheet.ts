/**
 * useL2CrossSheet — L2 应付利息跨sheet引擎 + L1/L3/L8联动
 *
 * Spec: .kiro/specs/l2-interest-payable/
 * Task: 3.2
 * Requirements: 2.5, 4.1-4.6
 *
 * 职责：
 * 1. adjudicationVsDetail — L2-1审定表合计 vs L2-2明细表合计 勾稽校验
 * 2. accrualVsL1L3 — L1/L3利息测算 vs L2账面计提 一致性核对
 * 3. EventBus订阅 — 监听 'l1:interest-calculated' / 'l3:interest-calculated'
 * 4. cross_wp_references — 跨底稿引用定义（L1, L3, L8）
 *
 * 联动方向：L1短期借款利息测算 + L3长期借款利息测算 → L2计提核对
 *           L2本期计提 → L8财务费用
 *
 * 科目：2231 应付利息（贷方/负债类）
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useL2FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** L1 利息测算载荷（来自 useL1CrossSheet.publishInterestCalculated） */
export interface L1InterestPayload {
  wpCode: string
  totalInterest: number
  financialExpenseInterest: number
  byContract: Array<{ contractNo: string; interest: number }>
  timestamp: number
}

/** L3 利息测算载荷（来自 L3 利息测算引擎） */
export interface L3InterestPayload {
  wpCode: string
  totalInterest: number
  financialExpenseInterest: number
  byContract: Array<{ contractNo: string; interest: number }>
  timestamp: number
}

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = 审定表合计 - 明细表合计 */
  diff: number
  /** 差额绝对值 ≤ 阈值 视为匹配 */
  isMatch: boolean
}

/** 计提核对 vs L1/L3 一致性结果 */
export interface AccrualVsL1L3Result {
  /** 差额 = L1/L3测算利息合计 - L2账面计提合计 */
  diff: number
  /** |差额| < 阈值 视为一致 */
  isConsistent: boolean
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

/** 勾稽匹配阈值（0.01元内视为匹配） */
const MATCH_THRESHOLD = 0.01

/** 计提核对一致性阈值（1元内视为一致，利息计算可能有四舍五入差异） */
const ACCRUAL_CONSISTENCY_THRESHOLD = 1.0

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全解析数字，NaN/null/undefined → 0
 */
function parseNum(v: any): number {
  if (v == null) return 0
  const n = Number(v)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L2 跨sheet引擎 + L1/L3/L8联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useL2FormData）
 */
export function useL2CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── L1/L3 利息测算接收状态 ────────────────────────────────────────────

  const l1InterestData = ref<L1InterestPayload | null>(null)
  const l3InterestData = ref<L3InterestPayload | null>(null)

  // ─── EventBus 订阅：l1:interest-calculated ─────────────────────────────

  function onL1InterestCalculated(payload: L1InterestPayload): void {
    l1InterestData.value = payload
  }

  // 订阅 mitt eventBus（L1 已注册类型）
  eventBus.on('l1:interest-calculated', onL1InterestCalculated as any)

  // ─── EventBus 订阅：l3:interest-calculated（mitt 类型安全） ─────────────

  function onL3InterestCalculated(payload: L3InterestPayload): void {
    l3InterestData.value = payload
  }

  // L3 已在 mitt Events 类型中注册（l2-interest-payable Task 6.1）
  eventBus.on('l3:interest-calculated', onL3InterestCalculated as any)

  // ─── 1. adjudicationVsDetail — 审定表L2-1合计 vs 明细表L2-2合计 ────────

  /**
   * L2-1 审定表各来源期末合计 应= L2-2 明细表各行期末合计
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - L2-1 审定表合计存于 item_id: "L2-L2-1-adjudication-total"
   * - L2-2 明细表行数据存于 item_id: "L2-L2-2-rows"
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：从 allResponses 读取审定表期末合计
    const adjResp = allResponses.value.get('L2-L2-1-adjudication-total')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：从行数据汇总期末应付
    const detailResp = allResponses.value.get('L2-L2-2-rows')
    const detailRows = safeParseRows<{ endBalance?: number }>(detailResp?.remark)
    let detailTotal = 0
    for (const row of detailRows) {
      detailTotal += parseNum(row.endBalance)
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) <= MATCH_THRESHOLD,
    }
  })

  // ─── 2. accrualVsL1L3 — L1/L3测算利息 vs L2账面计提 一致性 ────────────

  /**
   * L1短期借款 + L3长期借款 利息测算合计 vs L2-2 明细表本期计提合计
   * 差额 = 测算利息合计 - 账面计提合计
   *
   * 正值=账面少计提（应补提），负值=账面多计提（应冲回）
   */
  const accrualVsL1L3: ComputedRef<AccrualVsL1L3Result> = computed(() => {
    // L1/L3 测算利息合计
    const l1Total = l1InterestData.value?.totalInterest ?? 0
    const l3Total = l3InterestData.value?.totalInterest ?? 0
    const estimatedTotal = l1Total + l3Total

    // L2-2 明细表本期计提合计
    const detailResp = allResponses.value.get('L2-L2-2-rows')
    const detailRows = safeParseRows<{ accrued?: number }>(detailResp?.remark)
    let bookedTotal = 0
    for (const row of detailRows) {
      bookedTotal += parseNum(row.accrued)
    }

    const diff = parseFloat((estimatedTotal - bookedTotal).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= ACCRUAL_CONSISTENCY_THRESHOLD,
    }
  })

  // ─── 3. 辅助 computed ─────────────────────────────────────────────────

  /** L1/L3 利息测算是否已就绪（至少一方已推送数据） */
  const isInterestDataReady = computed<boolean>(() => {
    return l1InterestData.value !== null || l3InterestData.value !== null
  })

  /** L1 测算利息金额 */
  const l1EstimatedInterest = computed<number>(() => {
    return l1InterestData.value?.totalInterest ?? 0
  })

  /** L3 测算利息金额 */
  const l3EstimatedInterest = computed<number>(() => {
    return l3InterestData.value?.totalInterest ?? 0
  })

  // ─── 4. 跨底稿引用定义 ────────────────────────────────────────────────

  /** L2 应付利息 cross_wp_references（关联 L1, L3, L8） */
  const cross_wp_references: CrossWpReference[] = [
    {
      targetWpCode: 'L1',
      label: 'L1短期借款利息测算',
      direction: 'from',
    },
    {
      targetWpCode: 'L3',
      label: 'L3长期借款利息测算',
      direction: 'from',
    },
    {
      targetWpCode: 'L8',
      label: 'L8财务费用-利息支出',
      direction: 'to',
    },
  ]

  // ─── Cleanup on scope dispose ──────────────────────────────────────────

  onScopeDispose(() => {
    // 取消 mitt eventBus 订阅
    eventBus.off('l1:interest-calculated', onL1InterestCalculated as any)
    eventBus.off('l3:interest-calculated', onL3InterestCalculated as any)
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    accrualVsL1L3,
    // L1/L3 数据状态
    l1InterestData,
    l3InterestData,
    l1EstimatedInterest,
    l3EstimatedInterest,
    isInterestDataReady,
    // 跨底稿引用
    cross_wp_references,
  }
}

export default useL2CrossSheet
