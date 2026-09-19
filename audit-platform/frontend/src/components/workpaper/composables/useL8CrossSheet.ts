/**
 * useL8CrossSheet — L8 财务费用跨sheet校验引擎 + L1/L3/L4/L5利息汇聚
 *
 * Spec: .kiro/specs/l8-financial-expenses/
 * Task: 3.2
 * Requirements: 2.5, 3.6, 4.1-4.8
 *
 * 职责：
 * 1. adjudicationVsDetail — L8-1审定表合计 vs L8-2明细表合计 交叉验证
 * 2. interestFromLCycle — 订阅L1/L3/L4/L5 EventBus利息数据，汇总各来源利息
 * 3. estimatedVsBooked — 测算利息支出(来自L循环) vs 账面利息支出(L8-2) 一致性校验
 *
 * 联动方向：
 *   L1短期借款 → 'l1:interest-calculated'   → interestFromLCycle.l1
 *   L3长期借款 → 'l3:interest-calculated'   → interestFromLCycle.l3
 *   L4应付债券 → 'l4:interest-calculated'   → interestFromLCycle.l4
 *   L5长期应付款 → 'l5:amortization-calculated' → interestFromLCycle.l5
 *   L8-1审定表合计 ↔ L8-2明细表合计 双向勾稽
 *
 * 科目：6603 财务费用（借方/损益类！取发生额）
 *
 * L8是L筹资循环利息汇聚终点，接收L1/L3/L4利息测算 + L5未确认融资费用摊销。
 */
import { computed, ref, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { aggregateInterest, calcInterestDiff } from './useL8InterestEngine'
import type { ChecklistResponse } from './useL8FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = L8-1审定表合计发生额 - L8-2明细表费用项目合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

/** L循环各来源利息汇聚结果 */
export interface InterestFromLCycleResult {
  /** L1短期借款利息 */
  l1: number
  /** L3长期借款利息 */
  l3: number
  /** L4应付债券利息费用 */
  l4: number
  /** L5未确认融资费用摊销 */
  l5: number
  /** 测算利息支出合计 = l1+l3+l4+l5 */
  total: number
}

/** 测算利息 vs 账面利息 一致性校验结果 */
export interface EstimatedVsBookedResult {
  /** 差额 = 测算利息合计 - 账面利息支出 */
  diff: number
  /** |diff| < 阈值视为一致 */
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

/** 审定-明细勾稽匹配阈值（1元内） */
const MATCH_THRESHOLD = 1

/** 测算vs账面利息一致性阈值（100元，利息测算允许小额四舍五入误差） */
const INTEREST_CONSISTENCY_THRESHOLD = 100

// ─── Helpers ─────────────────────────────────────────────────────────────────

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
 * L8 跨sheet校验引擎 + L1/L3/L4/L5利息汇聚
 *
 * @param allResponses - 全部 checklist_responses（来自 useL8FormData）
 */
export function useL8CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── EventBus 订阅的利息数据（reactive refs） ──────────────────────────────

  /** L1短期借款利息（订阅 'l1:interest-calculated'） */
  const _l1Interest = ref(0)
  /** L3长期借款利息（订阅 'l3:interest-calculated'） */
  const _l3Interest = ref(0)
  /** L4应付债券利息费用（订阅 'l4:interest-calculated'） */
  const _l4Interest = ref(0)
  /** L5未确认融资费用摊销（订阅 'l5:amortization-calculated'） */
  const _l5Amortization = ref(0)

  // ─── EventBus 订阅 handlers ─────────────────────────────────────────────

  /**
   * L1短期借款利息测算完成
   * 载荷: { wpCode, totalInterest, financialExpenseInterest, byContract, timestamp }
   * 取 financialExpenseInterest（计入财务费用的利息）
   */
  function _onL1InterestCalculated(payload: any): void {
    _l1Interest.value = parseNum(payload?.financialExpenseInterest ?? payload?.totalInterest)
  }

  /**
   * L3长期借款利息测算完成
   * 载荷: { wpCode, totalInterest, financialExpenseInterest, byContract, timestamp }
   * 取 financialExpenseInterest（计入财务费用的利息）
   */
  function _onL3InterestCalculated(payload: any): void {
    _l3Interest.value = parseNum(payload?.financialExpenseInterest ?? payload?.totalInterest)
  }

  /**
   * L4应付债券利息费用完成
   * 载荷: { wpCode, periodInterest, totalInterest, timestamp }
   * 取 periodInterest（本期利息费用计入财务费用）
   */
  function _onL4InterestCalculated(payload: any): void {
    _l4Interest.value = parseNum(payload?.periodInterest ?? payload?.totalInterest)
  }

  /**
   * L5未确认融资费用本期摊销完成
   * 载荷: { wpCode, periodAmortization, timestamp }
   * 取 periodAmortization（计入财务费用）
   */
  function _onL5AmortizationCalculated(payload: any): void {
    _l5Amortization.value = parseNum(payload?.periodAmortization)
  }

  // ─── 订阅 EventBus ─────────────────────────────────────────────────────────

  eventBus.on('l1:interest-calculated', _onL1InterestCalculated)
  eventBus.on('l3:interest-calculated', _onL3InterestCalculated)
  eventBus.on('l4:interest-calculated', _onL4InterestCalculated)
  eventBus.on('l5:amortization-calculated', _onL5AmortizationCalculated)

  // ─── 初始化：从 allResponses 读取已持久化的利息数据 ─────────────────────────

  /**
   * 从 checklist_responses 恢复上次保存的利息数据
   * （EventBus 仅同会话有效，需要从持久化数据恢复）
   */
  function _restoreFromResponses(): void {
    const l1Resp = allResponses.value.get('L8-cross-l1-interest')
    if (l1Resp?.remark) _l1Interest.value = parseNum(l1Resp.remark)

    const l3Resp = allResponses.value.get('L8-cross-l3-interest')
    if (l3Resp?.remark) _l3Interest.value = parseNum(l3Resp.remark)

    const l4Resp = allResponses.value.get('L8-cross-l4-interest')
    if (l4Resp?.remark) _l4Interest.value = parseNum(l4Resp.remark)

    const l5Resp = allResponses.value.get('L8-cross-l5-amortization')
    if (l5Resp?.remark) _l5Amortization.value = parseNum(l5Resp.remark)
  }

  // 初次恢复
  _restoreFromResponses()

  // ─── 1. adjudicationVsDetail — 审定表L8-1合计 vs 明细表L8-2合计 ─────────

  /**
   * L8-1 审定表本期发生额合计 应= L8-2 明细表各费用项目发生额之和
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - L8-1 审定表合计存于 item_id: "L8-1-total-audited"（remark=本期审定发生额合计）
   * - L8-2 明细表各费用项目存于 item_id: "L8-2-netFinExpense"（remark=净财务费用合计）
   *   或遍历 "L8-2-*-occurrence" 模式累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：L8-1合计本期审定发生额
    const adjResp = allResponses.value.get('L8-1-total-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取净财务费用合计（L8-2汇总行）
    const detailNetResp = allResponses.value.get('L8-2-netFinExpense')
    let detailTotal = parseNum(detailNetResp?.remark)

    // 降级：如果净额合计无值，遍历明细项目发生额累加
    if (detailTotal === 0 && !detailNetResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('L8-2-') && key.endsWith('-occurrence')) {
          detailTotal += parseNum(resp.remark)
        }
      }
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── 2. interestFromLCycle — L循环利息汇聚 ─────────────────────────────────

  /**
   * 汇总L1/L3/L4/L5各来源利息（测算利息支出合计）
   *
   * 来源：
   * - _l1Interest: EventBus 'l1:interest-calculated' 或持久化恢复
   * - _l3Interest: EventBus 'l3:interest-calculated' 或持久化恢复
   * - _l4Interest: EventBus 'l4:interest-calculated' 或持久化恢复
   * - _l5Amortization: EventBus 'l5:amortization-calculated' 或持久化恢复
   */
  const interestFromLCycle: ComputedRef<InterestFromLCycleResult> = computed(() => {
    const l1 = _l1Interest.value
    const l3 = _l3Interest.value
    const l4 = _l4Interest.value
    const l5 = _l5Amortization.value
    const total = aggregateInterest(l1, l3, l4, l5)
    return { l1, l3, l4, l5, total }
  })

  // ─── 3. estimatedVsBooked — 测算利息 vs 账面利息 ───────────────────────────

  /**
   * 测算利息支出合计(L循环汇聚) vs 账面利息支出(L8-2明细表利息支出行)
   * 差额 = 测算合计 - 账面利息支出
   *
   * 正差异 = 测算>账面（可能有利息未入账，关注完整性）
   * 负差异 = 账面>测算（可能多计利息或来源底稿未完成测算）
   *
   * 数据来源：
   * - 测算利息: interestFromLCycle.total
   * - 账面利息支出: item_id "L8-2-interestExp-occurrence"（利息支出明细行本期发生额）
   */
  const estimatedVsBooked: ComputedRef<EstimatedVsBookedResult> = computed(() => {
    const estimated = interestFromLCycle.value.total

    // 账面利息支出：从L8-2明细表利息支出行读取
    const bookedResp = allResponses.value.get('L8-2-interestExp-occurrence')
    const booked = parseNum(bookedResp?.remark)

    const diff = calcInterestDiff(estimated, booked)
    return {
      diff: parseFloat(diff.toFixed(2)),
      isConsistent: Math.abs(diff) < INTEREST_CONSISTENCY_THRESHOLD,
    }
  })

  // ─── 5. 跨底稿引用定义 ────────────────────────────────────────────────────

  /** L8 财务费用 cross_wp_references（关联 L1/L3/L4/L5） */
  const crossWpReferences: CrossWpReference[] = [
    {
      targetWpCode: 'L1',
      label: 'L1短期借款-利息测算→L8利息支出',
      direction: 'from',
    },
    {
      targetWpCode: 'L3',
      label: 'L3长期借款-利息测算→L8利息支出',
      direction: 'from',
    },
    {
      targetWpCode: 'L4',
      label: 'L4应付债券-利息费用→L8利息支出',
      direction: 'from',
    },
    {
      targetWpCode: 'L5',
      label: 'L5长期应付款-未确认融资费用摊销→L8利息支出',
      direction: 'from',
    },
  ]

  // ─── Cleanup（组件卸载取消订阅） ──────────────────────────────────────────

  onScopeDispose(() => {
    eventBus.off('l1:interest-calculated', _onL1InterestCalculated)
    eventBus.off('l3:interest-calculated', _onL3InterestCalculated)
    eventBus.off('l4:interest-calculated', _onL4InterestCalculated)
    eventBus.off('l5:amortization-calculated', _onL5AmortizationCalculated)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    // L循环利息汇聚
    interestFromLCycle,
    // 测算vs账面一致性
    estimatedVsBooked,
    // 跨底稿引用
    crossWpReferences,
  }
}

export default useL8CrossSheet
