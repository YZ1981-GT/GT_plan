/**
 * useK4CrossSheet — K4 其他流动负债跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K4-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K4-2 明细表期末合计 → K4-1 审定表（detailTotals → adjudicationFromDetail）
 *
 * 科目方向：
 * - 2245 其他流动负债（贷方/负债类）：期末=期初+贷方-借方
 *
 * Spec: .kiro/specs/k4-other-current-liabilities/
 * Task: 3.2
 * Requirements: 2.5
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K4DetailTotals {
  /** 明细表期末合计 */
  total: number
}

export interface K4AdjudicationFromDetail {
  /** 从明细表聚合得到的审定数 */
  audited: number
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
 * K4 跨Sheet computed links：detail (K4-2) totals → adjudication (K4-1)
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 * @returns detailTotals / adjudicationFromDetail computed
 */
export function useK4CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<K4DetailTotals>
  adjudicationFromDetail: ComputedRef<K4AdjudicationFromDetail>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ detailTotals: K4-2 明细表期末合计 ═══

  /**
   * K4-2 明细表的期末余额合计。
   * 此数据向上聚合到 K4-1 审定表，做交叉验证。
   *
   * 负债类科目：完整性是主要风险，明细<审定需特别关注（少计负债）。
   *
   * Req 2.5: K4-1 审定表与 K4-2 明细合计交叉验证
   */
  const detailTotals: ComputedRef<K4DetailTotals> = computed(() => {
    const total = getNum('K4-2-detail-total')
    return { total }
  })

  // ═══ adjudicationFromDetail: K4-2 明细聚合 → K4-1 审定表审定数 ═══

  /**
   * 从 K4-2 明细表聚合得到的审定数，用于与 K4-1 审定表审定数对比。
   * diff = K4-1 审定 total - K4-2 明细期末 subtotal
   * 如果 |diff| > 0.01 则存在差异，需检查完整性。
   *
   * Req 2.5: K4-1 审定表与 K4-2 明细合计交叉验证
   */
  const adjudicationFromDetail: ComputedRef<K4AdjudicationFromDetail> = computed(() => {
    const audited = getNum('K4-2-detail-total')
    return { audited }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    detailTotals,
    adjudicationFromDetail,
  }
}

export default useK4CrossSheet
