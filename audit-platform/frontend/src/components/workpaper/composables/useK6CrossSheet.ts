/**
 * useK6CrossSheet — K6 持有待售资产和负债跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K6-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K6-1 审定表合计 vs K6-2 明细表合计（adjudicationVsDetail）
 * - K6-5 减值金额合计 vs K6-1 减值准备列（impairmentVsAdjudication）
 * - K6-6 处置组减值分摊合计 vs K6-5 处置组减值总额（groupVsImpairment）
 *
 * 科目方向：
 * - 1481 持有待售资产（借方/资产类）：期末=期初+增加-减少-减值
 * - 持有待售负债（贷方/负债类）：期末=期初+增加-减少
 *
 * Spec: .kiro/specs/k6-held-for-sale/
 * Task: 3.2
 * Requirements: 2.7, 3.3, 5.5, 6.4
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：左侧 - 右侧 */
  diff: number
  /** 是否匹配（|diff| < EPSILON） */
  isMatch: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 浮点容差（分以内视为一致） */
const EPSILON = 0.01

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
 * K6 跨Sheet computed links：
 * - K6-1 审定表合计 ↔ K6-2 明细表合计（审定表应等于明细表聚合）
 * - K6-5 减值金额合计 ↔ K6-1 减值准备列（减值测试结果应回连审定表）
 * - K6-6 处置组分摊合计 ↔ K6-5 处置组减值总额（分摊后合计应等于处置组总减值）
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 */
export function useK6CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  impairmentVsAdjudication: ComputedRef<CrossSheetCheckResult>
  groupVsImpairment: ComputedRef<CrossSheetCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K6-1 审定表合计 vs K6-2 明细表合计（Req 2.7, 3.3）═══

  /**
   * K6-1 审定表持有待售资产审定合计 与 K6-2 明细表账面价值合计交叉验证。
   * diff = K6-1 审定合计 - K6-2 明细合计
   * isMatch = |diff| < EPSILON
   *
   * 持有待售资产类：存在性是主要风险，审定>明细需特别关注。
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K6-1-audited-total')
    const detailTotal = getNum('K6-2-detail-book-value-total')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < EPSILON }
  })

  // ═══ impairmentVsAdjudication: K6-5 减值金额合计 vs K6-1 减值准备列（Req 5.5）═══

  /**
   * K6-5 减值测试表计算的减值金额合计 与 K6-1 审定表减值准备列合计交叉验证。
   * diff = K6-1 减值准备合计 - K6-5 减值金额合计
   * isMatch = |diff| < EPSILON
   *
   * diff>0 表示审定表减值多于测试结果（可能多提）；diff<0 表示审定表减值少于测试结果（需补提）。
   * 孰低法：减值 = MAX(0, 账面价值 - 公允价值净额)
   */
  const impairmentVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjImpairmentTotal = getNum('K6-1-impairment-total')
    const testImpairmentTotal = getNum('K6-5-impairment-amount-total')
    const diff = adjImpairmentTotal - testImpairmentTotal
    return { diff, isMatch: Math.abs(diff) < EPSILON }
  })

  // ═══ groupVsImpairment: K6-6 分摊合计 vs K6-5 处置组减值总额（Req 6.4）═══

  /**
   * K6-6 处置组减值测试表中各资产分摊减值合计 与 K6-5 处置组减值总额交叉验证。
   * diff = K6-5 处置组减值总额 - K6-6 分摊减值合计
   * isMatch = |diff| < EPSILON
   *
   * CAS42：处置组减值先抵减商誉，再按账面比例分摊至组内非流动资产。
   * 分摊后合计应等于处置组整体减值金额（扣除商誉吸收部分后）。
   */
  const groupVsImpairment: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const impairmentGroupTotal = getNum('K6-5-group-impairment-total')
    const allocationTotal = getNum('K6-6-allocation-total')
    const diff = impairmentGroupTotal - allocationTotal
    return { diff, isMatch: Math.abs(diff) < EPSILON }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    impairmentVsAdjudication,
    groupVsImpairment,
  }
}

export default useK6CrossSheet
