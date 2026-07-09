/**
 * useK2CrossSheet — K2 其他流动资产跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K2-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K2-1 审定表 total vs K2-2 明细表合计（adjudicationVsDetail）
 * - K2-4 合同成本企业摊销合计 vs K2-5 摊销测算摊销合计（contractCostVsAmort）
 *
 * 科目方向：
 * - 1231 其他流动资产（借方/资产类）：期末=期初+借方-贷方
 *
 * Spec: .kiro/specs/k2-other-current-assets/
 * Task: 3.2
 * Requirements: 2.5(K2-1与K2-2/K2-4交叉验证), 4.4-4.5(K2-4与K2-5交叉), 5.5(测算差异)
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface K2CrossSheetResult {
  diff: number
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

export function useK2CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<K2CrossSheetResult>
  contractCostVsAmort: ComputedRef<K2CrossSheetResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K2-1 审定表 total vs K2-2 明细表合计（Req 2.5）═══

  /**
   * K2-1 审定表审定数（其他流动资产合计）与 K2-2 明细表期末余额合计交叉验证。
   * diff = K2-1 审定 total - K2-2 明细期末 subtotal
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 不匹配说明审定表汇总与明细存在差异，需排查遗漏项目或计算偏差。
   */
  const adjudicationVsDetail: ComputedRef<K2CrossSheetResult> = computed(() => {
    const adjTotal = getNum('K2-1-end-balance-total')
    const detailTotal = getNum('K2-2-end-total')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ contractCostVsAmort: K2-4 企业摊销 vs K2-5 测算摊销（Req 4.4-4.5, 5.5）═══

  /**
   * K2-4 合同取得成本明细的企业摊销合计 与 K2-5 摊销测算表的测算摊销合计交叉验证。
   * diff = K2-4 企业摊销合计 - K2-5 测算摊销合计
   * isMatch = |diff| < 0.01
   *
   * 差异>0 表示企业多摊销（有利差异）；差异<0 表示企业少摊销（需提示调整）。
   * 此交叉验证确保合同成本明细中记录的企业实际摊销与独立测算一致。
   */
  const contractCostVsAmort: ComputedRef<K2CrossSheetResult> = computed(() => {
    const k4Amort = getNum('K2-4-amort-total')
    const k5Amort = getNum('K2-5-calculated-amort-total')
    const diff = k4Amort - k5Amort
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    contractCostVsAmort,
  }
}

export default useK2CrossSheet
