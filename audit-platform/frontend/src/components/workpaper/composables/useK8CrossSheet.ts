/**
 * useK8CrossSheet — K8 销售费用跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K8-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K8-1 审定表合计 vs K8-2 明细表合计（adjudicationVsDetail）
 * - K8-4 实质性分析合计 vs K8-2 明细表合计（analysisVsDetail）
 *
 * 科目方向：
 * - 6601 销售费用（借方/损益类）：取发生额=借方发生-贷方发生(红冲)
 *
 * Spec: .kiro/specs/k8-selling-expenses/
 * Task: 3.2
 * Requirements: 2.5, 3.2, 4.6
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：左侧(审定表/分析表) - 右侧(明细表) */
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
 * K8 跨Sheet computed links：
 * - K8-1 审定表审定合计 ↔ K8-2 明细表发生额合计
 * - K8-4 实质性分析合计 ↔ K8-2 明细表发生额合计
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 */
export function useK8CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  analysisVsDetail: ComputedRef<CrossSheetCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K8-1 审定表合计 vs K8-2 明细表合计（Req 2.5）═══

  /**
   * K8-1 审定表销售费用审定合计 与 K8-2 明细表本期发生额合计交叉验证。
   * diff = K8-1 审定 total - K8-2 明细发生额 total
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 损益类：存在性/准确性是主要风险，审定>明细需特别关注（费用多计/错分类）。
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K8-1-audited-total')
    const detailTotal = getNum('K8-2-total-audited')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ analysisVsDetail: K8-4 实质性分析合计 vs K8-2 明细表合计（Req 3.2, 4.6）═══

  /**
   * K8-4 实质性分析本期发生额合计 与 K8-2 明细表发生额合计交叉验证。
   * diff = K8-4 分析本期合计 - K8-2 明细发生额合计
   * isMatch = |diff| < 0.01
   *
   * K8-4 按费用项目逐项分析（同比/占比/异常），其合计应与 K8-2 明细表一致。
   * 差异通常说明分析表漏项或明细分类不一致，需排查。
   */
  const analysisVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const analysisTotal = getNum('K8-4-analysis-total')
    const detailTotal = getNum('K8-2-total-audited')
    const diff = analysisTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    analysisVsDetail,
  }
}

export default useK8CrossSheet
