/**
 * useL3PledgeCheck — L3-8 抵质押资产检查 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 3.4
 * Requirements: 7.4-7.5
 *
 * 职责：
 * - 担保比例 = 担保借款/账面价值×100%
 * - 担保覆盖率统计
 * - 行操作 + 持久化
 */
import { computed, type ComputedRef } from 'vue'
import { calcPledgeRatio, calcSubtotal } from '@/composables/useL3FormulaEngine'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 抵质押检查行原始数据 */
export interface L3PledgeCheckRow {
  /** 抵质押资产名称 */
  assetName: string
  /** 资产类型 */
  assetType: string
  /** 账面价值 */
  bookValue: number
  /** 担保借款额 */
  guaranteedLoan: number
  /** 担保比例（公式列） */
  pledgeRatio: number
  /** 权属核验结果 */
  ownershipVerified: string
  /** 评估日期 */
  appraisalDate: string
  /** 备注 */
  remark: string
}

/** 抵质押检查计算结果行 */
export interface L3PledgeCheckComputed extends L3PledgeCheckRow {
  /** 计算后的担保比例 */
  computedRatio: number
  /** 比例是否异常（>100% 贷款超过资产价值） */
  hasRatioWarning: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 担保比例警告阈值（超过100%说明贷款超过资产价值） */
const RATIO_WARNING_THRESHOLD = 100

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L3-8 抵质押资产检查业务逻辑
 *
 * @param formData 由调用方传入的 useL3FormData 实例
 * @param pledgeRows reactive ref of pledge check rows
 */
export function useL3PledgeCheck(
  formData: ReturnType<typeof useL3FormData>,
  pledgeRows: { value: L3PledgeCheckRow[] },
) {
  const { debouncedSave } = formData

  // ─── 1. 计算属性：每行担保比例 ────────────────────────────────────────

  /** 各行自动计算担保比例 */
  const computedRows: ComputedRef<L3PledgeCheckComputed[]> = computed(() => {
    return pledgeRows.value.map(row => {
      const computedRatio = calcPledgeRatio(row.guaranteedLoan, row.bookValue)
      return {
        ...row,
        computedRatio: parseFloat(computedRatio.toFixed(2)),
        hasRatioWarning: computedRatio > RATIO_WARNING_THRESHOLD,
      }
    })
  })

  // ─── 2. 统计 ──────────────────────────────────────────────────────────

  /** 担保借款总额 */
  const totalGuaranteedLoan: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(pledgeRows.value.map(r => r.guaranteedLoan)).toFixed(2),
    )
  })

  /** 资产账面价值总额 */
  const totalBookValue: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(pledgeRows.value.map(r => r.bookValue)).toFixed(2),
    )
  })

  /** 综合担保比例（总担保借款/总资产价值） */
  const overallRatio: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcPledgeRatio(totalGuaranteedLoan.value, totalBookValue.value).toFixed(2),
    )
  })

  /** 超标行数 */
  const warningCount: ComputedRef<number> = computed(() => {
    return computedRows.value.filter(r => r.hasRatioWarning).length
  })

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /** 更新某行字段 */
  function updateRow(index: number, field: keyof L3PledgeCheckRow, value: string | number): void {
    if (index < 0 || index >= pledgeRows.value.length) return
    const row = pledgeRows.value[index] as any
    row[field] = value

    // 如果修改了金额字段，重算比例
    if (field === 'guaranteedLoan' || field === 'bookValue') {
      row.pledgeRatio = calcPledgeRatio(row.guaranteedLoan, row.bookValue)
    }

    _triggerSave(index)
  }

  /** 新增抵质押检查行 */
  function addRow(assetName: string): void {
    const newRow: L3PledgeCheckRow = {
      assetName,
      assetType: '',
      bookValue: 0,
      guaranteedLoan: 0,
      pledgeRatio: 0,
      ownershipVerified: '',
      appraisalDate: '',
      remark: '',
    }
    pledgeRows.value.push(newRow)
    _triggerSave(pledgeRows.value.length - 1)
  }

  /** 删除行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= pledgeRows.value.length) return
    pledgeRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = pledgeRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields: (keyof L3PledgeCheckRow)[] = [
      'assetName', 'assetType', 'bookValue', 'guaranteedLoan',
      'pledgeRatio', 'ownershipVerified', 'appraisalDate', 'remark',
    ]
    for (const field of fields) {
      const val = (row as any)[field]
      debouncedSave(`L3-plg-${n}-${field}`, {
        remark: val != null && val !== '' && val !== 0 ? String(val) : null,
      })
    }
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < pledgeRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算
    computedRows,
    totalGuaranteedLoan,
    totalBookValue,
    overallRatio,
    warningCount,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL3PledgeCheck
