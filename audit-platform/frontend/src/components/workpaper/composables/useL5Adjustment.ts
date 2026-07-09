/**
 * useL5Adjustment — L5-4 调整分录 composable
 *
 * Spec: .kiro/specs/l5-long-term-payables/
 * Task: 3.4
 * Requirements: 5.3
 *
 * 职责：
 * - AJE/RJE 行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步L5-1审定表
 *
 * 科目：2701 长期应付款（贷方/负债类）+ 未确认融资费用（借方/备抵类）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useL5FormulaEngine'
import type { useL5FormData } from './useL5FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type L5AdjustmentType = 'AJE' | 'RJE'

/** 调整分录行 */
export interface L5AdjustmentEntry {
  /** 序号 */
  index: number
  /** AJE or RJE */
  type: L5AdjustmentType
  /** 摘要 */
  description: string
  /** 科目编码 */
  accountCode: string
  /** 科目名称 */
  accountName: string
  /** 借方金额 */
  debitAmount: number
  /** 贷方金额 */
  creditAmount: number
}

/** 借贷平衡状态 */
export interface L5BalanceStatus {
  /** 借方合计 */
  totalDebit: number
  /** 贷方合计 */
  totalCredit: number
  /** 差额 */
  diff: number
  /** 是否平衡（差额绝对值≤0.01） */
  isBalanced: boolean
}

// ─── Constants ───────────────────────────────────────────────────────────────

/** 平衡阈值 */
const BALANCE_THRESHOLD = 0.01

// ─── Composable ──────────────────────────────────────────────────────────────

/**
 * L5-4 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useL5FormData 实例
 */
export function useL5Adjustment(formData: ReturnType<typeof useL5FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<L5AdjustmentEntry[]>([])
  const activeType = ref<L5AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<L5AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<L5AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<L5AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<L5BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<L5BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<L5BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /** AJE 对科目2701长期应付款的净影响（贷方增加-借方减少） */
  const ajeNetPayable: ComputedRef<number> = computed(() => {
    const entries2701 = ajeEntries.value.filter(e => e.accountCode === '2701')
    const credit = calcSubtotal(entries2701.map(e => e.creditAmount))
    const debit = calcSubtotal(entries2701.map(e => e.debitAmount))
    return credit - debit
  })

  /** RJE 对科目2701长期应付款的净影响 */
  const rjeNetPayable: ComputedRef<number> = computed(() => {
    const entries2701 = rjeEntries.value.filter(e => e.accountCode === '2701')
    const credit = calcSubtotal(entries2701.map(e => e.creditAmount))
    const debit = calcSubtotal(entries2701.map(e => e.debitAmount))
    return credit - debit
  })

  /** AJE 对未确认融资费用的净影响（借方增加-贷方减少） */
  const ajeNetUnrecognized: ComputedRef<number> = computed(() => {
    const entries2702 = ajeEntries.value.filter(e => e.accountCode === '2702')
    const debit = calcSubtotal(entries2702.map(e => e.debitAmount))
    const credit = calcSubtotal(entries2702.map(e => e.creditAmount))
    return debit - credit
  })

  /** RJE 对未确认融资费用的净影响 */
  const rjeNetUnrecognized: ComputedRef<number> = computed(() => {
    const entries2702 = rjeEntries.value.filter(e => e.accountCode === '2702')
    const debit = calcSubtotal(entries2702.map(e => e.debitAmount))
    const credit = calcSubtotal(entries2702.map(e => e.creditAmount))
    return debit - credit
  })

  function _calcBalance(items: L5AdjustmentEntry[]): L5BalanceStatus {
    const totalDebit = parseFloat(calcSubtotal(items.map(e => e.debitAmount)).toFixed(2))
    const totalCredit = parseFloat(calcSubtotal(items.map(e => e.creditAmount)).toFixed(2))
    const diff = parseFloat((totalDebit - totalCredit).toFixed(2))
    return {
      totalDebit,
      totalCredit,
      diff,
      isBalanced: Math.abs(diff) <= BALANCE_THRESHOLD,
    }
  }

  // ─── 3. 行操作 ────────────────────────────────────────────────────────

  /** 新增调整分录行 */
  function addEntry(type?: L5AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: L5AdjustmentEntry = {
      index: entries.value.length + 1,
      type: t,
      description: '',
      accountCode: '',
      accountName: '',
      debitAmount: 0,
      creditAmount: 0,
    }
    entries.value.push(newEntry)
    _triggerSave(entries.value.length - 1)
  }

  /** 删除分录行 */
  function removeEntry(index: number): void {
    if (index < 0 || index >= entries.value.length) return
    entries.value.splice(index, 1)
    // 重新编号
    entries.value.forEach((e, i) => { e.index = i + 1 })
    _triggerSaveAll()
  }

  /** 更新分录行字段 */
  function updateEntry(
    index: number,
    field: keyof L5AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: L5AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步L5-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 L5-1 审定表（L5-1 订阅该事件刷新 AJE/RJE 列）
   */
  async function saveAndPublish(): Promise<void> {
    // 校验借贷平衡
    const balance = currentBalance.value
    if (!balance.isBalanced) {
      return // 不平衡时不允许发布
    }

    // 批量保存
    const items = entries.value.map((entry, i) => {
      const n = i + 1
      return [
        { itemId: `L5-L5-4-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `L5-L5-4-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `L5-L5-4-entry-${n}-code`, data: { remark: entry.accountCode || null } },
        { itemId: `L5-L5-4-entry-${n}-name`, data: { remark: entry.accountName || null } },
        { itemId: `L5-L5-4-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `L5-L5-4-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步L5-1 + 通知A13）
    eventBus.emit('adjustment:created', undefined as any)
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const pairs: [string, string | null][] = [
      [`L5-L5-4-entry-${n}-type`, entry.type],
      [`L5-L5-4-entry-${n}-desc`, entry.description || null],
      [`L5-L5-4-entry-${n}-code`, entry.accountCode || null],
      [`L5-L5-4-entry-${n}-name`, entry.accountName || null],
      [`L5-L5-4-entry-${n}-debit`, entry.debitAmount ? String(entry.debitAmount) : null],
      [`L5-L5-4-entry-${n}-credit`, entry.creditAmount ? String(entry.creditAmount) : null],
    ]
    for (const [itemId, remark] of pairs) {
      debouncedSave(itemId, { remark })
    }
  }

  function _triggerSaveAll(): void {
    for (let i = 0; i < entries.value.length; i++) {
      _triggerSave(i)
    }
  }

  // ─── Return ────────────────────────────────────────────────────────────

  return {
    // State
    entries,
    activeType,

    // 计算
    filteredEntries,
    ajeEntries,
    rjeEntries,
    ajeBalance,
    rjeBalance,
    currentBalance,
    ajeNetPayable,
    rjeNetPayable,
    ajeNetUnrecognized,
    rjeNetUnrecognized,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,
  }
}

export default useL5Adjustment
