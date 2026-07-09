/**
 * useL4CrossSheet — L4 应付债券跨sheet引擎 + L2/L8联动
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Task: 3.2
 * Requirements: 2.5, 5.4, 11.1-11.4
 *
 * 职责：
 * 1. adjudicationVsDetail — L4-1审定表合计 vs L4-2明细表合计 勾稽校验
 * 2. bookReconVsSubsequent — L4-8账面摊余成本 vs L4-7测算摊余成本 一致性
 * 3. interestToL2L8 — L4-7后续计量利息费用合计，供 EventBus 发布到 L2/L8
 * 4. publishInterestCalculated — EventBus 发布 'l4:interest-calculated'
 *
 * 联动方向：L4-7实际利息费用 → L2应付利息（计提核对）/ L8财务费用（利息支出）
 *           L4-1审定表 ↔ L4-2明细表 双向合计勾稽
 *           L4-8账面核对 ← L4-7后续计量测算摊余成本
 *
 * 科目：2502 应付债券（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useL4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = L4-1审定表合计审定数 - L4-2明细表合计审定数 */
  diff: number
  /** |diff| < 1 视为匹配（元级精度） */
  isMatch: boolean
}

/** 账面核对 vs 后续计量 一致性结果 */
export interface BookReconVsSubsequentResult {
  /** 差额 = L4-8账面摊余成本 - L4-7测算摊余成本 */
  diff: number
  /** |diff| < threshold(1) 视为匹配 */
  isMatch: boolean
}

/** 利息费用 → L2/L8 联动载荷 */
export interface InterestToL2L8Result {
  /** L4-7后续计量表全部期间实际利息费用合计 */
  totalInterest: number
}

/** EventBus 'l4:interest-calculated' 载荷 */
export interface L4InterestCalculatedPayload {
  wpCode: string
  totalInterest: number
  timestamp: number
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

/** 勾稽匹配阈值（1元内视为匹配，应付债券金额大精度低于L3） */
const MATCH_THRESHOLD = 1

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
 * L4 跨sheet引擎 + L2/L8联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useL4FormData）
 */
export function useL4CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 上次发布的利息值（用于变化检测，仅变化时发布） ─────────────────────────
  const _lastPublishedInterest = ref<number | null>(null)

  // ─── 1. adjudicationVsDetail — 审定表L4-1合计 vs 明细表L4-2合计 ─────────

  /**
   * L4-1 审定表合计审定数 应= L4-2 明细表合计审定数
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - L4-1 审定表合计存于 item_id: "L4-L4-1-adjudication-total"（remark=合计审定数）
   * - L4-2 明细表行数据存于 item_id: "L4-L4-2-rows"（remark=JSON数组，各行auditedAmount）
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：从 allResponses 读取审定表审定数合计
    const adjResp = allResponses.value.get('L4-L4-1-adjudication-total')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：从行数据汇总各行审定数
    const detailResp = allResponses.value.get('L4-L4-2-rows')
    const detailRows = safeParseRows<{ auditedAmount?: number }>(detailResp?.remark)
    let detailTotal = 0
    for (const row of detailRows) {
      detailTotal += parseNum(row.auditedAmount)
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── 2. bookReconVsSubsequent — L4-8账面摊余成本 vs L4-7测算摊余成本 ─────

  /**
   * L4-8 账面核对的"账面摊余成本"应≈ L4-7后续计量的"测算摊余成本"（期末值）
   * 差额 = 账面摊余成本 - 测算摊余成本
   *
   * 正差异=账面大于测算（可能未充分摊销/少确认利息费用）
   * 负差异=账面小于测算（可能多确认利息费用）
   *
   * 数据来源：
   * - L4-8 账面摊余成本合计存于 item_id: "L4-L4-8-book-amortized-cost"（remark=金额）
   * - L4-7 测算摊余成本合计存于 item_id: "L4-L4-7-calculated-amortized-cost"（remark=金额）
   */
  const bookReconVsSubsequent: ComputedRef<BookReconVsSubsequentResult> = computed(() => {
    const bookResp = allResponses.value.get('L4-L4-8-book-amortized-cost')
    const bookCost = parseNum(bookResp?.remark)

    const calcResp = allResponses.value.get('L4-L4-7-calculated-amortized-cost')
    const calcCost = parseNum(calcResp?.remark)

    const diff = parseFloat((bookCost - calcCost).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── 3. interestToL2L8 — L4-7利息费用合计 → L2/L8联动 ────────────────────

  /**
   * 汇总L4-7后续计量表全部期间的实际利息费用（interestExpense）。
   * 此合计值用于：
   * - L2应付利息 — 计提核对（订阅 'l4:interest-calculated'）
   * - L8财务费用 — 利息支出测算（订阅 'l4:interest-calculated'）
   *
   * 数据来源：
   * - L4-7 后续计量摊销表行数据存于 item_id: "L4-L4-7-schedule-rows"（remark=JSON数组）
   *   每行包含 interestExpense 字段（各期实际利息费用=期初摊余成本×EIR）
   */
  const interestToL2L8: ComputedRef<InterestToL2L8Result> = computed(() => {
    const scheduleResp = allResponses.value.get('L4-L4-7-schedule-rows')
    const scheduleRows = safeParseRows<{ interestExpense?: number }>(scheduleResp?.remark)

    let totalInterest = 0
    for (const row of scheduleRows) {
      totalInterest += parseNum(row.interestExpense)
    }

    return {
      totalInterest: parseFloat(totalInterest.toFixed(2)),
    }
  })

  // ─── 4. publishInterestCalculated — EventBus 发布 ──────────────────────────

  /**
   * 发布 'l4:interest-calculated' 事件到 EventBus。
   * 仅在值变化时发布（避免重复广播）。
   *
   * 载荷：wpCode / 总利息 / 时间戳
   * L2应付利息 订阅用于计提核对；L8财务费用 订阅用于利息支出测算。
   */
  function publishInterestCalculated(): void {
    const result = interestToL2L8.value
    const currentTotal = result.totalInterest

    // 仅在值变化时发布
    if (_lastPublishedInterest.value === currentTotal) return
    _lastPublishedInterest.value = currentTotal

    const payload: L4InterestCalculatedPayload = {
      wpCode: 'L4',
      totalInterest: result.totalInterest,
      timestamp: Date.now(),
    }

    eventBus.emit('l4:interest-calculated', payload)
  }

  // ─── 5. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** L4 应付债券 cross_wp_references（关联 L2, L8） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'L2',
      label: 'L2应付利息-实际利率法利息计提核对',
      direction: 'to',
    },
    {
      targetWpCode: 'L8',
      label: 'L8财务费用-应付债券利息支出',
      direction: 'to',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    bookReconVsSubsequent,
    // L2/L8联动
    interestToL2L8,
    publishInterestCalculated,
    // 跨底稿引用
    crossWpReferences,
  }
}

export default useL4CrossSheet
