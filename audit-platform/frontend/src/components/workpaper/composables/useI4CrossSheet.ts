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
 * 摊销分支互斥：I4-6（直线法）与 I4-7（工作量法）取有数据的一方（优先 I4-6）。
 *
 * Spec（归档）: .kiro/specs/_archive/05-business-features/i4-long-term-prepaid/
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

/** I4-2 明细行原始 JSON（滚转字段 + 旧别名） */
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

/** I4-3 调整分录行原始 JSON 结构（对齐 Excel 列 + 兼容旧 AJE/RJE 字段） */
export interface I4AdjustmentRowRaw {
  rowId?: string
  description?: string        // 调整事项说明
  category?: string           // 账项调整 / 报表调整 / 其他
  entryType?: string          // AJE / RJE（由类别推导，兼容旧数据）
  reportItem?: string         // 报表项目
  accountCode?: string        // 科目代码
  accountName?: string        // 科目名称
  noteItem?: string           // 附注项目
  summary?: string            // 摘要（旧字段，等同 description）
  debitAmount?: number        // 借方调整金额
  creditAmount?: number       // 贷方调整金额
  debit?: number              // 旧字段兼容
  credit?: number             // 旧字段兼容
  indexRef?: string           // 索引
  remark?: string
  projectName?: string        // 明细项目（匹配 I4-2 / I4-1）
}

/** I4-6/I4-7 摊销测算行原始 JSON 结构（源表测算/账面/差异 或旧12月矩阵） */
export interface I4AmortizationRowRaw {
  rowId?: string
  name?: string
  itemName?: string
  originalAmount?: number
  totalMonths?: number
  totalUnits?: number
  workStandard?: number
  monthlyAmorts?: number[]
  monthlyAmort?: number[]
  yearTotal?: number
  calcPeriodAmort?: number
  periodAmortization?: number
  annualTotal?: number
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
  detailTotals: ComputedRef<I4DetailTotals>
  adjudicationFromDetail: ComputedRef<{ audited: number }>
  amortizationMatrix: ComputedRef<number[][]>
  detailRowsRaw: ComputedRef<any[]>
  adjustmentRowsRaw: ComputedRef<I4AdjustmentRowRaw[]>
  amortizationRowsRaw: ComputedRef<I4AmortizationRowRaw[]>
} {
  // ─── 解析 I4-2 明细行数据 ──────────────────────────────────────────────

  const detailRowsRaw = computed<any[]>(() => {
    const resp = allResponses.value.get('I4-2-rows')
    return safeParseRows<any>(resp?.remark)
  })

  // ─── 解析 I4-3 调整分录行数据 ──────────────────────────────────────────

  const adjustmentRowsRaw = computed<I4AdjustmentRowRaw[]>(() => {
    const resp = allResponses.value.get('I4-3-rows')
    return safeParseRows<I4AdjustmentRowRaw>(resp?.remark)
  })

  // ─── 解析 I4-6/I4-7 摊销测算行数据（互斥分支，优先取有数据的一方）───

  const amortizationRowsRaw = computed<I4AmortizationRowRaw[]>(() => {
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
   * - beginBalance / increase / decrease / endBalance
   *
   * 兼容新旧字段：projectName|name、currentIncrease|increase 等。
   */
  const detailTotals: ComputedRef<I4DetailTotals> = computed(() => {
    let total = 0
    let amortization = 0
    let beginBalance = 0
    let increase = 0
    let decrease = 0
    let endBalance = 0

    for (const row of detailRowsRaw.value) {
      const name = String(row?.projectName || row?.name || '').trim()
      if (name === '合计') continue
      total += _getNum(row.originalAmount)
      amortization += _getNum(
        row.auditedAmortization ?? row.currentAmortization ?? row.unadjAmortization ?? row.amortization,
      )
      beginBalance += _getNum(row.auditedOpening ?? row.beginBalance ?? row.unadjOpening)
      increase += _getNum(row.auditedIncrease ?? row.currentIncrease ?? row.unadjIncrease ?? row.increase)
      decrease += _getNum(row.auditedOtherDecrease ?? row.currentDecrease ?? row.unadjOtherDecrease ?? row.decrease)
      endBalance += _getNum(row.auditedEnding ?? row.endBalance ?? row.unadjEnding)
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
    const totals = detailTotals.value
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

    for (const row of amortizationRowsRaw.value) {
      const monthlySrc = row.monthlyAmorts ?? row.monthlyAmort
      if (monthlySrc && Array.isArray(monthlySrc) && monthlySrc.length > 0) {
        // 直接使用月度数组（补齐12位）
        const months = monthlySrc.slice(0, 12).map(v => _getNum(v))
        while (months.length < 12) {
          months.push(0)
        }
        matrix.push(months)
      } else {
        // 降级：I4-7 源表测算本年 / 年度合计 / 年合计 → 均分12月（供跨表汇总）
        const annual = _getNum(row.periodAmortization)
          || _getNum(row.calcPeriodAmort)
          || _getNum(row.yearTotal)
          || _getNum(row.annualTotal)
        if (annual > 0) {
          const monthly = annual / 12
          matrix.push(Array(12).fill(monthly))
        }
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
    detailRowsRaw,
    adjustmentRowsRaw,
    amortizationRowsRaw,
  }
}

export default useI4CrossSheet
