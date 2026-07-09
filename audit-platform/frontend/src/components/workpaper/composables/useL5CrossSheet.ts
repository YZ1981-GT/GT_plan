/**
 * useL5CrossSheet — L5 长期应付款跨sheet引擎 + L8联动
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 3.2
 * Requirements: 2.7, 3.6, 4.7, 8.4
 *
 * 职责：
 * 1. adjudicationVsDetail — L5-1审定表合计 vs L5-2明细表合计 勾稽校验
 * 2. unrecognizedVsAmortization — L5-3未确认融资费用合计 vs L5-5摊销表累计摊销 一致性
 * 3. amortizationToL8 — L5-5本期摊销合计，供 EventBus 发布到 L8财务费用
 * 4. publishAmortizationCalculated — EventBus 发布 'l5:amortization-calculated'
 *
 * 联动方向：L5-5本期摊销 → L8财务费用（利息支出/未确认融资费用摊销）
 *           L5-1审定表 ↔ L5-2明细表 双向合计勾稽
 *           L5-3未确认明细 ← L5-5摊销表 累计摊销校验
 *
 * 科目：2701 长期应付款（贷方/负债类！期末=期初+贷方-借方）
 *       未确认融资费用（借方/负债备抵类！期末=期初+借方-贷方）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useL5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = L5-1审定表合计审定数 - L5-2明细表合计期末余额 */
  diff: number
  /** |diff| < 阈值 视为匹配 */
  isMatch: boolean
}

/** 未确认融资费用明细 vs 摊销表 一致性结果 */
export interface UnrecognizedVsAmortizationResult {
  /** 差额 = L5-3未确认融资费用余额合计 - L5-5摊销表未摊销余额合计 */
  diff: number
  /** |diff| < 阈值 视为一致 */
  isMatch: boolean
}

/** 本期摊销 → L8 联动载荷 */
export interface AmortizationToL8Result {
  /** L5-5摊销测算表本期摊销合计（计入L8财务费用） */
  periodAmortization: number
}

/** EventBus 'l5:amortization-calculated' 载荷 */
export interface L5AmortizationCalculatedPayload {
  wpCode: string
  periodAmortization: number
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

/** 勾稽匹配阈值（1元内视为匹配，长期应付款金额大允许元级精度） */
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
 * L5 跨sheet引擎 + L8联动
 *
 * @param allResponses - 全部 checklist_responses（来自 useL5FormData）
 */
export function useL5CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 上次发布的摊销值（用于变化检测，仅变化时发布） ─────────────────────────
  const _lastPublishedAmortization = ref<number | null>(null)

  // ─── 1. adjudicationVsDetail — 审定表L5-1合计 vs 明细表L5-2合计 ─────────

  /**
   * L5-1 审定表长期应付款审定数合计 应= L5-2 明细表各行期末余额合计
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - L5-1 审定表合计存于 item_id: "L5-L5-1-adjudication-total"（remark=合计审定数）
   * - L5-2 明细表行数据存于 item_id: "L5-L5-2-rows"（remark=JSON数组，各行endBalance）
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：从 allResponses 读取审定表审定数合计
    const adjResp = allResponses.value.get('L5-L5-1-adjudication-total')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：从行数据汇总各行期末余额
    const detailResp = allResponses.value.get('L5-L5-2-rows')
    const detailRows = safeParseRows<{ endBalance?: number }>(detailResp?.remark)
    let detailTotal = 0
    for (const row of detailRows) {
      detailTotal += parseNum(row.endBalance)
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── 2. unrecognizedVsAmortization — L5-3未确认明细 vs L5-5摊销表 ───────

  /**
   * L5-3 未确认融资费用余额合计 应= L5-5 摊销表未摊销余额合计（一致性校验）
   * 差额 = L5-3未确认余额合计 - L5-5未摊销余额合计
   *
   * 正差异 = L5-3大于摊销表（摊销计算未覆盖全部未确认余额）
   * 负差异 = 摊销表大于L5-3（可能摊销台账未同步更新至L5-3明细）
   *
   * 数据来源：
   * - L5-3 未确认明细行数据存于 item_id: "L5-L5-3-rows"（remark=JSON数组，各行unrecognizedBalance）
   * - L5-5 摊销表当前未摊销余额存于 item_id: "L5-L5-5-unamortized-total"（remark=未摊销余额合计）
   */
  const unrecognizedVsAmortization: ComputedRef<UnrecognizedVsAmortizationResult> = computed(() => {
    // L5-3 未确认融资费用余额合计
    const unrecResp = allResponses.value.get('L5-L5-3-rows')
    const unrecRows = safeParseRows<{ unrecognizedBalance?: number }>(unrecResp?.remark)
    let unrecTotal = 0
    for (const row of unrecRows) {
      unrecTotal += parseNum(row.unrecognizedBalance)
    }

    // L5-5 摊销表未摊销余额合计
    const amortResp = allResponses.value.get('L5-L5-5-unamortized-total')
    const amortTotal = parseNum(amortResp?.remark)

    const diff = parseFloat((unrecTotal - amortTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── 3. amortizationToL8 — L5-5本期摊销合计 → L8财务费用联动 ──────────────

  /**
   * 汇总L5-5摊销测算表本期（当期）摊销合计。
   * 此值用于：
   * - L8财务费用 — 未确认融资费用摊销计入利息支出（订阅 'l5:amortization-calculated'）
   *
   * 数据来源：
   * - L5-5 摊销表行数据存于 item_id: "L5-L5-5-schedule-rows"（remark=JSON数组）
   *   每行包含 amortization 字段（各期摊销额=期初摊余成本×实际利率）
   *   以及 isCurrent 字段标记是否为本期
   *
   * 注：若无 isCurrent 标记，则取 item_id: "L5-L5-5-period-amortization" 直接获取本期摊销合计
   */
  const amortizationToL8: ComputedRef<AmortizationToL8Result> = computed(() => {
    // 优先读取 本期摊销合计（直接值）
    const periodResp = allResponses.value.get('L5-L5-5-period-amortization')
    if (periodResp?.remark) {
      const direct = parseNum(periodResp.remark)
      if (direct !== 0) {
        return { periodAmortization: parseFloat(direct.toFixed(2)) }
      }
    }

    // 降级：从摊销表行数据中筛选 isCurrent=true 的行汇总
    const scheduleResp = allResponses.value.get('L5-L5-5-schedule-rows')
    const scheduleRows = safeParseRows<{ amortization?: number; isCurrent?: boolean }>(scheduleResp?.remark)

    let periodAmortization = 0
    for (const row of scheduleRows) {
      if (row.isCurrent) {
        periodAmortization += parseNum(row.amortization)
      }
    }

    return {
      periodAmortization: parseFloat(periodAmortization.toFixed(2)),
    }
  })

  // ─── 4. publishAmortizationCalculated — EventBus 发布 ──────────────────────

  /**
   * 发布 'l5:amortization-calculated' 事件到 EventBus。
   * 仅在值变化时发布（避免重复广播）。
   *
   * 载荷：wpCode / 本期摊销 / 时间戳
   * L8财务费用 订阅用于利息支出/摊销计入。
   */
  function publishAmortizationCalculated(): void {
    const result = amortizationToL8.value
    const currentTotal = result.periodAmortization

    // 仅在值变化时发布
    if (_lastPublishedAmortization.value === currentTotal) return
    _lastPublishedAmortization.value = currentTotal

    const payload: L5AmortizationCalculatedPayload = {
      wpCode: 'L5',
      periodAmortization: result.periodAmortization,
      timestamp: Date.now(),
    }

    eventBus.emit('l5:amortization-calculated', payload)
  }

  // ─── 5. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** L5 长期应付款 cross_wp_references（关联 L8） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'L8',
      label: 'L8财务费用-未确认融资费用本期摊销',
      direction: 'to',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    unrecognizedVsAmortization,
    // L8联动
    amortizationToL8,
    publishAmortizationCalculated,
    // 跨底稿引用
    crossWpReferences,
  }
}

export default useL5CrossSheet
