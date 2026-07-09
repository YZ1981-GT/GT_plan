/**
 * useL3OverdueCheck — L3-7 逾期贷款检查 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 3.4
 * Requirements: 7.1-7.3
 *
 * 职责：
 * - 逾期天数 = 报告日 - 到期日（>0 为逾期）
 * - 橙色/红色分级高亮（30天内橙色, >90天红色）
 * - 逾期统计汇总
 */
import { computed, type ComputedRef } from 'vue'
import { calcOverdueDays } from '@/composables/useL3InterestEngine'
import { calcSubtotal } from '@/composables/useL3FormulaEngine'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 逾期风险等级 */
export type L3OverdueLevel = 'none' | 'low' | 'medium' | 'high'

/** 逾期检查行原始数据 */
export interface L3OverdueCheckRow {
  /** 借款合同号 */
  contractNo: string
  /** 借款银行 */
  bank: string
  /** 到期日 (YYYY-MM-DD) */
  dueDate: string
  /** 逾期天数（公式列） */
  overdueDays: number
  /** 逾期金额 */
  overdueAmount: number
  /** 是否展期 */
  isExtended: string
  /** 风险评价 */
  riskEvaluation: string
}

/** 逾期检查计算结果行 */
export interface L3OverdueCheckComputed extends L3OverdueCheckRow {
  /** 计算后的逾期天数（正值=逾期，负值/0=未逾期） */
  computedOverdueDays: number
  /** 逾期风险等级（用于高亮：橙/红） */
  overdueLevel: L3OverdueLevel
  /** 是否逾期（天数>0） */
  isOverdue: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 逾期等级阈值 */
const OVERDUE_LOW_DAYS = 30    // ≤30天：橙色（关注）
const OVERDUE_HIGH_DAYS = 90   // >90天：红色（高风险）

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L3-7 逾期贷款检查业务逻辑
 *
 * @param formData 由调用方传入的 useL3FormData 实例
 * @param overdueRows reactive ref of overdue check rows
 * @param reportDate 报告期截止日 (YYYY-MM-DD)
 */
export function useL3OverdueCheck(
  formData: ReturnType<typeof useL3FormData>,
  overdueRows: { value: L3OverdueCheckRow[] },
  reportDate: string,
) {
  const { debouncedSave } = formData

  // ─── 1. 计算属性：每行逾期天数+等级 ──────────────────────────────────

  /** 各行自动计算逾期天数并分级 */
  const computedRows: ComputedRef<L3OverdueCheckComputed[]> = computed(() => {
    return overdueRows.value.map(row => {
      const computedOverdueDays = calcOverdueDays(row.dueDate, reportDate)
      const isOverdue = computedOverdueDays > 0

      // 分级：橙/红
      let overdueLevel: L3OverdueLevel = 'none'
      if (isOverdue) {
        if (computedOverdueDays <= OVERDUE_LOW_DAYS) {
          overdueLevel = 'low'
        } else if (computedOverdueDays <= OVERDUE_HIGH_DAYS) {
          overdueLevel = 'medium'
        } else {
          overdueLevel = 'high'
        }
      }

      return {
        ...row,
        computedOverdueDays,
        overdueLevel,
        isOverdue,
      }
    })
  })

  // ─── 2. 统计 ──────────────────────────────────────────────────────────

  /** 逾期笔数 */
  const overdueCount: ComputedRef<number> = computed(() => {
    return computedRows.value.filter(r => r.isOverdue).length
  })

  /** 逾期金额合计 */
  const totalOverdueAmount: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(
        computedRows.value.filter(r => r.isOverdue).map(r => r.overdueAmount),
      ).toFixed(2),
    )
  })

  /** 按等级分组统计 */
  const overdueSummary: ComputedRef<Record<L3OverdueLevel, number>> = computed(() => {
    const summary: Record<L3OverdueLevel, number> = { none: 0, low: 0, medium: 0, high: 0 }
    for (const row of computedRows.value) {
      summary[row.overdueLevel]++
    }
    return summary
  })

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /** 更新某行字段 */
  function updateRow(index: number, field: keyof L3OverdueCheckRow, value: string | number): void {
    if (index < 0 || index >= overdueRows.value.length) return
    const row = overdueRows.value[index] as any
    row[field] = value

    // 如果修改了到期日，重算逾期天数
    if (field === 'dueDate') {
      row.overdueDays = calcOverdueDays(value as string, reportDate)
    }

    _triggerSave(index)
  }

  /** 新增逾期检查行 */
  function addRow(contractNo: string, bank?: string): void {
    const newRow: L3OverdueCheckRow = {
      contractNo,
      bank: bank || '',
      dueDate: '',
      overdueDays: 0,
      overdueAmount: 0,
      isExtended: '',
      riskEvaluation: '',
    }
    overdueRows.value.push(newRow)
    _triggerSave(overdueRows.value.length - 1)
  }

  /** 删除行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= overdueRows.value.length) return
    overdueRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = overdueRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields: (keyof L3OverdueCheckRow)[] = [
      'contractNo', 'bank', 'dueDate', 'overdueDays',
      'overdueAmount', 'isExtended', 'riskEvaluation',
    ]
    for (const field of fields) {
      const val = (row as any)[field]
      debouncedSave(`L3-ovd-${n}-${field}`, {
        remark: val != null && val !== '' && val !== 0 ? String(val) : null,
      })
    }
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < overdueRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算
    computedRows,
    overdueCount,
    totalOverdueAmount,
    overdueSummary,

    // 行操作
    addRow,
    removeRow,
    updateRow,
  }
}

export default useL3OverdueCheck
