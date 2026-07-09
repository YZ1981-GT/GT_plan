/**
 * useK7CrossSheet — K7 递延收益跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K7-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K7-1 审定表聚合合计 vs K7-2 明细表期末合计（adjudicationVsDetail）
 * - K7-2 企业分摊 vs K7-4 测算分摊（detailVsCalc）
 *
 * 科目方向：
 * - 2401 递延收益（贷方/负债类）：期末=期初+收到(增加)-分摊(减少)
 *
 * Spec: .kiro/specs/k7-deferred-income/
 * Task: 3.2
 * Requirements: 2.5, 3.4, 4.5
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：左侧(审定表/汇总) - 右侧(明细/测算) */
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
 * K7 跨Sheet computed links：
 * - K7-1 审定表合计 ↔ K7-2 明细表期末合计（adjudicationVsDetail）
 * - K7-2 企业分摊 ↔ K7-4 测算分摊（detailVsCalc）
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 */
export function useK7CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  detailVsCalc: ComputedRef<CrossSheetCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K7-1 审定合计 vs K7-2 明细期末合计（Req 2.5, 3.4）═══

  /**
   * K7-1 审定表递延收益审定合计 与 K7-2 明细表期末余额合计交叉验证。
   * diff = K7-1 审定 total - K7-2 明细期末 subtotal
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 负债类：完整性是主要风险，明细<审定需特别关注（少计负债）。
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K7-1-audited-total')
    const detailSubtotal = getNum('K7-2-detail-end-total')
    const diff = adjTotal - detailSubtotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ detailVsCalc: K7-2 企业分摊 vs K7-4 测算分摊（Req 4.5）═══

  /**
   * K7-2 明细表中企业账面分摊合计 与 K7-4 测算表计算的应分摊合计交叉验证。
   * diff = K7-2 企业分摊合计 - K7-4 测算分摊合计
   * isMatch = |diff| < 0.01
   *
   * 差异>0 表示企业多摊了（可能高估费用/低估递延收益）；
   * 差异<0 表示企业少摊了（可能低估费用/高估递延收益，需补摊）。
   */
  const detailVsCalc: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const enterpriseAmort = getNum('K7-2-amort-total')
    const calculatedAmort = getNum('K7-4-calc-amort-total')
    const diff = enterpriseAmort - calculatedAmort
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    detailVsCalc,
  }
}

export default useK7CrossSheet
