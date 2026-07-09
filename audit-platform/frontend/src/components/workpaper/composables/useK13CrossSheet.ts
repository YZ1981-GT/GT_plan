/**
 * useK13CrossSheet — K13 营业外支出跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K13-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K13-1 审定表审定合计 vs K13-2 明细表合计（adjudicationVsDetail）
 *
 * 科目方向：
 * - 6711 营业外支出（借方/损益类）：取发生额=借方发生-贷方发生(红冲)
 *
 * Spec: .kiro/specs/k13-non-operating-expense/
 * Task: 3.2
 * Requirements: 2.5, 3.2
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：K13-1审定表合计 - K13-2明细表合计 */
  diff: number
  /** 是否匹配（|diff| < 0.01，分以内视为一致） */
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
 * K13 跨Sheet computed links：
 * - K13-1 审定表审定合计 ↔ K13-2 明细表发生额合计
 *
 * 营业外支出(6711)为损益类借方科目，审定表存发生额合计，
 * 明细表按去向（非流动资产处置损失/捐赠支出/罚款滞纳金/债务重组损失/资产盘亏损失/其他）逐项汇总。
 * 两者合计应一致，差额超过0.01元视为不匹配。
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 */
export function useK13CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K13-1 审定表合计 vs K13-2 明细表合计（Req 2.5, 3.2）═══

  /**
   * K13-1 审定表营业外支出审定合计 与 K13-2 明细表合计交叉验证。
   * diff = K13-1 审定 total - K13-2 明细合计
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 损益类：审定表各去向合计（非流动资产处置损失+捐赠支出+罚款滞纳金+债务重组损失+资产盘亏损失+其他）
   *       == 明细表逐笔金额汇总
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K13-1-audited-total')
    const detailTotal = getNum('K13-2-subtotal')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
  }
}

export default useK13CrossSheet
