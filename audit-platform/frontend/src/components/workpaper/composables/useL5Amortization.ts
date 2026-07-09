/**
 * useL5Amortization — L5-5 摊销测算表 composable（核心！）
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 3.4
 * Requirements: 4.1-4.7
 *
 * 职责：
 * - 调用 generateSchedule + validateSchedule
 * - 按款项筛选查看
 * - 本期摊销合计 → EventBus 'l5:amortization-calculated'
 * - 差异比对（测算余额 vs 账面余额）
 *
 * 核心计算：实际利率法（每期摊销=期初摊余成本×实际利率）
 */
import { computed, ref, watch, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  generateSchedule,
  validateSchedule,
  type AmortRow,
} from './useL5AmortizationEngine'
import { calcSubtotal } from './useL5FormulaEngine'
import type { useL5FormData } from './useL5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 摊销测算表款项数据（每个款项一张摊销表） */
export interface L5AmortizationItem {
  /** 款项唯一标识（对应L5-2/L5-3行key） */
  key: string
  /** 款项名称 */
  payableName: string
  /** 债权人 */
  creditor: string
  /** 初始摊余成本（初始应付本金总额） */
  initialCost: number
  /** 实际利率（EIR） */
  effectiveRate: number
  /** 各期付款金额数组 */
  repayments: number[]
  /** 总期数 */
  periods: number
  /** 当前期数（用于标记本期） */
  currentPeriod: number
}

/** 差异比对结果 */
export interface L5AmortizationDiff {
  /** 款项名称 */
  payableName: string
  /** 摊销测算余额 */
  calculatedBalance: number
  /** 账面余额（L5-3） */
  bookBalance: number
  /** 差额 */
  diff: number
  /** |diff| < 1 视为一致 */
  isMatch: boolean
}

/** 摊销表验证状态 */
export interface L5ScheduleValidation {
  /** 是否通过验证 */
  isValid: boolean
  /** 尾差 */
  tailDiff: number
  /** 款项名称 */
  payableName: string
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L5-5 摊销测算表业务逻辑（核心！实际利率法）
 *
 * @param formData 由调用方传入的 useL5FormData 实例
 * @param amortizationItems reactive ref of 各款项摊销数据
 */
export function useL5Amortization(
  formData: ReturnType<typeof useL5FormData>,
  amortizationItems: Ref<L5AmortizationItem[]>,
) {
  const { debouncedSave } = formData

  // ─── 1. 按款项筛选 ────────────────────────────────────────────────────

  /** 当前选中的款项key（null=全部） */
  const selectedItemKey = ref<string | null>(null)

  /** 款项筛选选项列表 */
  const filterOptions: ComputedRef<Array<{ key: string; label: string }>> = computed(() => {
    return [
      { key: '', label: '全部款项' },
      ...amortizationItems.value.map(item => ({
        key: item.key,
        label: item.payableName,
      })),
    ]
  })

  function selectItem(key: string | null): void {
    selectedItemKey.value = key || null
  }

  // ─── 2. 生成各款项摊销表 ──────────────────────────────────────────────

  /** 各款项完整摊销表Map */
  const scheduleMap: ComputedRef<Map<string, AmortRow[]>> = computed(() => {
    const map = new Map<string, AmortRow[]>()
    for (const item of amortizationItems.value) {
      if (item.initialCost <= 0 || item.periods <= 0) {
        map.set(item.key, [])
        continue
      }
      const schedule = generateSchedule(
        item.initialCost,
        item.repayments,
        item.effectiveRate,
        item.periods,
      )
      map.set(item.key, schedule)
    }
    return map
  })

  /** 当前选中款项的摊销表（或全部合并视图） */
  const currentSchedule: ComputedRef<AmortRow[]> = computed(() => {
    if (selectedItemKey.value) {
      return scheduleMap.value.get(selectedItemKey.value) || []
    }
    // 全部模式：返回第一个款项的摊销表（UI上用Tab切换）
    const firstItem = amortizationItems.value[0]
    if (!firstItem) return []
    return scheduleMap.value.get(firstItem.key) || []
  })

  // ─── 3. 验证各摊销表末期趋零 ─────────────────────────────────────────

  /** 各款项摊销表验证结果 */
  const validationResults: ComputedRef<L5ScheduleValidation[]> = computed(() => {
    return amortizationItems.value.map(item => {
      const schedule = scheduleMap.value.get(item.key) || []
      const validation = validateSchedule(schedule)
      return {
        isValid: validation.isValid,
        tailDiff: validation.tailDiff,
        payableName: item.payableName,
      }
    })
  })

  /** 是否全部验证通过 */
  const allValid: ComputedRef<boolean> = computed(() => {
    return validationResults.value.every(v => v.isValid)
  })

  // ─── 4. 本期摊销合计 ──────────────────────────────────────────────────

  /** 本期摊销合计（所有款项当前期的摊销之和） */
  const periodAmortizationTotal: ComputedRef<number> = computed(() => {
    let total = 0
    for (const item of amortizationItems.value) {
      const schedule = scheduleMap.value.get(item.key) || []
      if (item.currentPeriod > 0 && item.currentPeriod <= schedule.length) {
        total += schedule[item.currentPeriod - 1].amortization
      }
    }
    return parseFloat(total.toFixed(2))
  })

  /** 全部款项摊销合计总额（所有期数） */
  const totalAmortizationSum: ComputedRef<number> = computed(() => {
    let total = 0
    for (const item of amortizationItems.value) {
      const schedule = scheduleMap.value.get(item.key) || []
      total += calcSubtotal(schedule.map(r => r.amortization))
    }
    return parseFloat(total.toFixed(2))
  })

  // ─── 5. 差异比对（测算余额 vs 账面余额） ─────────────────────────────────

  /**
   * 比对各款项摊销测算当前期末余额 与 账面余额
   * @param bookBalances 账面余额Map（key→余额，来自L5-3）
   */
  function compareWithBook(bookBalances: Map<string, number>): L5AmortizationDiff[] {
    return amortizationItems.value.map(item => {
      const schedule = scheduleMap.value.get(item.key) || []
      const currentPeriodIdx = item.currentPeriod - 1
      const calculatedBalance = (currentPeriodIdx >= 0 && currentPeriodIdx < schedule.length)
        ? schedule[currentPeriodIdx].endCost
        : item.initialCost
      const bookBalance = bookBalances.get(item.key) || 0
      const diff = parseFloat((calculatedBalance - bookBalance).toFixed(2))

      return {
        payableName: item.payableName,
        calculatedBalance,
        bookBalance,
        diff,
        isMatch: Math.abs(diff) < 1,
      }
    })
  }

  // ─── 6. EventBus 发布本期摊销 → L8财务费用 ────────────────────────────

  /** 发布 'l5:amortization-calculated' 供L8订阅 */
  function publishAmortization(): void {
    eventBus.emit('l5:amortization-calculated' as any, {
      wpCode: 'L5',
      periodAmortization: periodAmortizationTotal.value,
      timestamp: Date.now(),
    })
  }

  // 监听本期摊销变化自动发布
  watch(
    () => periodAmortizationTotal.value,
    (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        publishAmortization()
        // 持久化本期摊销合计供CrossSheet读取
        debouncedSave('L5-L5-5-period-amortization', {
          remark: String(newVal),
        })
      }
    },
  )

  // ─── 7. 保存触发 ──────────────────────────────────────────────────────

  /** 保存摊销表未摊销余额合计（供CrossSheet） */
  function saveUnamortizedTotal(): void {
    // 各款项当前期末余额（未摊销余额）合计
    let total = 0
    for (const item of amortizationItems.value) {
      const schedule = scheduleMap.value.get(item.key) || []
      if (item.currentPeriod > 0 && item.currentPeriod <= schedule.length) {
        total += schedule[item.currentPeriod - 1].endCost
      } else if (schedule.length > 0) {
        total += schedule[schedule.length - 1].endCost
      }
    }
    debouncedSave('L5-L5-5-unamortized-total', {
      remark: String(parseFloat(total.toFixed(2))),
    })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 筛选
    selectedItemKey,
    filterOptions,
    selectItem,

    // 摊销表
    scheduleMap,
    currentSchedule,

    // 验证
    validationResults,
    allValid,

    // 合计
    periodAmortizationTotal,
    totalAmortizationSum,

    // 差异比对
    compareWithBook,

    // EventBus
    publishAmortization,

    // 保存
    saveUnamortizedTotal,
  }
}

export default useL5Amortization
