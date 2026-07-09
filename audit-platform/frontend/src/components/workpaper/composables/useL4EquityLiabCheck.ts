/**
 * useL4EquityLiabCheck — L4-5 权益负债划分检查 composable
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Task: 3.4
 * Requirements: 7.1-7.5
 *
 * 职责：
 * - calcLiabilityComponent（负债成分=未来现金流按市场利率折现）
 * - calcEquityComponent（权益成分=发行总额-负债成分）
 * - 权益成分<0时标记异常（红色警告"分拆异常"）
 *
 * CAS 37 复合金融工具分拆：
 *   可转债等含权益成分的金融工具需分拆。
 *   先按市场利率折现确定负债成分（NPV），
 *   剩余归权益成分（发行总额-负债成分）。
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import {
  calcLiabilityComponent,
  calcEquityComponent,
} from './useL4EquityLiabEngine'
import { calcSubtotal } from './useL4FormulaEngine'
import type { useL4FormData } from './useL4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 权益负债划分行数据 */
export interface L4EquityLiabRow {
  /** 行唯一标识 */
  key: string
  /** 工具名称（如：2024年可转债） */
  instrumentName: string
  /** 合同条款摘要 */
  contractTerms: string
  /** 发行总额 */
  totalProceeds: number
  /** 面值 */
  faceValue: number
  /** 票面利率 */
  couponRate: number
  /** 市场利率（同期限、无转换权的类似工具利率） */
  marketRate: number
  /** 期限（年） */
  periods: number
  /** 付息方式 */
  paymentType: 'bullet' | 'installment'
  /** 负债成分（公式列：NPV折现） */
  liabilityComponent: number
  /** 权益成分（公式列：总额-负债） */
  equityComponent: number
  /** 划分依据 */
  classificationBasis: string
  /** 是否异常（权益成分<0） */
  isAbnormal: boolean
}

/** 划分汇总 */
export interface L4EquityLiabSummary {
  totalProceeds: number
  totalLiability: number
  totalEquity: number
  abnormalCount: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L4-5 权益负债划分检查业务逻辑
 *
 * @param formData 由调用方传入的 useL4FormData 实例
 * @param checkRows reactive ref of check rows
 */
export function useL4EquityLiabCheck(
  formData: ReturnType<typeof useL4FormData>,
  checkRows: Ref<L4EquityLiabRow[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 计算属性：负债/权益成分 ───────────────────────────────────────

  /** 各行公式列自动计算 */
  const computedRows: ComputedRef<L4EquityLiabRow[]> = computed(() => {
    return checkRows.value.map(row => {
      // 构造未来现金流
      const cashFlows = _buildCashFlows(row)
      const liability = calcLiabilityComponent(cashFlows, row.marketRate)
      const equity = calcEquityComponent(row.totalProceeds, liability)
      const isAbnormal = equity < 0

      return {
        ...row,
        liabilityComponent: liability,
        equityComponent: equity,
        isAbnormal,
      }
    })
  })

  // ─── 2. 汇总 ─────────────────────────────────────────────────────────

  /** 划分汇总统计 */
  const summary: ComputedRef<L4EquityLiabSummary> = computed(() => {
    const rows = computedRows.value
    return {
      totalProceeds: calcSubtotal(rows.map(r => r.totalProceeds)),
      totalLiability: calcSubtotal(rows.map(r => r.liabilityComponent)),
      totalEquity: calcSubtotal(rows.map(r => r.equityComponent)),
      abnormalCount: rows.filter(r => r.isAbnormal).length,
    }
  })

  // ─── 3. 异常检测 ──────────────────────────────────────────────────────

  /** 异常行列表（权益成分<0） */
  const abnormalRows: ComputedRef<L4EquityLiabRow[]> = computed(() => {
    return computedRows.value.filter(r => r.isAbnormal)
  })

  /** 检查是否存在异常并提示 */
  function checkAbnormals(): void {
    const abnormals = abnormalRows.value
    if (abnormals.length > 0) {
      const names = abnormals.map(r => r.instrumentName).join('、')
      ElMessage.warning(`分拆异常：${names} 的权益成分为负，请检查市场利率或合同条款`)
    }
  }

  // ─── 4. 行操作 ────────────────────────────────────────────────────────

  /** 更新某行字段 */
  function updateRow(index: number, field: keyof L4EquityLiabRow, value: string | number): void {
    if (index < 0 || index >= checkRows.value.length) return
    const row = checkRows.value[index] as any
    row[field] = value

    // 重算公式列
    if (['totalProceeds', 'faceValue', 'couponRate', 'marketRate', 'periods', 'paymentType'].includes(field)) {
      const cashFlows = _buildCashFlows(row)
      row.liabilityComponent = calcLiabilityComponent(cashFlows, row.marketRate)
      row.equityComponent = calcEquityComponent(row.totalProceeds, row.liabilityComponent)
      row.isAbnormal = row.equityComponent < 0
    }

    _triggerSave(index)
  }

  /** 执行分拆计算（触发所有行重算+异常检查） */
  function executeClassification(): void {
    // 重算由 computedRows 自动完成，此处仅做异常检查+保存
    checkAbnormals()
    _triggerSaveAll()
  }

  // ─── 5. 工具方法 ──────────────────────────────────────────────────────

  /** 构造未来现金流数组 */
  function _buildCashFlows(row: L4EquityLiabRow): number[] {
    const cashFlows: number[] = []
    const couponPerPeriod = row.faceValue * row.couponRate

    if (row.paymentType === 'bullet') {
      // 到期一次还本付息
      for (let i = 0; i < row.periods - 1; i++) {
        cashFlows.push(0)
      }
      cashFlows.push(row.faceValue + couponPerPeriod * row.periods)
    } else {
      // 分期付息到期一次还本
      for (let i = 0; i < row.periods - 1; i++) {
        cashFlows.push(couponPerPeriod)
      }
      cashFlows.push(couponPerPeriod + row.faceValue)
    }

    return cashFlows
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const row = checkRows.value[rowIndex]
    if (!row) return
    const n = rowIndex + 1
    const fields: (keyof L4EquityLiabRow)[] = [
      'instrumentName', 'contractTerms', 'totalProceeds', 'faceValue',
      'couponRate', 'marketRate', 'periods', 'paymentType',
      'liabilityComponent', 'equityComponent', 'classificationBasis', 'isAbnormal',
    ]
    for (const field of fields) {
      const val = (row as any)[field]
      debouncedSave(`L4-5-row-${n}-${field}`, {
        remark: val != null && val !== '' && val !== 0 && val !== false ? String(val) : null,
      })
    }
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < checkRows.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算属性
    computedRows,
    summary,
    abnormalRows,

    // 操作
    updateRow,
    executeClassification,
    checkAbnormals,
  }
}

export default useL4EquityLiabCheck
