/**
 * useI4CrossSheet — I4 长期待摊费用跨Sheet联动 computed 引擎
 *
 * 通过 allResponses Map 实现跨 sheet 数据流（纯 computed 响应式链，不走 API）。
 * 数据读取模式：allResponses.get('I4-{sheet}-{field}')?.remark 存 JSON/数值。
 *
 * 跨Sheet映射（数据流图）：
 * - I4-2 明细表 → 聚合 → I4-1 审定表（原值/摊销/余额小计）
 * - I4-3 调整分录 → AJE/RJE → I4-1 审定表
 * - I4-6 直线法摊销测算 → 12月摊销矩阵合计 → I4-1 审定表"本期摊销"
 * - I4-7 工作量法摊销测算 → 12月摊销矩阵合计 → I4-1 审定表"本期摊销"
 * - I4-1 审定表 → 审定数回写 → TB 1801
 * - I4-1 + I4-2 → 附注披露（审定数 + 明细）
 *
 * 科目方向：
 * - 1801 长期待摊费用（借方/资产类）：期末=期初+增加-摊销-减少
 * - 无备抵科目（摊销直接减少原值，不设累计摊销备抵）
 *
 * 摊销分支互斥：I4-6（直线法）与 I4-7（工作量法）取有数据的一方。
 *
 * Spec: .kiro/specs/i4-long-term-prepaid/
 * Task: 3.2
 * Requirements: 2.2-2.5, 3.1-3.2, 6.4-6.6, 7.1-7.2, 8.1
 */
import { computed, type ComputedRef, type Ref } from 'vue'

// ─── Types ───────────────────────────────────────────────────────────────────

export interface ChecklistItem {
  item_id: string
  conclusion: string | null
  remark: string | null
}

/** I4-2 明细行原始 JSON 结构（25列3区段） */
export interface I4DetailRowRaw {
  rowId?: string
  name?: string               // 项目名称
  category?: string           // 费用类型
  incurredDate?: string       // 发生日期
  originalAmount?: number     // 原始金额

  // 摊销区段
  amortizationMethod?: string // 摊销方法（直线法/工作量法）
  totalMonths?: number        // 摊销总月数
  elapsedMonths?: number      // 已摊月数
  accAmortization?: number    // 累计摊销
  currentAmortization?: number // 本期摊销

  // 余额区段
  beginBalance?: number       // 期初余额
  increase?: number           // 本期增加
  decrease?: number           // 本期减少（非摊销的减少，如处置）
  endBalance?: number         // 期末余额
  remainingMonths?: number    // 剩余月数
}

/** I4-3 调整分录行原始 JSON 结构 */
export interface I4AdjustmentRowRaw {
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

/** I4-6/I4-7 摊销测算行原始 JSON 结构（12月矩阵） */
export interface I4AmortizationRowRaw {
  rowId?: string
  name?: string               // 项目名称
  originalAmount?: number     // 原始金额
  totalMonths?: number        // 摊销总月数（直线法）
  totalUnits?: number         // 总预计工作量（工作量法）
  monthlyAmorts?: number[]    // 12个月摊销额数组 [m1, m2, ..., m12]
  annualTotal?: number        // 年度摊销合计
}

// ─── Return Types ────────────────────────────────────────────────────────────

/** I4-2 明细合计 → I4-1 审定表交叉验证 */
export interface I4DetailTotals {
  total: number               // 原始金额合计
  amortization: number        // 本期摊销合计（从明细行累加）
  beginBalance: number        // 期初余额合计
  increase: number            // 本期增加合计
  decrease: number            // 本期减少合计
  endBalance: number          // 期末余额合计
}

/** 审定数从明细聚合 → I4-1 审定表 */
export interface I4AdjudicationFromDetail {
  audited: number             // 期末余额合计（= I4-1 审定表审定数来源）
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

export function useI4CrossSheet(allResponses: Ref<Map<string, any>>): {
  detailTotals: ComputedRef<{ total: number; amortization: number }>
  adjudicationFromDetail: ComputedRef<{ audited: number }>
  amortizationMatrix: ComputedRef<number[][]>
} {
  // ─── 解析 I4-2 明细行数据 ──────────────────────────────────────────────

  const detailRows = computed<I4DetailRowRaw[]>(() => {
    const resp = allResponses.value.get('I4-2-rows')
    return safeParseRows<I4DetailRowRaw>(resp?.remark)
  })

  // ─── 解析 I4-3 调整分录行数据 ──────────────────────────────────────────

  const adjustmentRows = computed<I4AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('I4-3-rows')
    return safeParseRows<I4AdjustmentRowRaw>(resp?.remark)
  })

  // ─── 解析 I4-6/I4-7 摊销测算行数据（互斥分支，优先取有数据的一方）───

  const amortizationRows = computed<I4AmortizationRowRaw[]>(() => {
    // 优先取 I4-6（直线法），若无则取 I4-7（工作量法）——两者互斥
    const resp6 = allResponses.value.get('I4-6-rows')
    const rows6 = safeParseRows<I4AmortizationRowRaw>(resp6?.remark)
    if (rows6.length > 0) return rows6

    const resp7 = allResponses.value.get('I4-7-rows')
    return safeParseRows<I4AmortizationRowRaw>(resp7?.remark)
  })

  // ═══ detailTotals: I4-2 明细聚合 → I4-1 审定表（Req 2.2-2.5, 3.1-3.2）══

  /**
   * 从 I4-2 明细行聚合长期待摊费用合计：
   * - total: 所有行原始金额之和
   * - amortization: 所有行本期摊销之和
   * - beginBalance: 所有行期初余额之和
   * - increase: 所有行本期增加之和
   * - decrease: 所有行本期减少之和
   * - endBalance: 所有行期末余额之和
   *
   * 用于与 I4-1 审定表小计行交叉验证。
   * 长期待摊费用特征：期末=期初+增加-摊销-减少
   */
  const detailTotals: ComputedRef<{ total: number; amortization: number }> = computed(() => {
    let total = 0
    let amortization = 0
    let beginBalance = 0
    let increase = 0
    let decrease = 0
    let endBalance = 0

    for (const row of detailRows.value) {
      total += _getNum(row.originalAmount)
      amortization += _getNum(row.currentAmortization)
      beginBalance += _getNum(row.beginBalance)
      increase += _getNum(row.increase)
      decrease += _getNum(row.decrease)
      endBalance += _getNum(row.endBalance)
    }

    return { total, amortization, beginBalance, increase, decrease, endBalance }
  })

  // ═══ adjudicationFromDetail: I4-2 合计 → I4-1 审定表（Req 2.2-2.5）═══

  /**
   * 从 I4-2 明细期末余额合计推导 I4-1 审定数参考值：
   * - audited: 期末余额合计（= I4-1 审定表 "审定数" 交叉验证来源）
   *
   * 当 I4-1 审定数 ≠ 此值时可能存在未记录调整或分类差异。
   *
   * 审定数最终公式：未审数 + AJE + RJE
   * 此处提供的是从明细侧推导的参考值（应与公式结果一致）。
   */
  const adjudicationFromDetail: ComputedRef<{ audited: number }> = computed(() => {
    // 明细侧推导：期末余额合计即为审定后的科目余额
    const totals = detailTotals.value as I4DetailTotals
    return { audited: totals.endBalance }
  })

  // ═══ amortizationMatrix: I4-6/I4-7 → 12月摊销矩阵（Req 6.4-6.6）═════

  /**
   * 从 I4-6（直线法）或 I4-7（工作量法）摊销测算行提取12月摊销矩阵：
   * 返回 number[][]，每行对应一个项目的12个月摊销额。
   *
   * 结构示例：
   * [
   *   [1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000, 1000], // 项目A
   *   [500,  500,  500,  500,  500,  500,  500,  500,  500,  500,  500,  500],  // 项目B
   * ]
   *
   * 用途：
   * - I4-1 审定表"本期摊销"列 = 各项目年度合计之和
   * - 摊销分配表按费用科目分摊（管理费用/销售费用等）
   * - 附注披露引用年度摊销合计
   *
   * 若行数据中无 monthlyAmorts 数组，则尝试从 annualTotal 平均分摊12个月。
   */
  const amortizationMatrix: ComputedRef<number[][]> = computed(() => {
    const matrix: number[][] = []

    for (const row of amortizationRows.value) {
      if (row.monthlyAmorts && Array.isArray(row.monthlyAmorts) && row.monthlyAmorts.length > 0) {
        // 直接使用月度数组（补齐12位）
        const months = row.monthlyAmorts.slice(0, 12).map(v => _getNum(v))
        while (months.length < 12) {
          months.push(0)
        }
        matrix.push(months)
      } else if (_getNum(row.annualTotal) > 0) {
        // 降级：从年度合计平均分摊12个月
        const monthly = _getNum(row.annualTotal) / 12
        matrix.push(Array(12).fill(monthly))
      }
      // 无数据行跳过（不占位）
    }

    return matrix
  })

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // I4-2 → I4-1 明细合计（原始金额/本期摊销）
    detailTotals,
    // I4-2 合计 → I4-1 审定表审定数参考（期末余额）
    adjudicationFromDetail,
    // I4-6/I4-7 → 12月摊销矩阵（每行一个项目×12月）
    amortizationMatrix,
  }
}

export default useI4CrossSheet
