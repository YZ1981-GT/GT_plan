/**
 * useL3CrossSheet — L3 长期借款跨sheet引擎 + L2/L8联动 + 重分类汇总
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 3.2
 * Requirements: 2.5, 3.6, 5.3, 6.4, 11.1-11.2
 *
 * 职责：
 * 1. adjudicationVsDetail — L3-1审定表合计 vs L3-2明细表合计 勾稽校验
 * 2. creditVsDetail — L3-4征信核对表余额 vs L3-2明细表合计 一致性（完整性）
 * 3. interestToL2L8 — L3-5利息测算结果打包，供 EventBus 发布到 L2/L8
 * 4. currentPortionTotal — L3-2一年内到期金额合计（重分类RJE依据）
 * 5. publishInterestCalculated — EventBus 发布 'l3:interest-calculated'
 *
 * 联动方向：L3-5利息测算 → L2应付利息（计提核对）/ L8财务费用（利息支出）
 *           L3-2一年内到期 → L3-3重分类RJE → 流动负债(2801)
 *
 * 科目：2501 长期借款（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import type { ChecklistResponse } from './useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = 审定表合计 - 明细表合计 */
  diff: number
  /** 差额绝对值 ≤ 阈值 视为匹配 */
  isMatch: boolean
}

/** 征信核对 vs 明细表 一致性结果 */
export interface CreditVsDetailResult {
  /** 差额 = 征信余额合计 - 明细表期末合计 */
  diff: number
  /** 差额绝对值 ≤ 阈值 视为一致 */
  isConsistent: boolean
}

/** 利息测算 → L2/L8 联动载荷 */
export interface InterestToL2L8Result {
  /** 测算利息合计 */
  totalInterest: number
  /** 计入财务费用(L8)的利息（长期借款利息全部费用化） */
  financialExpenseInterest: number
  /** 按合同明细 */
  byContract: Array<{ contractNo: string; interest: number }>
}

/** EventBus 'l3:interest-calculated' 载荷 */
export interface L3InterestCalculatedPayload {
  wpCode: string
  totalInterest: number
  financialExpenseInterest: number
  byContract: Array<{ contractNo: string; interest: number }>
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

/** 勾稽匹配阈值（0.01元内视为匹配） */
const MATCH_THRESHOLD = 0.01

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
 * L3 跨sheet引擎 + L2/L8联动 + 一年内到期重分类汇总
 *
 * @param allResponses - 全部 checklist_responses（来自 useL3FormData）
 */
export function useL3CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── 上次发布的利息值（用于变化检测，仅变化时发布） ─────────────────────────
  const _lastPublishedInterest = ref<number | null>(null)

  // ─── 1. adjudicationVsDetail — 审定表L3-1合计 vs 明细表L3-2合计 ─────────

  /**
   * L3-1 审定表各分类期末合计 应= L3-2 明细表各行期末余额合计
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - L3-1 审定表合计存于 item_id: "L3-L3-1-adjudication-total"（remark=合计金额）
   * - L3-2 明细表行数据存于 item_id: "L3-L3-2-rows"（remark=JSON数组）
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：从 allResponses 读取审定表期末合计
    const adjResp = allResponses.value.get('L3-L3-1-adjudication-total')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：从行数据汇总期末余额
    const detailResp = allResponses.value.get('L3-L3-2-rows')
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

  // ─── 2. creditVsDetail — 征信核对L3-4余额 vs 明细表L3-2合计 ────────────

  /**
   * L3-4 征信核对表各行征信余额合计 应= L3-2 明细表期末余额合计（完整性验证）
   * 差额 = 征信余额合计 - 明细表合计
   *
   * 正值=征信大于账面（可能有未入账借款，完整性风险）
   * 负值=账面大于征信（可能有虚增借款）
   *
   * 数据来源：
   * - L3-4 征信核对行数据存于 item_id: "L3-L3-4-rows"（remark=JSON数组）
   * - L3-2 明细表行数据存于 item_id: "L3-L3-2-rows"（remark=JSON数组）
   */
  const creditVsDetail: ComputedRef<CreditVsDetailResult> = computed(() => {
    // 征信核对表：各行 creditBalance 合计
    const creditResp = allResponses.value.get('L3-L3-4-rows')
    const creditRows = safeParseRows<{ creditBalance?: number }>(creditResp?.remark)
    let creditTotal = 0
    for (const row of creditRows) {
      creditTotal += parseNum(row.creditBalance)
    }

    // 明细表合计
    const detailResp = allResponses.value.get('L3-L3-2-rows')
    const detailRows = safeParseRows<{ endBalance?: number }>(detailResp?.remark)
    let detailTotal = 0
    for (const row of detailRows) {
      detailTotal += parseNum(row.endBalance)
    }

    const diff = parseFloat((creditTotal - detailTotal).toFixed(2))
    return {
      diff,
      isConsistent: Math.abs(diff) <= MATCH_THRESHOLD,
    }
  })

  // ─── 3. interestToL2L8 — 利息测算结果打包 ──────────────────────────────

  /**
   * 汇总L3-5每笔借款的测算利息：
   * - totalInterest: Σ calculatedInterest
   * - financialExpenseInterest: 计入财务费用(L8)的利息
   *   长期借款利息通常全部费用化（计入L8财务费用），除非有资本化部分（H2在建工程关联）
   * - byContract: 按合同号明细
   *
   * 数据来源：
   * - L3-5 利息测算行数据存于 item_id: "L3-L3-5-rows"（remark=JSON数组）
   */
  const interestToL2L8: ComputedRef<InterestToL2L8Result> = computed(() => {
    const interestResp = allResponses.value.get('L3-L3-5-rows')
    const interestRows = safeParseRows<{
      contractNo?: string
      calculatedInterest?: number
      isCapitalized?: boolean
    }>(interestResp?.remark)

    let totalInterest = 0
    let financialExpenseInterest = 0
    const byContract: Array<{ contractNo: string; interest: number }> = []

    for (const row of interestRows) {
      const interest = parseNum(row.calculatedInterest)
      totalInterest += interest

      // 非资本化部分计入财务费用（默认全部费用化，除非标记 isCapitalized）
      if (!row.isCapitalized) {
        financialExpenseInterest += interest
      }

      if (row.contractNo) {
        byContract.push({
          contractNo: row.contractNo,
          interest,
        })
      }
    }

    return {
      totalInterest: parseFloat(totalInterest.toFixed(2)),
      financialExpenseInterest: parseFloat(financialExpenseInterest.toFixed(2)),
      byContract,
    }
  })

  // ─── 4. currentPortionTotal — 一年内到期金额合计 ───────────────────────

  /**
   * 汇总L3-2明细表所有借款的"一年内到期金额"列合计。
   * 此值用于：
   * - L3-1审定表单列显示"其中：一年内到期"合计
   * - L3-3调整分录生成重分类RJE的金额依据
   * - 流动/非流动分类报表列报
   *
   * 数据来源：
   * - L3-2 明细行存于 item_id: "L3-L3-2-rows"（remark=JSON数组）
   * - 每行 currentPortion 字段 = calcCurrentPortion() 的输出
   */
  const currentPortionTotal: ComputedRef<number> = computed(() => {
    const detailResp = allResponses.value.get('L3-L3-2-rows')
    const detailRows = safeParseRows<{ currentPortion?: number }>(detailResp?.remark)

    let total = 0
    for (const row of detailRows) {
      total += parseNum(row.currentPortion)
    }
    return parseFloat(total.toFixed(2))
  })

  // ─── 5. publishInterestCalculated — EventBus 发布 ──────────────────────

  /**
   * 发布 'l3:interest-calculated' 事件到 EventBus。
   * 仅在值变化时发布（避免重复广播）。
   *
   * 载荷：wpCode / 总利息 / 财务费用利息 / 按合同明细 / 时间戳
   * L2应付利息 订阅用于计提核对；L8财务费用 订阅用于利息支出测算。
   */
  function publishInterestCalculated(): void {
    const result = interestToL2L8.value
    const currentTotal = result.totalInterest

    // 仅在值变化时发布
    if (_lastPublishedInterest.value === currentTotal) return
    _lastPublishedInterest.value = currentTotal

    const payload: L3InterestCalculatedPayload = {
      wpCode: 'L3',
      totalInterest: result.totalInterest,
      financialExpenseInterest: result.financialExpenseInterest,
      byContract: result.byContract,
      timestamp: Date.now(),
    }

    eventBus.emit('l3:interest-calculated', payload)
  }

  // ─── 6. 跨底稿引用定义 ────────────────────────────────────────────────

  /** L3 长期借款 cross_wp_references（关联 L2, L8） */
  const cross_wp_references: CrossWpReference[] = [
    {
      targetWpCode: 'L2',
      label: 'L2应付利息-利息计提核对',
      direction: 'to',
    },
    {
      targetWpCode: 'L8',
      label: 'L8财务费用-利息支出',
      direction: 'to',
    },
  ]

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // 核心勾稽
    adjudicationVsDetail,
    creditVsDetail,
    // L2/L8联动
    interestToL2L8,
    publishInterestCalculated,
    // 一年内到期重分类
    currentPortionTotal,
    // 跨底稿引用
    cross_wp_references,
  }
}

export default useL3CrossSheet
