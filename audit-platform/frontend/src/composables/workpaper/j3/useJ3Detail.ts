/**
 * useJ3Detail — J3-1 股份支付情况表 composable
 *
 * 管理 18列情况表的动态行数据 + 费用分摊计算 + BS参数展示。
 * 列：方案名|类型|授予日|行权价|标的股数|等待期|可行权日|有效期|
 *     公允价值方法|变更情况|估计更新|剩余等待期限|索引号|
 *     单位FV|总FV|已确认|本期|累计|剩余|状态
 *
 * Spec: .kiro/specs/j3-share-based-payment/
 * Requirements: 2.1-2.7
 */
import { ref, computed, type Ref } from 'vue'
import {
  calcCumulativeExpense,
  calcVestingExpense,
  calcRemainingExpense,
  calcTotalFairValue,
  calcSubtotal,
} from './useJ3FormulaEngine'
import type { J3Plan } from './useJ3FormData'

export interface J3DetailRow extends J3Plan {
  totalFairValue: number
  fvMethod: string         // 公允价值确定方法
  changeNote: string       // 变更/取消情况
  estimateUpdate: string   // 估计更新情况
  remainingVesting: number // 剩余等待期限
  indexRef: string         // 协议索引号
  calcIndexRef: string     // 计算表索引号
}

export function useJ3Detail(plans: Ref<J3Plan[]>) {
  const searchTerm = ref('')

  // ── 行级公式重算 ──────────────────────────────────────────────────────────

  function recalcRow(plan: J3Plan): J3Plan {
    const totalFV = calcTotalFairValue(plan.unitFairValue, plan.sharesCount)
    const cumulative = calcCumulativeExpense(totalFV, plan.vestingPeriod, plan.serviceYears)
    const current = calcVestingExpense(totalFV, plan.vestingPeriod, plan.serviceYears, plan.priorCumulative)
    const remaining = calcRemainingExpense(totalFV, cumulative)
    return {
      ...plan,
      cumulativeExpense: cumulative,
      currentExpense: current,
      remainingExpense: remaining,
    }
  }

  // ── 合计行 ────────────────────────────────────────────────────────────────

  const subtotals = computed(() => ({
    totalShares: calcSubtotal(plans.value.map(p => p.sharesCount)),
    totalCurrentExpense: calcSubtotal(plans.value.map(p => p.currentExpense)),
    totalCumulativeExpense: calcSubtotal(plans.value.map(p => p.cumulativeExpense)),
    totalRemainingExpense: calcSubtotal(plans.value.map(p => p.remainingExpense)),
    totalFairValue: calcSubtotal(plans.value.map(p => calcTotalFairValue(p.unitFairValue, p.sharesCount))),
  }))

  // ── 权益/现金分类统计 ─────────────────────────────────────────────────────

  const equitySummary = computed(() => {
    const eq = plans.value.filter(p => p.type === 'equity')
    return {
      count: eq.length,
      totalExpense: calcSubtotal(eq.map(p => p.currentExpense)),
      label: '贷记资本公积',
    }
  })

  const cashSummary = computed(() => {
    const ca = plans.value.filter(p => p.type === 'cash')
    return {
      count: ca.length,
      totalExpense: calcSubtotal(ca.map(p => p.currentExpense)),
      label: '贷记应付职工薪酬',
    }
  })

  // ── 筛选 ──────────────────────────────────────────────────────────────────

  const filteredPlans = computed(() => {
    if (!searchTerm.value) return plans.value
    const term = searchTerm.value.toLowerCase()
    return plans.value.filter(p =>
      p.name.toLowerCase().includes(term) || p.type.includes(term),
    )
  })

  // ── 动态行操作 ────────────────────────────────────────────────────────────

  function addPlan(plan: J3Plan) {
    plans.value.push(recalcRow(plan))
  }

  function removePlan(index: number) {
    plans.value.splice(index, 1)
  }

  function updatePlan(index: number, updates: Partial<J3Plan>) {
    const existing = plans.value[index]
    if (existing) {
      const updated = { ...existing, ...updates }
      plans.value[index] = recalcRow(updated)
    }
  }

  return {
    searchTerm,
    subtotals,
    equitySummary,
    cashSummary,
    filteredPlans,
    recalcRow,
    addPlan,
    removePlan,
    updatePlan,
  }
}
