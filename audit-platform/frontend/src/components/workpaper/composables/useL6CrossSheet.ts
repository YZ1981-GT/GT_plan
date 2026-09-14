/**
 * useL6CrossSheet — L6 专项应付款跨sheet校验引擎
 *
 * Spec: .kiro/specs/l6-special-payables/
 * Task: 3.2
 * Requirements: 2.5, 3.5
 *
 * 职责：
 * 1. adjudicationVsDetail — L6-1审定表合计期末审定数 vs L6-2明细表各专项项目期末余额之和
 *
 * 联动方向：L6-1审定表 ↔ L6-2明细表 双向合计勾稽
 *
 * 科目：2601 专项应付款（贷方/负债类！期末=期初+贷方-借方）
 *
 * L6是L筹资循环标准负债底稿，专项应付款按专项项目列示。
 * 核心校验：审定表合计=明细表各项目期末余额之和。
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { validateAdjudicationVsDetail } from './useL6FormulaEngine'
import type { ChecklistResponse } from './useL6FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表 vs 明细表 勾稽结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = L6-1审定表合计期末审定数 - L6-2明细表各专项项目期末余额之和 */
  diff: number
  /** diff === 0 视为匹配 */
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
 * L6 跨sheet校验引擎
 *
 * @param allResponses - 全部 checklist_responses（来自 useL6FormData）
 */
export function useL6CrossSheet(allResponses: Ref<Map<string, ChecklistResponse>>) {
  // ─── adjudicationVsDetail — 审定表L6-1合计 vs 明细表L6-2合计 ─────────────

  /**
   * L6-1 审定表合计期末审定数 应= L6-2 明细表各专项项目期末余额之和
   * 差额 = 审定表合计 - 明细表合计
   *
   * 数据来源：
   * - L6-1 审定表合计存于 item_id: "L6-L6-1-total-audited"（remark=合计期末审定数）
   * - L6-2 明细表各项目期末余额存于 item_id 模式: "L6-L6-2-*-end_balance"
   *   遍历所有匹配 key 累加
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：从 allResponses 读取 L6-1 合计期末审定数
    const adjResp = allResponses.value.get('L6-L6-1-total-audited')
    const adjTotalVal = parseNum(adjResp?.remark)

    // 明细表合计：遍历所有 "L6-L6-2-*-end_balance" 模式的 item_id 累加
    let detailTotalVal = 0
    for (const [key, resp] of allResponses.value) {
      if (key.startsWith('L6-L6-2-') && key.endsWith('-end_balance')) {
        detailTotalVal += parseNum(resp.remark)
      }
    }

    // 使用公式引擎的纯函数做交叉验证
    return validateAdjudicationVsDetail(adjTotalVal, detailTotalVal)
  })

  // ─── 便捷计算属性（独立暴露供组件直接使用） ─────────────────────────────────

  /** 审定表合计（L6-1期末审定合计） */
  const adjTotal: ComputedRef<number> = computed(() => {
    const adjResp = allResponses.value.get('L6-L6-1-total-audited')
    return parseNum(adjResp?.remark)
  })

  /** 明细合计（L6-2各专项项目期末余额之和） */
  const detailTotal: ComputedRef<number> = computed(() => {
    let total = 0
    for (const [key, resp] of allResponses.value) {
      if (key.startsWith('L6-L6-2-') && key.endsWith('-end_balance')) {
        total += parseNum(resp.remark)
      }
    }
    return total
  })

  /** 是否勾稽一致 */
  const isMatch: ComputedRef<boolean> = computed(() => adjudicationVsDetail.value.isMatch)

  /** 差额 */
  const diff: ComputedRef<number> = computed(() => adjudicationVsDetail.value.diff)

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    adjTotal,
    detailTotal,
    isMatch,
    diff,
  }
}

export default useL6CrossSheet
