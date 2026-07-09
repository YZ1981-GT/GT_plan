/**
 * useL5Adjudication — L5-1 审定表 composable
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 3.4
 * Requirements: 2.1-2.8
 *
 * 职责：
 * - 双区块管理：一、长期应付款(贷方/负债) → 二、未确认融资费用(借方/备抵) → 净额
 * - 行按款项类型：融资租赁/分期付款/其他
 * - 调用 calcAuditedAmount, calcLiabilityEndBalance, calcContraLiabilityEndBalance, calcNetPayable
 * - 审定数变化→writebackTB(2701+未确认融资费用)
 * - EventBus subscribe 附注刷新
 *
 * 科目：2701 长期应付款（贷方/负债类！期末=期初+贷方-借方）
 *       未确认融资费用（借方/负债备抵类！期末=期初+借方-贷方）
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcContraLiabilityEndBalance,
  calcNetPayable,
  calcSubtotal,
} from './useL5FormulaEngine'
import type { useL5FormData } from './useL5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 款项类型 */
export type L5PayableCategory = '融资租赁' | '分期付款' | '其他'

/** 审定表行数据（长期应付款区块/未确认融资费用区块共用结构） */
export interface L5AdjudicationRow {
  /** 行唯一标识 */
  key: string
  /** 款项类型 */
  category: L5PayableCategory
  /** 项目名称 */
  itemName: string
  /** 期初余额 */
  beginning: number
  /** 贷方/借方发生额（增加方向） */
  increaseAmount: number
  /** 借方/贷方发生额（减少方向） */
  decreaseAmount: number
  /** 期末余额（公式列） */
  endBalance: number
  /** 未审数 */
  unadjusted: number
  /** AJE调整 */
  aje: number
  /** RJE调整 */
  rje: number
  /** 审定数（公式列：未审+AJE+RJE） */
  audited: number
}

/** 区块合计行 */
export interface L5AdjudicationTotal {
  beginning: number
  increase: number
  decrease: number
  end: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

/** 双区块数据结构 */
export interface L5AdjudicationData {
  /** 一、长期应付款（贷方/负债）行 */
  payableRows: L5AdjudicationRow[]
  /** 二、未确认融资费用（借方/备抵）行 */
  unrecognizedRows: L5AdjudicationRow[]
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L5-1 审定表业务逻辑（双区块+净额）
 *
 * @param formData 由调用方传入的 useL5FormData 实例
 * @param adjudicationData reactive 双区块行数据
 */
export function useL5Adjudication(
  formData: ReturnType<typeof useL5FormData>,
  adjudicationData: L5AdjudicationData,
) {
  const { writebackTB, saveBatch } = formData

  // ─── 1. 长期应付款区块：负债类贷方（期末=期初+贷方-借方） ──────────────────

  /** 长期应付款行（公式列自动计算） */
  const computedPayableRows: ComputedRef<L5AdjudicationRow[]> = computed(() => {
    return adjudicationData.payableRows.map(row => ({
      ...row,
      // 负债类贷方：期末 = 期初 + 贷方(增加) - 借方(减少)
      endBalance: calcLiabilityEndBalance(row.beginning, row.increaseAmount, row.decreaseAmount),
      // 审定数 = 未审 + AJE + RJE
      audited: calcAuditedAmount(row.unadjusted, row.aje, row.rje),
    }))
  })

  // ─── 2. 未确认融资费用区块：备抵类借方（期末=期初+借方-贷方） ───────────────

  /** 未确认融资费用行（公式列自动计算） */
  const computedUnrecognizedRows: ComputedRef<L5AdjudicationRow[]> = computed(() => {
    return adjudicationData.unrecognizedRows.map(row => ({
      ...row,
      // 备抵类借方：期末 = 期初 + 借方(增加) - 贷方(摊销减少)
      endBalance: calcContraLiabilityEndBalance(row.beginning, row.increaseAmount, row.decreaseAmount),
      // 审定数 = 未审 + AJE + RJE
      audited: calcAuditedAmount(row.unadjusted, row.aje, row.rje),
    }))
  })

  // ─── 3. 分类小计（按款项类型） ────────────────────────────────────────────

  /** 长期应付款按款项类型分组小计 */
  const payableCategorySubtotals: ComputedRef<Record<L5PayableCategory, L5AdjudicationTotal>> = computed(() => {
    const result = {} as Record<L5PayableCategory, L5AdjudicationTotal>
    const categories: L5PayableCategory[] = ['融资租赁', '分期付款', '其他']

    for (const cat of categories) {
      const rows = computedPayableRows.value.filter(r => r.category === cat)
      result[cat] = {
        beginning: calcSubtotal(rows.map(r => r.beginning)),
        increase: calcSubtotal(rows.map(r => r.increaseAmount)),
        decrease: calcSubtotal(rows.map(r => r.decreaseAmount)),
        end: calcSubtotal(rows.map(r => r.endBalance)),
        unadjusted: calcSubtotal(rows.map(r => r.unadjusted)),
        aje: calcSubtotal(rows.map(r => r.aje)),
        rje: calcSubtotal(rows.map(r => r.rje)),
        audited: calcSubtotal(rows.map(r => r.audited)),
      }
    }

    return result
  })

  // ─── 4. 区块合计 ──────────────────────────────────────────────────────

  /** 长期应付款合计 */
  const payableTotal: ComputedRef<L5AdjudicationTotal> = computed(() => {
    const rows = computedPayableRows.value
    return {
      beginning: calcSubtotal(rows.map(r => r.beginning)),
      increase: calcSubtotal(rows.map(r => r.increaseAmount)),
      decrease: calcSubtotal(rows.map(r => r.decreaseAmount)),
      end: calcSubtotal(rows.map(r => r.endBalance)),
      unadjusted: calcSubtotal(rows.map(r => r.unadjusted)),
      aje: calcSubtotal(rows.map(r => r.aje)),
      rje: calcSubtotal(rows.map(r => r.rje)),
      audited: calcSubtotal(rows.map(r => r.audited)),
    }
  })

  /** 未确认融资费用合计 */
  const unrecognizedTotal: ComputedRef<L5AdjudicationTotal> = computed(() => {
    const rows = computedUnrecognizedRows.value
    return {
      beginning: calcSubtotal(rows.map(r => r.beginning)),
      increase: calcSubtotal(rows.map(r => r.increaseAmount)),
      decrease: calcSubtotal(rows.map(r => r.decreaseAmount)),
      end: calcSubtotal(rows.map(r => r.endBalance)),
      unadjusted: calcSubtotal(rows.map(r => r.unadjusted)),
      aje: calcSubtotal(rows.map(r => r.aje)),
      rje: calcSubtotal(rows.map(r => r.rje)),
      audited: calcSubtotal(rows.map(r => r.audited)),
    }
  })

  // ─── 5. 净额（长期应付款 - 未确认融资费用） ────────────────────────────────

  /** 净额审定数 = 长期应付款审定 - 未确认融资费用审定 */
  const netPayableAudited: ComputedRef<number> = computed(() => {
    return calcNetPayable(payableTotal.value.audited, unrecognizedTotal.value.audited)
  })

  /** 净额期末 = 长期应付款期末 - 未确认融资费用期末 */
  const netPayableEnd: ComputedRef<number> = computed(() => {
    return calcNetPayable(payableTotal.value.end, unrecognizedTotal.value.end)
  })

  // ─── 6. 行操作 ────────────────────────────────────────────────────────

  /**
   * 更新长期应付款行的可编辑字段
   */
  function updatePayableRow(
    index: number,
    field: 'beginning' | 'increaseAmount' | 'decreaseAmount' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): void {
    const rows = adjudicationData.payableRows
    if (index < 0 || index >= rows.length) return
    rows[index][field] = value
    // 同步公式列
    const row = rows[index]
    row.endBalance = calcLiabilityEndBalance(row.beginning, row.increaseAmount, row.decreaseAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
  }

  /**
   * 更新未确认融资费用行的可编辑字段
   */
  function updateUnrecognizedRow(
    index: number,
    field: 'beginning' | 'increaseAmount' | 'decreaseAmount' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): void {
    const rows = adjudicationData.unrecognizedRows
    if (index < 0 || index >= rows.length) return
    rows[index][field] = value
    // 同步公式列（备抵类：期末=期初+借方-贷方）
    const row = rows[index]
    row.endBalance = calcContraLiabilityEndBalance(row.beginning, row.increaseAmount, row.decreaseAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)
  }

  // ─── 7. TB回写 + EventBus ─────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 2701 + 未确认融资费用
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    // 序列化审定表行（长期应付款+未确认融资费用）
    const items = [
      ...adjudicationData.payableRows.map((row, i) => {
        const n = i + 1
        return [
          { itemId: `L5-L5-1-payable-${n}-endBalance`, data: { remark: String(row.endBalance) } },
          { itemId: `L5-L5-1-payable-${n}-audited`, data: { remark: String(row.audited) } },
        ]
      }).flat(),
      ...adjudicationData.unrecognizedRows.map((row, i) => {
        const n = i + 1
        return [
          { itemId: `L5-L5-1-unrec-${n}-endBalance`, data: { remark: String(row.endBalance) } },
          { itemId: `L5-L5-1-unrec-${n}-audited`, data: { remark: String(row.audited) } },
        ]
      }).flat(),
      // 合计值（供 CrossSheet 勾稽）
      { itemId: 'L5-L5-1-adjudication-total', data: { remark: String(payableTotal.value.audited) } },
    ]

    await saveBatch(items)

    // TB回写（双科目）
    await writebackTB({
      payableAmount: payableTotal.value.audited,
      unrecognizedAmount: unrecognizedTotal.value.audited,
    })
  }

  // ─── 8. 审定数变化监听 → 自动回写 ────────────────────────────────────────

  watch(
    () => [payableTotal.value.audited, unrecognizedTotal.value.audited],
    async ([newPayable, newUnrec], [oldPayable, oldUnrec]) => {
      if (oldPayable !== undefined && (newPayable !== oldPayable || newUnrec !== oldUnrec)) {
        await saveAndWriteback()
      }
    },
  )

  // ─── 9. EventBus 订阅附注刷新 ────────────────────────────────────────────

  /** 订阅附注变化通知 */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated' as any, handler)
    return () => eventBus.off('disclosure:note-text-updated' as any, handler)
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // 计算行
    computedPayableRows,
    computedUnrecognizedRows,
    // 分类小计
    payableCategorySubtotals,
    // 区块合计
    payableTotal,
    unrecognizedTotal,
    // 净额
    netPayableAudited,
    netPayableEnd,
    // 行操作
    updatePayableRow,
    updateUnrecognizedRow,
    // 保存+回写
    saveAndWriteback,
    subscribeDisclosure,
  }
}

export default useL5Adjudication
