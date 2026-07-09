/**
 * useL4Adjustment — L4-4 调整分录 composable
 *
 * Spec: .kiro/specs/l4-bonds-payable/
 * Task: 3.4
 * Requirements: 8.1
 *
 * 职责：
 * - AJE/RJE 行管理
 * - 借贷平衡校验（∑借方 === ∑贷方）
 * - EventBus publish 'adjustment:created'
 * - 双向同步 L4-1 审定表
 *
 * 科目：2502 应付债券（贷方/负债类）
 */
import { computed, ref, type ComputedRef } from 'vue'
import { eventBus } from '@/utils/eventBus'
import { calcSubtotal } from './useL4FormulaEngine'
import type { useL4FormData } from './useL4FormData'

// ─── Types ───────────────────────────────────────────────────────────────────

/** 调整分录类型 */
export type L4AdjustmentType = 'AJE' | 'RJE'

/** 调整分录行 */
export interface L4AdjustmentEntry {
  /** 序号 */
  index: number
  /** AJE or RJE */
  type: L4AdjustmentType
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
export interface L4BalanceStatus {
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
 * L4-4 调整分录业务逻辑
 *
 * @param formData 由调用方传入的 useL4FormData 实例
 */
export function useL4Adjustment(formData: ReturnType<typeof useL4FormData>) {
  const { debouncedSave, saveBatch } = formData

  // ─── 1. State ─────────────────────────────────────────────────────────

  const entries = ref<L4AdjustmentEntry[]>([])
  const activeType = ref<L4AdjustmentType>('AJE')

  // ─── 2. 计算属性 ──────────────────────────────────────────────────────

  /** 当前类型（AJE/RJE）的分录 */
  const filteredEntries: ComputedRef<L4AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === activeType.value)
  })

  /** AJE分录 */
  const ajeEntries: ComputedRef<L4AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'AJE')
  })

  /** RJE分录 */
  const rjeEntries: ComputedRef<L4AdjustmentEntry[]> = computed(() => {
    return entries.value.filter(e => e.type === 'RJE')
  })

  /** AJE 借贷平衡状态 */
  const ajeBalance: ComputedRef<L4BalanceStatus> = computed(() => {
    return _calcBalance(ajeEntries.value)
  })

  /** RJE 借贷平衡状态 */
  const rjeBalance: ComputedRef<L4BalanceStatus> = computed(() => {
    return _calcBalance(rjeEntries.value)
  })

  /** 当前类型的借贷平衡 */
  const currentBalance: ComputedRef<L4BalanceStatus> = computed(() => {
    return activeType.value === 'AJE' ? ajeBalance.value : rjeBalance.value
  })

  /** AJE 对科目2502的净影响（贷方增加-借方减少） */
  const ajeNetAmount: ComputedRef<number> = computed(() => {
    const aje2502 = ajeEntries.value.filter(e => e.accountCode === '2502')
    const credit = calcSubtotal(aje2502.map(e => e.creditAmount))
    const debit = calcSubtotal(aje2502.map(e => e.debitAmount))
    return credit - debit
  })

  /** RJE 对科目2502的净影响 */
  const rjeNetAmount: ComputedRef<number> = computed(() => {
    const rje2502 = rjeEntries.value.filter(e => e.accountCode === '2502')
    const credit = calcSubtotal(rje2502.map(e => e.creditAmount))
    const debit = calcSubtotal(rje2502.map(e => e.debitAmount))
    return credit - debit
  })

  function _calcBalance(items: L4AdjustmentEntry[]): L4BalanceStatus {
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
  function addEntry(type?: L4AdjustmentType): void {
    const t = type || activeType.value
    const newEntry: L4AdjustmentEntry = {
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
    field: keyof L4AdjustmentEntry,
    value: string | number,
  ): void {
    if (index < 0 || index >= entries.value.length) return
    const entry = entries.value[index] as any
    entry[field] = value
    _triggerSave(index)
  }

  /** 切换 AJE/RJE Tab */
  function switchType(type: L4AdjustmentType): void {
    activeType.value = type
  }

  // ─── 4. EventBus 发布 + 双向同步L4-1 ─────────────────────────────────

  /**
   * 保存并发布 'adjustment:created' 事件
   * - 借贷平衡校验通过才允许发布
   * - 通知 A13 审计调整汇总
   * - 双向同步 L4-1 审定表（L4-1 订阅该事件刷新 AJE/RJE 列）
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
        { itemId: `L4-4-entry-${n}-type`, data: { remark: entry.type } },
        { itemId: `L4-4-entry-${n}-desc`, data: { remark: entry.description || null } },
        { itemId: `L4-4-entry-${n}-code`, data: { remark: entry.accountCode || null } },
        { itemId: `L4-4-entry-${n}-name`, data: { remark: entry.accountName || null } },
        { itemId: `L4-4-entry-${n}-debit`, data: { remark: entry.debitAmount ? String(entry.debitAmount) : null } },
        { itemId: `L4-4-entry-${n}-credit`, data: { remark: entry.creditAmount ? String(entry.creditAmount) : null } },
      ]
    }).flat()

    await saveBatch(items)

    // EventBus publish（双向同步L4-1 + 通知A13）
    eventBus.emit('adjustment:created', {
      wpCode: 'L4',
      type: activeType.value,
      entries: filteredEntries.value,
      balance: balance,
      ajeNet2502: ajeNetAmount.value,
      rjeNet2502: rjeNetAmount.value,
      timestamp: Date.now(),
    })
  }

  // ─── 5. 保存触发 ──────────────────────────────────────────────────────

  function _triggerSave(rowIndex: number): void {
    const entry = entries.value[rowIndex]
    if (!entry) return
    const n = rowIndex + 1
    const pairs: [string, string | null][] = [
      [`L4-4-entry-${n}-type`, entry.type],
      [`L4-4-entry-${n}-desc`, entry.description || null],
      [`L4-4-entry-${n}-code`, entry.accountCode || null],
      [`L4-4-entry-${n}-name`, entry.accountName || null],
      [`L4-4-entry-${n}-debit`, entry.debitAmount ? String(entry.debitAmount) : null],
      [`L4-4-entry-${n}-credit`, entry.creditAmount ? String(entry.creditAmount) : null],
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
    ajeNetAmount,
    rjeNetAmount,

    // 行操作
    addEntry,
    removeEntry,
    updateEntry,
    switchType,

    // 保存+发布
    saveAndPublish,
  }
}

export default useL4Adjustment
