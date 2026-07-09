/**
 * useN5RdSuperDeduction — N5-6-1 加计扣除研发费用情况明细表 composable
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 3.4
 * Requirements: 5.1-5.5
 *
 * 职责：
 * - 管理N5-6-1数据（研发费用项目，6大费用类别）
 * - Uses calcRdSuperDeduction from useN5IncomeTaxEngine
 * - Uses calcSubtotal from useN5FormulaEngine
 * - 计算研发费用合计 + 加计扣除额
 * - 区分费用化/资本化研发费用
 * - 接收I6研发费用/I2开发支出联动
 * - 加计扣除额回填N5-5纳税调整调减项
 *
 * 加计比例：
 * - 100%：一般企业（2023年起）
 * - 120%：集成电路/工业母机等特定行业
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcRdSuperDeduction } from './useN5IncomeTaxEngine'
import { calcSubtotal, parseNum } from './useN5FormulaEngine'
import type { ChecklistResponse } from './useN5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 研发费用6大类别 */
export type RdExpenseCategory = '人员人工' | '直接投入' | '折旧费用' | '无形资产摊销' | '新产品设计费' | '其他费用'

/** 研发项目行 */
export interface N5RdProjectRow {
  /** 行序号 */
  index: number
  /** 研发项目名称 */
  projectName: string
  /** 人员人工费用 */
  personnelCost: number
  /** 直接投入费用 */
  directInput: number
  /** 折旧费用 */
  depreciation: number
  /** 无形资产摊销 */
  amortization: number
  /** 新产品设计费等其他费用 */
  otherExpense: number
  /** 研发费用合计 = Σ各类 */
  totalExpense: number
  /** 费用化(true)/资本化(false) */
  isExpensed: boolean
  /** 来源（I6/I2联动或手填） */
  source?: string
}

/** 研发费用汇总 */
export interface N5RdSuperDeductionSummary {
  /** 费用化研发费用合计 */
  expensedTotal: number
  /** 资本化研发费用合计（按摊销加计） */
  capitalizedTotal: number
  /** 研发费用总计 */
  grandTotal: number
  /** 加计比例（小数，如1.0=100%） */
  superRate: number
  /** 费用化部分加计扣除额 */
  expensedDeduction: number
  /** 资本化部分加计扣除额（按年摊销×加计比例） */
  capitalizedDeduction: number
  /** 加计扣除额合计 */
  totalDeduction: number
  /** 项目数量 */
  projectCount: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认加计比例（2023年起一般企业100%加计） */
const DEFAULT_SUPER_RATE = 1.0

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN5RdSuperDeductionOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN5RdSuperDeduction(options: UseN5RdSuperDeductionOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 加计比例 ──────────────────────────────────────────────────────────

  const superRate: ComputedRef<number> = computed(() => {
    const rate = getField('6-1', 'super-rate')
    return rate != null ? parseNum(rate) : DEFAULT_SUPER_RATE
  })

  // ─── 2. 研发项目行数据 ────────────────────────────────────────────────────

  const rows: ComputedRef<N5RdProjectRow[]> = computed(() => {
    const itemId = 'N5-6-1-rd-projects'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    if (raw.length === 0) return []

    return raw.map((r: any, i: number) => {
      const personnelCost = parseNum(r.personnelCost)
      const directInput = parseNum(r.directInput)
      const depreciation = parseNum(r.depreciation)
      const amortization = parseNum(r.amortization)
      const otherExpense = parseNum(r.otherExpense)
      const totalExpense = calcSubtotal([personnelCost, directInput, depreciation, amortization, otherExpense])

      return {
        index: i + 1,
        projectName: r.projectName || `研发项目${i + 1}`,
        personnelCost,
        directInput,
        depreciation,
        amortization,
        otherExpense,
        totalExpense,
        isExpensed: r.isExpensed !== false,
        source: r.source || undefined,
      }
    })
  })

  // ─── 3. 费用化 / 资本化分组 ───────────────────────────────────────────────

  const expensedRows: ComputedRef<N5RdProjectRow[]> = computed(() => {
    return rows.value.filter(r => r.isExpensed)
  })

  const capitalizedRows: ComputedRef<N5RdProjectRow[]> = computed(() => {
    return rows.value.filter(r => !r.isExpensed)
  })

  // ─── 4. 合计 ──────────────────────────────────────────────────────────────

  const expensedTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(expensedRows.value.map(r => r.totalExpense))
  })

  const capitalizedTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(capitalizedRows.value.map(r => r.totalExpense))
  })

  const grandTotal: ComputedRef<number> = computed(() => {
    return calcSubtotal(rows.value.map(r => r.totalExpense))
  })

  // ─── 5. 加计扣除额（核心公式：研发费用×加计比例） ─────────────────────────

  const expensedDeduction: ComputedRef<number> = computed(() => {
    return calcRdSuperDeduction(expensedTotal.value, superRate.value)
  })

  const capitalizedDeduction: ComputedRef<number> = computed(() => {
    // 资本化部分按年摊销金额×加计比例（简化处理为资本化总额×比例）
    return calcRdSuperDeduction(capitalizedTotal.value, superRate.value)
  })

  const totalDeduction: ComputedRef<number> = computed(() => {
    return expensedDeduction.value + capitalizedDeduction.value
  })

  // ─── 6. 汇总 ─────────────────────────────────────────────────────────────

  const summary: ComputedRef<N5RdSuperDeductionSummary> = computed(() => ({
    expensedTotal: expensedTotal.value,
    capitalizedTotal: capitalizedTotal.value,
    grandTotal: grandTotal.value,
    superRate: superRate.value,
    expensedDeduction: expensedDeduction.value,
    capitalizedDeduction: capitalizedDeduction.value,
    totalDeduction: totalDeduction.value,
    projectCount: rows.value.length,
  }))

  // ─── 7. 各费用类别小计 ────────────────────────────────────────────────────

  const categoryBreakdown: ComputedRef<Record<RdExpenseCategory, number>> = computed(() => {
    const r = rows.value
    return {
      '人员人工': calcSubtotal(r.map(x => x.personnelCost)),
      '直接投入': calcSubtotal(r.map(x => x.directInput)),
      '折旧费用': calcSubtotal(r.map(x => x.depreciation)),
      '无形资产摊销': calcSubtotal(r.map(x => x.amortization)),
      '新产品设计费': 0, // 包含在otherExpense中
      '其他费用': calcSubtotal(r.map(x => x.otherExpense)),
    }
  })

  // ─── 8. 行操作 ────────────────────────────────────────────────────────────

  /**
   * 更新指定行字段
   */
  async function updateRow(
    rowIndex: number,
    field: keyof Pick<N5RdProjectRow, 'projectName' | 'personnelCost' | 'directInput' | 'depreciation' | 'amortization' | 'otherExpense' | 'isExpensed'>,
    value: number | string | boolean,
  ): Promise<void> {
    const currentRows = rows.value.map(r => ({ ...r }))
    if (rowIndex >= 0 && rowIndex < currentRows.length) {
      ;(currentRows[rowIndex] as any)[field] = value
      await _saveRows(currentRows)
    }
  }

  /**
   * 新增研发项目行
   */
  async function addProject(projectName: string): Promise<void> {
    const currentRows = rows.value.map(r => ({ ...r }))
    currentRows.push({
      index: currentRows.length + 1,
      projectName,
      personnelCost: 0,
      directInput: 0,
      depreciation: 0,
      amortization: 0,
      otherExpense: 0,
      totalExpense: 0,
      isExpensed: true,
    })
    await _saveRows(currentRows)
  }

  /**
   * 删除指定行
   */
  async function removeProject(rowIndex: number): Promise<void> {
    const currentRows = rows.value.filter((_, i) => i !== rowIndex)
    await _saveRows(currentRows)
  }

  /**
   * 设置加计比例
   */
  async function setSuperRate(rate: number): Promise<void> {
    await saveField('6-1', 'super-rate', rate)
  }

  /**
   * 同步加计扣除额到N5-5调减项
   */
  async function syncDeductionToTaxAdjustment(): Promise<void> {
    await saveField('6-1', 'super-deduction-total', totalDeduction.value)
  }

  // ─── 9. I6/I2联动数据设置 ─────────────────────────────────────────────────

  /**
   * 从I6研发费用/I2开发支出接收研发费用数据（EventBus联动）
   */
  async function setFromI6I2(data: { expensed: number; capitalized: number }): Promise<void> {
    await saveField('6-1', 'i6-expensed', data.expensed)
    await saveField('6-1', 'i2-capitalized', data.capitalized)
  }

  // ─── 10. 内部helper ───────────────────────────────────────────────────────

  async function _saveRows(data: N5RdProjectRow[]): Promise<void> {
    const itemId = 'N5-6-1-rd-projects'
    const conclusion = JSON.stringify(data)
    allResponses.value.set(itemId, {
      item_id: itemId,
      conclusion,
      remark: null,
    })
    await saveField('6-1', 'rd-projects', data)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // Computed
    superRate,
    rows,
    expensedRows,
    capitalizedRows,
    expensedTotal,
    capitalizedTotal,
    grandTotal,
    expensedDeduction,
    capitalizedDeduction,
    totalDeduction,
    summary,
    categoryBreakdown,
    // Actions
    updateRow,
    addProject,
    removeProject,
    setSuperRate,
    syncDeductionToTaxAdjustment,
    setFromI6I2,
  }
}

export default useN5RdSuperDeduction
