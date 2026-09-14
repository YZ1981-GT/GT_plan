/**
 * useL4InitialMeasure — L4-6 初始计量 composable
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Task: 3.4
 * Requirements: 6.1-6.5
 *
 * 职责：
 * - calcInitialAmount（发行价-交易费用）
 * - calcPremiumDiscount（溢折价=初始入账-面值）
 * - IRR求解（solveEIR）
 * - 与L4-7期初摊余成本对接
 *
 * 科目：2502 应付债券（贷方/负债类）
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  calcInitialAmount,
  calcPremiumDiscount,
  calcSubtotal,
} from './useL4FormulaEngine'
import { solveEIR } from './useL4EIREngine'
import type { useL4FormData, ChecklistResponse } from './useL4FormData'

/** 🔴 P0 修复：JSON-array 存储（此前 flat keys `L4-6-row-{n}-{field}` 无 hydration → 刷新数据丢失） */
const ITEM_ROWS = 'L4-6-rows'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 初始计量行数据 */
export interface L4InitialMeasureRow {
  /** 行唯一标识 */
  key: string
  /** 债券名称 */
  bondName: string
  /** 面值 */
  faceValue: number
  /** 发行价格 */
  issuePrice: number
  /** 交易费用 */
  transactionCost: number
  /** 初始入账金额（公式列：发行价-交易费用） */
  initialAmount: number
  /** 溢折价（公式列：初始入账-面值） */
  premiumDiscount: number
  /** 票面利率 */
  couponRate: number
  /** 期限（年） */
  periods: number
  /** 付息方式 */
  paymentType: 'bullet' | 'installment'
  /** 实际利率（IRR求解或手动输入） */
  effectiveRate: number
  /** IRR是否已求解 */
  isEirSolved: boolean
}

/** 溢折价类型枚举 */
export type PremiumDiscountType = '溢价' | '折价' | '平价'

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L4-6 初始计量业务逻辑
 *
 * @param formData 由调用方传入的 useL4FormData 实例
 * @param measureRows reactive ref of measure rows
 */
export function useL4InitialMeasure(
  formData: ReturnType<typeof useL4FormData>,
  measureRows: Ref<L4InitialMeasureRow[]>,
) {
  const { allResponses, debouncedSave } = formData

  /** IRR求解中状态 */
  const isSolvingEIR = ref(false)

  // ─── 0. Hydration ────────────────────────────────────────────────────
  function hydrate(): void {
    const raw = allResponses.value.get(ITEM_ROWS)?.remark
    if (!raw) return
    try {
      const parsed = JSON.parse(raw)
      if (Array.isArray(parsed)) measureRows.value = parsed
    } catch { /* ignore */ }
  }
  hydrate()
  watch(
    () => allResponses.value.get(ITEM_ROWS)?.remark,
    (v) => { if (v && measureRows.value.length === 0) hydrate() },
  )

  function _persist(): void {
    debouncedSave(ITEM_ROWS, { remark: JSON.stringify(measureRows.value) } as Partial<ChecklistResponse>)
  }

  // ─── 1. 计算属性 ──────────────────────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<L4InitialMeasureRow[]> = computed(() => {
    return measureRows.value.map(row => ({
      ...row,
      initialAmount: calcInitialAmount(row.issuePrice, row.transactionCost),
      premiumDiscount: calcPremiumDiscount(
        calcInitialAmount(row.issuePrice, row.transactionCost),
        row.faceValue,
      ),
    }))
  })

  /** 初始入账合计 */
  const totalInitialAmount: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.initialAmount))
  })

  /** 溢折价合计 */
  const totalPremiumDiscount: ComputedRef<number> = computed(() => {
    return calcSubtotal(computedRows.value.map(r => r.premiumDiscount))
  })

  // ─── 2. 溢折价判定 ────────────────────────────────────────────────────

  /** 判定溢折价类型 */
  function getPremiumDiscountType(premiumDiscount: number): PremiumDiscountType {
    if (premiumDiscount > 0.01) return '溢价'
    if (premiumDiscount < -0.01) return '折价'
    return '平价'
  }

  // ─── 3. IRR求解 ───────────────────────────────────────────────────────

  /**
   * 求解实际利率（EIR/IRR）
   * 构造未来现金流并调用 solveEIR
   *
   * @param rowIndex 行索引
   */
  function solveRowEIR(rowIndex: number): void {
    const row = measureRows.value[rowIndex]
    if (!row) return

    const initial = calcInitialAmount(row.issuePrice, row.transactionCost)
    if (initial <= 0 || row.periods <= 0 || row.faceValue <= 0) {
      ElMessage.warning('请先填写完整数据（发行价、交易费用、面值、期限）')
      return
    }

    isSolvingEIR.value = true

    try {
      // 构造未来现金流
      const cashFlows: number[] = []
      const couponPerPeriod = row.faceValue * row.couponRate

      if (row.paymentType === 'bullet') {
        // 到期一次还本付息：前N-1期无现金流，最后一期=面值+全部累积票面利息
        for (let i = 0; i < row.periods - 1; i++) {
          cashFlows.push(0)
        }
        cashFlows.push(row.faceValue + couponPerPeriod * row.periods)
      } else {
        // 分期付息：每期付票面利息，最后一期额外还本金
        for (let i = 0; i < row.periods - 1; i++) {
          cashFlows.push(couponPerPeriod)
        }
        cashFlows.push(couponPerPeriod + row.faceValue)
      }

      const eir = solveEIR(cashFlows, initial)

      if (eir > 0) {
        row.effectiveRate = Math.round(eir * 1e8) / 1e8 // 保留8位小数
        row.isEirSolved = true
        _persist()
        ElMessage.success(`实际利率已求解：${(eir * 100).toFixed(4)}%`)
      } else {
        ElMessage.warning('IRR未收敛，请手动输入实际利率')
      }
    } finally {
      isSolvingEIR.value = false
    }
  }

  // ─── 4. 行操作 ────────────────────────────────────────────────────────

  /** 更新某行字段 */
  function updateRow(index: number, field: keyof L4InitialMeasureRow, value: string | number | boolean): void {
    if (index < 0 || index >= measureRows.value.length) return
    const row = measureRows.value[index] as any
    row[field] = value

    // 重算公式列
    if (['issuePrice', 'transactionCost', 'faceValue'].includes(field)) {
      row.initialAmount = calcInitialAmount(row.issuePrice, row.transactionCost)
      row.premiumDiscount = calcPremiumDiscount(row.initialAmount, row.faceValue)
    }

    _persist()
  }

  /**
   * 获取某行的初始摊余成本（供L4-7期初摊余成本对接）
   */
  function getInitialCostForSubsequent(rowIndex: number): number {
    const row = measureRows.value[rowIndex]
    if (!row) return 0
    return calcInitialAmount(row.issuePrice, row.transactionCost)
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    isSolvingEIR,

    // 计算属性
    computedRows,
    totalInitialAmount,
    totalPremiumDiscount,

    // 操作
    updateRow,
    solveRowEIR,
    getPremiumDiscountType,
    getInitialCostForSubsequent,
  }
}

export default useL4InitialMeasure
