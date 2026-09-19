/**
 * useJ1AllocationCheck — J1-7 分配情况检查表 composable
 *
 * 核心：薪酬费用分配到各科目(管理/销售/生产/制造/研发/在建)的闭合校验
 * 关键联动：管理费用→K9, 销售费用→K8
 *
 * Source: J1-7 分配情况检查表 48行×13列
 *
 * Spec: .kiro/specs/j1-employee-compensation/
 * Requirements: 5.3, 6.2-6.5
 */
import { ref, computed, type Ref } from 'vue'
import { validateAllocationClosure, calcSubtotal, parseNum } from './useJ1FormulaEngine'

export interface AllocationRow {
  id: string
  category: string          // 薪酬项目（工资/社保/公积金等）
  adminExpense: number      // 管理费用 → K9
  sellingExpense: number    // 销售费用 → K8
  productionCost: number    // 生产成本
  manufacturing: number     // 制造费用
  researchExpense: number   // 研发费用
  construction: number      // 在建工程
  otherExpense: number      // 其他
  rowTotal: number          // 行合计
  creditIncrease: number    // 明细表贷方增加
  difference: number        // 差额=行合计-贷方增加
  isBalanced: boolean       // 是否平衡
}

export function useJ1AllocationCheck(htmlData: Ref<Record<string, unknown>>) {
  const rows: Ref<AllocationRow[]> = ref([])

  function initFromHtmlData(data: Record<string, unknown>) {
    const rawRows = (data.allocation_check_rows || []) as Array<Record<string, unknown>>
    rows.value = rawRows.map(r => {
      const adminExpense = parseNum(r.admin_expense as number)
      const sellingExpense = parseNum(r.selling_expense as number)
      const productionCost = parseNum(r.production_cost as number)
      const manufacturing = parseNum(r.manufacturing as number)
      const researchExpense = parseNum(r.research_expense as number)
      const construction = parseNum(r.construction as number)
      const otherExpense = parseNum(r.other_expense as number)
      const rowTotal = calcSubtotal([
        adminExpense, sellingExpense, productionCost,
        manufacturing, researchExpense, construction, otherExpense,
      ])
      const creditIncrease = parseNum(r.credit_increase as number)
      const diff = rowTotal - creditIncrease

      return {
        id: String(r.id || ''),
        category: String(r.category || ''),
        adminExpense,
        sellingExpense,
        productionCost,
        manufacturing,
        researchExpense,
        construction,
        otherExpense,
        rowTotal,
        creditIncrease,
        difference: diff,
        isBalanced: Math.abs(diff) < 0.01,
      }
    })
  }

  // ── 列合计（用于K8/K9联动） ───────────────────────────────────────────────

  const totalAdmin = computed(() => calcSubtotal(rows.value.map(r => r.adminExpense)))
  const totalSelling = computed(() => calcSubtotal(rows.value.map(r => r.sellingExpense)))
  const totalProduction = computed(() => calcSubtotal(rows.value.map(r => r.productionCost)))
  const totalResearch = computed(() => calcSubtotal(rows.value.map(r => r.researchExpense)))

  // ── 整体闭合校验 ──────────────────────────────────────────────────────────

  const overallClosure = computed(() => {
    const allocated = rows.value.map(r => r.rowTotal)
    const total = calcSubtotal(rows.value.map(r => r.creditIncrease))
    return validateAllocationClosure(allocated, total)
  })

  const hasImbalance = computed(() => rows.value.some(r => !r.isBalanced))

  return {
    rows,
    totalAdmin,
    totalSelling,
    totalProduction,
    totalResearch,
    overallClosure,
    hasImbalance,
    initFromHtmlData,
  }
}
