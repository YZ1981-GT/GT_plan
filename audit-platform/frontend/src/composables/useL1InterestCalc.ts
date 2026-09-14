/**
 * useL1InterestCalc — L1-5 利息测算表 composable（核心！）
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.4
 * Requirements: 4.1-4.7
 *
 * 职责：
 * - 每行调用 calcStartDate/calcEndDate/calcInterestDays/calcInterest
 * - 自动计算差异 = 测算利息 - 账载利息
 * - 高亮差异>0行
 * - 触发 publishInterestCalculated（通过 useL1CrossSheet）
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import {
  calcInterest,
  calcInterestDiff,
  calcStartDate,
  calcEndDate,
  calcInterestDays,
} from '@/composables/useL1InterestEngine'
import { calcSubtotal } from '@/composables/useL1FormulaEngine'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { InterestCalcRow } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 利息测算计算结果行（含公式列） */
export interface InterestCalcComputed extends InterestCalcRow {
  /** 计算后的计息天数 */
  computedDays: number
  /** 测算利息 */
  computedInterest: number
  /** 差异 = 测算 - 账载 */
  computedDiff: number
  /** 差异是否超阈值（需高亮） */
  hasDiffWarning: boolean
}

/** 筛选配置 */
export interface InterestFilterConfig {
  contractNo?: string
  bank?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 差异高亮阈值（元），|差异| > 此值红色高亮 */
const DIFF_THRESHOLD = 0.01

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1-5 利息测算表业务逻辑
 *
 * @param formData 由调用方传入的 useL1FormData 实例
 * @param reportStart 报告期起始日（如 2024-01-01）
 * @param reportEnd 报告期截止日（如 2024-12-31）
 */
export function useL1InterestCalc(
  formData: ReturnType<typeof useL1FormData>,
  reportStart: Ref<Date>,
  reportEnd: Ref<Date>,
) {
  const { interestCalcRows, debounceSave } = formData

  // ─── 1. 筛选状态 ──────────────────────────────────────────────────────

  const filterConfig = ref<InterestFilterConfig>({})

  function setFilter(config: Partial<InterestFilterConfig>): void {
    filterConfig.value = { ...filterConfig.value, ...config }
  }

  function clearFilter(): void {
    filterConfig.value = {}
  }

  // ─── 2. 计算属性：每行利息测算 ────────────────────────────────────────

  /**
   * 每行自动计算：
   * 1. 起算时点 = max(报告期起始, 借款起始)
   * 2. 截止时点 = min(借款到期, 报告期截止)
   * 3. 计息天数（xlsx公式逻辑）
   * 4. 测算利息 = 本金 × 年利率 × 天数 / 365
   * 5. 差异 = 测算 - 账载
   */
  const computedRows: ComputedRef<InterestCalcComputed[]> = computed(() => {
    return interestCalcRows.value.map(row => {
      // 解析日期
      const loanStart = row.startDate ? new Date(row.startDate) : null
      const loanEnd = row.endDate ? new Date(row.endDate) : null

      let computedDays = 0
      let computedInterest = 0

      if (loanStart && loanEnd) {
        const effectiveStart = calcStartDate(loanStart, reportStart.value)
        const effectiveEnd = calcEndDate(loanEnd, reportEnd.value)
        computedDays = calcInterestDays(effectiveStart, effectiveEnd)
        computedInterest = calcInterest(row.principal, row.rate, computedDays)
      } else {
        // 如果有手动输入的天数，直接用
        computedDays = row.days
        computedInterest = calcInterest(row.principal, row.rate, computedDays)
      }

      const computedDiff = calcInterestDiff(computedInterest, row.bookedInterest)

      return {
        ...row,
        computedDays,
        computedInterest: parseFloat(computedInterest.toFixed(2)),
        computedDiff: parseFloat(computedDiff.toFixed(2)),
        hasDiffWarning: Math.abs(computedDiff) > DIFF_THRESHOLD,
      }
    })
  })

  /** 筛选后的行 */
  const filteredRows: ComputedRef<InterestCalcComputed[]> = computed(() => {
    let rows = computedRows.value
    const f = filterConfig.value
    if (f.contractNo) {
      rows = rows.filter(r => r.contractNo.includes(f.contractNo!))
    }
    if (f.bank) {
      rows = rows.filter(r => r.bank.includes(f.bank!))
    }
    return rows
  })

  // ─── 3. 合计 ──────────────────────────────────────────────────────────

  /** 测算利息合计 */
  const totalCalculatedInterest: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(computedRows.value.map(r => r.computedInterest)).toFixed(2),
    )
  })

  /** 账载利息合计 */
  const totalBookedInterest: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(computedRows.value.map(r => r.bookedInterest)).toFixed(2),
    )
  })

  /** 差异合计 */
  const totalDiff: ComputedRef<number> = computed(() => {
    return parseFloat((totalCalculatedInterest.value - totalBookedInterest.value).toFixed(2))
  })

  /** 存在差异的行数 */
  const warningCount: ComputedRef<number> = computed(() => {
    return computedRows.value.filter(r => r.hasDiffWarning).length
  })

  // ─── 4. 行操作 ────────────────────────────────────────────────────────

  /**
   * 更新某行字段
   */
  function updateRow(index: number, field: keyof InterestCalcRow, value: string | number): void {
    if (index < 0 || index >= interestCalcRows.value.length) return
    const row = interestCalcRows.value[index] as any
    row[field] = value
    _triggerSave(index)
  }

  /**
   * 新增利息测算行
   */
  function addRow(contractNo: string, bank: string): void {
    const newRow: InterestCalcRow = {
      bank,
      contractNo,
      loanStart: '',
      loanEnd: '',
      startDate: '',
      endDate: '',
      rate: 0,
      principal: 0,
      days: 0,
      calculatedInterest: 0,
      bookedInterest: 0,
      diff: 0,
    }
    interestCalcRows.value.push(newRow)
    _triggerSave(interestCalcRows.value.length - 1)
  }

  /**
   * 删除行
   */
  function removeRow(index: number): void {
    if (index < 0 || index >= interestCalcRows.value.length) return
    interestCalcRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = interestCalcRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields = ['bank', 'contractNo', 'loanStart', 'loanEnd', 'startDate', 'endDate',
      'rate', 'principal', 'days', 'calculatedInterest', 'bookedInterest', 'diff']
    const items = fields.map(field => ({
      item_id: `L1-int-${n}-${field}`,
      conclusion: null,
      remark: (row as any)[field] != null && (row as any)[field] !== 0 ? String((row as any)[field]) : null,
    }))
    debounceSave(items)
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < interestCalcRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 筛选
    filterConfig,
    setFilter,
    clearFilter,

    // 计算
    computedRows,
    filteredRows,
    totalCalculatedInterest,
    totalBookedInterest,
    totalDiff,
    warningCount,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL1InterestCalc
