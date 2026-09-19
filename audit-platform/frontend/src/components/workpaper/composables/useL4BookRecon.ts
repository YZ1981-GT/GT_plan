/**
 * useL4BookRecon — L4-8 账面核对 composable（2分支）
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Task: 3.4
 * Requirements: 5.1-5.6
 *
 * 职责：
 * - 接收 bondBranch inject（与L4-7联动，分支同步）
 * - 差异计算 = 账面摊余成本 - 测算摊余成本（来自L4-7）
 * - 阈值高亮逻辑（|差异|>阈值 → 红色高亮）
 *
 * 核对逻辑：
 *   账面摊余成本 = 实际账面记录（从明细账/试算表取得）
 *   测算摊余成本 = L4-7后续计量的 endCost（审计测算值）
 *   差异 = 账面 - 测算，应为0或极小尾差
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { calcSubtotal } from './useL4FormulaEngine'
import type { EIRRow } from './useL4EIREngine'
import type { useL4FormData } from './useL4FormData'
import type { L4BondBranch } from './useL4Subsequent'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 账面核对行数据 */
export interface L4BookReconRow {
  /** 债券名称 */
  bondName: string
  /** 期数 */
  period: number
  /** 账面摊余成本（实际记录） */
  bookAmortizedCost: number
  /** 测算摊余成本（来自L4-7） */
  calcAmortizedCost: number
  /** 差异（公式列：账面-测算） */
  difference: number
  /** 是否超阈值（高亮标记） */
  isOverThreshold: boolean
}

/** 核对汇总 */
export interface L4BookReconSummary {
  /** 总行数 */
  totalRows: number
  /** 差异为0的行数 */
  matchedRows: number
  /** 超阈值行数 */
  overThresholdRows: number
  /** 最大差异绝对值 */
  maxAbsDifference: number
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 默认差异阈值（元） */
const DEFAULT_THRESHOLD = 1.0

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L4-8 账面核对业务逻辑（2分支，与L4-7联动）
 *
 * @param formData 由调用方传入的 useL4FormData 实例
 * @param bondBranch 当前分支（与L4-7共享，主入口provide）
 * @param schedules L4-7生成的摊销表数据（inject或prop传入）
 * @param bookData 账面实际数据（各期账面摊余成本）
 */
export function useL4BookRecon(
  formData: ReturnType<typeof useL4FormData>,
  bondBranch: Ref<L4BondBranch>,
  schedules: Ref<EIRRow[][]>,
  bookData: Ref<Array<{ bondName: string; periodCosts: number[] }>>,
) {
  const { debouncedSave } = formData

  /** 差异阈值（可调整） */
  const threshold = ref(DEFAULT_THRESHOLD)

  /** 当前选中债券索引 */
  const activeBondIndex = ref(0)

  // ─── 1. 核对行计算 ────────────────────────────────────────────────────

  /** 所有债券的核对明细 */
  const reconRows: ComputedRef<L4BookReconRow[][]> = computed(() => {
    return schedules.value.map((schedule, bondIdx) => {
      const book = bookData.value[bondIdx]
      if (!book || !schedule.length) return []

      return schedule.map((row, periodIdx) => {
        const bookCost = book.periodCosts[periodIdx] ?? 0
        const calcCost = row.endCost
        const diff = bookCost - calcCost
        return {
          bondName: book.bondName,
          period: row.period,
          bookAmortizedCost: bookCost,
          calcAmortizedCost: calcCost,
          difference: diff,
          isOverThreshold: Math.abs(diff) > threshold.value,
        }
      })
    })
  })

  /** 当前债券的核对行 */
  const activeReconRows: ComputedRef<L4BookReconRow[]> = computed(() => {
    return reconRows.value[activeBondIndex.value] || []
  })

  // ─── 2. 汇总统计 ──────────────────────────────────────────────────────

  /** 当前债券的核对汇总 */
  const activeSummary: ComputedRef<L4BookReconSummary> = computed(() => {
    const rows = activeReconRows.value
    if (rows.length === 0) {
      return { totalRows: 0, matchedRows: 0, overThresholdRows: 0, maxAbsDifference: 0 }
    }

    const absDiffs = rows.map(r => Math.abs(r.difference))
    return {
      totalRows: rows.length,
      matchedRows: rows.filter(r => Math.abs(r.difference) <= 0.01).length,
      overThresholdRows: rows.filter(r => r.isOverThreshold).length,
      maxAbsDifference: Math.max(...absDiffs),
    }
  })

  /** 全部债券的汇总 */
  const totalSummary: ComputedRef<L4BookReconSummary> = computed(() => {
    const allRows = reconRows.value.flat()
    if (allRows.length === 0) {
      return { totalRows: 0, matchedRows: 0, overThresholdRows: 0, maxAbsDifference: 0 }
    }

    const absDiffs = allRows.map(r => Math.abs(r.difference))
    return {
      totalRows: allRows.length,
      matchedRows: allRows.filter(r => Math.abs(r.difference) <= 0.01).length,
      overThresholdRows: allRows.filter(r => r.isOverThreshold).length,
      maxAbsDifference: Math.max(...absDiffs),
    }
  })

  // ─── 3. 阈值管理 ──────────────────────────────────────────────────────

  /** 更新差异阈值 */
  function setThreshold(value: number): void {
    if (value > 0) {
      threshold.value = value
    }
  }

  // ─── 4. 账面数据更新 ──────────────────────────────────────────────────

  /** 更新某期的账面摊余成本 */
  function updateBookCost(bondIdx: number, periodIdx: number, value: number): void {
    const book = bookData.value[bondIdx]
    if (!book) return
    if (periodIdx < 0) return

    // 确保数组足够长
    while (book.periodCosts.length <= periodIdx) {
      book.periodCosts.push(0)
    }
    book.periodCosts[periodIdx] = value

    // 持久化
    const branchKey = bondBranch.value === 'bullet' ? '8A' : '8B'
    const n = bondIdx + 1
    const p = periodIdx + 1
    debouncedSave(`L4-${branchKey}-bond${n}-p${p}-bookCost`, {
      remark: value !== 0 ? String(value) : null,
    })
  }

  // ─── 5. 债券切换 ──────────────────────────────────────────────────────

  function selectBond(index: number): void {
    if (index >= 0 && index < bookData.value.length) {
      activeBondIndex.value = index
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 状态
    threshold,
    activeBondIndex,

    // 核对数据
    reconRows,
    activeReconRows,

    // 汇总
    activeSummary,
    totalSummary,

    // 操作
    setThreshold,
    updateBookCost,
    selectBond,
  }
}

export default useL4BookRecon
