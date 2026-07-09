/**
 * useJ1CrossSheet — J1 应付职工薪酬 跨sheet交叉验证 + K8/K9联动
 *
 * 职责：
 * - 审定表 vs 明细表合计核对
 * - 月度分析合计 vs 审定表核对
 * - 分配闭合校验（J1-7 → K8/K9）
 * - K8/K9联动状态管理
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 3.2, 3.5, 6.2-6.5
 */
import { computed, type Ref, type ComputedRef } from 'vue'
import { validateAllocationClosure } from './useJ1FormulaEngine'

export interface CrossSheetCheckResult {
  diff: number
  isMatch: boolean
}

export interface AllocationClosureResult {
  diff: number
  isBalanced: boolean
  items: { label: string; amount: number }[]
}

export interface K8K9LinkageStatus {
  k8Amount: number     // K8销售费用-薪酬
  k9Amount: number     // K9管理费用-薪酬
  isLinked: boolean
}

export function useJ1CrossSheet(allResponses: Ref<Map<string, unknown> | Record<string, unknown>>) {
  // ── 辅助：从responses提取数值 ────────────────────────────────────────────

  function getNum(key: string): number {
    const map = allResponses.value
    let val: unknown
    if (map instanceof Map) {
      val = map.get(key)
    } else {
      val = (map as Record<string, unknown>)[key]
    }
    if (val === null || val === undefined) return 0
    const n = Number(val)
    return Number.isFinite(n) ? n : 0
  }

  // ── 审定表 vs 明细表合计 ───────────────────────────────────────────────────

  const adjudicationVsDetail: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const adjTotal = getNum('J1-1-audited-total')
    const detailTotal = getNum('J1-2-end-total')
    const diff = adjTotal - detailTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ── 月度分析合计 vs 审定表 ─────────────────────────────────────────────────

  const monthlyVsAdjudication: ComputedRef<CrossSheetCheckResult> = computed(() => {
    const monthlyTotal = getNum('J1-4-annual-total')
    const adjTotal = getNum('J1-1-audited-total')
    const diff = monthlyTotal - adjTotal
    return { diff, isMatch: Math.abs(diff) < 0.01 }
  })

  // ── 分配闭合校验 ──────────────────────────────────────────────────────────

  const allocationClosure: ComputedRef<AllocationClosureResult> = computed(() => {
    const items = [
      { label: '管理费用', amount: getNum('J1-7-admin-expense') },
      { label: '销售费用', amount: getNum('J1-7-selling-expense') },
      { label: '生产成本', amount: getNum('J1-7-production-cost') },
      { label: '制造费用', amount: getNum('J1-7-manufacturing') },
      { label: '研发费用', amount: getNum('J1-7-research') },
      { label: '在建工程', amount: getNum('J1-7-construction') },
    ]
    const total = getNum('J1-7-salary-total')
    const amounts = items.map(i => i.amount)
    const result = validateAllocationClosure(amounts, total)
    return {
      diff: result.difference,
      isBalanced: result.isValid,
      items,
    }
  })

  // ── K8/K9联动状态 ─────────────────────────────────────────────────────────

  const k8k9LinkageStatus: ComputedRef<K8K9LinkageStatus> = computed(() => {
    const k8Amount = getNum('J1-7-selling-expense')
    const k9Amount = getNum('J1-7-admin-expense')
    return {
      k8Amount,
      k9Amount,
      isLinked: k8Amount > 0 || k9Amount > 0,
    }
  })

  return {
    adjudicationVsDetail,
    monthlyVsAdjudication,
    allocationClosure,
    k8k9LinkageStatus,
  }
}
