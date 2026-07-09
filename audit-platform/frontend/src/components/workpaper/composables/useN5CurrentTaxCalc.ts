/**
 * useN5CurrentTaxCalc — N5-4 当期所得税费用计算表 composable
 *
 * Spec: .kiro/specs/n5-income-tax-expense/
 * Task: 3.4
 * Requirements: 3.1-3.7
 *
 * 职责：
 * - 管理N5-4数据行（82行），计算链：会计利润→±调整→应纳税所得额→×税率→-减免→当期所得税
 * - Uses calcTaxableIncome / calcCurrentTax from useN5IncomeTaxEngine
 * - Uses calcSubtotal from useN5FormulaEngine
 * - 提供getters/setters：会计利润/纳税调增/调减/适用税率/减免税额/当期所得税
 * - 回填N5-1审定表当期所得税费用行
 *
 * 科目：6801 所得税费用（损益类）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcTaxableIncome, calcCurrentTax } from './useN5IncomeTaxEngine'
import { calcSubtotal, parseNum } from './useN5FormulaEngine'
import type { ChecklistResponse } from './useN5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** N5-4 计算表行数据 */
export interface N5CurrentTaxRow {
  /** 行序号 */
  index: number
  /** 项目名称 */
  label: string
  /** 行号（税务申报表行号对应） */
  lineNo: string
  /** 金额 */
  amount: number
  /** 是否公式行（只读计算） */
  isFormula: boolean
  /** 来源说明 */
  source?: string
}

/** 当期所得税计算链汇总 */
export interface N5CurrentTaxSummary {
  /** 会计利润总额（A利润表） */
  accountingProfit: number
  /** 纳税调增合计（N5-5） */
  addBackTotal: number
  /** 纳税调减合计（N5-5） */
  deductTotal: number
  /** 应纳税所得额 = 会计利润 + 调增 - 调减 */
  taxableIncome: number
  /** 适用税率 */
  taxRate: number
  /** 应纳所得税额 = 应纳税所得额 × 税率 */
  grossTax: number
  /** 减免税额合计（N5-6） */
  taxRelief: number
  /** 抵免税额 */
  taxCredit: number
  /** 加计扣除额（N5-6-1） */
  superDeduction: number
  /** 当期应纳所得税 = 应纳所得税额 - 减免 - 抵免 */
  currentTax: number
  /** 亏损标记（应纳税所得额<0） */
  isLoss: boolean
}

// ─── Composable ──────────────────────────────────────────────────────────────

export interface UseN5CurrentTaxCalcOptions {
  allResponses: Ref<Map<string, ChecklistResponse>>
  wpId: Ref<string>
  projectId: Ref<string>
  saveField: (sheet: string, field: string, value: any) => Promise<void>
  getField: (sheet: string, field: string) => any
}

export function useN5CurrentTaxCalc(options: UseN5CurrentTaxCalcOptions) {
  const { allResponses, saveField, getField } = options

  // ─── 1. 会计利润总额（来自A类利润表联动或手填） ────────────────────────────

  const accountingProfit: ComputedRef<number> = computed(() => {
    return parseNum(getField('4', 'accounting-profit'))
  })

  // ─── 2. 纳税调增/调减合计（来自N5-5纳税调整明细） ─────────────────────────

  const addBackTotal: ComputedRef<number> = computed(() => {
    return parseNum(getField('5', 'add-back-total'))
  })

  const deductTotal: ComputedRef<number> = computed(() => {
    return parseNum(getField('5', 'deduct-total'))
  })

  // ─── 3. 适用税率 ──────────────────────────────────────────────────────────

  const taxRate: ComputedRef<number> = computed(() => {
    const rate = getField('4', 'tax-rate')
    return rate != null ? parseNum(rate) : 0.25 // 默认25%一般企业
  })

  // ─── 4. 应纳税所得额（核心公式：会计利润+调增-调减） ─────────────────────

  const taxableIncome: ComputedRef<number> = computed(() => {
    return calcTaxableIncome(
      accountingProfit.value,
      addBackTotal.value,
      deductTotal.value,
    )
  })

  // ─── 5. 应纳所得税额 = 应纳税所得额 × 适用税率 ───────────────────────────

  const grossTax: ComputedRef<number> = computed(() => {
    // 亏损时当期所得税为0
    if (taxableIncome.value <= 0) return 0
    return calcCurrentTax(taxableIncome.value, taxRate.value)
  })

  // ─── 6. 减免税额 / 抵免税额（来自N5-6税收优惠） ──────────────────────────

  const taxRelief: ComputedRef<number> = computed(() => {
    return parseNum(getField('6', 'tax-relief-total'))
  })

  const taxCredit: ComputedRef<number> = computed(() => {
    return parseNum(getField('4', 'tax-credit'))
  })

  // ─── 7. 加计扣除额（来自N5-6-1） ─────────────────────────────────────────

  const superDeduction: ComputedRef<number> = computed(() => {
    return parseNum(getField('6-1', 'super-deduction-total'))
  })

  // ─── 8. 当期应纳所得税（最终结果） ───────────────────────────────────────

  const currentTax: ComputedRef<number> = computed(() => {
    // 亏损时当期所得税为0
    if (taxableIncome.value <= 0) return 0
    const result = grossTax.value - taxRelief.value - taxCredit.value
    return Math.max(0, result) // 当期所得税不为负
  })

  // ─── 9. 亏损判断 ──────────────────────────────────────────────────────────

  const isLoss: ComputedRef<boolean> = computed(() => {
    return taxableIncome.value < 0
  })

  // ─── 10. 汇总（供外部使用） ───────────────────────────────────────────────

  const summary: ComputedRef<N5CurrentTaxSummary> = computed(() => ({
    accountingProfit: accountingProfit.value,
    addBackTotal: addBackTotal.value,
    deductTotal: deductTotal.value,
    taxableIncome: taxableIncome.value,
    taxRate: taxRate.value,
    grossTax: grossTax.value,
    taxRelief: taxRelief.value,
    taxCredit: taxCredit.value,
    superDeduction: superDeduction.value,
    currentTax: currentTax.value,
    isLoss: isLoss.value,
  }))

  // ─── 11. 82行表结构数据 ───────────────────────────────────────────────────

  const rows: ComputedRef<N5CurrentTaxRow[]> = computed(() => {
    const itemId = 'N5-4-calc-rows'
    const resp = allResponses.value.get(itemId)
    let raw: any[] = []
    if (resp?.conclusion) {
      try { raw = JSON.parse(resp.conclusion) } catch { raw = [] }
    }

    // 核心计算行（固定结构）
    const coreRows: N5CurrentTaxRow[] = [
      { index: 1, label: '一、会计利润总额', lineNo: '1', amount: accountingProfit.value, isFormula: true, source: 'A类利润表' },
      { index: 2, label: '加：纳税调增合计', lineNo: '2', amount: addBackTotal.value, isFormula: true, source: 'N5-5' },
      { index: 3, label: '减：纳税调减合计', lineNo: '3', amount: deductTotal.value, isFormula: true, source: 'N5-5' },
      { index: 4, label: '二、应纳税所得额(1+2-3)', lineNo: '4', amount: taxableIncome.value, isFormula: true },
      { index: 5, label: '税率', lineNo: '5', amount: taxRate.value, isFormula: false },
      { index: 6, label: '三、应纳所得税额(4×5)', lineNo: '6', amount: grossTax.value, isFormula: true },
      { index: 7, label: '减：减免所得税额', lineNo: '7', amount: taxRelief.value, isFormula: true, source: 'N5-6' },
      { index: 8, label: '减：抵免所得税额', lineNo: '8', amount: taxCredit.value, isFormula: false },
      { index: 9, label: '四、当期应纳所得税额(6-7-8)', lineNo: '9', amount: currentTax.value, isFormula: true },
    ]

    // 如果有动态附加行，追加
    if (raw.length > 0) {
      const dynamicRows = raw.map((r: any, i: number) => ({
        index: coreRows.length + i + 1,
        label: r.label || `附加项${i + 1}`,
        lineNo: r.lineNo || '',
        amount: parseNum(r.amount),
        isFormula: false,
        source: r.source,
      }))
      return [...coreRows, ...dynamicRows]
    }

    return coreRows
  })

  // ─── 12. Setters ──────────────────────────────────────────────────────────

  /**
   * 设置会计利润（通常由A类利润表联动自动填入，也可手动覆盖）
   */
  async function setAccountingProfit(value: number): Promise<void> {
    await saveField('4', 'accounting-profit', value)
  }

  /**
   * 设置适用税率
   */
  async function setTaxRate(value: number): Promise<void> {
    await saveField('4', 'tax-rate', value)
  }

  /**
   * 设置抵免税额
   */
  async function setTaxCredit(value: number): Promise<void> {
    await saveField('4', 'tax-credit', value)
  }

  /**
   * 同步当期所得税到N5-1审定表（回填）
   */
  async function syncCurrentTaxToAdjudication(): Promise<void> {
    await saveField('1', 'current-tax', currentTax.value)
  }

  // ─── Return ────────────────────────────────────────────────────────────────

  return {
    // Computed
    accountingProfit,
    addBackTotal,
    deductTotal,
    taxRate,
    taxableIncome,
    grossTax,
    taxRelief,
    taxCredit,
    superDeduction,
    currentTax,
    isLoss,
    summary,
    rows,
    // Actions
    setAccountingProfit,
    setTaxRate,
    setTaxCredit,
    syncCurrentTaxToAdjudication,
  }
}

export default useN5CurrentTaxCalc
