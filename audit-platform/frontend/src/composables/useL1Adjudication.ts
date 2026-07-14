/**
 * useL1Adjudication — L1-1 审定表 composable
 *
 * Spec: .kiro/specs/l1-short-term-loans/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 负债类贷方期末计算：endBalance = beginning + credit - debit
 * - 审定数计算：audited = unadjusted + aje + rje
 * - 分类小计（信用/保证/抵押/质押）
 * - TB回写触发（科目2001）+ EventBus publish
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from '@/composables/useL1FormulaEngine'
import type { useL1FormData } from '@/composables/useL1FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 审定表分类计算结果 */
export interface AdjudicationComputed {
  name: string
  beginning: number
  creditAmount: number
  debitAmount: number
  endBalance: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

/** 审定表合计行 */
export interface AdjudicationTotal {
  beginning: number
  credit: number
  debit: number
  end: number
  unadjusted: number
  aje: number
  rje: number
  audited: number
}

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L1-1 审定表业务逻辑
 *
 * @param formData 由调用方传入的 useL1FormData 实例
 */
export function useL1Adjudication(formData: ReturnType<typeof useL1FormData>) {
  const { adjudicationData, saveImmediate, writebackTB } = formData

  // ─── 1. 计算属性：每行 endBalance + audited ─────────────────────────────

  /** 审定表各分类行（公式列自动计算） */
  const computedCategories: ComputedRef<AdjudicationComputed[]> = computed(() => {
    return adjudicationData.value.categories.map(cat => ({
      name: cat.name,
      beginning: cat.beginning,
      creditAmount: cat.creditAmount,
      debitAmount: cat.debitAmount,
      // 负债类贷方：期末 = 期初 + 贷方 - 借方
      endBalance: calcLiabilityEndBalance(cat.beginning, cat.creditAmount, cat.debitAmount),
      unadjusted: cat.unadjusted,
      aje: cat.aje,
      rje: cat.rje,
      // 审定数 = 未审 + AJE + RJE
      audited: calcAuditedAmount(cat.unadjusted, cat.aje, cat.rje),
    }))
  })

  // ─── 2. 合计行 ─────────────────────────────────────────────────────────

  /** 合计行（Σ 各分类） */
  const total: ComputedRef<AdjudicationTotal> = computed(() => {
    const cats = computedCategories.value
    return {
      beginning: calcSubtotal(cats.map(c => c.beginning)),
      credit: calcSubtotal(cats.map(c => c.creditAmount)),
      debit: calcSubtotal(cats.map(c => c.debitAmount)),
      end: calcSubtotal(cats.map(c => c.endBalance)),
      unadjusted: calcSubtotal(cats.map(c => c.unadjusted)),
      aje: calcSubtotal(cats.map(c => c.aje)),
      rje: calcSubtotal(cats.map(c => c.rje)),
      audited: calcSubtotal(cats.map(c => c.audited)),
    }
  })

  // ─── 3. 行操作 ─────────────────────────────────────────────────────────

  /**
   * 更新某分类的可编辑字段
   * 公式列(endBalance/audited)自动由computed刷新，无需手动设置
   */
  function updateCategory(
    index: number,
    field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): void {
    const categories = adjudicationData.value.categories
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
    const cats = adjudicationData.value.categories
    adjudicationData.value.total = {
      beginning: calcSubtotal(cats.map(c => c.beginning)),
      credit: calcSubtotal(cats.map(c => c.creditAmount)),
      debit: calcSubtotal(cats.map(c => c.debitAmount)),
      end: calcSubtotal(cats.map(c => c.endBalance)),
      unadjusted: calcSubtotal(cats.map(c => c.unadjusted)),
      aje: calcSubtotal(cats.map(c => c.aje)),
      rje: calcSubtotal(cats.map(c => c.rje)),
      audited: calcSubtotal(cats.map(c => c.audited)),
    }
  }

  // ─── 4. TB回写 + EventBus ──────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 2001
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    // 序列化审定表行：必须持久化「可编辑输入字段」，否则刷新后公式列
    // （endBalance/audited 由 computedCategories 重算）会回落为 0（Round_Trip 失败）。
    // _parseAdjudication 已支持解析全部字段，此处补齐 beginning/credit/debit/unadjusted/aje/rje。
    const items = adjudicationData.value.categories.map((cat, i) => {
      const n = i + 1
      return [
        { item_id: `L1-adj-${n}-beginning`, conclusion: null, remark: String(cat.beginning) },
        { item_id: `L1-adj-${n}-creditAmount`, conclusion: null, remark: String(cat.creditAmount) },
        { item_id: `L1-adj-${n}-debitAmount`, conclusion: null, remark: String(cat.debitAmount) },
        { item_id: `L1-adj-${n}-unadjusted`, conclusion: null, remark: String(cat.unadjusted) },
        { item_id: `L1-adj-${n}-aje`, conclusion: null, remark: String(cat.aje) },
        { item_id: `L1-adj-${n}-rje`, conclusion: null, remark: String(cat.rje) },
        // 公式列（只读，供跨表勾稽/回读参考）
        { item_id: `L1-adj-${n}-endBalance`, conclusion: null, remark: String(cat.endBalance) },
        { item_id: `L1-adj-${n}-audited`, conclusion: null, remark: String(cat.audited) },
      ]
    }).flat()

    await saveImmediate(items)

    // TB回写
    const auditedTotal = total.value.audited
    await writebackTB(auditedTotal)

    // EventBus publish
    eventBus.emit('substantive:adjudicated', {
      accountCode: '2001',
      auditedAmount: auditedTotal,
      wpCode: 'L1',
      timestamp: Date.now(),
    })
  }

  // ─── 5. 审定数变化监听 → 自动回写 ─────────────────────────────────────

  /**
   * 监听全部可编辑字段变化，自动触发保存 + 回写。
   * 不能只监听 audited：编辑 期初/贷方/借方 只改 endBalance 不改 audited，
   * 若仅监听 audited 这些字段永不落库（Round_Trip 失败）。
   */
  const _editableSignature = computed(() =>
    adjudicationData.value.categories
      .map(c => `${c.beginning}|${c.creditAmount}|${c.debitAmount}|${c.unadjusted}|${c.aje}|${c.rje}`)
      .join(';'),
  )
  watch(_editableSignature, async (newVal, oldVal) => {
    if (oldVal !== undefined && newVal !== oldVal) {
      await saveAndWriteback()
    }
  })

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    computedCategories,
    total,
    updateCategory,
    saveAndWriteback,
  }
}

export default useL1Adjudication
