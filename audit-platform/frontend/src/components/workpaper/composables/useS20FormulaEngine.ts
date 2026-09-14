/**
 * useS20FormulaEngine — S20 营业收入扣除情况核查公式引擎
 *
 * 纯函数，无副作用、无 Vue reactivity、确定性输出。
 *
 * 本引擎覆盖：
 * - 营业收入 = 主营业务收入(SUM) + 其他业务收入(SUM)
 * - 扣除合计 = 与主营无关 + 不具备商业实质
 * - 占比 = 扣除合计 / 营业收入（revenue=0 时 unable=true, ratio=0）
 * - 扣除后金额 = 营业收入 - 扣除合计
 *
 * Spec: .kiro/specs/s-estimate-calculation-workpapers/ Task 3.2
 * Requirements: 4.1, 4.2, 4.3
 */

import { computed, type Ref } from 'vue'

// ─── helpers ────────────────────────────────────────────────

/** 安全数值解析：null/undefined/NaN/空→0 */
export function parseNum(val: string | number | null | undefined): number {
  if (val === null || val === undefined || val === '') return 0
  const n = typeof val === 'number' ? val : Number(val)
  return Number.isFinite(n) ? n : 0
}

// ─── interfaces ─────────────────────────────────────────────

export interface RevenueDeductionInput {
  mainBusiness: number[]     // 主营业务收入明细
  otherBusiness: number[]    // 其他业务收入明细
  unrelatedRevenue: number   // 与主营业务无关的业务收入
  noSubstanceRevenue: number // 不具备商业实质的收入
}

export interface RevenueDeductionResult {
  revenue: number              // = SUM(main) + SUM(other)
  mainBusinessTotal: number    // = SUM(main)
  otherBusinessTotal: number   // = SUM(other)
  deductionTotal: number       // = unrelated + noSubstance
  deductionRatio: number       // = deductionTotal / revenue (0 if revenue=0)
  revenueAfterDeduction: number // = revenue - deductionTotal
  unable: boolean              // true if revenue = 0 (ratio undefined)
}

// ─── 核心公式（Property P5） ────────────────────────────────

/**
 * 计算营业收入扣除项目
 *
 * 公式链（来源：S20 营业收入扣除情况核查底稿 区段3）：
 * - 营业收入 C16 = SUM(主营C17) + SUM(其他C22)
 * - 扣除项目合计 C27 = 与主营无关C28 + 不具备商业实质C29
 * - 占比 C30 = C27 / C16
 * - 扣除后金额 C31 = C16 - C27
 *
 * @param i - RevenueDeductionInput
 * @returns RevenueDeductionResult
 */
export function calcRevenueDeduction(i: RevenueDeductionInput): RevenueDeductionResult {
  // 安全处理数组：确保为数组，空数组→SUM=0
  const mainArr = Array.isArray(i.mainBusiness) ? i.mainBusiness : []
  const otherArr = Array.isArray(i.otherBusiness) ? i.otherBusiness : []

  // 主营业务收入合计 = SUM(mainBusiness)
  const mainBusinessTotal = mainArr.reduce((sum, v) => sum + parseNum(v), 0)

  // 其他业务收入合计 = SUM(otherBusiness)
  const otherBusinessTotal = otherArr.reduce((sum, v) => sum + parseNum(v), 0)

  // 营业收入 = 主营 + 其他
  const revenue = mainBusinessTotal + otherBusinessTotal

  // 扣除合计 = 与主营无关 + 不具备商业实质
  const unrelated = parseNum(i.unrelatedRevenue)
  const noSubstance = parseNum(i.noSubstanceRevenue)
  const deductionTotal = unrelated + noSubstance

  // 占比 = 扣除合计 / 营业收入（revenue=0 时不可计算）
  const unable = revenue === 0
  const deductionRatio = unable ? 0 : deductionTotal / revenue

  // 扣除后金额 = 营业收入 - 扣除合计
  const revenueAfterDeduction = revenue - deductionTotal

  return {
    revenue,
    mainBusinessTotal,
    otherBusinessTotal,
    deductionTotal,
    deductionRatio,
    revenueAfterDeduction,
    unable,
  }
}

// ─── composable wrapper ─────────────────────────────────────

/**
 * Vue composable wrapper — 将纯函数以 reactive 方式暴露给组件
 *
 * 使用方式：
 * ```ts
 * const { result } = useS20FormulaEngine(inputRef)
 * // result.value.revenue / result.value.deductionRatio / ...
 * ```
 */
export function useS20FormulaEngine(input?: Ref<RevenueDeductionInput>) {
  const result = computed<RevenueDeductionResult>(() => {
    if (!input?.value) {
      return {
        revenue: 0,
        mainBusinessTotal: 0,
        otherBusinessTotal: 0,
        deductionTotal: 0,
        deductionRatio: 0,
        revenueAfterDeduction: 0,
        unable: true,
      }
    }
    return calcRevenueDeduction(input.value)
  })

  return {
    // 纯函数（直接导出供独立调用）
    calcRevenueDeduction,
    parseNum,
    // reactive computed
    result,
  }
}
