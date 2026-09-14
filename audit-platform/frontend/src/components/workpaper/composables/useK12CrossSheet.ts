/**
 * useK12CrossSheet — K12 营业外收入跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K12-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K12-1 审定表审定合计 vs K12-2 明细表合计（adjudicationVsDetail）
 *
 * 科目方向：
 * - 6301 营业外收入（贷方/损益类）：取发生额=贷方发生-借方发生(红冲)
 *
 * Spec: .kiro/specs/k12-non-operating-income/
 * Task: 3.2
 * Requirements: 2.5, 3.2
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：K12-1审定表合计 - K12-2明细表合计 */
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
 * K12 跨Sheet computed links：
 * - K12-1 审定表审定合计 ↔ K12-2 明细表发生额合计
 *
 * 营业外收入(6301)为损益类贷方科目，审定表存发生额合计，
 * 明细表按来源（政府补助/债务重组利得/资产盘盈/罚款收入/捐赠利得等）逐项汇总。
 * 两者合计应一致，差额超过0.01元视为不匹配。
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 */
export function useK12CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K12-1 审定表合计 vs K12-2 明细表合计（Req 2.5, 3.2）═══

  /**
   * K12-1 审定表营业外收入审定合计 与 K12-2 明细表合计交叉验证。
   * diff = K12-1 审定 total - K12-2 明细合计
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 损益类：审定表各来源合计（政府补助+债务重组利得+资产盘盈+罚款收入+捐赠利得+其他）
   *       == 明细表逐笔金额汇总
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K12-1-audited-total')
    const detailTotal = getNum('K12-2-subtotal')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
  }
}

export default useK12CrossSheet
