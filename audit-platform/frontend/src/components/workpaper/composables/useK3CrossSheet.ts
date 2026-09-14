/**
 * useK3CrossSheet — K3 其他应付款跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K3-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K3-1 审定表 audited total vs K3-2 明细表期末合计（adjudicationVsDetail）
 * - K3-2 明细表3年以上账龄行联动 → K3-5 长期挂账检查（longOutstandingVsDetail）
 * - K3-2 明细表大额筛选 → K3-4 大额分析（largeAmountVsDetail）
 *
 * 科目方向：
 * - 2241 其他应付款（贷方/负债类）：期末=期初+贷方-借方
 *
 * Spec: .kiro/specs/k3-other-payables/
 * Task: 3.2
 * Requirements: 2.5, 3.3, 4.4, 5.4
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K3CrossSheetCheckResult {
  diff: number
  isMatch: boolean
}

export interface K3CrossSheetCountResult {
  count: number
  total: number
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

export function useK3CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<K3CrossSheetCheckResult>
  longOutstandingVsDetail: ComputedRef<K3CrossSheetCountResult>
  largeAmountVsDetail: ComputedRef<K3CrossSheetCountResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K3-1 审定表 total vs K3-2 明细表合计（Req 2.5, 3.3）═══

  /**
   * K3-1 审定表审定数（其他应付款合计）与 K3-2 明细表期末余额合计交叉验证。
   * diff = K3-1 审定 total - K3-2 明细期末 subtotal
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 不匹配说明审定表汇总与明细存在差异，需排查遗漏项目或计算偏差。
   * 负债类科目：完整性是主要风险，少计负债（明细<审定）需特别关注。
   */
  const adjudicationVsDetail: ComputedRef<K3CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K3-1-audited-total')
    const detailTotal = getNum('K3-2-detail-total')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ longOutstandingVsDetail: K3-2 明细3年以上 → K3-5 长期挂账联动（Req 5.4）═══

  /**
   * K3-2 明细表中3年以上账龄行的笔数和金额合计，供 K3-5 长期挂账检查表使用。
   * count = K3-2 中3年以上账龄行数
   * total = K3-2 中3年以上账龄金额小计
   *
   * 该数据用于与 K3-5 交叉验证：K3-5 覆盖的长期挂账笔数应≥ count（完整覆盖）。
   * 3年以上未偿付款项需评估是否转营业外收入（联动K12）。
   */
  const longOutstandingVsDetail: ComputedRef<K3CrossSheetCountResult> = computed(() => {
    const count = getNum('K3-2-aging-over3y-count')
    const total = getNum('K3-2-aging-over3y-total')
    return { count, total }
  })

  // ═══ largeAmountVsDetail: K3-2 明细大额筛选 → K3-4 大额分析联动（Req 4.4）═══

  /**
   * K3-2 明细表中符合大额标准的行笔数和金额合计，供 K3-4 大额分析表使用。
   * count = K3-2 中大额款项笔数
   * total = K3-2 中大额款项金额小计
   *
   * 该数据用于与 K3-4 交叉验证：K3-4 覆盖的大额笔数应≥ count（完整覆盖）。
   * 大额标准由项目重要性水平决定（通常为其他应付款合计的5%或固定阈值）。
   */
  const largeAmountVsDetail: ComputedRef<K3CrossSheetCountResult> = computed(() => {
    const count = getNum('K3-2-large-amount-count')
    const total = getNum('K3-2-large-amount-total')
    return { count, total }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    longOutstandingVsDetail,
    largeAmountVsDetail,
  }
}

export default useK3CrossSheet
