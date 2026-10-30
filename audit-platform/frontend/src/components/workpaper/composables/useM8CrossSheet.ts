/**
 * useM8CrossSheet — M8 一般风险准备跨sheet校验引擎
 *
 * Spec: .kiro/specs/m8-general-risk-reserve/
 * Task: 3.2
 * Requirements: 2.5
 *
 * 职责：adjudicationVsDetail — M8-1审定表合计 vs M8-2明细表合计 交叉验证。
 *
 * 原第 2 项 isFinancialEntity（按项目「行业」关键词判金融企业）已删：平台没有项目级行业来源，
 * project_info.industry 恒空；适用性改由宿主按试算表有无一般风险准备科目提示（不阻断），
 * 不适用走程序裁剪（spec trim-followup-residual-findings-closure R1）。
 *
 * 联动方向：
 *   M8-1 审定表 row 13 = SUM(rows 7-12) 期末合计
 *   M8-2 明细表 row 17 = SUM(rows 10-16) 期末合计
 *   两者应匹配，差额!=0 红色高亮
 *
 * 科目：一般风险准备（**贷方/权益类！期末=期初+贷方-借方**）
 * 金融企业专属：银行/证券/保险/信托/基金/期货/金融租赁
 *
 * ADR-2: 一般风险准备是金融企业（银行、证券、保险等）从净利润中计提、
 *   用于弥补尚未识别的可能性损失的权益类准备。非金融企业不适用。
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

/** checklist_responses 基础类型（与 useM8FormData 对齐） */
export interface ChecklistResponse {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** 审定表 vs 明细表 交叉验证结果 */
export interface AdjudicationVsDetailResult {
  /** 差额 = M8-1审定表期末合计 - M8-2明细表期末合计 */
  diff: number
  /** |diff| < 阈值视为匹配 */
  isMatch: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 审定-明细勾稽匹配阈值（1元内视为匹配，考虑四舍五入差异） */
const MATCH_THRESHOLD = 1

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
 * M8 跨sheet校验引擎
 *
 * @param allResponses - 全部 checklist_responses（来自 useM8FormData）
 */
export function useM8CrossSheet(
  allResponses: Ref<Map<string, ChecklistResponse>>,
) {
  // ─── 1. adjudicationVsDetail — 审定表M8-1合计 vs 明细表M8-2合计 ─────────

  /**
   * M8-1 审定表期末合计（row 13 = SUM rows 7-12）应= M8-2 明细表合计（row 17 = SUM rows 10-16）
   * 差额 = 审定表期末合计 - 明细表合计
   *
   * 权益类贷方：期末=期初+贷方(计提)-借方(转回/使用)
   *
   * 数据来源：
   * - M8-1 审定表期末合计存于 item_id: "M8-M8-1-total-end-audited"（remark=期末审定余额合计）
   * - M8-2 明细表合计存于 item_id: "M8-M8-2-total-end-amount"（remark=明细表期末合计）
   *   或遍历 "M8-M8-2-row-*-end" 模式累加
   *
   * 对应xlsx: M8-1 row 13 SUM(rows 7-12) = M8-2 row 17 SUM(rows 10-16)
   */
  const adjudicationVsDetail: ComputedRef<AdjudicationVsDetailResult> = computed(() => {
    // 审定表合计：M8-1期末审定余额合计
    const adjResp = allResponses.value.get('M8-M8-1-total-end-audited')
    const adjTotal = parseNum(adjResp?.remark)

    // 明细表合计：优先取汇总行（M8-2合计行）
    const detailTotalResp = allResponses.value.get('M8-M8-2-total-end-amount')
    let detailTotal = parseNum(detailTotalResp?.remark)

    // 降级：如果汇总行无值，遍历明细行期末累加
    if (detailTotal === 0 && !detailTotalResp?.remark) {
      for (const [key, resp] of allResponses.value) {
        if (key.startsWith('M8-M8-2-row-') && key.endsWith('-end')) {
          detailTotal += parseNum(resp.remark)
        }
      }
    }

    const diff = parseFloat((adjTotal - detailTotal).toFixed(2))
    return {
      diff,
      isMatch: Math.abs(diff) < MATCH_THRESHOLD,
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
  }
}

export default useM8CrossSheet
