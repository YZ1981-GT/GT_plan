/**
 * useL1PledgeCheck — L1-8 抵质押检查 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.4
 * Requirements: 6.4-6.5
 *
 * 职责：
 * - calcPledgeRatio：担保比例 = 担保借款 / 账面价值 × 100
 * - 比例>100% 红色警告
 */
import { computed, type ComputedRef } from 'vue'
import { calcPledgeRatio, calcSubtotal } from '@/composables/useL1FormulaEngine'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { PledgeCheckRow } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 抵质押检查计算结果行 */
export interface PledgeCheckComputed extends PledgeCheckRow {
  /** 计算后的担保比例（百分比） */
  computedPledgeRatio: number
  /** 比例>100% 需红色警告 */
  hasRatioWarning: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 担保比例警告阈值（100%=贷款超过资产价值） */
const RATIO_WARNING_THRESHOLD = 100

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1-8 抵质押资产检查业务逻辑
 *
 * @param formData 由调用方传入的 useL1FormData 实例
 */
export function useL1PledgeCheck(formData: ReturnType<typeof useL1FormData>) {
  const { pledgeCheckRows, debounceSave } = formData

  // ─── 1. 计算属性：每行担保比例 ────────────────────────────────────────

  /** 各行自动计算担保比例 */
  const computedRows: ComputedRef<PledgeCheckComputed[]> = computed(() => {
    return pledgeCheckRows.value.map(row => {
      const computedPledgeRatio = calcPledgeRatio(row.guaranteedLoan, row.bookValue)
      return {
        ...row,
        computedPledgeRatio: parseFloat(computedPledgeRatio.toFixed(2)),
        hasRatioWarning: computedPledgeRatio > RATIO_WARNING_THRESHOLD,
      }
    })
  })

  // ─── 2. 统计 ──────────────────────────────────────────────────────────

  /** 担保借款合计 */
  const totalGuaranteedLoan: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(pledgeCheckRows.value.map(r => r.guaranteedLoan)).toFixed(2),
    )
  })

  /** 账面价值合计 */
  const totalBookValue: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(pledgeCheckRows.value.map(r => r.bookValue)).toFixed(2),
    )
  })

  /** 综合担保比例（合计口径） */
  const overallPledgeRatio: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcPledgeRatio(totalGuaranteedLoan.value, totalBookValue.value).toFixed(2),
    )
  })

  /** 比例>100%的行数（高风险） */
  const warningCount: ComputedRef<number> = computed(() => {
    return computedRows.value.filter(r => r.hasRatioWarning).length
  })

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /**
   * 更新某行字段
   */
  function updateRow(index: number, field: keyof PledgeCheckRow, value: string | number): void {
    if (index < 0 || index >= pledgeCheckRows.value.length) return
    const row = pledgeCheckRows.value[index] as any
    row[field] = value

    // 如果修改了金额字段，重算比例
    if (field === 'guaranteedLoan' || field === 'bookValue') {
      row.pledgeRatio = calcPledgeRatio(row.guaranteedLoan, row.bookValue)
    }

    _triggerSave(index)
  }

  /**
   * 新增抵质押检查行
   */
  function addRow(assetName: string): void {
    const newRow: PledgeCheckRow = {
      assetName,
      bookValue: 0,
      guaranteedLoan: 0,
      pledgeRatio: 0,
      ownershipVerified: '',
    }
    pledgeCheckRows.value.push(newRow)
    _triggerSave(pledgeCheckRows.value.length - 1)
  }

  /**
   * 删除行
   */
  function removeRow(index: number): void {
    if (index < 0 || index >= pledgeCheckRows.value.length) return
    pledgeCheckRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = pledgeCheckRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields = ['assetName', 'bookValue', 'guaranteedLoan', 'pledgeRatio', 'ownershipVerified']
    const items = fields.map(field => ({
      item_id: `L1-plg-${n}-${field}`,
      conclusion: null,
      remark: (row as any)[field] != null && (row as any)[field] !== '' && (row as any)[field] !== 0
        ? String((row as any)[field])
        : null,
    }))
    debounceSave(items)
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < pledgeCheckRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算
    computedRows,
    totalGuaranteedLoan,
    totalBookValue,
    overallPledgeRatio,
    warningCount,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL1PledgeCheck
