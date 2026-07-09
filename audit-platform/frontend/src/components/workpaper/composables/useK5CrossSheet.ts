/**
 * useK5CrossSheet — K5 预计负债跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K5-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K5-2 明细合计 vs K5-1 审定表总额（adjudicationVsDetail）
 * - K5-4 质保测算合计 vs K5-1 "产品质量保证" 行（warrantyVsAdjudication）
 * - K5-5 弃置现值合计 vs K5-1 "弃置义务" 行（decommissionVsAdjudication）
 * - K5-6 诉讼预计损失合计 vs K5-1 "未决诉讼" 行（litigationVsAdjudication）
 *
 * 科目方向：
 * - 2701 预计负债（贷方/负债类）：期末=期初+计提-转销
 *
 * Spec: .kiro/specs/k5-provisions/
 * Task: 3.2
 * Requirements: 2.6, 3.4, 6.3, 7.4, 8.2
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额：左侧(审定表/汇总) - 右侧(明细/专项) */
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
 * K5 跨Sheet computed links：
 * - K5-2 明细合计 ↔ K5-1 审定表
 * - K5-4 质保测算 ↔ K5-1 产品质量保证行
 * - K5-5 弃置现值 ↔ K5-1 弃置义务行
 * - K5-6 诉讼预计损失 ↔ K5-1 未决诉讼行
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 */
export function useK5CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  warrantyVsAdjudication: ComputedRef<CrossSheetCheckResult>
  decommissionVsAdjudication: ComputedRef<CrossSheetCheckResult>
  litigationVsAdjudication: ComputedRef<CrossSheetCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K5-1 审定合计 vs K5-2 明细期末合计（Req 2.6, 3.4）═══

  /**
   * K5-1 审定表预计负债审定合计 与 K5-2 明细表期末余额合计交叉验证。
   * diff = K5-1 审定 total - K5-2 明细期末 subtotal
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 负债类：完整性是主要风险，明细<审定需特别关注（少计负债）。
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K5-1-audited-total')
    const detailSubtotal = getNum('K5-2-detail-end-total')
    const diff = adjTotal - detailSubtotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ warrantyVsAdjudication: K5-4 质保测算合计 vs K5-1 产品质量保证行（Req 6.3）═══

  /**
   * K5-4 产品质量保修检查表测算的期末质保准备合计 与 K5-1 审定表"产品质量保证"行期末审定数交叉验证。
   * diff = K5-1 产品质量保证审定 - K5-4 质保测算期末合计
   * isMatch = |diff| < 0.01
   *
   * 差异>0 表示审定表多于测算（企业可能多提）；差异<0 表示审定表少于测算（需补提）。
   */
  const warrantyVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjWarranty = getNum('K5-1-audited-warranty')
    const warrantyCalcTotal = getNum('K5-4-warranty-end-total')
    const diff = adjWarranty - warrantyCalcTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ decommissionVsAdjudication: K5-5 弃置现值合计 vs K5-1 弃置义务行（Req 7.4）═══

  /**
   * K5-5 弃置费用检查表测算的期末现值合计 与 K5-1 审定表"弃置义务"行期末审定数交叉验证。
   * diff = K5-1 弃置义务审定 - K5-5 弃置现值期末合计
   * isMatch = |diff| < 0.01
   *
   * 差异>0 表示审定表多于现值测算（可能过时/折现率变化）；差异<0 表示审定表少于测算（需补提）。
   */
  const decommissionVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjDecommission = getNum('K5-1-audited-decommission')
    const decommissionCalcTotal = getNum('K5-5-decommission-end-total')
    const diff = adjDecommission - decommissionCalcTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ litigationVsAdjudication: K5-6 诉讼预计损失合计 vs K5-1 未决诉讼行（Req 8.2）═══

  /**
   * K5-6 未决诉讼检查表中"确认"类诉讼的预计损失合计 与 K5-1 审定表"未决诉讼"行期末审定数交叉验证。
   * diff = K5-1 未决诉讼审定 - K5-6 诉讼预计损失合计
   * isMatch = |diff| < 0.01
   *
   * 仅 "确认"（很可能败诉）的案件金额才纳入预计负债，"披露"类不含在内。
   */
  const litigationVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjLitigation = getNum('K5-1-audited-litigation')
    const litigationLossTotal = getNum('K5-6-litigation-loss-total')
    const diff = adjLitigation - litigationLossTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    warrantyVsAdjudication,
    decommissionVsAdjudication,
    litigationVsAdjudication,
  }
}

export default useK5CrossSheet
