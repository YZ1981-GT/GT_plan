/**
 * useI5CrossSheet — I5 其他非流动资产跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('I5-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射（数据流图）：
 * - I5-2 明细表 → 聚合 → I5-1 审定表（期初/增加/减少/期末小计）
 * - I5-3 调整分录 → AJE/RJE → I5-1 审定表
 * - I5-1 审定表 → 审定数回写 → TB 1911
 * - I5-1 + I5-2 → 附注披露（审定数 + 明细）
 *
 * 科目方向：
 * - 1911 其他非流动资产（借方/资产类）：期末=期初+增加-减少
 * - 最简单标准资产类，无摊销/减值等特殊逻辑
 *
 * Spec: .kiro/specs/i5-other-noncurrent-assets/
 * Task: 3.2
 * Requirements: 2.1-2.5, 3.1-3.2
 */
import { computed, onScopeDispose, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal } from './useI5FormulaEngine'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I5-2 明细行原始 JSON 结构（26列3区段） */
export interface I5DetailRowRaw {
  rowId?: string
  name?: string               // 项目名称
  category?: string           // 资产类型
  incurredDate?: string       // 发生日期
  maturityDate?: string       // 到期日期

  // 金额区段
  beginBalance?: number       // 期初余额
  increase?: number           // 本期增加
  decrease?: number           // 本期减少
  endBalance?: number         // 期末余额

  // 检查区段
  voucherRef?: string         // 凭证号
  remark?: string             // 备注
  conclusion?: string         // 结论
}

/** I5-3 调整分录行原始 JSON 结构 */
export interface I5AdjustmentRowRaw {
  rowId?: string
  description?: string        // 调整事项
  entryType?: string          // AJE / RJE
  accountCode?: string        // 科目代码
  accountName?: string        // 科目名称
  summary?: string            // 摘要
  debitAmount?: number        // 借方
  creditAmount?: number       // 贷方
  indexRef?: string           // 索引
  remark?: string
}

// ─── Return Types ────────────────────────────────────────────────────────────

/** I5-2 明细合计 → I5-1 审定表交叉验证 */
export interface I5DetailTotals {
  total: number               // 期末余额合计（主合计）
  beginBalance: number        // 期初余额合计
  increase: number            // 本期增加合计
  decrease: number            // 本期减少合计
  endBalance: number          // 期末余额合计
}

/** 审定数从明细聚合 → I5-1 审定表 */
export interface I5AdjudicationFromDetail {
  audited: number             // 期末余额合计（= I5-1 审定表审定数参考来源）
}

// ─── Helpers ─────────────────────────────────────────────────────────────────

/**
 * 安全解析 JSON 数组字符串，失败回退空数组
 */
function safeParseRows<T>(jsonStr: string | null | undefined): T[] {
  if (!jsonStr) return []
  try {
    const parsed = JSON.parse(jsonStr)
    return Array.isArray(parsed) ? parsed : []
  } catch {
    return []
  }
}

/**
 * 安全提取数值，NaN/null/undefined → 0
 */
function _getNum(val: any): number {
  if (val == null) return 0
  const n = Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── Composable ──────────────────────────────────────────────────────────────

export function useI5CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<{ total: number }>
  adjudicationFromDetail: ComputedRef<{ audited: number }>
} {
  // ─── 解析 I5-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I5DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('I5-2-rows')
    return safeParseRows<I5DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 I5-3 调整分录行数据 ──────────────────────────────────────────

  const adjustmentRows = computed<I5AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('I5-3-rows')
    return safeParseRows<I5AdjustmentRowRaw>(resp?.remark)
  })

  // ═══ detailTotals: I5-2 明细聚合 → I5-1 审定表（Req 2.2-2.5, 3.1-3.2）══

  /**
   * 从 I5-2 明细行聚合其他非流动资产合计：
   * - total: 期末余额合计（主合计字段）
   * - beginBalance: 所有行期初余额之和
   * - increase: 所有行本期增加之和
   * - decrease: 所有行本期减少之和
   * - endBalance: 所有行期末余额之和
   *
   * 使用 calcSubtotal 聚合。
   * 用于与 I5-1 审定表小计行交叉验证。
   * 其他非流动资产特征：期末=期初+增加-减少（标准资产类）
   */
  const detailTotals: ComputedRef<{ total: number }> = computed(() => {
    const beginBalances: number[] = []
    const increases: number[] = []
    const decreases: number[] = []
    const endBalances: number[] = []

    for (const row of detailRows.value) {
      beginBalances.push(_getNum(row.beginBalance))
      increases.push(_getNum(row.increase))
      decreases.push(_getNum(row.decrease))
      endBalances.push(_getNum(row.endBalance))
    }

    const beginBalance = calcSubtotal(beginBalances)
    const increase = calcSubtotal(increases)
    const decrease = calcSubtotal(decreases)
    const endBalance = calcSubtotal(endBalances)

    return {
      total: endBalance,
      beginBalance,
      increase,
      decrease,
      endBalance,
    } as I5DetailTotals
  })

  // ═══ adjudicationFromDetail: I5-2 合计 → I5-1 审定表（Req 2.2-2.5）═══

  /**
   * 从 I5-2 明细期末余额合计推导 I5-1 审定数参考值：
   * - audited: 期末余额合计（= I5-1 审定表 "审定数" 交叉验证来源）
   *
   * 当 I5-1 审定数 ≠ 此值时可能存在未记录调整或分类差异。
   *
   * 审定数最终公式：未审数 + AJE + RJE
   * 此处提供的是从明细侧推导的参考值（应与公式结果一致）。
   */
  const adjudicationFromDetail: ComputedRef<{ audited: number }> = computed(() => {
    const totals = detailTotals.value as I5DetailTotals
    return { audited: totals.endBalance }
  })

  // ─── EventBus: Subscribe 'substantive:adjudicated' for cross-sheet updates ─

  /**
   * 监听 substantive:adjudicated 事件，当其他 sheet 审定完成时
   * 触发跨 sheet 的 computed 重新计算（通过 allResponses Map 自动联动）。
   *
   * I5 最简逻辑：接收事件后无需额外处理，allResponses 的 Map 更新
   * 由 useI5FormData 处理，本 composable 的 computed 自动响应变化。
   */
  function _onSubstantiveAdjudicated(event: Event): void {
    // I5 最简底稿：无需处理特殊逻辑
    // allResponses Map 响应式变化自动驱动 detailTotals / adjudicationFromDetail 重算
    // 此处仅为事件通道占位，供未来扩展（如刷新附注披露数据）
    void event
  }

  window.addEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)

  // ─── Cleanup on scope dispose ─────────────────────────────────────────────

  onScopeDispose(() => {
    window.removeEventListener('substantive:adjudicated', _onSubstantiveAdjudicated)
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // I5-2 → I5-1 明细合计（期末余额 = 主合计）
    detailTotals,
    // I5-2 合计 → I5-1 审定表审定数参考（期末余额）
    adjudicationFromDetail,
  }
}

export default useI5CrossSheet
