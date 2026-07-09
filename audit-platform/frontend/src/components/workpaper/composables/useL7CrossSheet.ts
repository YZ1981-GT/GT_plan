/**
 * useL7CrossSheet — L7 其他非流动负债跨sheet校验引擎
 *
 * Spec: .kiro/specs/l7-other-noncurrent-liabilities/
 * Task: 3.2
 * Requirements: 2.5, 3.5
 *
 * 职责：
 * 1. adjudicationVsDetail — L7-1审定表合计期末审定数 vs L7-2明细表各项目期末余额之和
 *
 * 联动方向：L7-1审定表 ↔ L7-2明细表 双向合计勾稽
 *
 * 科目：2801 其他非流动负债（贷方/负债类！期末=期初+贷方-借方）
 *
 * L7是L筹资循环最简底稿，无利息测算/摊销/L8联动，仅需审定-明细勾稽。
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { validateAdjudicationVsDetail } from './useL7FormulaEngine'
import type { ChecklistResponse } from './useL7FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = L7-1审定表合计期末审定数 - L7-2明细表各项目期末余额之和 */
  diff: number
  /** diff === 0 视为匹配（L7金额相对小，精确匹配） */
  isMatch: boolean
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

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
 * L7 跨sheet校验引擎
 *
 * @param allResponses - 全部 checklist_responses（来自 useL7FormData）
 */
export function useL7CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── adjudicationVsDetail — 审定表L7-1合计 vs 明细表L7-2合计 ─────────────

  /**
   * L7-1 审定表合计期末审定数 应= L7-2 明细表各项目期末余额之和
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - L7-1 审定表合计存于 item_id 模式: "L7-L7-1-total-*"（remark=合计审定数）
   *   具体使用 "L7-L7-1-total-audited" 存储合计期末审定数
   * - L7-2 明细表各项目期末余额存于 item_id 模式: "L7-L7-2-*-end_balance"
   *   遍历所有匹配 key 累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：从 allResponses 读取 L7-1 合计期末审定数
    const adjResp = allResponses.value.get('L7-L7-1-total-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：遍历所有 "L7-L7-2-*-end_balance" 模式的 item_id 累加
    let detailTotal = 0
    for (const [key, resp] of allResponses.value) {
      if (key.startsWith('L7-L7-2-') && key.endsWith('-end_balance')) {
        detailTotal += parseNum(resp.remark)
      }
    }

    // 使用公式引擎的纯函数做交叉验证
    return validateAdjudicationVsDetail(adjTotal, detailTotal)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
  }
}

export default useL7CrossSheet
