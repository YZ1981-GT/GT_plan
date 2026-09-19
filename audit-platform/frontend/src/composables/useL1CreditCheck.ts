/**
 * useL1CreditCheck — L1-4 征信核对 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.4
 * Requirements: 5.1-5.5
 *
 * 职责：
 * - 倒轧余额 calcCreditRollForward
 * - 差异 calcCreditDiff = 征信余额 - 账面余额
 * - 差异≠0 红色高亮
 * - 合计与L1-2明细交叉验证
 */
import { computed, type ComputedRef } from 'vue'
import { calcCreditDiff, calcSubtotal } from '@/composables/useL1FormulaEngine'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { CreditCheckRow } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 征信核对计算结果行 */
export interface CreditCheckComputed extends CreditCheckRow {
  /** 计算后的差异 = 征信余额 - 账面余额 */
  computedDiff: number
  /** 差异≠0 需红色高亮 */
  hasDiffWarning: boolean
  /** 差异说明是否已填（差异≠0时必填） */
  needsExplanation: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 差异阈值（0.01元内视为无差异） */
const DIFF_THRESHOLD = 0.01

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1-4 征信报告核对业务逻辑
 *
 * @param formData 由调用方传入的 useL1FormData 实例
 */
export function useL1CreditCheck(formData: ReturnType<typeof useL1FormData>) {
  const { creditCheckRows, debounceSave } = formData

  // ─── 1. 计算属性：每行差异 ────────────────────────────────────────────

  /** 各行自动计算差异 */
  const computedRows: ComputedRef<CreditCheckComputed[]> = computed(() => {
    return creditCheckRows.value.map(row => {
      const computedDiff = calcCreditDiff(row.creditBalance, row.bookBalance)
      const hasDiffWarning = Math.abs(computedDiff) > DIFF_THRESHOLD
      return {
        ...row,
        computedDiff: parseFloat(computedDiff.toFixed(2)),
        hasDiffWarning,
        needsExplanation: hasDiffWarning && (!row.diffExplanation || !row.diffExplanation.trim()),
      }
    })
  })

  // ─── 2. 合计 ──────────────────────────────────────────────────────────

  /** 征信余额合计 */
  const totalCreditBalance: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(creditCheckRows.value.map(r => r.creditBalance)).toFixed(2),
    )
  })

  /** 账面余额合计 */
  const totalBookBalance: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(creditCheckRows.value.map(r => r.bookBalance)).toFixed(2),
    )
  })

  /** 差异合计 */
  const totalDiff: ComputedRef<number> = computed(() => {
    return parseFloat((totalCreditBalance.value - totalBookBalance.value).toFixed(2))
  })

  /** 存在差异的行数 */
  const warningCount: ComputedRef<number> = computed(() => {
    return computedRows.value.filter(r => r.hasDiffWarning).length
  })

  /** 需要补填说明的行数 */
  const pendingExplanationCount: ComputedRef<number> = computed(() => {
    return computedRows.value.filter(r => r.needsExplanation).length
  })

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /**
   * 更新某行字段
   */
  function updateRow(index: number, field: keyof CreditCheckRow, value: string | number): void {
    if (index < 0 || index >= creditCheckRows.value.length) return
    const row = creditCheckRows.value[index] as any
    row[field] = value

    // 如果修改了余额字段，重算差异
    if (field === 'creditBalance' || field === 'bookBalance') {
      row.diff = calcCreditDiff(row.creditBalance, row.bookBalance)
    }

    _triggerSave(index)
  }

  /**
   * 新增征信核对行
   */
  function addRow(bank: string): void {
    const newRow: CreditCheckRow = {
      bank,
      creditLimit: 0,
      usedLimit: 0,
      creditBalance: 0,
      bookBalance: 0,
      diff: 0,
      diffExplanation: '',
    }
    creditCheckRows.value.push(newRow)
    _triggerSave(creditCheckRows.value.length - 1)
  }

  /**
   * 删除行
   */
  function removeRow(index: number): void {
    if (index < 0 || index >= creditCheckRows.value.length) return
    creditCheckRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = creditCheckRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields = ['bank', 'creditLimit', 'usedLimit', 'creditBalance',
      'bookBalance', 'diff', 'diffExplanation']
    const items = fields.map(field => ({
      item_id: `L1-cred-${n}-${field}`,
      conclusion: null,
      remark: (row as any)[field] != null && (row as any)[field] !== '' && (row as any)[field] !== 0
        ? String((row as any)[field])
        : null,
    }))
    debounceSave(items)
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < creditCheckRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算
    computedRows,
    totalCreditBalance,
    totalBookBalance,
    totalDiff,
    warningCount,
    pendingExplanationCount,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL1CreditCheck
