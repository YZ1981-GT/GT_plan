/**
 * useL3InterestCalc — L3-5 利息测算表 composable（核心！联动L2/L8）
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 3.4
 * Requirements: 4.1-4.6
 *
 * 职责：
 * - 每行利息测算：本金×年利率×天数/365
 * - 差异 = 测算利息 - 账载利息
 * - 差异>阈值高亮
 * - EventBus publish 'l3:interest-calculated'（供L2/L8订阅）
 * - cross_wp_ref 关联 L2应付利息 / L8财务费用
 */
import { computed, ref, type ComputedRef, type Ref } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcInterest,
  calcInterestDiff,
  calcInterestDays,
} from '@/composables/useL3InterestEngine'
import { calcSubtotal } from '@/composables/useL3FormulaEngine'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 利息测算行原始数据 */
export interface L3InterestCalcRow {
  /** 借款合同号 */
  contractNo: string
  /** 借款银行 */
  bank: string
  /** 本金 */
  principal: number
  /** 年利率（如0.05表示5%） */
  annualRate: number
  /** 借款起始日 (YYYY-MM-DD) */
  loanStart: string
  /** 借款到期日 (YYYY-MM-DD) */
  loanEnd: string
  /** 账载利息 */
  bookedInterest: number
}

/** 利息测算计算结果行（含公式列） */
export interface L3InterestCalcComputed extends L3InterestCalcRow {
  /** 计算后的计息天数 */
  computedDays: number
  /** 测算利息 */
  computedInterest: number
  /** 差异 = 测算 - 账载 */
  computedDiff: number
  /** 差异是否超阈值（需高亮） */
  hasDiffWarning: boolean
}

/** 筛选配置 */
export interface L3InterestFilterConfig {
  contractNo?: string
  bank?: string
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 差异高亮阈值（元），|差异| > 此值红色高亮 */
const DIFF_THRESHOLD = 0.01

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L3-5 利息测算表业务逻辑
 *
 * @param formData 由调用方传入的 useL3FormData 实例
 * @param interestRows reactive ref of interest calc rows
 * @param reportStart 报告期起始日 (YYYY-MM-DD)
 * @param reportEnd 报告期截止日 (YYYY-MM-DD)
 */
export function useL3InterestCalc(
  formData: ReturnType<typeof useL3FormData>,
  interestRows: { value: L3InterestCalcRow[] },
  reportStart: Ref<string>,
  reportEnd: Ref<string>,
) {
  const { debouncedSave } = formData

  // ─── 1. 筛选状态 ──────────────────────────────────────────────────────

  const filterConfig = ref<L3InterestFilterConfig>({})

  function setFilter(config: Partial<L3InterestFilterConfig>): void {
    filterConfig.value = { ...filterConfig.value, ...config }
  }

  function clearFilter(): void {
    filterConfig.value = {}
  }

  // ─── 2. 计算属性：每行利息测算 ────────────────────────────────────────

  /**
   * 每行自动计算：
   * 1. 计息天数（区间裁剪）
   * 2. 测算利息 = 本金 × 年利率 × 天数 / 365
   * 3. 差异 = 测算 - 账载
   */
  const computedRows: ComputedRef<L3InterestCalcComputed[]> = computed(() => {
    return interestRows.value.map(row => {
      const computedDays = calcInterestDays(
        row.loanStart,
        row.loanEnd,
        reportStart.value,
        reportEnd.value,
      )
      const computedInterest = calcInterest(row.principal, row.annualRate, computedDays)
      const computedDiff = calcInterestDiff(computedInterest, row.bookedInterest)

      return {
        ...row,
        computedDays,
        computedInterest: parseFloat(computedInterest.toFixed(2)),
        computedDiff: parseFloat(computedDiff.toFixed(2)),
        hasDiffWarning: Math.abs(computedDiff) > DIFF_THRESHOLD,
      }
    })
  })

  /** 筛选后的行 */
  const filteredRows: ComputedRef<L3InterestCalcComputed[]> = computed(() => {
    let rows = computedRows.value
    const f = filterConfig.value
    if (f.contractNo) {
      rows = rows.filter(r => r.contractNo.includes(f.contractNo!))
    }
    if (f.bank) {
      rows = rows.filter(r => r.bank.includes(f.bank!))
    }
    return rows
  })

  // ─── 3. 合计 ──────────────────────────────────────────────────────────

  /** 测算利息合计 */
  const totalCalculatedInterest: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(computedRows.value.map(r => r.computedInterest)).toFixed(2),
    )
  })

  /** 账载利息合计 */
  const totalBookedInterest: ComputedRef<number> = computed(() => {
    return parseFloat(
      calcSubtotal(computedRows.value.map(r => r.bookedInterest)).toFixed(2),
    )
  })

  /** 差异合计 */
  const totalDiff: ComputedRef<number> = computed(() => {
    return parseFloat((totalCalculatedInterest.value - totalBookedInterest.value).toFixed(2))
  })

  /** 存在差异的行数 */
  const warningCount: ComputedRef<number> = computed(() => {
    return computedRows.value.filter(r => r.hasDiffWarning).length
  })

  // ─── 4. 行操作 ────────────────────────────────────────────────────────

  /** 更新某行字段 */
  function updateRow(index: number, field: keyof L3InterestCalcRow, value: string | number): void {
    if (index < 0 || index >= interestRows.value.length) return
    const row = interestRows.value[index] as any
    row[field] = value
    _persist()
  }

  /** 新增利息测算行 */
  function addRow(contractNo: string, bank: string): void {
    const newRow: L3InterestCalcRow = {
      contractNo,
      bank,
      principal: 0,
      annualRate: 0,
      loanStart: '',
      loanEnd: '',
      bookedInterest: 0,
    }
    interestRows.value.push(newRow)
    _persist()
  }

  /** 删除行 */
  function removeRow(index: number): void {
    if (index < 0 || index >= interestRows.value.length) return
    interestRows.value.splice(index, 1)
    _persist()
  }

  // ─── 5. EventBus: publish 'l3:interest-calculated' ────────────────────

  /**
   * 发布利息测算结果，供L2应付利息、L8财务费用订阅
   * cross_wp_ref 关联：L2（应付利息）、L8（财务费用）
   */
  function publishInterestCalculated(): void {
    eventBus.emit('l3:interest-calculated', {
      wpCode: 'L3',
      totalInterest: totalCalculatedInterest.value,
      totalDiff: totalDiff.value,
      byContract: computedRows.value.map(r => ({
        contractNo: r.contractNo,
        principal: r.principal,
        interest: r.computedInterest,
        diff: r.computedDiff,
      })),
      cross_wp_ref: ['L2', 'L8'],
      timestamp: Date.now(),
    })
  }

  // ─── 6. 保存触发 ──────────────────────────────────────────────────────
  //
  // 🔴 P0 修复（2026-07）：统一 JSON-array 存储 item_id `L3-L3-5-rows`。
  // 此前用 flat per-field keys `L3-int-{n}-{field}` 且组件无 hydration → 刷新数据全丢。

  function _persist(): void {
    debouncedSave('L3-L3-5-rows', { remark: JSON.stringify(interestRows.value) })
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 筛选
    filterConfig,
    setFilter,
    clearFilter,

    // 计算
    computedRows,
    filteredRows,
    totalCalculatedInterest,
    totalBookedInterest,
    totalDiff,
    warningCount,

    // 行操作
    addRow,
    removeRow,
    updateRow,

    // EventBus
    publishInterestCalculated,
  }
}

export default useL3InterestCalc
