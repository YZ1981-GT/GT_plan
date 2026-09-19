/**
 * useK10CrossSheet — K10 其他收益跨Sheet交叉验证 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('K10-{sheet}-{field}')?.remark 存数值。
 *
 * 跨Sheet映射（数据流图）：
 * - K10-1 审定表审定合计 vs K10-2 明细表合计（adjudicationVsDetail）
 * - K10-4 递延分摊计入 vs K7 递延收益本期分摊（reconcileVsK7）
 *
 * 科目方向：
 * - 6117 其他收益（贷方/损益类）：取发生额=贷方发生-借方发生(红冲)
 *
 * K10核心特殊：
 * ① 损益类贷方科目！取发生额非余额
 * ② 政府补助核对：递延分摊计入 ↔ K7递延收益(2401)本期分摊一致性校验
 *
 * Spec: .kiro/specs/k10-other-income/
 * Task: 3.2
 * Requirements: 2.5, 4.3-4.5
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { parseNum } from './useK10FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface CrossSheetCheckResult {
  /** 差额 */
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
  return parseNum(raw)
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * K10 跨Sheet computed links：
 * - adjudicationVsDetail: K10-1 审定表审定合计 ↔ K10-2 明细表发生额合计
 * - reconcileVsK7: K10-4 递延分摊计入合计 ↔ K7 递延收益(2401)本期分摊
 *
 * 其他收益(6117)为损益类贷方科目，审定表存发生额合计，
 * 明细表按补助项目/来源（政府补助-即征即退/财政贴息/研发补助/稳岗补贴等）逐项汇总。
 * K10-4政府补助核对表中"递延分摊计入"需与K7底稿递延收益本期分摊金额一致。
 *
 * @param allResponses 全部 checklist_responses 的响应式 Map
 */
export function useK10CrossSheet(allResponses: Ref<Map<string, any>>): {
  adjudicationVsDetail: ComputedRef<CrossSheetCheckResult>
  reconcileVsK7: ComputedRef<CrossSheetCheckResult>
} {
  // 辅助：从 allResponses 提取数值
  function getNum(key: string): number {
    return getNumFromMap(allResponses.value, key)
  }

  // ═══ adjudicationVsDetail: K10-1 审定表合计 vs K10-2 明细表合计（Req 2.5）═══

  /**
   * K10-1 审定表其他收益审定合计 与 K10-2 明细表合计交叉验证。
   * diff = K10-1 审定 total - K10-2 明细合计
   * isMatch = |diff| < 0.01（分以内视为一致）
   *
   * 损益类（贷方）：审定表各来源合计（即征即退+财政贴息+研发补助+稳岗补贴+其他）
   *               == 明细表逐笔本期计入金额汇总
   */
  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('K10-1-audited-total')
    const detailTotal = getNum('K10-2-subtotal')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ═══ reconcileVsK7: K10-4 递延分摊计入 vs K7 递延收益本期分摊（Req 4.3-4.5）═══

  /**
   * K10-4 政府补助核对表中"递延分摊计入"合计 与 K7 递延收益(2401)本期分摊金额核对。
   * diff = K10-4 递延分摊合计 - K7 递延收益本期分摊
   * isMatch = |diff| < 0.01（容差0.01元）
   *
   * 核对逻辑：
   * - K10-4记录的递延分摊计入（递延收益分期确认为其他收益的金额）
   * - K7递延收益(2401)底稿中的本期分摊金额
   * - 两者应一致，不一致时红色标记提示用户核查
   *
   * 数据来源：
   * - K10-4-deferred-amort-total: K10-4表底部递延分摊计入合计（本底稿内）
   * - K7-deferred-amort-current: K7递延收益本期分摊（跨底稿联动，由EventBus或手动填入）
   */
  const reconcileVsK7: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const deferredInK10 = getNum('K10-4-deferred-amort-total')
    const amortInK7 = getNum('K7-deferred-amort-current')
    const diff = deferredInK10 - amortInK7
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    adjudicationVsDetail,
    reconcileVsK7,
  }
}

export default useK10CrossSheet
