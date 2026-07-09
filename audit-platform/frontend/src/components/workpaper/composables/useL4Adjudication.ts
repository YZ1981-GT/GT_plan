/**
 * useL4Adjudication — L4-1 审定表 composable
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Task: 3.4
 * Requirements: 2.1-2.7
 *
 * 职责：
 * - 负债类贷方 品种(普通/可转换)×子项(成本/利息调整/应计利息/小计)
 * - 调用 useL4FormulaEngine (calcAuditedAmount, calcLiabilityEndBalance)
 * - 审定数变化→writebackTB(2502)
 * - EventBus subscribe 附注刷新
 *
 * 科目：2502 应付债券（贷方/负债类！期末=期初+贷方-借方）
 */
import { computed, watch, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import {
  calcAuditedAmount,
  calcLiabilityEndBalance,
  calcSubtotal,
} from './useL4FormulaEngine'
import type { useL4FormData } from './useL4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 债券品种 */
export type L4BondVariety = '普通债券' | '可转换债券'

/** 审定表子项类型 */
export type L4AdjSubItem = '成本' | '利息调整' | '应计利息' | '小计'

/** 审定表分类行数据 */
export interface L4AdjudicationRow {
  /** 品种 */
  variety: L4BondVariety
  /** 子项 */
  subItem: L4AdjSubItem
  /** 期初余额 */
  beginning: number
  /** 贷方发生额（发行/利息调整增加） */
  creditAmount: number
  /** 借方发生额（兑付/减少） */
  debitAmount: number
  /** 期末余额（公式列：期初+贷方-借方） */
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

/** 审定表合计行 */
export interface L4AdjudicationTotal {
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
 * L4-1 审定表业务逻辑
 *
 * @param formData 由调用方传入的 useL4FormData 实例
 * @param adjudicationData reactive data containing rows
 */
export function useL4Adjudication(
  formData: ReturnType<typeof useL4FormData>,
  adjudicationData: {
    rows: L4AdjudicationRow[]
    total: L4AdjudicationTotal
  },
) {
  const { writebackTB, saveBatch } = formData

  // ─── 1. 计算属性：每行 endBalance + audited ─────────────────────────────

  /** 审定表各行（公式列自动计算） */
  const computedRows: ComputedRef<L4AdjudicationRow[]> = computed(() => {
    return adjudicationData.rows.map(row => ({
      ...row,
      // 负债类贷方：期末 = 期初 + 贷方 - 借方
      endBalance: calcLiabilityEndBalance(row.beginning, row.creditAmount, row.debitAmount),
      // 审定数 = 未审 + AJE + RJE
      audited: calcAuditedAmount(row.unadjusted, row.aje, row.rje),
    }))
  })

  // ─── 2. 品种小计 ───────────────────────────────────────────────────────

  /** 按品种分组小计 */
  const varietySubtotals: ComputedRef<Record<L4BondVariety, L4AdjudicationTotal>> = computed(() => {
    const result = {} as Record<L4BondVariety, L4AdjudicationTotal>
    const varieties: L4BondVariety[] = ['普通债券', '可转换债券']

    for (const v of varieties) {
      const rows = computedRows.value.filter(r => r.variety === v && r.subItem !== '小计')
      result[v] = {
        beginning: calcSubtotal(rows.map(r => r.beginning)),
        credit: calcSubtotal(rows.map(r => r.creditAmount)),
        debit: calcSubtotal(rows.map(r => r.debitAmount)),
        end: calcSubtotal(rows.map(r => r.endBalance)),
        unadjusted: calcSubtotal(rows.map(r => r.unadjusted)),
        aje: calcSubtotal(rows.map(r => r.aje)),
        rje: calcSubtotal(rows.map(r => r.rje)),
        audited: calcSubtotal(rows.map(r => r.audited)),
      }
    }

    return result
  })

  // ─── 3. 合计行 ─────────────────────────────────────────────────────────

  /** 合计行（全品种） */
  const total: ComputedRef<L4AdjudicationTotal> = computed(() => {
    const rows = computedRows.value.filter(r => r.subItem !== '小计')
    return {
      beginning: calcSubtotal(rows.map(r => r.beginning)),
      credit: calcSubtotal(rows.map(r => r.creditAmount)),
      debit: calcSubtotal(rows.map(r => r.debitAmount)),
      end: calcSubtotal(rows.map(r => r.endBalance)),
      unadjusted: calcSubtotal(rows.map(r => r.unadjusted)),
      aje: calcSubtotal(rows.map(r => r.aje)),
      rje: calcSubtotal(rows.map(r => r.rje)),
      audited: calcSubtotal(rows.map(r => r.audited)),
    }
  })

  // ─── 4. 行操作 ─────────────────────────────────────────────────────────

  /**
   * 更新某行的可编辑字段
   * 公式列(endBalance/audited)自动由computed刷新
   */
  function updateRow(
    index: number,
    field: 'beginning' | 'creditAmount' | 'debitAmount' | 'unadjusted' | 'aje' | 'rje',
    value: number,
  ): void {
    const rows = adjudicationData.rows
    if (index < 0 || index >= rows.length) return

    rows[index][field] = value

    // 同步计算公式列到 formData（供持久化）
    const row = rows[index]
    row.endBalance = calcLiabilityEndBalance(row.beginning, row.creditAmount, row.debitAmount)
    row.audited = calcAuditedAmount(row.unadjusted, row.aje, row.rje)

    // 重算合计
    _syncTotal()
  }

  /** 同步合计到 adjudicationData */
  function _syncTotal(): void {
    const rows = adjudicationData.rows.filter(r => r.subItem !== '小计')
    adjudicationData.total = {
      beginning: calcSubtotal(rows.map(r => r.beginning)),
      credit: calcSubtotal(rows.map(r => r.creditAmount)),
      debit: calcSubtotal(rows.map(r => r.debitAmount)),
      end: calcSubtotal(rows.map(r => r.endBalance)),
      unadjusted: calcSubtotal(rows.map(r => r.unadjusted)),
      aje: calcSubtotal(rows.map(r => r.aje)),
      rje: calcSubtotal(rows.map(r => r.rje)),
      audited: calcSubtotal(rows.map(r => r.audited)),
    }
  }

  // ─── 5. TB回写 + EventBus ──────────────────────────────────────────────

  /**
   * 保存审定表并触发TB回写 + EventBus
   * - 回写 trial_balance 科目 2502
   * - publish 'substantive:adjudicated'
   */
  async function saveAndWriteback(): Promise<void> {
    // 序列化审定表行
    const items = adjudicationData.rows.map((row, i) => {
      const n = i + 1
      return [
        { itemId: `L4-1-row-${n}-endBalance`, data: { remark: String(row.endBalance) } },
        { itemId: `L4-1-row-${n}-audited`, data: { remark: String(row.audited) } },
      ]
    }).flat()

    await saveBatch(items)

    // TB回写（科目2502应付债券）
    const auditedTotal = total.value.audited
    await writebackTB(auditedTotal)
  }

  // ─── 6. 审定数变化监听 → 自动回写 ─────────────────────────────────────

  watch(
    () => total.value.audited,
    async (newVal, oldVal) => {
      if (oldVal !== undefined && newVal !== oldVal) {
        await saveAndWriteback()
      }
    },
  )

  // ─── 7. EventBus 订阅附注刷新 ─────────────────────────────────────────

  /** 订阅附注变化通知（附注→审定表反查） */
  function subscribeDisclosure(callback: () => void): () => void {
    const handler = () => callback()
    eventBus.on('disclosure:note-text-updated', handler)
    return () => eventBus.off('disclosure:note-text-updated', handler)
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    computedRows,
    varietySubtotals,
    total,
    updateRow,
    saveAndWriteback,
    subscribeDisclosure,
  }
}

export default useL4Adjudication
