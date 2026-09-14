/**
 * useL1OverdueCheck — L1-7 逾期检查 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.4
 * Requirements: 6.1-6.3
 *
 * 职责：
 * - calcOverdueDays：逾期天数 = 报告日 - 到期日
 * - calcOverdueInterest：逾期利息
 * - 逾期天数分级高亮（<30天黄 / 30-90天橙 / >90天红）
 */
import { computed, type ComputedRef, type Ref } from 'vue'
import { calcOverdueDays, calcOverdueInterest } from '@/composables/useL1InterestEngine'
import { calcSubtotal } from '@/composables/useL1FormulaEngine'
import type { useL1FormData } from '@/composables/useL1FormData'
import type { OverdueCheckRow } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 逾期风险等级 */
export type OverdueLevel = 'none' | 'low' | 'medium' | 'high'

/** 逾期检查计算结果行 */
export interface OverdueCheckComputed extends OverdueCheckRow {
  /** 计算后的逾期天数（正值=逾期，负值/0=未逾期） */
  computedOverdueDays: number
  /** 逾期风险等级（用于高亮） */
  overdueLevel: OverdueLevel
  /** 是否逾期（天数>0） */
  isOverdue: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 逾期等级阈值 */
const OVERDUE_LOW_DAYS = 30    // <30天：黄色（低风险）
const OVERDUE_MEDIUM_DAYS = 90 // 30-90天：橙色（中风险）
                                // >90天：红色（高风险）

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1-7 逾期贷款检查业务逻辑
 *
 * @param formData 由调用方传入的 useL1FormData 实例
 * @param reportDate 报告期截止日
 */
export function useL1OverdueCheck(
  formData: ReturnType<typeof useL1FormData>,
  reportDate: Ref<Date>,
) {
  const { overdueCheckRows, debounceSave } = formData

  // ─── 1. 计算属性：每行逾期天数+等级 ──────────────────────────────────

  /** 各行自动计算逾期天数并分级 */
  const computedRows: ComputedRef<OverdueCheckComputed[]> = computed(() => {
    return overdueCheckRows.value.map(row => {
      // 解析到期日
      const dueDate = row.dueDate ? new Date(row.dueDate) : null
      const computedOverdueDays = calcOverdueDays(dueDate, reportDate.value)
      const isOverdue = computedOverdueDays > 0

      // 分级
      let overdueLevel: OverdueLevel = 'none'
      if (isOverdue) {
        if (computedOverdueDays < OVERDUE_LOW_DAYS) {
          overdueLevel = 'low'
        } else if (computedOverdueDays <= OVERDUE_MEDIUM_DAYS) {
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
  const overdueSummary: ComputedRef<Record<OverdueLevel, number>> = computed(() => {
    const summary: Record<OverdueLevel, number> = { none: 0, low: 0, medium: 0, high: 0 }
    for (const row of computedRows.value) {
      summary[row.overdueLevel]++
    }
    return summary
  })

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /**
   * 更新某行字段
   */
  function updateRow(index: number, field: keyof OverdueCheckRow, value: string | number): void {
    if (index < 0 || index >= overdueCheckRows.value.length) return
    const row = overdueCheckRows.value[index] as any
    row[field] = value

    // 如果修改了到期日，重算逾期天数
    if (field === 'dueDate') {
      const dueDate = value ? new Date(value as string) : null
      row.overdueDays = calcOverdueDays(dueDate, reportDate.value)
    }

    _triggerSave(index)
  }

  /**
   * 新增逾期检查行
   */
  function addRow(contractNo: string): void {
    const newRow: OverdueCheckRow = {
      contractNo,
      dueDate: '',
      reportDate: reportDate.value.toISOString().slice(0, 10),
      overdueDays: 0,
      overdueAmount: 0,
      isExtended: '',
      riskEvaluation: '',
    }
    overdueCheckRows.value.push(newRow)
    _triggerSave(overdueCheckRows.value.length - 1)
  }

  /**
   * 删除行
   */
  function removeRow(index: number): void {
    if (index < 0 || index >= overdueCheckRows.value.length) return
    overdueCheckRows.value.splice(index, 1)
    _triggerSaveAll()
  }

  // ─── 4. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = overdueCheckRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields = ['contractNo', 'dueDate', 'reportDate', 'overdueDays',
      'overdueAmount', 'isExtended', 'riskEvaluation']
    const items = fields.map(field => ({
      item_id: `L1-ovd-${n}-${field}`,
      conclusion: null,
      remark: (row as any)[field] != null && (row as any)[field] !== '' && (row as any)[field] !== 0
        ? String((row as any)[field])
        : null,
    }))
    debounceSave(items)
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < overdueCheckRows.value.length; i++) {
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

export default useL1OverdueCheck
