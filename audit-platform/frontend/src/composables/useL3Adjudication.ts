/**
 * useL3Adjudication — L3-1 审定表 composable
 *
 * Spec: .kiro/specs/l3-long-term-loans/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 负债类贷方期末计算：endBalance = beginning + credit - debit
 * - 审定数计算：audited = unadjusted + aje + rje
 * - 分类小计（按借款类型分类）
 * - 单列"其中：一年内到期"
 * - TB回写触发（科目2501）+ EventBus publish 'substantive:adjudicated'
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '@/composables/useL3FormulaEngine'
import type { useL3FormData } from '@/components/workpaper/composables/useL3FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表分类行数据（可编辑原始字段） */
export interface L3AdjudicationCategory {
  name: string
  beginning: number
  creditAmount: number
  debitAmount: number
  endBalance: number
  currentPortion: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

/** 审定表分类计算结果 */
export interface L3AdjudicationComputed {
  name: string
  beginning: number
  creditAmount: number
  debitAmount: number
  endBalance: number
  currentPortion: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

/** 审定表合计行 */
export interface L3AdjudicationTotal {
  beginning: number
  credit: number
  debit: number
  end: number
  currentPortion: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L3-1 审定表业务逻辑
 *
 * @param formData 由调用方传入的 useL3FormData 实例
 * @param adjudicationData reactive data containing categories
 */
export function useL3Adjudication(formData: ReturnType<typeof useL3FormData>, adjudicationData: {
  categories: L3AdjudicationCategory[]
  total: L3AdjudicationTotal
}) {
  const { writebackTB, saveBatch } = formData

  // ─── 1. 计算属性：每行 endBalance + audited ─────────────────────────────

  /** 审定表各分类行（公式列自动计算） */
  const computedCategories: ComputedRef<L3AdjudicationComputed[]> = computed(() => {
    return adjudicationData.categories.map(cat => ({
      name: cat.name,
      beginning: cat.beginning,
      creditAmount: cat.creditAmount,
      debitAmount: cat.debitAmount,
      // 负债类贷方：期末 = 期初 + 贷方 - 借方
      endBalance: calcLiabilityEndBalance(cat.beginning, cat.creditAmount, cat.debitAmount),
      currentPortion: cat.currentPortion,
      unadjusted: cat.unadjusted,
      aje: cat.aje,
      rje: cat.rje,
      // 审定数 = 未审 + AJE + RJE
      audited: calcAuditedAmount(cat.unadjusted, cat.aje, cat.rje),
    }))
  })

  // ─── 2. 合计行 ─────────────────────────────────────────────────────────

  /** 合计行（Σ 各分类） */
  const total: ComputedRef<L3AdjudicationTotal> = computed(() => {
    const cats = computedCategories.value
    return {
      beginning: calcSubtotal(cats.map(c => c.beginning)),
      credit: calcSubtotal(cats.map(c => c.creditAmount)),
      debit: calcSubtotal(cats.map(c => c.debitAmount)),
      end: calcSubtotal(cats.map(c => c.endBalance)),
      currentPortion: calcSubtotal(cats.map(c => c.currentPortion)),
      unadjusted: calcSubtotal(cats.map(c => c.unadjusted)),
      aje: calcSubtotal(cats.map(c => c.aje)),
      rje: calcSubtotal(cats.map(c => c.rje)),
      audited: calcSubtotal(cats.map(c => c.audited)),
    }
  })

  // ─── 3. 行操作 ─────────────────────────────────────────────────────────

  /**
   * 更新某分类的可编辑字段
   * 公式列(endBalance/audited)自动由computed刷新
   */
  function updateCategory(
    index: number,
    field: 'beginning' | 'creditAmount' | 'debitAmount' | 'currentPortion' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): void {
    const categories = adjudicationData.categories
    if (index < 0 || index >= categories.length) return

    categories[index][field] = value

    // 同步计算公式列到 formData（供持久化）
    const cat = categories[index]
    cat.endBalance = calcLiabilityEndBalance(cat.beginning, cat.creditAmount, cat.debitAmount)
    cat.audited = calcAuditedAmount(cat.unadjusted, cat.aje, cat.rje)

    // 重算合计
    _syncTotal()
  }

  /** 同步合计到 formData state */
  function _syncTotal(): void {
    const cats = adjudicationData.categories
    adjudicationData.total = {
      beginning: calcSubtotal(cats.map(c => c.beginning)),
      credit: calcSubtotal(cats.map(c => c.creditAmount)),
      debit: calcSubtotal(cats.map(c => c.debitAmount)),
      end: calcSubtotal(cats.map(c => c.endBalance)),
      currentPortion: calcSubtotal(cats.map(c => c.currentPortion)),
      unadjusted: calcSubtotal(cats.map(c => c.unadjusted)),
      aje: calcSubtotal(cats.map(c => c.aje)),
      rje: calcSubtotal(cats.map(c => c.rje)),
      audited: calcSubtotal(cats.map(c => c.audited)),
    }
  }

  // ─── 4. TB回写 + EventBus ──────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 2501
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    // 序列化审定表行
    const items = adjudicationData.categories.map((cat, i) => {
      const n = i + 1
      return [
        { itemId: `L3-adj-${n}-endBalance`, data: { remark: String(cat.endBalance) } },
        { itemId: `L3-adj-${n}-audited`, data: { remark: String(cat.audited) } },
        { itemId: `L3-adj-${n}-currentPortion`, data: { remark: String(cat.currentPortion) } },
      ]
    }).flat()

    await saveBatch(items)

    // TB回写（科目2501长期借款）
    const auditedTotal = total.value.audited
    await writebackTB(auditedTotal)

    // EventBus publish（writebackTB内部已发布，此处为冗余保障）
    eventBus.emit('substantive:adjudicated', {
      accountCode: '2501',
      auditedAmount: auditedTotal,
      wpCode: 'L3',
      timestamp: Date.now(),
    })
  }

  // ─── 5. 审定数变化监听 → 自动回写 ─────────────────────────────────────

  /** 监听审定数变化，自动触发回写 */
  watch(
    () => total.value.audited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        await saveAndWriteback()
      }
    },
  )

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    computedCategories,
    total,
    updateCategory,
    saveAndWriteback,
  }
}

export default useL3Adjudication
