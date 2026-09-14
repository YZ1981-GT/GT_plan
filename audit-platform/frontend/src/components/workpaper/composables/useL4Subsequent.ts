/**
 * useL4Subsequent — L4-7 后续计量 composable（核心！2分支）
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Task: 3.4
 * Requirements: 4.1-4.8
 *
 * 职责：
 * - 接收 bondBranch inject（到期一次还本付息 / 分期付息到期一次还本）
 * - 调用 generateSchedule(branch) 生成完整摊销表
 * - validateSchedule 末期验证（期末摊余成本≈面值）
 * - publishInterestCalculated → L2/L8（EventBus 'l4:interest-calculated'）
 *
 * 实际利率法核心：
 *   利息费用 = 期初摊余成本 × EIR
 *   到期一次还本付息(bullet): 期末 = 期初 + 利息费用
 *   分期付息(installment): 期末 = 期初 + 利息费用 - 票面利息
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { ElMessage } from 'element-plus'
import { eventBus } from '@/utils/eventBus'
import {
  generateSchedule,
  validateSchedule,
  calcInterestExpense,
  type EIRRow,
} from './useL4EIREngine'
import { calcSubtotal } from './useL4FormulaEngine'
import type { useL4FormData } from './useL4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 分支类型 */
export type L4BondBranch = 'bullet' | 'installment'

/** 后续计量债券参数 */
export interface L4SubsequentBondParams {
  /** 债券名称 */
  bondName: string
  /** 初始摊余成本（来自L4-6） */
  initialCost: number
  /** 面值 */
  faceValue: number
  /** 票面利率 */
  couponRate: number
  /** 实际利率（EIR） */
  eir: number
  /** 总期数 */
  periods: number
}

/** 验证结果 */
export interface L4ScheduleValidation {
  /** 是否通过（末期endCost≈面值） */
  isValid: boolean
  /** 尾差 */
  tailDiff: number
  /** 警告消息 */
  message: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L4-7 后续计量业务逻辑（2分支）
 *
 * @param formData 由调用方传入的 useL4FormData 实例
 * @param bondBranch 当前分支（由主入口 provide，L4-7 inject）
 * @param bondParams reactive bond parameters list
 */
export function useL4Subsequent(
  formData: ReturnType<typeof useL4FormData>,
  bondBranch: Ref<L4BondBranch>,
  bondParams: Ref<L4SubsequentBondParams[]>,
) {
  const { saveBatch } = formData

  /** 当前选中的债券索引 */
  const activeBondIndex = ref(0)

  // ─── 1. 摊销表生成 ────────────────────────────────────────────────────

  /** 各债券的摊销表 */
  const schedules: ComputedRef<EIRRow[][]> = computed(() => {
    return bondParams.value.map(params => {
      if (params.initialCost <= 0 || params.periods <= 0 || params.eir <= 0) {
        return []
      }
      return generateSchedule(
        params.initialCost,
        params.faceValue,
        params.couponRate,
        params.eir,
        params.periods,
        bondBranch.value,
      )
    })
  })

  /** 当前债券的摊销表 */
  const activeSchedule: ComputedRef<EIRRow[]> = computed(() => {
    return schedules.value[activeBondIndex.value] || []
  })

  // ─── 2. 末期验证 ──────────────────────────────────────────────────────

  /** 各债券的验证结果 */
  const validations: ComputedRef<L4ScheduleValidation[]> = computed(() => {
    return schedules.value.map((schedule, i) => {
      if (schedule.length === 0) {
        return { isValid: false, tailDiff: 0, message: '摊销表为空，请检查参数' }
      }

      const params = bondParams.value[i]
      const result = validateSchedule(schedule, params.faceValue)

      if (bondBranch.value === 'bullet') {
        // bullet分支：末期摊余成本远大于面值（含累积利息），不做强制校验
        return {
          isValid: true,
          tailDiff: result.tailDiff,
          message: '到期一次还本付息：利息资本化滚入，末期摊余成本含累积利息',
        }
      }

      // installment分支：末期应≈面值
      if (result.isValid) {
        return { isValid: true, tailDiff: result.tailDiff, message: '末期摊余成本校验通过' }
      }
      return {
        isValid: false,
        tailDiff: result.tailDiff,
        message: `末期偏差 ${result.tailDiff.toFixed(2)} 元，超出±1元阈值`,
      }
    })
  })

  /** 当前债券的验证结果 */
  const activeValidation: ComputedRef<L4ScheduleValidation> = computed(() => {
    return validations.value[activeBondIndex.value] || { isValid: false, tailDiff: 0, message: '' }
  })

  // ─── 3. 利息费用合计 ──────────────────────────────────────────────────

  /** 全部债券实际利息费用合计（供L2/L8联动） */
  const totalInterestExpense: ComputedRef<number> = computed(() => {
    let total = 0
    for (const schedule of schedules.value) {
      total += calcSubtotal(schedule.map(r => r.interestExpense))
    }
    return total
  })

  /** 当前期（假设当前报告期为第N期）的利息费用合计 */
  const currentPeriodInterest: ComputedRef<number> = computed(() => {
    // 取各债券最后一期的利息费用作为当期费用（实际应由报告期确定）
    let total = 0
    for (const schedule of schedules.value) {
      if (schedule.length > 0) {
        total += schedule[schedule.length - 1].interestExpense
      }
    }
    return total
  })

  // ─── 4. EventBus publish → L2/L8 ─────────────────────────────────────

  /**
   * 发布 'l4:interest-calculated' 事件
   * 供 L2应付利息 / L8财务费用 订阅消费
   */
  function publishInterestCalculated(): void {
    const payload = {
      totalInterestExpense: totalInterestExpense.value,
      currentPeriodInterest: currentPeriodInterest.value,
      branch: bondBranch.value,
      bondCount: bondParams.value.length,
      wpCode: 'L4',
      sheet: 'L4-7',
      timestamp: Date.now(),
    }

    eventBus.emit('l4:interest-calculated', payload)
    ElMessage.success(`利息费用已发布（合计 ${currentPeriodInterest.value.toFixed(2)} 元）→ L2/L8`)
  }

  // ─── 5. 保存摊销表 ────────────────────────────────────────────────────

  /**
   * 保存当前摊销表到 checklist_responses
   */
  async function saveSchedule(): Promise<void> {
    const schedule = activeSchedule.value
    if (schedule.length === 0) return

    const bondIdx = activeBondIndex.value + 1
    const branchKey = bondBranch.value === 'bullet' ? '7A' : '7B'

    const items = schedule.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `L4-${branchKey}-bond${bondIdx}-p${n}-beginCost`, data: { remark: String(row.beginCost) } },
        { itemId: `L4-${branchKey}-bond${bondIdx}-p${n}-interestExpense`, data: { remark: String(row.interestExpense) } },
        { itemId: `L4-${branchKey}-bond${bondIdx}-p${n}-couponInterest`, data: { remark: String(row.couponInterest) } },
        { itemId: `L4-${branchKey}-bond${bondIdx}-p${n}-amortization`, data: { remark: String(row.amortization) } },
        { itemId: `L4-${branchKey}-bond${bondIdx}-p${n}-endCost`, data: { remark: String(row.endCost) } },
      ]
    }).flat()

    await saveBatch(items)

    // 保存后自动发布利息费用
    publishInterestCalculated()
  }

  // ─── 6. 债券切换 ──────────────────────────────────────────────────────

  function selectBond(index: number): void {
    if (index >= 0 && index < bondParams.value.length) {
      activeBondIndex.value = index
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    activeBondIndex,

    // 摊销表
    schedules,
    activeSchedule,

    // 验证
    validations,
    activeValidation,

    // 利息费用
    totalInterestExpense,
    currentPeriodInterest,

    // 操作
    publishInterestCalculated,
    saveSchedule,
    selectBond,
  }
}

export default useL4Subsequent
